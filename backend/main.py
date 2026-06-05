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
import hashlib
from dotenv import load_dotenv

# 在 main.py 最上層加入全域快取字典
_rag_cache: dict = {}
RAG_CACHE_SIZE = 200  # 最多快取 200 組查詢結果

def get_query_fingerprint(query: str) -> str:
    """把查詢字串轉成固定長度的雜湊，作為快取 key"""
    return hashlib.md5(query.strip().lower().encode()).hexdigest()

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

# --- System Prompts (極簡優化版：支援列點排版) ---
BASE_PERSONA = (
    "你叫「AREQA」，是一位專精中華文化與古典文學的評論型問答助手。請一律使用繁體中文。\n"
    "【回答結構與風格】\n"
    "1. 破題立論：首段用1-2句話直擊問題核心，給出明確判斷。\n"
    "2. 混合排版（段落+列點）：分析主體請先用「連貫段落」闡述概念；當需要羅列證據、步驟、或多重觀點時，允許使用「清晰的條列式」整理，讓畫面易讀。\n"
    "3. 評論腔調：自然使用「關鍵在於」「表面上...實則...」「由此可見」等詞彙，展現文學講評的深度。不空泛、不機械。\n"
    "4. 資料邊界：若參考資料不足，請直接回答「根據目前資料無法充分解答」，絕不編造。\n"
)

# 1. 普通模式
SYSTEM_PROMPT_NORMAL = BASE_PERSONA + (
    "5. 若使用者提出蘇格拉底式的探討，結尾可帶一句引導性反問。\n"
    "【重要格式限制】\n"
    "6. 本次對話沒有提供任何 <context> 參考資料。\n"
    "   請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
    "   歷史對話中的引用標記僅屬於當時那一輪，不代表現在有相同文獻可引用。\n"
)

# 2. 強制思考模式 (嚴格限制 think 長度，內容放進正式回答)
SYSTEM_PROMPT_FORCE_THINK = BASE_PERSONA + (
    "【思考區塊限制】\n"
    "必須全程用繁體中文。只能條列最多3點核心關鍵詞，絕不在思考時長篇大論或自我修正。\n"
    "所有精采的文本分析與列點整理，請全部放到正式回答中展現。\n"
    "【重要格式限制】\n"
    "本次對話沒有提供任何 <context> 參考資料。\n"
    "請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
)

# 3. RAG 檢索模式 (嚴格標註來源)
SYSTEM_PROMPT_WITH_RAG = BASE_PERSONA + (
    "【檢索引用限制】\n"
    "必須嚴格基於提供的 <context> 回答。每次引用或轉述資料時，務必在句末或列點後明確標註來源（如：【文獻1】）。"
)

