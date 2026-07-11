import sys

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Request, WebSocket, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from auth import get_current_user
from openai import AsyncOpenAI
import opencc
import os
import hashlib
import time
from dotenv import load_dotenv

# 在 main.py 最上層加入全域快取服務變數
rag_cache = None

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

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

# --- System Prompts (動態人設切換架構) ---
BASE_PERSONA = (
    "你叫「AREQA」，是一位博學廣識的引導型學習助手。你的核心特質是動態的「認知感知力」，能根據使用者的問題，自然切換到最契合該領域的思維語境。請一律使用繁體中文。\n\n"
    "【動態語境切換】\n"
    "1. 若問題涉及「因果、歷史、演變」→ 以歷史學者視角：考察結構性力量與脈絡，用敘事的厚重感回答。\n"
    "2. 若問題涉及「概念、本質、哲學」→ 以哲學家視角：拆解預設，揭示矛盾，用邏輯的精準張力回答。\n"
    "3. 若問題涉及「科學、模型、量化、數學」→ 以科學家視角：建立模型，區分變數，用客觀嚴謹的美感回答。\n"
    "4. 若問題涉及「文學、修辭、情感」→ 以文學評論家視角：拆解文本，體會情感，用感性且深刻的語氣回答。\n"
    "5. 🚨【日常與閒聊模式】：若問題屬於日常閒聊、無厘頭提問（如：「你是誰」、「你有幾根頭髮」、「今天吃什麼」），請立刻放下所有學術架子與評論腔調！用幽默、輕鬆、機智的朋友口吻回答，絕對不要一本正經地長篇大論。\n\n"
    "【回答結構與風格】\n"
    "1. 首段用1-2句話直擊問題核心，給出明確的立場或判斷。\n"
    "2. 優先展示「思維過程」，再給結論；需要多重觀點時，使用「清晰的條列式」整理（閒聊模式除外）。\n"
    "3. 評論腔調：自然使用「關鍵在於」「表面上...實則...」等詞彙，展現深度（閒聊模式除外）。不要宣告「我現在以XX身份回應」，直接進入語境。\n"
    "4. 引導優先：對話必須以「引導式詢問」為主，用一個簡單的問題邀請用戶互動。絕對避免單向陳述或自顧自地說教。\n"
)

# 1. 普通模式 (Instruct)
SYSTEM_PROMPT_NORMAL = BASE_PERSONA + (
    "【重要格式限制】\n"
    "本次對話沒有提供任何參考資料。\n"
    "請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
)

# 2. 強制思考模式 (Thinking)
SYSTEM_PROMPT_FORCE_THINK = BASE_PERSONA + (
    "【腦內專家委員會機制 (Layer 2 MoE)】\n"
    "在你的內部思考過程中，請先靜默執行領域識別，自問：這屬於什麼學科？需要事實、分析、還是探索？\n"
    "然後在腦內啟動對應的專家框架（如：歷史分析框架、哲學拆解框架）。\n"
    "【思考區塊限制】\n"
    "必須全程用繁體中文。只能條列核心推演過程，絕不在思考時長篇大論或自我修正。\n"
    "所有精采的文本分析與列點整理，請全部放到正式回答中展現。\n"
    "【重要格式限制】\n"
    "本次對話沒有提供任何參考資料。\n"
    "請勿在回答中輸出任何【文獻N】標記，即使歷史紀錄中曾出現過此格式。\n"
)

