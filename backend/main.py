import sys
import pysqlite3
sys.modules['sqlite3'] = pysqlite3
sys.modules['sqlite3.dbapi2'] = pysqlite3.dbapi2

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
import opencc
import os
import hashlib
from dotenv import load_dotenv

from gum_integration import init_gum_instance, stop_gum_instance, push_observation, get_all_memory, get_suggestions, query_memory_for_context, get_hot_memory_snapshot, query_cold_memory_for_context, async_evaluate_and_update_state

# 在 main.py 最上層加入全域快取服務變數
rag_cache = None

def get_query_fingerprint(query: str) -> str:
    """把查詢字串轉成固定長度的雜湊，作為快取 key"""
    return hashlib.md5(query.strip().lower().encode()).hexdigest()

# Try to import transformers for local chat template
# try:
#     from transformers import AutoTokenizer
#     # Initialize tokenizer globally
#     # _tokenizer = AutoTokenizer.from_pretrained("CongJ-Pan/XiaoHong-v1")
# except Exception as e:
#     _tokenizer = None
#     print(f"Warning: Could not load tokenizer. Ensure transformers is installed. {e}")

from pathlib import Path
import os
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

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
    "1. 首段用1-2句話直擊問題核心，給出明確判斷。\n"
    "2. 分析主體請先用「連貫段落」闡述概念；當需要羅列證據、步驟、或多重觀點時，允許使用「清晰的條列式」整理，讓畫面易讀。\n"
    "3. 評論腔調：自然使用「關鍵在於」「表面上...實則...」「由此可見」等詞彙，展現文學講評的深度。不空泛、不機械。\n"
    "4. 資料邊界：若參考資料不足，請直接回答「根據目前資料無法充分解答」，絕不編造。\n"
    "5. 領域限制：你只回答與國學、或中華古典文學相關的問題。如果遇到無關領域（例如：解數學方程式、現代科技、物理化學、程式碼等），請直接以幽默委婉的語氣拒絕（例如：「這是數學領域的問題呢，AREQA只熟悉國學知識，不在我的範疇內。歡迎詢問古典文學相關問題 😊」），絕不要嘗試去解題或回答該無關知識。\n"
)

# 1. 普通模式
SYSTEM_PROMPT_NORMAL = BASE_PERSONA + (
    "5. 若使用者提出蘇格拉底式的探討，結尾可帶一句引導性反問。\n"
    "【重要格式限制】\n"
    "6. 本次對話沒有提供任何參考資料。\n"
    "   請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
    "   歷史對話中的引用標記僅屬於當時那一輪，不代表現在有相同文獻可引用。\n"
)

# 2. 強制思考模式 (嚴格限制 think 長度，內容放進正式回答)
SYSTEM_PROMPT_FORCE_THINK = BASE_PERSONA + (
    "【思考區塊限制】\n"
    "必須全程用繁體中文。只能條列最多3點核心關鍵詞，絕不在思考時長篇大論或自我修正。\n"
    "所有精采的文本分析與列點整理，請全部放到正式回答中展現。\n"
    "【重要格式限制】\n"
    "本次對話沒有提供任何參考資料。\n"
    "請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
)

# 3. RAG 檢索模式 (嚴格標註來源)
SYSTEM_PROMPT_WITH_RAG = BASE_PERSONA + (
    "【檢索引用限制】\n"
    "必須嚴格基於提供的 <context> 參考資料 回答。每次引用或轉述資料時，務必在句末或列點後明確標註來源（如：【文獻1】）。"
)

# 4. RAG + 強制思考模式 (兩者疊加)
SYSTEM_PROMPT_WITH_RAG_THINK = BASE_PERSONA + (
    "【思考與檢索引用限制】\n"
    "1. 必須全程用繁體中文。只能條列最多3點核心關鍵詞，絕不在思考時長篇大論或自我修正。\n"
    "2. 所有精采的文本分析與列點整理，請全部放到正式回答中展現。"
    "3. 正式回答必須嚴格基於 <context>參考資料 ，並在句末或列點後標註來源（如：【文獻1】）。"
)

