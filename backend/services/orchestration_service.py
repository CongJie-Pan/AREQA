import json
import asyncio
import os
import re
import time
from typing import AsyncGenerator, List, Dict, Any, Optional
from fastapi import Request
from openai import AsyncOpenAI

from backend.gum_integration import (
    push_observation,
    query_cold_memory_for_context,
    query_memory_for_context,
    get_hot_memory_snapshot,
    async_evaluate_and_update_state
)

def reorder_for_attention(results):
    """
    解決 Lost in the Middle：注意力重排序 (Best-First & Second-Last)
    把最高分的放第一，次高分的放最後，其餘夾中間。
    """
    if len(results) <= 2:
        return results
    top = [results[0]]           
    bottom = [results[1]]       
    middle = results[2:]       
    return top + middle + bottom

async def parse_and_decompose_query(query: str, client: AsyncOpenAI) -> List[Dict[str, str]]:
    prompt = f"""你是一個「古典文學檢索分析師」。你的任務是解析使用者的提問，並將其拆解為適合進行混合檢索（BM25 與 FAISS）的「乾淨檢索詞」，同時判斷這個檢索詞的類型。

要求：
1. 去除所有冗言贅字與題幹指令語（如「請問」、「最適當的是」、「下列何者」、「哪一項」等）。
2. 若問題包含多個實體或複雜比較，必須將其拆解為多個獨立的子查詢。拋棄現代白話文連接詞（如「的」、「與」、「和」）。
3. 判斷每一個子查詢的類型 (type)，限定為以下兩種：
   - "exact_entity": 專有名詞、具體物品、人名、書名（例如：冷香丸、薛寶釵、紅樓夢）
   - "abstract_concept": 抽象意境、情感、事件脈絡、賞析（例如：命運悲劇、悲憫古今之幽思）

請嚴格以 JSON 陣列 (Array of Objects) 的格式輸出，每個物件包含 "query" 與 "type" 兩個欄位。
範例輸出格式：
[
    {{"query": "冷香丸", "type": "exact_entity"}},
    {{"query": "薛寶釵 命運", "type": "abstract_concept"}}
]

問題：{query}"""
    
    queries = []
    start_time = time.time()
    try:
        response = await client.chat.completions.create(
            model="qwen/qwen3-30b-a3b-instruct-2507",
            messages=[
                {"role": "system", "content": "你是一個古典文學檢索分析師。請嚴格輸出 JSON 格式。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=200,
        )
        if response.choices and response.choices[0].message.content:
            content = response.choices[0].message.content.strip()
            
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'^```\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            content = content.strip()
            
            try:
                parsed_json = json.loads(content)
                if isinstance(parsed_json, list):
                    for item in parsed_json:
                        if isinstance(item, dict) and "query" in item and "type" in item:
                            if item["type"] not in ["exact_entity", "abstract_concept"]:
                                item["type"] = "abstract_concept" # fallback
                            queries.append(item)
            except json.JSONDecodeError as je:
                print(f"[RAG API] JSON parsing failed, raw content: {content}, error: {je}")
    except Exception as e:
        print(f"[RAG API] Intent Parsing error: {e}")
        
    elapsed = time.time() - start_time
    print(f"[RAG API] Intent Parsing & Query Decomposition took {elapsed:.2f}s")
    
    if not queries:
        queries = [{"query": query, "type": "abstract_concept"}]
        
    return queries

async def classify_dialogue_policy(client: AsyncOpenAI, model: str, user_msg: str, chat_history: list) -> str:
    prompt = f"""Analyze the user's message and determine the pedagogical dialogue policy.
User message: {user_msg}
Select one of: PROBE_UNDERSTANDING, SUGGEST_ACTION, PUSH_LIMIT, NORMAL.
Return ONLY the policy name."""
    try:
        rsp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.1
        )
        policy = rsp.choices[0].message.content.strip()
        if policy not in ["PROBE_UNDERSTANDING", "SUGGEST_ACTION", "PUSH_LIMIT", "NORMAL"]:
            return "NORMAL"
        return policy
    except Exception as e:
        print(f"[Policy Classifier] Error: {e}")
        return "NORMAL"


class OrchestrationService:
    def __init__(self, router_service, rag_service, suggestion_service, client):
        self.router = router_service
        self.rag = rag_service
        self.suggestion = suggestion_service
        self.client = client

    async def execute(self, messages: List[Dict[str, str]], use_rag: bool, force_think: bool,
                      max_tokens: int, temperature: float, top_p: float,
                      repetition_penalty: float, request: Request) -> AsyncGenerator[str, None]:
        
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        
        # Node 1: Intent Routing
        denied = False
        async for event in self._node_intent_routing(last_user_msg):
            if event == "event: REFUSED\n\n":
                denied = True
                continue
            yield event
                
        if denied:
            yield "data: [DONE]\n\n"
            return
            
        if last_user_msg:
            print(f"[EDF-LOG] streaming endpoint received message, evaluating student state asynchronously...")
            from services.compeer_scheduler import user_flag, last_interaction_time
            user_flag["default_user"] = True
            last_interaction_time["default_user"] = time.time()
            asyncio.create_task(push_observation(f"User asked: {last_user_msg}"))
            if self.client:
                asyncio.create_task(async_evaluate_and_update_state(self.client, "qwen/qwen3-30b-a3b-instruct-2507", messages))

        yield f"event: metadata\ndata: {json.dumps({'promptTokens': 1024, 'completionTokens': 0, 'totalTokens': 1024})}\n\n"

        # Node 2 & 3: Parallel Tasks (HyDE & Policy)
        policy_task = None
        if last_user_msg and self.client:
            policy_task = asyncio.create_task(
                classify_dialogue_policy(self.client, "qwen/qwen3-30b-a3b-instruct-2507", last_user_msg, messages)
            )

        rag_queries = []
        if use_rag and self.rag and last_user_msg:
            from main import get_query_fingerprint, _rag_cache
            fingerprint = get_query_fingerprint(last_user_msg)
            if fingerprint not in _rag_cache:
                rag_queries = await parse_and_decompose_query(last_user_msg, self.client)
            else:
                rag_queries = None

        # Node 4: RAG Retrieval
        context_results_obj = None
        if use_rag and self.rag and last_user_msg:
            async for event in self._node_rag_retrieval(last_user_msg, rag_queries):
                if event.startswith("event: results_obj"):
                    context_results_obj = getattr(self, "_temp_rag_obj", None)
                    continue
                if event == "event: REFUSED\n\n":
                    yield "data: [DONE]\n\n"
                    return
                yield event

        # Node 5: Prompt Assembly
        policy = "NORMAL"
        if policy_task:
            while not policy_task.done():
                done, pending = await asyncio.wait([policy_task], timeout=5.0)
                if not done:
                    yield ": heartbeat\n\n"
            policy = await policy_task
            print(f"[EDF Policy] Evaluated pedagogical policy: {policy}")

        final_messages = await self._node_prompt_assembly(messages, use_rag, force_think, context_results_obj, last_user_msg)

        effective_max_tokens = max_tokens
        if policy in ["PROBE_UNDERSTANDING", "SUGGEST_ACTION"]:
            effective_max_tokens = 1500
        elif use_rag and max_tokens == 2048:
            effective_max_tokens = 2500
            
        if force_think:
            effective_max_tokens = 3200

        # Node 6: Main LLM Stream
        answer_content_accumulator = ""
        async for event in self._node_llm_stream(final_messages, force_think, effective_max_tokens, temperature, top_p, repetition_penalty, request):
            if event.startswith("event: accumulator:"):
                answer_content_accumulator = event.split("event: accumulator:", 1)[1]
                continue
            yield event

        # Node 7: Post-generation
        async for event in self._node_post_generation(last_user_msg, answer_content_accumulator, context_results_obj, use_rag):
            yield event
            
        yield "data: [DONE]\n\n"


    async def _node_intent_routing(self, query: str) -> AsyncGenerator[str, None]:
        if not query or not self.client:
            return
            
        # Fast intent check to quickly reject out-of-domain queries (like math)
        # without triggering RAG or EDF.
        prompt = f"""請判斷以下使用者的提問是否屬於「古典文學」、「國學知識」、「紅樓夢」的範疇，或是「一般性的對話/請求協助」（例如：好、我需要協助、請幫我整理、繼續等）。
如果是以上任一情況，請回覆 "YES"。如果明顯且完全無關（例如純數學計算、寫程式、物理化學、現代科技等專業無關領域），才回覆 "NO"。
使用者的提問：{query}"""
        try:
            start = time.time()
            rsp = await self.client.chat.completions.create(
                model="qwen/qwen3-30b-a3b-instruct-2507",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0.1
            )
            ans = rsp.choices[0].message.content.strip().upper()
            print(f"[Router API] Fast domain check took {time.time() - start:.2f}s, result: {ans}")
            if "NO" in ans:
                refusal = "這是與古典文學無關的領域呢，小紅只熟悉《紅樓夢》與國學知識，不在我的範疇內。歡迎詢問古典文學相關問題 😊"
                yield f"data: {json.dumps({'choices': [{'delta': {'content': refusal}, 'index': 0, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                yield "event: REFUSED\n\n"
        except Exception as e:
            print(f"[Router API] Error: {e}")
            pass


    async def _node_rag_retrieval(self, last_user_msg: str, rag_queries: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
        from main import get_query_fingerprint, _rag_cache, RAG_CACHE_SIZE, _thread_pool
        fingerprint = get_query_fingerprint(last_user_msg)
        context_results_obj = None
        
        if rag_queries is None: # Cache hit
            context_results_obj = _rag_cache[fingerprint]
        else:
            gen = self.rag.retrieve_with_events(rag_queries)
            while True:
                rag_task = asyncio.get_running_loop().run_in_executor(_thread_pool, next, gen, None)
                while not rag_task.done():
                    done, pending = await asyncio.wait([rag_task], timeout=5.0)
                    if not done:
                        yield f": heartbeat\n\n"
                event = await rag_task
                if event is None:
                    break
                if event["type"] == "status":
                    yield f"event: status\ndata: {json.dumps({'status': event['status'], 'message': event['message']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "results":
                    context_results_obj = event["data"]
                    
            if context_results_obj:
                if len(_rag_cache) >= RAG_CACHE_SIZE:
                    del _rag_cache[next(iter(_rag_cache))]
                _rag_cache[fingerprint] = context_results_obj
                
        if context_results_obj:
            is_reranked = False
            if context_results_obj.final_results and len(context_results_obj.final_results) > 0:
                first_res = context_results_obj.final_results[0]
                is_reranked = hasattr(first_res, 'reranker_score') or (isinstance(first_res, dict) and 'reranker_score' in first_res)
            
            effective_threshold = 0.35 if is_reranked else 0.005
            if context_results_obj.highest_score < effective_threshold:
                refusal = "AREQA查閱了相關古籍文獻，暫時沒能找到與您問題直接相關的內容。為了保證回答的準確性，AREQA建議您換個方式提問，或是詢問關於《紅樓夢》與國學的其他問題喔！ 😊"
                yield f"data: {json.dumps({'choices': [{'delta': {'content': refusal}, 'index': 0, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                yield "event: REFUSED\n\n"
                return
                
            valid_results = [r for r in context_results_obj.final_results if r.text and r.text.strip()]
            highest_score = context_results_obj.highest_score
            
            dynamic_results = []
            for doc in valid_results:
                if len(dynamic_results) >= 7: break
                if doc.score < 0.005: continue
                if (highest_score - doc.score) > 0.60: continue
                dynamic_results.append(doc)
                
            valid_results = reorder_for_attention(dynamic_results)
            
            sources_payload = []
            context_texts = []
            for idx, chunk in enumerate(valid_results, 1):
                raw_source = (getattr(chunk, 'source', None) or getattr(getattr(chunk, 'metadata', None), 'source', None) or getattr(getattr(chunk, 'metadata', None), 'book', None) or getattr(getattr(chunk, 'metadata', None), 'book_name', None))
                chunk_id = getattr(chunk, 'chunk_id', None) or "N/A"
                if not raw_source and chunk_id != "N/A":
                    raw_source = chunk_id.split('_')[0] if '_' in str(chunk_id) else None
                source = raw_source or "古籍文獻"
                context_texts.append(f"[文獻{idx}] {source}\n{chunk.text}")
                sources_payload.append({"title": source, "snippet": chunk.text, "score": float(chunk.score), "chunk_id": chunk_id})
                
            yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': 'generating', 'message': '✍️ 援引文獻，生成解說...' }, ensure_ascii=False)}\n\n"
            
            context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
            self._temp_rag_obj = context_results_obj
            self._temp_context_prompt = context_prompt
            yield "event: results_obj\n\n"


    async def _node_prompt_assembly(self, messages: List[Dict[str, str]], use_rag: bool, force_think: bool, context_results_obj: Any, last_user_msg: str) -> List[Dict[str, str]]:
        from backend.main import SYSTEM_PROMPT_WITH_RAG_THINK, SYSTEM_PROMPT_WITH_RAG, SYSTEM_PROMPT_FORCE_THINK, SYSTEM_PROMPT_NORMAL
        
        new_messages = [m.copy() for m in messages]
        has_system = len(new_messages) > 0 and new_messages[0]["role"] == "system"
        
        if use_rag and context_results_obj and hasattr(self, "_temp_context_prompt"):
            for idx in range(len(new_messages)-1, -1, -1):
                if new_messages[idx]["role"] == "user":
                    new_messages[idx]["content"] = self._temp_context_prompt + new_messages[idx]["content"]
                    break
                    
        if not use_rag:
            for msg in new_messages:
                if msg.get("role") == "assistant" and msg.get("content"):
                    msg["content"] = re.sub(r'【文獻\d+】', '', msg["content"])
                    
        if not has_system:
            if use_rag:
                sys_prompt_text = SYSTEM_PROMPT_WITH_RAG_THINK if force_think else SYSTEM_PROMPT_WITH_RAG
                rag_status_note = "\n【本回合狀態】：已注入 <context> 參考資料，請嚴格依文獻回答並標註來源。"
            else:
                sys_prompt_text = SYSTEM_PROMPT_FORCE_THINK if force_think else SYSTEM_PROMPT_NORMAL
                rag_status_note = "\n【本回合狀態】：本回合無任何 <context> 資料注入。禁止輸出【文獻N】等引用標記。"
                
            final_system_prompt = sys_prompt_text + rag_status_note
            final_system_prompt += "\n\n【工具使用規則】你必須先用繁體中文完整回答使用者的問題，再選擇性地呼叫工具（如 update_memory）。嚴禁只呼叫工具而不輸出任何文字回應。"
            final_system_prompt += "\n【記憶使用規則】請自然地運用記憶區塊中的資訊，嚴禁在回覆中輸出「【retrieved_memory】」、「【working_memory】」或類似的引註標記。記憶是你自身認知的一部分，無需引註。"
            
            hot_snapshot = get_hot_memory_snapshot()
            if hot_snapshot:
                final_system_prompt += f"\n\n<working_memory>\n{hot_snapshot}\n</working_memory>"
                
            cold_memory_ctx = await query_cold_memory_for_context(last_user_msg, top_k=5, client=self.client, model="qwen/qwen3-30b-a3b-instruct-2507")
            if cold_memory_ctx:
                final_system_prompt += f"\n\n<retrieved_memory>\n{cold_memory_ctx}\n</retrieved_memory>"
                
            memory_ctx = await query_memory_for_context(last_user_msg, limit=3)
            if memory_ctx:
                final_system_prompt += memory_ctx
                
            if force_think:
                think_control_prompt = "\n【重要指令】你的思考過程請務必簡明扼要（盡量控制在 500 字以內），不要把時間浪費在複述上下文，請把所有詳細的分析與長篇論述都放在 </think> 之後的正式回答中！"
                final_system_prompt += think_control_prompt
                
            new_messages.insert(0, {"role": "system", "content": final_system_prompt})
            
        return new_messages


    async def _node_llm_stream(self, messages: List[Dict[str, str]], force_think: bool, max_tokens: int, temperature: float, top_p: float, repetition_penalty: float, request: Request) -> AsyncGenerator[str, None]:
        if not self.client:
            yield f"data: {json.dumps({'choices': [{'delta': {'content': '[System Error] OPENROUTER_API_KEY is missing.'}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            return
            
        target_model_name = "qwen/qwen3-235b-a22b-thinking-2507" if force_think else "qwen/qwen3-235b-a22b-2507"
        extra_body = {"repetition_penalty": repetition_penalty}
        if force_think:
            extra_body["provider"] = {"require_parameters": True}
            extra_body["reasoning"] = {"max_tokens": 512}
            
        tools = [{
            "type": "function",
            "function": {
                "name": "update_memory",
                "description": "[SUPPLEMENTARY ONLY] After answering the user in text, you MUST call this tool if the user reveals ANY facts about their identity, preferences (e.g., favorite books, characters, food), or long-term interests. This saves it to their permanent user profile. Always answer in text first, then call this tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "The attribute key (e.g., 'user_profile_favorite_character')"},
                        "value": {"type": "string", "description": "The attribute value"}
                    },
                    "required": ["key", "value"]
                }
            }
        }]
        
        answer_content_accumulator = ""
        inside_reasoning = False
        tool_call_name = ""
        tool_call_args = ""
        
        try:
            gen_task = asyncio.create_task(
                self.client.chat.completions.create(
                    model=target_model_name,
                    messages=messages,
                    stream=True,
                    max_tokens=max_tokens,
                    temperature=temperature if temperature > 0 else 0.001,
                    top_p=top_p,
                    extra_body=extra_body,
                    tools=tools,
                    tool_choice="auto"
                )
            )
            
            while not gen_task.done():
                done, pending = await asyncio.wait([gen_task], timeout=5.0)
                if not done:
                    yield ": heartbeat\n\n"
                    
            response = await gen_task
            
            async for chunk in response:
                if await request.is_disconnected():
                    break
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    tc = delta.tool_calls[0]
                    if hasattr(tc, 'function') and tc.function:
                        if getattr(tc.function, 'name', None): tool_call_name = tc.function.name
                        if getattr(tc.function, 'arguments', None): tool_call_args += tc.function.arguments
                    continue
                    
                reasoning_text = ""
                if hasattr(delta, 'reasoning') and delta.reasoning:
                    reasoning_text = delta.reasoning
                elif hasattr(delta, 'reasoning_details') and delta.reasoning_details:
                    if isinstance(delta.reasoning_details, str):
                        reasoning_text = delta.reasoning_details
                    elif isinstance(delta.reasoning_details, list):
                        for part in delta.reasoning_details:
                            if isinstance(part, dict) and "text" in part:
                                reasoning_text += part["text"]
                            elif hasattr(part, "text") and part.text:
                                reasoning_text += part.text
                                
                content_text = delta.content if (hasattr(delta, 'content') and delta.content) else ""
                if content_text:
                    content_text = re.sub(r'<\s*/?\s*think\s*>', '', content_text)
                    if not content_text: continue
                    
                if reasoning_text:
                    if not inside_reasoning:
                        inside_reasoning = True
                        yield f"data: {json.dumps({'choices': [{'delta': {'content': '<think>'}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': reasoning_text}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                    
                if content_text:
                    if inside_reasoning:
                        inside_reasoning = False
                        yield f"data: {json.dumps({'choices': [{'delta': {'content': '</think>'}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                    answer_content_accumulator += content_text
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': content_text}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                    
                await asyncio.sleep(0)
                
        except Exception as e:
            error_msg = f'**[API Error]** 發生錯誤請重試。Hugging Face Endpoint 回應：\n\n```\n{e}\n```'
            yield f"data: {json.dumps({'choices': [{'delta': {'content': error_msg}, 'index': 0}]}, ensure_ascii=False)}\n\n"
            
        if inside_reasoning:
            yield f"data: {json.dumps({'choices': [{'delta': {'content': '</think>'}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            
        if tool_call_name == "update_memory" and tool_call_args:
            try:
                args = json.loads(tool_call_args)
                from backend.memory_store import get_global_store
                store = get_global_store()
                if store:
                    store.update_user_profile(args["key"], args["value"])
            except Exception as e:
                pass
                
        yield f"event: accumulator:{answer_content_accumulator}"

    async def _node_post_generation(self, last_user_msg: str, answer_content_accumulator: str, context_results_obj: Any, use_rag: bool) -> AsyncGenerator[str, None]:
        if self.suggestion:
            try:
                reranked_results = context_results_obj.final_results if (use_rag and context_results_obj) else []
                suggestions = await self.suggestion.generate_suggestions(
                    user_query=last_user_msg,
                    answer_text=answer_content_accumulator,
                    reranked_results=reranked_results
                )
                if suggestions:
                    yield f"event: suggestions\ndata: {json.dumps(suggestions, ensure_ascii=False)}\n\n"
                yield f"event: done\ndata: {json.dumps({'suggestions': suggestions or []}, ensure_ascii=False)}\n\n"
            except Exception as sug_err:
                yield f"event: done\ndata: {json.dumps({'suggestions': []}, ensure_ascii=False)}\n\n"
                
        try:
            from backend.main import PROJECT_ROOT
            log_path = PROJECT_ROOT / "data" / "gum_data" / "reflection_log_default_user.jsonl"
            with open(log_path, "a", encoding="utf-8") as f:
                if last_user_msg:
                    f.write(json.dumps({"role": "user", "content": last_user_msg}, ensure_ascii=False) + "\n")
                if answer_content_accumulator:
                    f.write(json.dumps({"role": "assistant", "content": answer_content_accumulator}, ensure_ascii=False) + "\n")
        except Exception:
            pass