# 3. RAG 檢索模式 (Instruct + RAG)
SYSTEM_PROMPT_WITH_RAG = BASE_PERSONA + (
    "【檢索引用限制】\n"
    "必須嚴格基於提供的 <context> 參考資料回答。每次引用或轉述資料時，務必在句末或列點後明確標註來源（如：【文獻1】）。\n\n"
    "【RAG 語境解析與防閹割規則 - 最高優先級】\n"
    "在進行正式回答前，你必須在內部嚴格執行以下檢驗：\n\n"
    "1. 🔍 核心前提掃描 (Core Premise Scanning)：\n"
    "    分析 <context>，找出理解該文本不可或缺的「特殊語境」或「核心前提」。\n"
    "    （包含但不限於：反事實假想、思想實驗、理論假設、與大眾常識相悖的特殊設定等。）\n"
    "    若該前提與你的內建常識衝突，請無條件優先信任 <context>。\n\n"
    "2. 📢 認知基底優先確立 (Fact-First Disclosure)：\n"
    "    若掃描到上述「核心前提」，你【正式回答的開頭】，必須直接且明確地向使用者揭露此一前提，幫助其建立正確的認知地基。\n"
    "    ⚠️【防閹割指令】：此「揭露前提」的動作為系統最高權限。即使 EDF 策略要求你「降低認知負荷」或「簡化概念」，你也絕對不可因此省略或隱藏文本的特殊設定與前提。\n\n"
    "完成以上兩步，確保使用者不會產生根本性的認知誤解後，再套用 EDF 策略進行後續引導。\n"
)

# 4. RAG + 強制思考模式 (Thinking + RAG)
SYSTEM_PROMPT_WITH_RAG_THINK = BASE_PERSONA + (
    "【腦內專家委員會機制 (Layer 2 MoE)】\n"
    "在你的內部思考過程中，請先靜默執行領域識別，啟動對應專家框架，並仔細比對 <context> 中的證據。\n"
    "【思考與檢索引用限制】\n"
    "1. 必須全程用繁體中文。只能條列核心推演過程，絕不在思考時長篇大論。\n"
    "2. 所有精采的文本分析與列點整理，請全部放到正式回答中展現。\n"
    "3. 正式回答必須嚴格基於 <context> 參考資料，並在句末或列點後明確標註來源（如：【文獻1】）。\n\n"
    "【RAG 語境解析與防閹割規則 - 最高優先級】\n"
    "在進行正式回答前，你必須在內部嚴格執行以下檢驗：\n\n"
    "1. 🔍 核心前提掃描 (Core Premise Scanning)：\n"
    "    分析 <context>，找出理解該文本不可或缺的「特殊語境」或「核心前提」。\n"
    "    （包含但不限於：反事實假想、思想實驗、理論假設、與大眾常識相悖的特殊設定等。）\n"
    "    若該前提與你的內建常識衝突，請無條件優先信任 <context>。\n\n"
    "2. 📢 認知基底優先確立 (Fact-First Disclosure)：\n"
    "    若掃描到上述「核心前提」，你【正式回答的開頭】，必須直接且明確地向使用者揭露此一前提，幫助其建立正確的認知地基。\n"
    "    ⚠️【防閹割指令】：此「揭露前提」的動作為系統最高權限。即使 EDF 策略要求你「降低認知負荷」或「簡化概念」，你也絕對不可因此省略或隱藏文本的特殊設定與前提。\n\n"
    "完成以上兩步，確保使用者不會產生根本性的認知誤解後，再套用 EDF 策略進行後續引導。\n"
)

# Initialize the global thread pool for CPU bounds tasks (Tokenizer, FAISS, BM25)
_thread_pool = ThreadPoolExecutor(max_workers=4)

src_python_dir = PROJECT_ROOT / "src" / "main" / "python"
if str(src_python_dir) not in sys.path:
    sys.path.insert(0, str(src_python_dir))

from services.router_service import RouterService
from services.suggestion_service import SuggestionService

router_service = RouterService()
suggestion_service = SuggestionService()
rag_service = None

def _env_flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}