# Initialize the global thread pool for CPU bounds tasks (Tokenizer, FAISS, BM25)
_thread_pool = ThreadPoolExecutor(max_workers=4)

# Load RAG Service globally
try:
    import sys
    from pathlib import Path
    
    # In the new structure, backend/main.py is one level down from project root
    
    # Add the src/main/python folder to sys.path to resolve internal service imports
    src_python_dir = PROJECT_ROOT / "src" / "main" / "python"
    if str(src_python_dir) not in sys.path:
        sys.path.insert(0, str(src_python_dir))
        
    from services.rag_service import RAGService
    from services.router_service import RouterService
    from services.suggestion_service import SuggestionService
    
    faiss_dir = PROJECT_ROOT / "data" / "rag" / "faiss_index"
    bm25_dir = PROJECT_ROOT / "data" / "rag" / "bm25_index"
    
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
    
    print("DEBUG: Before RAGService")
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
    print("DEBUG: After RAGService")
    router_service = RouterService()
    print("DEBUG: After RouterService")
    suggestion_service = SuggestionService()
    print("RAG, Router, and Suggestion Services initialized successfully.")
except Exception as e:
    rag_service = None
    print(f"Warning: Could not load RAGService. Details: {e}")

app = FastAPI(title="XiaoHong Ancient Chinese QA - RAG Backend API")

import sqlite3
import sqlalchemy.exc
from fastapi.responses import JSONResponse
from fastapi import Request

@app.middleware("http")
async def db_error_recovery_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except sqlalchemy.exc.OperationalError as e:
        err_msg = str(e).lower()
        if "disk i/o error" in err_msg or "i/o error" in err_msg:
            print("MIDDLEWARE CAUGHT DISK I/O ERROR. Attempting emergency engine reset...")
            from gum_integration import gum_instance
            if gum_instance and hasattr(gum_instance, "engine"):
                await gum_instance.engine.dispose()
                # Attempt to reconnect
                try:
                    await gum_instance.connect_db()
                except Exception as ex:
                    print(f"Emergency reconnect failed: {ex}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Database connection reset due to I/O error. Please retry your request.",
                    "error_type": "db_io_recovery"
                }
            )
        raise
    except sqlite3.OperationalError as e:
        err_msg = str(e).lower()
        if "disk i/o error" in err_msg or "i/o error" in err_msg:
            print("MIDDLEWARE CAUGHT DISK I/O ERROR. Attempting emergency engine reset...")
            from gum_integration import gum_instance
            if gum_instance and hasattr(gum_instance, "engine"):
                await gum_instance.engine.dispose()
                # Attempt to reconnect
                try:
                    await gum_instance.connect_db()
                except Exception as ex:
                    print(f"Emergency reconnect failed: {ex}")
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Database connection reset due to I/O error. Please retry your request.",
                    "error_type": "db_io_recovery"
                }
            )
        raise

# Strict CORS: Only allow connections from the Next.js local server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    from memory_store import init_global_store
    
    # Init store
    hot_path = PROJECT_ROOT / "data" / "gum_data" / "hot_memory.json"
    profile_path = PROJECT_ROOT / "data" / "gum_data" / "user_profile.json"
    store = init_global_store(str(hot_path), str(profile_path), budget_limit=1000000)
    store.clear_all_pending_alerts()
    print("Memory Store initialized successfully.")
    
    await init_gum_instance()
    
    global rag_cache
    from services.cache_service import RagCacheService
    rag_cache = RagCacheService("redis://localhost:6379")
    print("Redis RAG Cache initialized successfully.")
    
    # Start ComPeer Scheduler
    import sys
    sys.path.append(str(PROJECT_ROOT / "backend" / "services"))
    from services.compeer_scheduler import proactive_scheduler_loop, daily_scheduler_loop
    app.state.proactive_task = asyncio.create_task(proactive_scheduler_loop())
    app.state.daily_task = asyncio.create_task(daily_scheduler_loop())

@app.on_event("shutdown")
async def shutdown_event():
    await stop_gum_instance()
    if hasattr(app.state, 'proactive_task'):
        app.state.proactive_task.cancel()
    if hasattr(app.state, 'daily_task'):
        app.state.daily_task.cancel()