# 4. RAG + 強制思考模式 (兩者疊加)
SYSTEM_PROMPT_WITH_RAG_THINK = BASE_PERSONA + (
    "【思考與檢索引用限制】\n"
    "1. 必須全程用繁體中文。只能條列最多3點核心關鍵詞，絕不在思考時長篇大論或自我修正。\n"
    "2. 所有精采的文本分析與列點整理，請全部放到正式回答中展現。"
    "3. 正式回答必須嚴格基於 <context>，並在句末或列點後標註來源（如：【文獻1】）。"
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
        score_threshold=0.0,
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
    import time
    start_time = time.time()
    try:
        response = await client.chat.completions.create(
            model="qwen/qwen-2.5-7b-instruct",
            messages=[
                {"role": "system", "content": "你是一個古典文學檢索分析師。請嚴格輸出 JSON 格式。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=200,
            # If supported by OpenRouter/Qwen, we could use response_format={"type": "json_object"}
            # but since we're outputting an array, we'll parse the string.
        )
        if response.choices and response.choices[0].message.content:
            content = response.choices[0].message.content.strip()
            
            # Clean markdown code blocks if the LLM wrapped it in ```json ... ```
            import re
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
    
    # 如果 LLM 解析失敗或回傳空，退回使用原始 query
    if not queries:
        queries = [{"query": query, "type": "abstract_concept"}]
        
    return queries

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
            # ✅ 在函數頂端初始化所有 RAG 相關變數，避免 UnboundLocalError
            context_texts = []
            context_citations = []
            sources_payload = []
            context_prompt = ""
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
                                fingerprint = get_query_fingerprint(last_user_msg)
                                if fingerprint in _rag_cache:
                                    context_results_obj = _rag_cache[fingerprint]
                                else:
                                    context_results_obj = None
                                    # Parse and Decompose Query for targeted BM25/FAISS retrieval
                                    rag_queries = await parse_and_decompose_query(last_user_msg, client)
                                    print(f"DEBUG RAG Queries (Decomposed): {rag_queries}")
                                    
                                    # Loop through generator to yield SSE progress events!
                                    # Use an executor to avoid blocking the event loop with synchronous RAG operations
                                    gen = rag_service.retrieve_with_events(rag_queries)
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
                                        if len(_rag_cache) >= RAG_CACHE_SIZE:
                                            oldest_key = next(iter(_rag_cache))
                                            del _rag_cache[oldest_key]
                                        _rag_cache[fingerprint] = context_results_obj
                                        
                                if context_results_obj:
                                    # Layer 2: Rerank Score Fallback (Guardrail)
                                    # Detect if results were reranked to apply appropriate threshold
                                    is_reranked = False
                                    if context_results_obj.final_results and len(context_results_obj.final_results) > 0:
                                        # If reranker is active, results usually have a 'reranker_score' attribute
                                        first_res = context_results_obj.final_results[0]
                                        is_reranked = hasattr(first_res, 'reranker_score') or (isinstance(first_res, dict) and 'reranker_score' in first_res)
                                    
                                    # Use a much lower threshold for RRF scores (max ~0.033) vs Reranker scores (0.0-1.0)
                                    effective_threshold = 0.35 if is_reranked else 0.005
                                    
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
                                    
                                    # 1. 取得最高分作為基準
                                    highest_score = context_results_obj.highest_score

                                    # 2. 階梯式分數差值過濾 (Delta Score Filtering)
                                    MAX_DOCS = 7
                                    SCORE_DROP_TOLERANCE = 0.60  # 允許與第一名的最大分數差距
                                    ABSOLUTE_MIN_SCORE = 0.005    # 絕對最低及格線

                                    dynamic_results = []
                                    for doc in valid_results:
                                        # 條件A：數量不能超過 7 篇
                                        if len(dynamic_results) >= MAX_DOCS:
                                            break
                                        
                                        # 條件B：分數不能低於絕對及格線
                                        if doc.score < ABSOLUTE_MIN_SCORE:
                                            continue
                                            
                                        # 條件C：分數不能比第一名掉超過 0.40（斷崖式下跌攔截）
                                        if (highest_score - doc.score) > SCORE_DROP_TOLERANCE:
                                            continue
                                            
                                        dynamic_results.append(doc)

                                    valid_results = dynamic_results

                                    # 3. 解決 Lost in the Middle：注意力重排序 (Best-First & Second-Last)
                                    # 3. 解決 Lost in the Middle：注意力重排序 (Best-First & Second-Last)


                                    valid_results = reorder_for_attention(valid_results)

                                    # 4. DEBUG 觀察輸出
                                    print(f"DEBUG RAG: highest={highest_score:.4f}, final count={len(valid_results)}")
                                    for i, r in enumerate(valid_results):
                                        print(f"  Doc {i+1}: score={r.score:.4f}")
                                    
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

                    # 0.4. History Sanitization (防止 Context Bleeding)
                    import re
                    if not chat_req.use_rag:
                        for msg in chat_req.messages:
                            if msg.get("role") == "assistant" and msg.get("content"):
                                msg["content"] = re.sub(r'【文獻\d+】', '', msg["content"])

                    # 0.5. Inject System Prompt logic mimicking chat_app.py
                    if not has_system:
                        # Determine which prompt to use based on RAG and force_think flags
                        if chat_req.use_rag:
                            sys_prompt_text = SYSTEM_PROMPT_WITH_RAG_THINK if chat_req.force_think else SYSTEM_PROMPT_WITH_RAG
                            rag_status_note = "\n【本回合狀態】：已注入 <context> 參考資料，請嚴格依文獻回答並標註來源。"
                        else:
                            sys_prompt_text = SYSTEM_PROMPT_FORCE_THINK if chat_req.force_think else SYSTEM_PROMPT_NORMAL
                            rag_status_note = "\n【本回合狀態】：本回合無任何 <context> 資料注入。禁止輸出【文獻N】等引用標記。"
                        
                        final_system_prompt = sys_prompt_text + rag_status_note
                        
                        # Insert at the beginning of the messages list
                        chat_req.messages.insert(0, {"role": "system", "content": final_system_prompt})
                    
                    # Apply dynamic max_tokens based on RAG mode
                    effective_max_tokens = chat_req.max_tokens
                    if chat_req.use_rag and chat_req.max_tokens == 2048:
                        effective_max_tokens = 2500
                    
                    if chat_req.force_think:
                        # 思考模型需要非常大的 token 預算，否則會把正式回答截斷
                        effective_max_tokens = 3200
                        
                        # 補充 System Prompt，強制要求簡短思考
                        think_control_prompt = "\n【重要指令】你的思考過程請務必簡明扼要（盡量控制在 500 字以內），不要把時間浪費在複述上下文，請把所有詳細的分析與長篇論述都放在 </think> 之後的正式回答中！"
                        if chat_req.messages and chat_req.messages[0]["role"] == "system":
                            chat_req.messages[0]["content"] += think_control_prompt
                        else:
                            chat_req.messages.insert(0, {"role": "system", "content": think_control_prompt})
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

                    # 1. Using OpenRouter Qwen3 dynamic model routing
                    if chat_req.force_think:
                        # 使用者點擊了「思考」，調用 Thinking-Only 旗艦模型
                        target_model_name = "qwen/qwen3-235b-a22b-thinking-2507"
                    else:
                        # 使用者需要「即時回答」，切換到不會思考的 Instruct 模型 (依據 OpenRouter 文件，ID 為 qwen/qwen3-235b-a22b-2507)
                        target_model_name = "qwen/qwen3-235b-a22b-2507"
                    
                    extra_body = {
                        "repetition_penalty": chat_req.repetition_penalty
                    }
                    if chat_req.force_think:
                        # [核心設定]：強制思考過程最多只能用 512 個 token，逼它立刻進入正式回答
                        extra_body["provider"] = {"require_parameters": True}
                        extra_body["reasoning"] = {"max_tokens": 512}

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
                    import re
                    
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
                        
                        if content_text:
                            # Strip accidental think tags from content if the model natively generated them
                            # Use regex to handle spaces within the tags (e.g. < think >)
                            content_text = re.sub(r'<\s*/?\s*think\s*>', '', content_text)
                            if not content_text:
                                continue

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