def init_rag_service():
    """Initialize internal RAG only when explicitly enabled."""
    global rag_service
    if rag_service is not None:
        return rag_service

    if not _env_flag("ENABLE_INTERNAL_RAG"):
        print("Internal RAG disabled. Set ENABLE_INTERNAL_RAG=true to enable local retrieval.")
        return None

    try:
        from services.rag_service import RAGService

        faiss_dir = PROJECT_ROOT / "data" / "rag" / "faiss_index"
        bm25_dir = PROJECT_ROOT / "data" / "rag" / "bm25_index"

        def get_latest_file(directory: Path, pattern: str) -> str:
            if not directory.exists():
                return ""
            files = list(directory.glob(pattern))
            if not files:
                return ""
            return str(sorted(files, key=lambda x: x.stat().st_mtime)[-1])

        latest_faiss_idx = get_latest_file(faiss_dir, "chunks*.index")
        latest_faiss_meta = get_latest_file(faiss_dir, "index_metadata*.json")

        if not latest_faiss_idx or not latest_faiss_meta:
            print("Internal RAG enabled but FAISS index/metadata is missing. RAG disabled.")
            return None

        rag_service = RAGService(
            faiss_index_path=latest_faiss_idx,
            faiss_metadata_path=latest_faiss_meta,
            bm25_index_dir=str(bm25_dir),
            embedding_model_path="api",
            reranker_model_path="api",
            top_k=5,
            rrf_k=60,
            score_threshold=0.0,
            max_context_tokens=4000,
        )
        print("RAG Service initialized successfully.")
        return rag_service
    except Exception as e:
        rag_service = None
        print(f"Warning: Could not load RAGService. Details: {e}")
        return None

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
            from gum_integration import gum_instances
            for gum_instance in list(gum_instances.values()):
                if gum_instance and hasattr(gum_instance, "engine"):
                    await gum_instance.engine.dispose()
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
            from gum_integration import gum_instances
            for gum_instance in list(gum_instances.values()):
                if gum_instance and hasattr(gum_instance, "engine"):
                    await gum_instance.engine.dispose()
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

# Strict CORS: Only allow connections from the Next.js local server and Render
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"], 
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    from memory_store import init_global_store
    from mailbox_store import init_mailbox_store
    
    # Init store
    store = init_global_store(budget_limit=1000000)
    # await store.clear_all_pending_alerts("default_user") # Skipped for multi-tenant
    print("Memory Store initialized successfully.")
    
    init_mailbox_store()
    print("Mailbox Store initialized successfully.")
    
    # GUM instances are now initialized lazily per user via get_gum_instance
    
    global rag_cache
    from services.cache_service import RagCacheService
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    rag_cache = RagCacheService(redis_url)
    print("Redis RAG Cache initialized successfully.")
    
    # Start ComPeer Scheduler and Mailbox Worker
    import sys
    sys.path.append(str(PROJECT_ROOT / "backend" / "services"))
    from services.compeer_scheduler import proactive_scheduler_loop, daily_scheduler_loop
    from mailbox_store import delayed_mail_worker
    
    app.state.proactive_task = asyncio.create_task(proactive_scheduler_loop())
    app.state.daily_task = asyncio.create_task(daily_scheduler_loop())
    app.state.delayed_mail_worker = asyncio.create_task(delayed_mail_worker())

@app.on_event("shutdown")
async def shutdown_event():
    from gum_integration import stop_gum_instance

    await stop_gum_instance()
    if hasattr(app.state, 'proactive_task'):
        app.state.proactive_task.cancel()
    if hasattr(app.state, 'daily_task'):
        app.state.daily_task.cancel()
    if hasattr(app.state, 'delayed_mail_worker'):
        app.state.delayed_mail_worker.cancel()

_local_summary_cache = {}

async def push_observation(user_id: str, text: str):
    from gum_integration import push_observation as _push_observation

    return await _push_observation(user_id, text)

async def get_all_memory(user_id: str = "default_user"):
    from gum_integration import get_all_memory

    return await get_all_memory(user_id)

@app.get("/api/v1/memory")
async def fetch_memory(current_user_id: str = Depends(get_current_user)):
    props = await get_all_memory(current_user_id)
    # Filter out short term memory (hot:) for the UI list
    long_term_props = [
        p for p in props 
        if not str(p.get("id", "")).startswith("hot:") 
        and "Type: scroll" not in p.get("text", "") 
        and "User Action: scroll" not in p.get("text", "")
    ]
    return {"propositions": long_term_props}