@app.get("/api/v1/memory")
async def fetch_memory():
    props = await get_all_memory()
    return {"propositions": props}

@app.get("/api/v1/suggestions")
async def fetch_suggestions_endpoint():
    sugs = await get_suggestions()
    return {"suggestions": sugs}

class EditMemoryRequest(BaseModel):
    text: str

@app.delete("/api/v1/memory/{mem_id}")
async def delete_memory_endpoint(mem_id: str):
    from gum_integration import gum_instance
    from memory_store import get_global_store
    
    if mem_id.startswith("profile:"):
        store = get_global_store()
        key = mem_id.split("profile:")[1]
        profile = store.get_user_profile()
        if key in profile:
            del profile[key]
            store._atomic_write(store.user_profile_path, profile)
    elif mem_id.startswith("hot:"):
        store = get_global_store()
        key = mem_id.split("hot:")[1]
        hot_mem = store.get_hot_memory()
        if key in hot_mem:
            del hot_mem[key]
            store._atomic_write(store.hot_memory_path, hot_mem)
    else:
        if gum_instance:
            await gum_instance.update_status(int(mem_id), "deleted")
    return {"status": "success"}

class DeleteBatchRequest(BaseModel):
    ids: List[str]

@app.post("/api/v1/memory/batch-delete")
async def batch_delete_memory_endpoint(req: DeleteBatchRequest):
    for mem_id in req.ids:
        await delete_memory_endpoint(mem_id)
    return {"status": "success", "deleted_count": len(req.ids)}

@app.put("/api/v1/memory/{mem_id}")
async def edit_memory_endpoint(mem_id: str, req: EditMemoryRequest):
    from gum_integration import gum_instance
    from memory_store import get_global_store
    
    if mem_id.startswith("profile:"):
        store = get_global_store()
        key = mem_id.split("profile:")[1]
        profile = store.get_user_profile()
        if key in profile:
            profile[key] = req.text
            store._atomic_write(store.user_profile_path, profile)
    elif mem_id.startswith("hot:"):
        store = get_global_store()
        key = mem_id.split("hot:")[1]
        hot_mem = store.get_hot_memory()
        if key in hot_mem:
            if isinstance(hot_mem[key], dict):
                hot_mem[key]["text"] = req.text
            else:
                hot_mem[key] = req.text
            store._atomic_write(store.hot_memory_path, hot_mem)
    else:
        if gum_instance:
            await gum_instance.update_text(int(mem_id), req.text)
            
            # Update cold memory search indexes (FTS & Vector)
            try:
                from cold_memory import ColdMemoryRetriever
                import os
                from pathlib import Path
                db_path = str(Path(__file__).resolve().parent.parent / "data" / "gum_data" / "gum.db")
                api_key = os.environ.get("OPENROUTER_API_KEY", "")
                if api_key:
                    cold_retriever = ColdMemoryRetriever(db_path, api_key)
                    embed = await cold_retriever.get_embedding(req.text)
                    if embed:
                        import struct
                        embed_bytes = struct.pack(f'{len(embed)}f', *embed)
                        with cold_retriever._get_conn() as conn:
                            conn.execute("UPDATE propositions_fts SET text = ? WHERE rowid = ?", (req.text, int(mem_id)))
                            conn.execute("UPDATE vec_memory SET embedding = ? WHERE id = ?", (embed_bytes, int(mem_id)))
                            conn.commit()
            except Exception as e:
                print(f"Failed to update cold memory indexes for edit: {e}")
            
    return {"status": "success"}

class ActionLogRequest(BaseModel):
    user_id: str = "default"
    action_type: str
    timestamp: int
    context: Dict[str, Any] = {}

