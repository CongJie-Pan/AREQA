import json
import asyncio
import os
import re
import time
from typing import AsyncGenerator, List, Dict, Any, Optional
from fastapi import Request
from openai import AsyncOpenAI

from gum_integration import (
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
   - "exact_entity": 專有名詞、具體物品、人名、書名
   - "abstract_concept": 抽象意境、情感、事件脈絡、賞析

請嚴格以 JSON 陣列 (Array of Objects) 的格式輸出，每個物件包含 "query" 與 "type" 兩個欄位。
範例輸出格式：
[
    {{"query": "水杯", "type": "exact_entity"}},
    {{"query": "水杯 裝水的器皿", "type": "abstract_concept"}}
]

問題：{query}"""
    
    queries = []
    start_time = time.time()
    try:
        from config import settings
        response = await client.chat.completions.create(
            model=settings.model_policy_classifier,
            messages=[
                {"role": "system", "content": "你是一個檢索分析師。請嚴格輸出 JSON 格式。"},
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

    async def execute(self, messages: List[Dict[str, str]], use_rag: bool, use_web_search: bool, force_think: bool,
                      max_tokens: int, temperature: float, top_p: float,
                      repetition_penalty: float, request: Request) -> AsyncGenerator[str, None]:
        
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        
        # Node 1: Intent Routing (DISABLED BY USER REQUEST)
        denied = False
        # async for event in self._node_intent_routing(last_user_msg):
        #     if event == "event: REFUSED\n\n":
        #         denied = True
        #         continue
        #     yield event
                
        # if denied:
        #     yield "data: [DONE]\n\n"
        #     return

            
        if last_user_msg:
            print(f"[EDF-LOG] streaming endpoint received message, evaluating student state asynchronously...")
            from services.compeer_scheduler import last_interaction_time
            last_interaction_time["default_user"] = time.time()
            asyncio.create_task(push_observation(f"User asked: {last_user_msg}"))
            if self.client:
                RECENT_WINDOW = 10
                recent_messages = messages[-RECENT_WINDOW:]
                from config import settings
                asyncio.create_task(async_evaluate_and_update_state(self.client, settings.model_policy_classifier, recent_messages))

        yield f"event: metadata\ndata: {json.dumps({'promptTokens': 1024, 'completionTokens': 0, 'totalTokens': 1024})}\n\n"

        # Node 2 & 3: Parallel Tasks (HyDE & Policy)
        policy_task = None
        if last_user_msg and self.client:
            from config import settings
            policy_task = asyncio.create_task(
                classify_dialogue_policy(self.client, settings.model_policy_classifier, last_user_msg, messages)
            )

        rag_queries = []
        cached_results = None
        if use_rag and not use_web_search and self.rag and last_user_msg:
            from main import get_query_fingerprint, rag_cache
            fingerprint = get_query_fingerprint(last_user_msg)
            if rag_cache:
                cached_results = await rag_cache.get(fingerprint)
                
            if not cached_results:
                rag_queries = await parse_and_decompose_query(last_user_msg, self.client)
            else:
                rag_queries = None

        # Node 4: RAG Retrieval
        context_results_obj = None
        if use_web_search and last_user_msg:
            async for event in self._node_perplexity_search(last_user_msg):
                if event.startswith("event: results_obj"):
                    context_results_obj = getattr(self, "_temp_rag_obj", None)
                    continue
                if event == "event: REFUSED\n\n":
                    yield "data: [DONE]\n\n"
                    return
                yield event
        elif use_rag and self.rag and last_user_msg:
            async for event in self._node_rag_retrieval(last_user_msg, rag_queries, cached_results):
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

        final_messages = await self._node_prompt_assembly(messages, use_rag, use_web_search, force_think, context_results_obj, last_user_msg)

        effective_max_tokens = max_tokens
        if policy in ["PROBE_UNDERSTANDING", "SUGGEST_ACTION"]:
            effective_max_tokens = 1500
        elif (use_rag or use_web_search) and max_tokens == 2048:
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
        async for event in self._node_post_generation(last_user_msg, answer_content_accumulator, context_results_obj, use_rag, use_web_search):
            yield event
            
        yield "data: [DONE]\n\n"


    async def _node_intent_routing(self, query: str) -> AsyncGenerator[str, None]:
        if not query or not self.client:
            return
            
        # Fast intent check to quickly reject truly harmful or out-of-scope queries
        # Router LLM is currently DISABLED. All queries pass through.
        # If re-enabled in the future, the prompt should be updated to reflect
        # the new universal learning scope of AREQA.
        pass


    async def _node_rag_retrieval(self, last_user_msg: str, rag_queries: List[Dict[str, str]], cached_results=None) -> AsyncGenerator[str, None]:
        from main import get_query_fingerprint, rag_cache, _thread_pool
        fingerprint = get_query_fingerprint(last_user_msg)
        context_results_obj = cached_results
        
        if not context_results_obj and rag_queries is not None:
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
                    
            if context_results_obj and rag_cache:
                await rag_cache.set(fingerprint, context_results_obj)
                
        if context_results_obj:
            is_reranked = False
            if context_results_obj.final_results and len(context_results_obj.final_results) > 0:
                first_res = context_results_obj.final_results[0]
                is_reranked = hasattr(first_res, 'reranker_score') or (isinstance(first_res, dict) and 'reranker_score' in first_res)
            
            effective_threshold = 0.35 if is_reranked else 0.005
            if context_results_obj.highest_score < effective_threshold:
                refusal = "AREQA查閱了相關文獻，暫時沒能找到與您問題直接相關的內容。為了保證回答的準確性，AREQA建議您換個方式提問，或詢問其他相關問題喔！ 😊"
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

    async def _node_perplexity_search(self, last_user_msg: str) -> AsyncGenerator[str, None]:
        import httpx
        import os
        
        print(f"[Perplexity] 開始聯網搜尋: {last_user_msg}")
        yield f"event: status\ndata: {json.dumps({'status': 'searching_dense', 'message': '🌐 網路檢索中...'}, ensure_ascii=False)}\n\n"

        
        api_key = os.environ.get("PERPLEXITY_API_KEY", "")
        if not api_key:
            yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 未設定 PERPLEXITY_API_KEY，改用一般對話...'}, ensure_ascii=False)}\n\n"
            self._temp_context_prompt = ""
            return
            
        import hashlib
        import redis.asyncio as aioredis
        search_hash = f"websearch:{hashlib.md5(last_user_msg.encode('utf-8')).hexdigest()}"
        redis_client = None
        cached_data_str = None
        
        try:
            redis_client = aioredis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
            cached_data_str = await redis_client.get(search_hash)
        except Exception as e:
            print(f"[Perplexity] Redis cache check error: {e}")
            
        if cached_data_str:
            print(f"[Perplexity] 命中 Redis 快取，直接使用先前的搜尋結果")
            data = json.loads(cached_data_str)
        else:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        "https://api.perplexity.ai/search",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "query": last_user_msg,
                            "max_results": 5
                        }
                    )
                    response.raise_for_status()
                    data = response.json()
                    
                    if redis_client:
                        try:
                            await redis_client.setex(search_hash, 86400, json.dumps(data, ensure_ascii=False))
                        except Exception as e:
                            print(f"[Perplexity] Redis cache set error: {e}")
            except httpx.HTTPStatusError as e:
                print(f"[EDF Perplexity Error] HTTPStatusError: {e.response.status_code} - {e.response.text}")
                yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 聯網搜尋服務暫時無法使用，改用一般對話...'}, ensure_ascii=False)}\n\n"
                self._temp_context_prompt = ""
                if redis_client: await redis_client.close()
                return
            except Exception as e:
                print(f"[EDF Perplexity Error] {type(e).__name__}: {str(e)}")
                yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 聯網搜尋服務暫時無法使用，改用一般對話...'}, ensure_ascii=False)}\n\n"
                self._temp_context_prompt = ""
                if redis_client: await redis_client.close()
                return
        
        if redis_client: await redis_client.close()
            
        results = data.get("results", [])
        
        print(f"[Perplexity] 成功取得回傳，共 {len(results)} 篇引用文獻")
        yield f"event: status\ndata: {json.dumps({'status': 'reranking', 'message': '⚡ 篩選與統整網路資訊...'}, ensure_ascii=False)}\n\n"
        
        context_texts = []
        sources_payload = []
        if results:
            for idx, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("snippet", "")
                context_texts.append(f"[文獻{idx}] {title}\nURL: {url}\n內容段落: {snippet}")
                sources_payload.append({
                    "title": title,
                    "chunk_id": url,
                    "snippet": snippet
                })
            
            # Send structured sources event 
            yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
        
        self._temp_context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
        self._temp_rag_obj = {"mock": True}
        yield "event: results_obj\n\n"

    async def _node_prompt_assembly(self, messages: List[Dict[str, str]], use_rag: bool, use_web_search: bool, force_think: bool, context_results_obj: Any, last_user_msg: str) -> List[Dict[str, str]]:
        from main import SYSTEM_PROMPT_WITH_RAG_THINK, SYSTEM_PROMPT_WITH_RAG, SYSTEM_PROMPT_FORCE_THINK, SYSTEM_PROMPT_NORMAL
        
        new_messages = [m.copy() for m in messages]
        has_system = len(new_messages) > 0 and new_messages[0]["role"] == "system"
        
        if (use_rag or use_web_search) and context_results_obj and hasattr(self, "_temp_context_prompt") and self._temp_context_prompt:
            for idx in range(len(new_messages)-1, -1, -1):
                if new_messages[idx]["role"] == "user":
                    new_messages[idx]["content"] = self._temp_context_prompt + new_messages[idx]["content"]
                    break
                    
        if not use_rag and not use_web_search:
            for msg in new_messages:
                if msg.get("role") == "assistant" and msg.get("content"):
                    msg["content"] = re.sub(r'【文獻\d+】', '', msg["content"])
                    
        if not has_system:
            if use_rag or use_web_search:
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
                
                # Dynamic Tone/Vocabulary Adaptation based on Learner State
                from memory_store import get_global_store
                store = get_global_store()
                if store:
                    learner_state = store.get_hot_memory().get("current_learner_state", "")
                    if learner_state == "STARTING":
                        final_system_prompt += "\n\n【動態表達限制：STARTING 階段】\n注意：使用者目前為初學者（STARTING）。你必須「嚴格降低詞彙難度」，絕對禁止使用未經解釋的進階專有名詞。請用最白話、最生活化的比喻來引導，一次只講一個重點，避免造成認知負荷超載。"
                    elif learner_state == "TINKERING":
                        final_system_prompt += "\n\n【動態表達限制：TINKERING 階段】\n注意：使用者正在摸索與建構概念（TINKERING）。你可以適度引入專有名詞，但必須伴隨具體例證與解釋。鼓勵思辨，但避免過度拋出艱澀的哲學大哉問而讓使用者不知所措。"
                    
                    active_avatar = store.get_hot_memory().get("active_avatar")
                    if active_avatar:
                        final_system_prompt += f"\n\n【特殊語境：英靈附體】\n注意：你現在已被召喚為「{active_avatar}」。請全程以第一人稱與用戶對話，語氣必須極度符合{active_avatar}的歷史定位、思維模式與經典口吻，直到話題轉移或用戶要求停止。"
                
            from config import settings
            cold_memory_ctx = await query_cold_memory_for_context(last_user_msg, top_k=5, client=self.client, model=settings.model_policy_classifier)
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
            
        from config import settings
        target_model_name = settings.model_main_thinking if force_think else settings.model_main_instruct
        extra_body = {"repetition_penalty": repetition_penalty}
        if force_think:
            extra_body["reasoning"] = {"enabled": True, "max_tokens": 512}
            
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
                from memory_store import get_global_store
                store = get_global_store()
                if store:
                    store.update_user_profile(args["key"], args["value"])
            except Exception as e:
                pass
                
        yield f"event: accumulator:{answer_content_accumulator}"

    async def _node_post_generation(self, last_user_msg: str, answer_content_accumulator: str, context_results_obj: Any, use_rag: bool, use_web_search: bool) -> AsyncGenerator[str, None]:
        if self.suggestion:
            try:
                reranked_results = context_results_obj.final_results if (use_rag and not use_web_search and context_results_obj) else []
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
            if answer_content_accumulator:
                asyncio.create_task(push_observation(f"Assistant answered: {answer_content_accumulator[:300]}"))
        except Exception:
            pass