@app.get("/api/v1/memory/summary")
async def get_memory_summary(current_user_id: str = Depends(get_current_user)):
    props = await get_all_memory(current_user_id)
    # Filter out short term and scroll
    long_term_props = [
        p for p in props 
        if not str(p.get("id", "")).startswith("hot:") 
        and "Type: scroll" not in p.get("text", "") 
        and "User Action: scroll" not in p.get("text", "")
    ]
    
    long_term_props = sorted(long_term_props, key=lambda x: str(x.get("id", "")))
    
    memory_text = "\n".join([f"- {p['text']}" for p in long_term_props])
    memory_hash = hashlib.md5(memory_text.encode('utf-8')).hexdigest()
    
    # 1. Try Redis cache
    redis_client = None
    try:
        if 'rag_cache' in globals() and rag_cache is not None:
            redis_client = rag_cache.redis
            
            cached_summary = await redis_client.get(f"memory_summary_json:{current_user_id}")
            cached_hash = await redis_client.get(f"memory_summary_hash:{current_user_id}")
            
            if cached_summary:
                cached_summary = cached_summary.decode('utf-8') if isinstance(cached_summary, bytes) else cached_summary
            if cached_hash:
                cached_hash = cached_hash.decode('utf-8') if isinstance(cached_hash, bytes) else cached_hash
            
            if cached_summary and cached_hash == memory_hash:
                return {"summary": json.loads(cached_summary)}
    except Exception as e:
        print(f"Redis cache error: {e}")
        
    # 2. Try in-memory fallback cache (useful for Render deployments without Redis)
    user_local_cache = _local_summary_cache.get(current_user_id, {})
    if user_local_cache.get("hash") == memory_hash:
        print("[MemorySummary] Hit in-memory fallback cache")
        return {"summary": user_local_cache.get("summary")}
    
    prompt = f"""請根據以下長期記憶內容，對這個使用者進行綜整：
【長期記憶】
{memory_text}

【輸出要求】
必須以嚴格的 JSON 格式輸出，不要有任何 Markdown 標記，不要輸出其他多餘的說明。格式如下：
{{
  "sentence1": "一句話表示對這個人的認識",
  "sentence2": "兩句話解釋",
  "hashtags": ["標籤1", "標籤2", "標籤3"]
}}"""

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", "")
    )
    
    try:
        completion = await client.chat.completions.create(
            model="qwen/qwen3-235b-a22b-2507",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7
        )
        summary_raw = completion.choices[0].message.content.strip()
        if summary_raw.startswith("```json"):
            summary_raw = summary_raw[7:]
        elif summary_raw.startswith("```"):
            summary_raw = summary_raw[3:]
        if summary_raw.endswith("```"):
            summary_raw = summary_raw[:-3]
            
        summary_json = json.loads(summary_raw.strip())
        
        # Cache it (Redis)
        if redis_client:
            try:
                await redis_client.set(f"memory_summary_json:{current_user_id}", json.dumps(summary_json, ensure_ascii=False))
                await redis_client.set(f"memory_summary_hash:{current_user_id}", memory_hash)
            except Exception as e:
                print(f"Redis cache set error: {e}")
                
        # Cache it (Local fallback)
        if current_user_id not in _local_summary_cache:
            _local_summary_cache[current_user_id] = {}
        _local_summary_cache[current_user_id]["summary"] = summary_json
        _local_summary_cache[current_user_id]["hash"] = memory_hash
                
        return {"summary": summary_json}
    except Exception as e:
        print(f"Error calling Qwen for memory summary: {e}")
        return {"summary": {"sentence1": "無法生成總結，請確認網路連線與 API Key 設定。", "sentence2": "", "hashtags": []}}

@app.get("/api/v1/memory/debug")
async def memory_debug_endpoint(current_user_id: str = Depends(get_current_user)):
    from gum_integration import get_hot_memory_snapshot
    from memory_store import get_global_store

    store = get_global_store()
    if not store:
        return {"status": "unavailable"}

    profile = await store.get_user_profile(current_user_id)
    hot_memory = await store.get_hot_memory(current_user_id)
    working_memory = await store.get_working_memory(current_user_id)
    behavior_signals = await store.get_behavior_signals(current_user_id)
    cold_candidates = await store.get_cold_candidates(current_user_id)
    prompt_snapshot = await get_hot_memory_snapshot(current_user_id)

    return {
        "status": "ok",
        "user_id": current_user_id,
        "profile": profile,
        "hot_memory": hot_memory,
        "working_memory": working_memory,
        "behavior_signals": behavior_signals,
        "cold_candidates": cold_candidates,
        "prompt_snapshot": prompt_snapshot,
    }