class MemoryQueryRequest(BaseModel):
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
    Generate a conversation title using OpenRouter (qwen/qwen3-30b-a3b-instruct-2507).
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

        system_prompt = (
            "你是一個標題生成器。請根據對話內容，為這個對話命名一個極簡的繁體中文標題。\n"
            "規則：\n"
            "1. 必須小於 10 個字。\n"
            "2. 絕不包含引號、句號或其他標點符號。\n"
            "3. 直接輸出標題文字，不加任何解釋說明（例如不可以說「標題是：...」）。\n"
            "4. 直接萃取對話中最核心的關鍵字即可。"
        )

        # We only need the first user message and assistant reply to generate a title
        # Filter messages to ensure we don't send too much context
        filtered_messages = [msg for msg in title_req.messages if msg["role"] in ["user", "assistant"]]

        full_messages = [
            {"role": "system", "content": system_prompt}
        ] + filtered_messages

        try:
            response = await client.chat.completions.create(
                model="qwen/qwen3-30b-a3b-instruct-2507",
                messages=full_messages,
                stream=True,
                max_tokens=15,
                temperature=0.3,
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
            model="qwen/qwen3-30b-a3b-instruct-2507",
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

@app.post("/api/v1/log_action")
async def log_action(req: ActionLogRequest):
    """
    接收前端事件 (如點擊燈泡、UI 互動、語音打斷)
    """
    obs_text = f"[User Action] Type: {req.action_type}, Context: {req.context}"
    print(f"[EDF-LOG] log_action endpoint received: {obs_text}")
    
    if req.action_type == "scroll":
        # Pure UI telemetry like scrolling doesn't need to go to GUM's cold memory evolution
        # Just write it directly to hot memory for the compeer scheduler to evaluate
        from memory_store import get_global_store
        import time
        store = get_global_store()
        if store:
            import uuid
            key = f"obs_{time.time()}_{uuid.uuid4().hex[:8]}"
            asyncio.create_task(store.update_hot_memory_async(key, obs_text))
    else:
        # Meaningful interactions go to GUM to become semantic propositions
        asyncio.create_task(push_observation(obs_text))
        
    return {"status": "ok"}

@app.get("/api/v1/proactive-check")
async def proactive_check_endpoint(user_id: str = "default_user"):
    from memory_store import get_global_store
    store = get_global_store()
    if store:
        alert_content = store.get_and_clear_pending_alert(user_id)
        if alert_content:
            print(f"[EDF-LOG] proactive-check endpoint returning alert: {alert_content}")
            return {"has_alert": True, "content": alert_content}
    return {"has_alert": False}

from services.connection_manager import ws_manager

@app.websocket("/api/v1/ws/notifications")
async def ws_notifications(websocket: WebSocket, user_id: str = "default_user"):
    # 手動驗證 Origin（CORSMiddleware 不覆蓋 WebSocket）
    origin = websocket.headers.get("origin", "")
    allowed = ["http://localhost:3000", "http://127.0.0.1:3000"]
    if origin not in allowed:
        await websocket.close(code=1008)  # Policy Violation
        return
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # 維持連線存活
    except Exception:
        ws_manager.disconnect(user_id)

@app.post("/api/v1/stream")
async def stream_endpoint(request: Request, chat_req: ChatRequest):
    """
    Core streaming endpoint for textual generation using OrchestrationService.
    """
    import services.compeer_scheduler as compeer
    compeer.user_flag["default_user"] = True
    
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        async def mock_missing_key_stream():
            yield 'data: {"choices": [{"delta": {"content": "[System] OPENROUTER_API_KEY is missing! Please configure it in .env file."}}]}\n\n'
            yield 'data: [DONE]\n\n'
        return StreamingResponse(
            mock_missing_key_stream(),
            media_type="text/event-stream"
        )

    client = None
    if api_key:
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=120.0
        )
        
    from backend.services.orchestration_service import OrchestrationService
    orchestrator = OrchestrationService(
        router_service=router_service,
        rag_service=rag_service,
        suggestion_service=suggestion_service,
        client=client
    )

    return StreamingResponse(
        orchestrator.execute(
            messages=chat_req.messages,
            use_rag=chat_req.use_rag,
            force_think=chat_req.force_think,
            max_tokens=chat_req.max_tokens,
            temperature=chat_req.temperature,
            top_p=chat_req.top_p,
            repetition_penalty=chat_req.repetition_penalty,
            request=request
        ), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
