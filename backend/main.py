import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
import opencc
import os
from dotenv import load_dotenv

# Try to import transformers for local chat template
try:
    from transformers import AutoTokenizer
    # Initialize tokenizer globally
    _tokenizer = AutoTokenizer.from_pretrained("CongJ-Pan/XiaoHong-v1")
except Exception as e:
    _tokenizer = None
    print(f"Warning: Could not load tokenizer. Ensure transformers is installed. {e}")

from pathlib import Path
import os
from dotenv import load_dotenv

# Try loading from the unified global .env file in the project root
# Support both .env and .env.local
for env_name in [".env", ".env.local"]:
    env_path = Path(__file__).resolve().parent.parent / env_name
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment variables from {env_name}")
        break

HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_ENDPOINT_URL = os.environ.get("HF_ENDPOINT_URL", "")
HF_REPO_ID = os.environ.get("HF_REPO_ID", "/repository")

# Initialize global OpenCC converter (Simplified to Traditional Taiwan variant)
_converter = opencc.OpenCC('s2twp')

# Cache to store the dynamically resolved model name so we don't spam models.list() APIs
_resolved_model_name = None

# --- System Prompts (精簡強化版：嚴防幻覺與歸因錯誤) ---
SYSTEM_PROMPT_NORMAL = (
    "你叫「小紅」，專業國學助手。請始終用繁體中文回答。"
    "【準則】：回答須基於事實，不確定的事請誠實告知，嚴禁編造。"
    "輸出時請以列點式為主，段落為輔。"
)
SYSTEM_PROMPT_FORCE_THINK = (
    "你叫「小紅」，專業國學助手。請始終用繁體中文回答。"
    "【準則】：在 <think> 內務必核對事實，嚴禁臆測。"
    "輸出時請以列點式為主，段落為輔。"
)
SYSTEM_PROMPT_WITH_RAG = (
    "你叫「小紅」，繁體中文國學助手，始終用繁體中文回答。RAG 守則：\n"
    "1. **歸因核實**：若 <context> 未出現用戶詢問的人名、學者或特定主體，必先聲明「文獻未提及 [該主體]」，嚴禁強行掛名回答。\n"
    "2. **證據鎖定**：回答須嚴格鎖定 <context>。若資料中找不到與主體對應的證據，必須直言「未提及」，切勿配合用戶誘導而腦補。\n"
    "3. **邏輯隔離**：資料有相關內容但無該主體時，應回答：「資料未提及 [主體] 的說法，但相關文獻記載如下...」。"
    "4. 輸出時請以列點式為主，段落為輔。"
)
SYSTEM_PROMPT_WITH_RAG_THINK = (
    "你叫「小紅」，繁體中文國學助手，始終用繁體中文回答。RAG 守則：\n"
    "1. **歸因核實**：若 <context> 未出現用戶詢問的人名、學者或特定主體，必先聲明「文獻未提及 [該主體]」，嚴禁強行掛名回答。若用戶詢問的主體不在名單內，回答必先於<think>聲明「資料未提及 [主體]」\n"
    "2. **證據鎖定**：回答須嚴格鎖定 <context>。若資料中找不到與主體對應的證據，必須直言「未提及」，切勿配合用戶誘導而腦補。\n"
    "3. **邏輯隔離**：資料有相關內容但無該主體時，應回答：「資料未提及 [主體] 的說法，但相關文獻記載如下...」。"
    "4. 輸出時請以列點式為主，段落為輔。"
)


# Initialize the global thread pool for CPU bounds tasks (Tokenizer, FAISS, BM25)
_thread_pool = ThreadPoolExecutor(max_workers=4)