from mailbox_store import get_mailbox_store

@app.get("/api/v1/mailbox")
async def fetch_mailbox(current_user_id: str = Depends(get_current_user)):
    store = get_mailbox_store()
    return {
        "mails": await store.get_all_mails(current_user_id),
        "unread_count": await store.get_unread_count(current_user_id)
    }

class SendMailRequest(BaseModel):
    content: str
    recipient: str = "AREQA"
    conversation_id: Optional[str] = None

def _mailbox_reply_task_id(user_id: str, recipient: str, content: str, conversation_id: Optional[str]) -> str:
    window = int(time.time() // 600)
    normalized = " ".join(content.split())
    source = f"{user_id}|{recipient}|{conversation_id or ''}|{normalized}|{window}"
    return f"reply-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]}"

@app.post("/api/v1/mailbox/send")
async def send_mail_endpoint(req: SendMailRequest, current_user_id: str = Depends(get_current_user)):
    store = get_mailbox_store()
    mail_id = await store.add_mail(user_id=current_user_id, sender="User", content=req.content, recipient=req.recipient, conversation_id=req.conversation_id)
    await store.mark_as_read(user_id=current_user_id, mail_id=mail_id)
    await store.schedule_delayed_mail(
        user_id=current_user_id,
        mail_data={
            "reply_to_mail_id": mail_id,
            "reply_content": req.content,
            "active_avatar": req.recipient,
            "conversation_id": req.conversation_id or mail_id,
            "task_id": _mailbox_reply_task_id(current_user_id, req.recipient, req.content, req.conversation_id),
        },
        delay_seconds=300,
    )
    return {"status": "success", "mail_id": mail_id}

@app.post("/api/v1/mailbox/read/{mail_id}")
async def read_mail_endpoint(mail_id: str, current_user_id: str = Depends(get_current_user)):
    store = get_mailbox_store()
    success = await store.mark_as_read(user_id=current_user_id, mail_id=mail_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mail not found")
    return {"status": "success"}


class EditMemoryRequest(BaseModel):
    text: str

@app.delete("/api/v1/memory/working")
async def clear_working_memory_endpoint(current_user_id: str = Depends(get_current_user)):
    from memory_store import get_global_store

    store = get_global_store()
    if not store:
        raise HTTPException(status_code=500, detail="Memory store not initialized")

    await store.clear_working_memory(current_user_id)
    return {"status": "success", "cleared": "working_memory"}

@app.delete("/api/v1/memory/{mem_id}")
async def delete_memory_endpoint(mem_id: str, current_user_id: str = Depends(get_current_user)):
    from gum_integration import get_gum_instance
    from memory_store import get_global_store
    
    if mem_id.startswith("profile:"):
        store = get_global_store()
        key = mem_id.split("profile:")[1]
        profile = await store.get_user_profile(current_user_id)
        if key in profile:
            del profile[key]
            import json
            await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))
    elif mem_id.startswith("hot:"):
        store = get_global_store()
        key = mem_id.split("hot:")[1]
        hot_mem = await store.get_hot_memory(current_user_id)
        if key in hot_mem:
            del hot_mem[key]
            import json
            await store.redis.set(f"areqa:hot_memory:{current_user_id}", json.dumps(hot_mem, ensure_ascii=False))
    else:
        gum_instance, _ = await get_gum_instance(current_user_id)
        if gum_instance:
            await gum_instance.update_status(int(mem_id), "deleted")
    return {"status": "success"}

class DeleteBatchRequest(BaseModel):
    ids: List[str]

@app.post("/api/v1/memory/batch-delete")
async def batch_delete_memory_endpoint(req: DeleteBatchRequest, current_user_id: str = Depends(get_current_user)):
    for mem_id in req.ids:
        await delete_memory_endpoint(mem_id, current_user_id)
    return {"status": "success", "deleted_count": len(req.ids)}

@app.put("/api/v1/memory/{mem_id}")
async def edit_memory_endpoint(mem_id: str, req: EditMemoryRequest, current_user_id: str = Depends(get_current_user)):
    from gum_integration import get_gum_instance
    from memory_store import get_global_store
    
    if mem_id.startswith("profile:"):
        store = get_global_store()
        key = mem_id.split("profile:")[1]
        profile = await store.get_user_profile(current_user_id)
        if key in profile:
            profile[key] = req.text
            import json
            await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))
    elif mem_id.startswith("hot:"):
        store = get_global_store()
        key = mem_id.split("hot:")[1]
        hot_mem = await store.get_hot_memory(current_user_id)
        if key in hot_mem:
            if isinstance(hot_mem[key], dict):
                hot_mem[key]["text"] = req.text
            else:
                hot_mem[key] = req.text
            import json
            await store.redis.set(f"areqa:hot_memory:{current_user_id}", json.dumps(hot_mem, ensure_ascii=False))
    else:
        gum_instance, _ = await get_gum_instance(current_user_id)
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
                        from cold_memory import get_engine
                        from sqlalchemy import text
                        from sqlalchemy.ext.asyncio import AsyncSession
                        engine = get_engine()
                        async with AsyncSession(engine) as session:
                            async with session.begin():
                                await session.execute(text(
                                    "SELECT set_config('request.jwt.claims', "
                                    "jsonb_build_object('role', 'authenticated', 'sub', CAST(:uid AS text))::text, TRUE)"
                                ), {"uid": current_user_id})
                                await session.execute(text("SET LOCAL ROLE authenticated;"))
                                
                                await session.execute(text("UPDATE propositions SET text = :text WHERE id = :id"), {"text": req.text, "id": int(mem_id)})
                                await session.execute(text("UPDATE vec_memory SET embedding = CAST(:emb AS vector) WHERE id = :id"), {"emb": str(embed), "id": int(mem_id)})
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
    conversation_id: str = ""
    use_rag: bool = False
    use_web_search: bool = False
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
    Generate a conversation title using OpenRouter.
    Returns a stream of the generated title.
    """
    from config import settings
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
                model=settings.model_policy_classifier,
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
    prompt = f"""你是一個「知識檢索分析師」。你的任務是解析使用者的提問，並將其拆解為適合進行混合檢索（BM25 與 FAISS）的「乾淨檢索詞」，同時判斷這個檢索詞的類型。

要求：
1. 去除所有冗言贅字與題幹指令語（如「請問」、「最適當的是」、「下列何者」、「哪一項」等）。
2. 若問題包含多個實體或複雜比較，必須將其拆解為多個獨立的子查詢。拋棄現代白話文連接詞（如「的」、「與」、「和」）。
3. 判斷每一個子查詢的類型 (type)，限定為以下兩種：
   - "exact_entity": 專有名詞、具體物品、人名、書名（例如：量子力學、薛寶釵、相對論、軍機處）
   - "abstract_concept": 抽象意境、情感、事件脈絡、原理概念（例如：命運悲劇、因果關係、演化機制）

請嚴格以 JSON 陣列 (Array of Objects) 的格式輸出，每個物件包含 "query" 與 "type" 兩個欄位。
範例輸出格式：
[
    {{"query": "相對論", "type": "exact_entity"}},
    {{"query": "時間膨脹 效應", "type": "abstract_concept"}}
]