# Load RAG Service globally
try:
    import sys
    from pathlib import Path
    
    # In the new structure, backend/main.py is one level down from project root
    project_root = Path(__file__).resolve().parents[1]
    
    # Add the src/main/python folder to sys.path to resolve internal service imports
    src_python_dir = project_root / "src" / "main" / "python"
    if str(src_python_dir) not in sys.path:
        sys.path.insert(0, str(src_python_dir))
        
    from services.rag_service import RAGService
    from services.router_service import RouterService
    from services.suggestion_service import SuggestionService
    
    faiss_dir = project_root / "data" / "rag" / "faiss_index"
    bm25_dir = project_root / "data" / "rag" / "bm25_index"
    
    def get_latest_file(directory: Path, pattern: str) -> str:
        if not directory.exists():
            return ""
        files = list(directory.glob(pattern))
        if not files:
            return ""
        return str(sorted(files, key=lambda x: x.stat().st_mtime)[-1])
        
    # Check if empty data folder issue occurs, if so, fail gracefully
    latest_faiss_idx = get_latest_file(faiss_dir, "chunks*.index")
    latest_faiss_meta = get_latest_file(faiss_dir, "index_metadata*.json")
    
    if not latest_faiss_idx:
        latest_faiss_idx = "dummy_not_found.index"  # Prevent Path("") resolving to '.'
        print("Warning: No FAISS index found in data/rag/faiss_index. RAG will not work locally.")
    
    rag_service = RAGService(
        faiss_index_path=latest_faiss_idx,
        faiss_metadata_path=latest_faiss_meta,
        bm25_index_dir=str(bm25_dir),
        embedding_model_path="api", 
        reranker_model_path="api", # Added this back to enable high-quality reranking via API
        top_k=5,
        rrf_k=60,
        score_threshold=0.35,
        max_context_tokens=4000,
    )
    router_service = RouterService()
    suggestion_service = SuggestionService()
    print("RAG, Router, and Suggestion Services initialized successfully.")
except Exception as e:
    rag_service = None
    print(f"Warning: Could not load RAGService. Details: {e}")

app = FastAPI(title="XiaoHong Ancient Chinese QA - RAG Backend API")

# Strict CORS: Only allow connections from the Next.js local server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    use_rag: bool = False
    force_think: bool = False
    temperature: float = 0.7
    top_p: float = 0.8
    max_tokens: int = 2048
    repetition_penalty: float = 1.2
    presence_penalty: float = 1.5
    no_repeat_ngram_size: int = 3

class TitleRequest(BaseModel):
    messages: List[Dict[str, str]]