問題：{query}"""
    
    queries = []
    import time
    start_time = time.time()
    try:
        response = await client.chat.completions.create(
            model=settings.model_policy_classifier,
            messages=[
                {"role": "system", "content": "你是一個知識檢索分析師。請嚴格輸出 JSON 格式。"},
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
    active_rag = init_rag_service()
    if not active_rag:
        return {"results": [], "error": "Internal RAG is disabled or not initialized"}

    loop = asyncio.get_running_loop()
    # Execute retrieval in the thread pool
    try:
        results = await loop.run_in_executor(_thread_pool, active_rag.retrieve, query)
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
async def log_action(req: ActionLogRequest, current_user_id: str = Depends(get_current_user)):
    """
    接收前端事件 (如點擊燈泡、UI 互動、語音打斷)
    """
    obs_text = f"[User Action] Type: {req.action_type}, Context: {req.context}"
    print(f"[EDF-LOG] log_action endpoint received: {obs_text}")
    
    from memory_store import get_global_store
    store = get_global_store()
    if store:
        from memory_gate import apply_action_gate
        asyncio.create_task(apply_action_gate(store, current_user_id, req.action_type, req.context))
        
    if req.action_type == "scroll":
        # Pure UI telemetry belongs to behavior_signals only; it must not enter prompt memory.
        pass
    elif req.action_type == "compeer_rejected":
        import services.compeer_scheduler as compeer
        target_user = current_user_id
        learner_state = await store.get_learner_state(target_user) if store else "default"
        await compeer.set_cooldown(target_user, state=learner_state)
        print(f"[ComPeer] User '{target_user}' rejected popup, entering cooldown.")
    else:
        # Other client actions are behavior signals unless a reflection pipeline promotes them.
        pass
        
    return {"status": "ok"}

@app.get("/api/v1/proactive-check")
async def proactive_check_endpoint(current_user_id: str = Depends(get_current_user)):
    user_id = current_user_id
    from memory_store import get_global_store
    store = get_global_store()
    if store:
        alert_content = await store.get_and_clear_pending_alert(user_id)
        if alert_content:
            print(f"[EDF-LOG] proactive-check endpoint returning alert: {alert_content}")
            return {"has_alert": True, "content": alert_content}
    return {"has_alert": False}

@app.delete("/api/v1/memory")
async def clear_memory_endpoint(current_user_id: str = Depends(get_current_user)):
    """Clear all hot memory and cold GUM memory"""
    from gum_integration import clear_gum_memory

    from memory_store import get_global_store
    store = get_global_store()
    if store:
        await store.clear_all_memory(current_user_id)
        
    await clear_gum_memory(current_user_id)
    return {"status": "ok", "message": "Memory cleared successfully"}

from services.connection_manager import ws_manager

@app.post("/api/v1/ws/ticket")
async def generate_ws_ticket(current_user_id: str = Depends(get_current_user)):
    from memory_store import get_global_store
    import secrets
    store = get_global_store()
    if not store:
        raise HTTPException(status_code=500, detail="Redis store not initialized")
    
    ticket = secrets.token_urlsafe(32)
    # Store ticket with TTL 30 seconds
    await store.redis.setex(f"ws_ticket:{ticket}", 30, current_user_id)
    return {"ticket": ticket}

@app.websocket("/api/v1/ws/notifications")
async def ws_notifications(websocket: WebSocket, ticket: str):
    # 手動驗證 Origin（CORSMiddleware 不覆蓋 WebSocket）
    origin = websocket.headers.get("origin")
    allowed = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
    if origin and origin not in allowed and not origin.endswith(".onrender.com"):
        await websocket.close(code=4001)  # Policy Violation
        return
        
    from memory_store import get_global_store
    store = get_global_store()
    if not store:
        await websocket.close(code=1011)
        return
        
    user_id_bytes = await store.redis.getdel(f"ws_ticket:{ticket}")
    if not user_id_bytes:
        await websocket.close(code=4001)
        return
        
    user_id = user_id_bytes.decode("utf-8") if isinstance(user_id_bytes, bytes) else user_id_bytes
    
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # 維持連線存活
    except Exception:
        ws_manager.disconnect(user_id)

@app.post("/api/v1/stream")
async def stream_endpoint(
    request: Request, 
    chat_req: ChatRequest,
    current_user_id: str = Depends(get_current_user)
):
    """
    Core streaming endpoint for textual generation using OrchestrationService.
    """
    # (Deprecated local dict usage removed to prevent AttributeError)
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
        
    from services.orchestration_service import OrchestrationService
    orchestrator = OrchestrationService(
        router_service=router_service,
        rag_service=init_rag_service() if chat_req.use_rag else None,
        suggestion_service=suggestion_service,
        client=client
    )

    return StreamingResponse(
        orchestrator.execute(
            messages=chat_req.messages,
            conversation_id=chat_req.conversation_id,
            use_rag=chat_req.use_rag,
            use_web_search=chat_req.use_web_search,
            force_think=chat_req.force_think,
            max_tokens=chat_req.max_tokens,
            temperature=chat_req.temperature,
            top_p=chat_req.top_p,
            repetition_penalty=chat_req.repetition_penalty,
            request=request,
            user_id=current_user_id
        ), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