@app.post("/api/v1/generate-title")
async def generate_title_endpoint(request: Request, title_req: TitleRequest):
    """
    Generate a conversation title using OpenRouter (qwen/qwen-2.5-7b-instruct).
    Returns a stream of the generated title.
    """
    async def generate():
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("Error: OPENROUTER_API_KEY is missing")
            yield "data: [ERROR] OPENROUTER_API_KEY missing\n\n"
            yield "data: [DONE]\n\n"
            return

        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=30.0
        )

        system_prompt = "你是一個助理，請根據以下對話內容，總結出一個簡短的繁體中文對話標題（不超過 10 個字，不要加引號或其他標點符號）。"

        # We only need the first user message and assistant reply to generate a title
        # Filter messages to ensure we don't send too much context
        filtered_messages = [msg for msg in title_req.messages if msg["role"] in ["user", "assistant"]]

        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + filtered_messages

        try:
            response = await client.chat.completions.create(
                model="qwen/qwen-2.5-7b-instruct",
                messages=full_messages,
                stream=True,
                max_tokens=64,
                temperature=0.7,
                top_p=0.9,
            )

            async for chunk in response:
                if await request.is_disconnected():
                    break

                if not chunk.choices:
                    continue

                content = chunk.choices[0].delta.content
                if content:
                    # Apply OpenCC conversion as a failsafe
                    converted_content = _converter.convert(content)
                    yield f"data: {json.dumps({'content': converted_content}, ensure_ascii=False)}\n\n"

        except Exception as e:
            print(f"Title generation error: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )

@app.get("/api/v1/retrieve")
async def retrieve_endpoint(query: str, top_k: int = 20, offset: int = 0, limit: int = 10):
    """
    Search endpoint that returns pure JSON snippets.
    Suitable for frontend debug panels or citation references.
    Includes pagination support (offset/limit).
    """
    if not rag_service:
        return {"results": [], "error": "RAG service not initialized"}
        
    loop = asyncio.get_running_loop()
    # Execute retrieval in the thread pool
    try:
        results = await loop.run_in_executor(_thread_pool, rag_service.retrieve, query)
        # Convert RetrievalResult objects to dicts
        dict_results = [
            {
                "text": r.text,
                "score": float(r.score),
                "source": r.source,
                "chunk_id": r.chunk_id
            } for r in results
        ]
        
        # Apply pagination
        paginated_results = dict_results[offset : offset + limit]
        return {
            "results": paginated_results,
            "total": len(dict_results),
            "offset": offset,
            "limit": limit
        }
    except Exception as e:
        print(f"Retrieve endpoint error: {e}")
        return {"results": [], "error": str(e)}

@app.post("/api/v1/stream")
async def stream_endpoint(request: Request, chat_req: ChatRequest):
    """
    Core streaming endpoint for textual generation.
    Returns:
       1) metadata event (syncing token calculations)
       2) ongoing chunk data events from vLLM
    """
    async def generate():
        try:
            # 0. Gatekeeper / Smart Routing phase (Absolute First Layer)
            # Yield an initial status to trigger the loading spinner (message is empty to avoid text display)
            yield f"event: status\ndata: {json.dumps({'status': 'routing', 'message': ''}, ensure_ascii=False)}\n\n"

            # Detect if the query is Out-of-Domain (OOD) before any other processing
            last_user_msg = next((m["content"] for m in reversed(chat_req.messages) if m["role"] == "user"), "")
            if last_user_msg and router_service:
                # Use a task to run the router while occasionally yielding a heartbeat if it takes too long
                router_task = asyncio.create_task(router_service.check_query_intent(last_user_msg))
                
                while not router_task.done():
                    # Wait for a bit, or until task finishes
                    done, pending = await asyncio.wait([router_task], timeout=5.0)
                    if not done:
                        # Task still running after 5s, send heartbeat to keep connection alive
                        yield f": heartbeat\n\n"
                
                intent_result = await router_task
                
                if intent_result.get("action") == "DENY":
                    # Update status to refusal
                    yield f"event: status\ndata: {json.dumps({'status': 'refused', 'message': '❌ 非相關領域問題'}, ensure_ascii=False)}\n\n"
                    
                    refusal = intent_result.get("refusal_message") or "小紅目前僅能回答關於《紅樓夢》與國學相關的問題，請換個問題試試看喔！"
                    chunk_data = {
                        "choices": [
                            {
                                "delta": {"content": refusal},
                                "index": 0,
                                "finish_reason": "stop",
                            }
                        ]
                    }
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    return

            # 1. Metadata synchronization phase
            metadata = {
                "promptTokens": 1024,
                "completionTokens": 0,
                "totalTokens": 1024
            }
            yield f"event: metadata\ndata: {json.dumps(metadata)}\n\n"
            
            # 2. Token generation stream phase
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                chunk_data = {"choices": [{"delta": {"content": "[System Error] OPENROUTER_API_KEY is missing in the global .env file."}, "index": 0, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            else:
                try:
                    # [Commented Out] Original Hugging Face Endpoint client initialization
                    # hf_base_url = HF_ENDPOINT_URL.strip()
                    # if not hf_base_url.strip("/").endswith("v1"):
                    #     hf_base_url = hf_base_url.rstrip("/") + "/v1/"
                    # client = AsyncOpenAI(
                    #     base_url=hf_base_url, 
                    #     api_key=HF_TOKEN, 
                    #     timeout=120.0
                    # )
                    
                    # Upgraded client: Connect to OpenRouter
                    client = AsyncOpenAI(
                        base_url="https://openrouter.ai/api/v1",
                        api_key=api_key,
                        timeout=120.0
                    )
                    
                    # 0. RAG Retrieval phase
                    has_system = len(chat_req.messages) > 0 and chat_req.messages[0]["role"] == "system"
                    context_citations = []
                    
                    if chat_req.use_rag and rag_service:
                        last_user_msg = next((m["content"] for m in reversed(chat_req.messages) if m["role"] == "user"), "")
                        if last_user_msg:
                            try:
                                context_results_obj = None
                                # Loop through generator to yield SSE progress events!
                                # Use an executor to avoid blocking the event loop with synchronous RAG operations
                                gen = rag_service.retrieve_with_events(last_user_msg)
                                while True:
                                    # Use a task to run the executor while occasionally yielding a heartbeat
                                    rag_task = asyncio.get_running_loop().run_in_executor(_thread_pool, next, gen, None)
                                    
                                    while not rag_task.done():
                                        done, pending = await asyncio.wait([rag_task], timeout=5.0)
                                        if not done:
                                            yield f": heartbeat\n\n"
                                    
                                    event = await rag_task
                                    if event is None:
                                        break
                                    if event["type"] == "status":
                                        status_payload = {"status": event["status"], "message": event["message"]}
                                        yield f"event: status\ndata: {json.dumps(status_payload, ensure_ascii=False)}\n\n"
                                    elif event["type"] == "results":
                                        context_results_obj = event["data"]
                                        
                                if context_results_obj:
                                    # Layer 2: Rerank Score Fallback (Guardrail)
                                    # Detect if results were reranked to apply appropriate threshold
                                    is_reranked = False
                                    if context_results_obj.final_results and len(context_results_obj.final_results) > 0:
                                        # If reranker is active, results usually have a 'reranker_score' attribute
                                        first_res = context_results_obj.final_results[0]
                                        is_reranked = hasattr(first_res, 'reranker_score') or (isinstance(first_res, dict) and 'reranker_score' in first_res)
                                    
                                    # Use a much lower threshold for RRF scores (max ~0.033) vs Reranker scores (0.0-1.0)
                                    effective_threshold = rag_service.score_threshold if is_reranked else 0.005
                                    
                                    # If RAG is enabled but no document score exceeds the threshold, trigger refusal
                                    if context_results_obj.highest_score < effective_threshold:
                                        refusal = "小紅查閱了相關古籍文獻，暫時沒能找到與您問題直接相關的內容。為了保證回答的準確性，小紅建議您換個方式提問，或是詢問關於《紅樓夢》與國學的其他問題喔！ 😊"
                                        chunk_data = {
                                            "choices": [
                                                {
                                                    "delta": {"content": refusal},
                                                    "index": 0,
                                                    "finish_reason": "stop",
                                                }
                                            ]
                                        }
                                        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                                        yield "data: [DONE]\n\n"
                                        return

                                    if context_results_obj.final_results:
                                        context_texts = []
                                    sources_payload = []
                                    
                                    # Filter out results with empty or whitespace-only text
                                    valid_results = [r for r in context_results_obj.final_results if r.text and r.text.strip()]
                                    
                                    for idx, chunk in enumerate(valid_results, 1):
                                        # Try multiple attributes to get a meaningful source title
                                        # Priority: chunk.source > chunk.metadata.source > chunk.metadata.book > chunk_id prefix
                                        raw_source = (
                                            getattr(chunk, 'source', None)
                                            or getattr(getattr(chunk, 'metadata', None), 'source', None)
                                            or getattr(getattr(chunk, 'metadata', None), 'book', None)
                                            or getattr(getattr(chunk, 'metadata', None), 'book_name', None)
                                        )
                                        chunk_id = getattr(chunk, 'chunk_id', None) or "N/A"
                                        
                                        # If still no source, use chunk_id prefix (e.g. 'hongloumeng_ch01_0' → 'hongloumeng')
                                        if not raw_source and chunk_id != "N/A":
                                            raw_source = chunk_id.split('_')[0] if '_' in str(chunk_id) else None
                                        
                                        source = raw_source or "古籍文獻"
                                        text = chunk.text
                                        score = chunk.score
                                        
                                        context_texts.append(f"[文獻{idx}] {source}\n{text}")
                                        context_citations.append(f"[{source}] (Chunk: {chunk_id})")
                                        
                                        # Standardise source schema for interactive citation cards
                                        sources_payload.append({
                                            "title": source,
                                            "snippet": text,
                                            "score": float(score),
                                            "chunk_id": chunk_id
                                        })
                                    
                                    # Push the structured sources payload before generation begins
                                    yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
                                    
                                    yield f"event: status\ndata: {json.dumps({'status': 'generating', 'message': '✍️ 援引文獻，生成解說...' }, ensure_ascii=False)}\n\n"
                                    
                                    context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
                                    # Update the last user message to include context!
                                    for idx in range(len(chat_req.messages)-1, -1, -1):
                                        if chat_req.messages[idx]["role"] == "user":
                                            chat_req.messages[idx]["content"] = context_prompt + chat_req.messages[idx]["content"]
                                            break
                            except Exception as e:
                                print(f"RAG retrieval failed: {e}")
                                yield f"event: error\ndata: {json.dumps({'detail': f'RAG Error: {e}'}, ensure_ascii=False)}\n\n"

                    # 0.5. Inject System Prompt logic mimicking chat_app.py
                    if not has_system:
                        # Determine which prompt to use based on RAG and force_think flags
                        if chat_req.use_rag:
                            sys_prompt_text = SYSTEM_PROMPT_WITH_RAG_THINK if chat_req.force_think else SYSTEM_PROMPT_WITH_RAG
                        else:
                            sys_prompt_text = SYSTEM_PROMPT_FORCE_THINK if chat_req.force_think else SYSTEM_PROMPT_NORMAL
                            
                        # Insert at the beginning of the messages list
                        chat_req.messages.insert(0, {"role": "system", "content": sys_prompt_text})
                    
                    # Apply dynamic max_tokens based on RAG mode
                    effective_max_tokens = chat_req.max_tokens
                    if chat_req.use_rag and chat_req.max_tokens == 2048:
                        effective_max_tokens = 2500

                    # [Commented Out] Original Hugging Face completions creation logic
                    # try:
                    #     if HF_REPO_ID and HF_REPO_ID != "/repository":
                    #         target_model_name = HF_REPO_ID
                    #     else:
                    #         models_resp = await client.models.list()
                    #         target_model_name = models_resp.data[0].id
                    # except Exception:
                    #     target_model_name = "/repository"
                    # 
                    # response = await client.completions.create(
                    #     model=target_model_name,
                    #     prompt=prompt,
                    #     stream=True,
                    #     max_tokens=effective_max_tokens,
                    #     temperature=chat_req.temperature if chat_req.temperature > 0 else 0.001,
                    #     top_p=chat_req.top_p,
                    #     extra_body={
                    #         "repetition_penalty": chat_req.repetition_penalty,
                    #         "skip_special_tokens": False
                    #     },
                    #     stop=["<|im_end|>", "<|endoftext|>"]
                    # )

                    # 1. Using OpenRouter Qwen3.5 397B A17B
                    target_model_name = "qwen/qwen3.5-397b-a17b"
                    
                    extra_body = {
                        "repetition_penalty": chat_req.repetition_penalty
                    }
                    if chat_req.force_think:
                        extra_body["chat_template_kwargs"] = {
                            "enable_thinking": True
                        }

                    response = await client.chat.completions.create(
                        model=target_model_name,
                        messages=chat_req.messages,
                        stream=True,
                        max_tokens=effective_max_tokens,
                        temperature=chat_req.temperature if chat_req.temperature > 0 else 0.001,
                        top_p=chat_req.top_p,
                        extra_body=extra_body,
                    )
                    
                    answer_content_accumulator = ""
                    inside_reasoning = False
                    
                    async for chunk in response:
                        if await request.is_disconnected():
                            break
                        
                        if not chunk.choices:
                            continue
                            
                        delta = chunk.choices[0].delta
                        
                        # Extract reasoning tokens
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

                        # Extract content tokens
                        content_text = delta.content if (hasattr(delta, 'content') and delta.content) else ""

                        # If reasoning is streaming
                        if reasoning_text:
                            if not inside_reasoning:
                                inside_reasoning = True
                                # Yield <think> start tag to client
                                chunk_data = {
                                    "choices": [
                                        {
                                            "delta": {"content": "<think>"},
                                            "index": 0,
                                            "finish_reason": None,
                                        }
                                    ]
                                }
                                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                            
                            # Stream the reasoning content
                            chunk_data = {
                                "choices": [
                                    {
                                        "delta": {"content": reasoning_text},
                                        "index": 0,
                                        "finish_reason": None,
                                    }
                                ]
                            }
                            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                        # If content is streaming
                        if content_text:
                            if inside_reasoning:
                                inside_reasoning = False
                                # Yield </think> end tag to client
                                chunk_data = {
                                    "choices": [
                                        {
                                            "delta": {"content": "</think>"},
                                            "index": 0,
                                            "finish_reason": None,
                                        }
                                    ]
                                }
                                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                            answer_content_accumulator += content_text
                            chunk_data = {
                                "choices": [
                                    {
                                        "delta": {"content": content_text},
                                        "index": 0,
                                        "finish_reason": None,
                                    }
                                ]
                            }
                            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

                        await asyncio.sleep(0)

                    # Post-loop safety check for closing think tag
                    if inside_reasoning:
                        inside_reasoning = False
                        chunk_data = {
                            "choices": [
                                    {
                                        "delta": {"content": "</think>"},
                                        "index": 0,
                                        "finish_reason": None,
                                    }
                                ]
                            }
                        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
                    
                    # 2.5. Generate Suggestions (Suggested Questions)
                    # Triggered after main generation is complete, reusing RAG contexts
                    if suggestion_service:
                        try:
                            # We only generate if we have a valid last user message and results
                            # context_results_obj was captured during RAG phase
                            # last_user_msg was captured at the start of generate()
                            
                            # Note: context_results_obj might be None if RAG was disabled
                            # But suggestion_service can still generate based on query and answer
                            reranked_results = context_results_obj.final_results if (chat_req.use_rag and context_results_obj) else []
                            
                            suggestions = await suggestion_service.generate_suggestions(
                                user_query=last_user_msg,
                                answer_text=answer_content_accumulator,
                                reranked_results=reranked_results
                            )
                            
                            if suggestions:
                                yield f"event: suggestions\ndata: {json.dumps(suggestions, ensure_ascii=False)}\n\n"
                            # Bundle in event: done for Store synchronization
                            yield f"event: done\ndata: {json.dumps({'suggestions': suggestions or []}, ensure_ascii=False)}\n\n"
                        except Exception as sug_err:
                            print(f"Failed to generate suggestions: {sug_err}")
                            yield f"event: done\ndata: {json.dumps({'suggestions': []}, ensure_ascii=False)}\n\n"
                        
                except Exception as e:
                    reason = str(e)
                    error_output = f"**[API Error]** 發生錯誤請重試。Hugging Face Endpoint 回應：\n\n```\n{reason}\n```"
                    chunk_data = {"choices": [{"delta": {"content": error_output}, "index": 0}]}
                    yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            
            # 3. Stream End signal
            yield "data: [DONE]\n\n"
            
        except asyncio.CancelledError:
            print("DEBUG: Stream cancelled by client (asyncio.CancelledError)")
            pass
        except Exception as e:
            print(f"DEBUG: Critical Stream Error: {e}")
            import traceback
            traceback.print_exc()
            error_msg = f"\n\n**[系統錯誤]** 發生未預期錯誤：{str(e)}"
            chunk_data = {
                "choices": [
                    {
                        "delta": {"content": error_msg},
                        "index": 0,
                        "finish_reason": "error",
                    }
                ]
            }
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
