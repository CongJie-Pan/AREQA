"""Diagnostics, retrieval, action-log, and proactive-check routes."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import re
import sys
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel

from auth import get_current_user, get_optional_current_user

router = APIRouter()
logger = logging.getLogger("backend.main")


def _main_module():
    return (
        sys.modules.get("backend.main")
        or sys.modules.get("main")
        or importlib.import_module("main")
    )

class ActionLogRequest(BaseModel):
    user_id: str = "default"
    action_type: str
    timestamp: int
    context: Dict[str, Any] = {}

class ShareDebugLogRequest(BaseModel):
    event: str
    context: Dict[str, Any] = {}

class ConversationHistoryDebugLogRequest(BaseModel):
    event: str
    context: Dict[str, Any] = {}

class MemoryQueryRequest(BaseModel):
    query: str
    top_k: int = 5


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
    from config import settings

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

@router.get("/api/v1/retrieve")
async def retrieve_endpoint(query: str, top_k: int = 20, offset: int = 0, limit: int = 10):
    """
    Search endpoint that returns pure JSON snippets.
    Suitable for frontend debug panels or citation references.
    Includes pagination support (offset/limit).
    """
    active_rag = _main_module().init_rag_service()
    if not active_rag:
        return {"results": [], "error": "Internal RAG is disabled or not initialized"}

    loop = asyncio.get_running_loop()
    # Execute retrieval in the thread pool
    try:
        results = await loop.run_in_executor(_main_module()._thread_pool, active_rag.retrieve, query)
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

async def classify_dialogue_policy(
    client: AsyncOpenAI,
    model: str,
    user_msg: str,
    chat_history: list,
    *,
    has_pdf_attachment: bool = False,
    pdf_attachment_count: int = 0,
) -> str:
    """Return a legacy dialogue policy via the structured EDF policy service.

    Args:
        client: Chat-completions compatible model client.
        model: Policy classifier model identifier.
        user_msg: Current user-authored message.
        chat_history: Recent conversation history.
        has_pdf_attachment: Whether the current request contains a PDF.
        pdf_attachment_count: Number of PDF attachments in the current request.

    Returns:
        One of the legacy policy labels expected by older tests and callers.

    Compatibility:
        ``backend.main`` keeps this wrapper because some tests and legacy imports
        still reference it directly. The implementation delegates to
        ``services.query_policy_service`` so the authoritative policy behavior
        stays in one service module.
    """

    from services.query_policy.classifier import classify_dialogue_policy_impl

    return await classify_dialogue_policy_impl(
        client,
        model,
        user_msg,
        chat_history,
        has_pdf_attachment=has_pdf_attachment,
        pdf_attachment_count=pdf_attachment_count,
    )

def _safe_share_debug_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Keep share diagnostics operational and free of user content/secrets."""
    allowed_keys = {
        "component",
        "conversationId",
        "hasConversationPayload",
        "hasError",
        "hasInsertedShare",
        "messageCount",
        "shareDebugId",
        "status",
        "titleLength",
        "validMessageCount",
    }
    safe: Dict[str, Any] = {}
    for key, value in context.items():
        if key not in allowed_keys:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    supabase_error = context.get("supabaseError")
    if isinstance(supabase_error, dict):
        safe["supabaseError"] = {
            key: value
            for key, value in supabase_error.items()
            if key in {"code", "message", "details", "hint", "status"}
            and (isinstance(value, (str, int, float, bool)) or value is None)
        }
    return safe


def _safe_conversation_history_debug_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Keep conversation history diagnostics metadata-only."""
    allowed_keys = {
        "activeConversationId",
        "assistantMessageCount",
        "clearBeforeLoad",
        "component",
        "conversationId",
        "deletionMarkerCount",
        "displayMessageCount",
        "durationMs",
        "errorName",
        "latestMessageUpdatedAt",
        "latestQueuedAt",
        "messageCount",
        "pendingSyncCount",
        "previousActiveConversationId",
        "status",
        "userMessageCount",
        "requestId", "previousSearchMode", "searchMode", "useWebSearch",
        "uiSearchMode", "uiUseWebSearch", "useRag", "attachmentCount", "sourceCount", "clientTimestampMs",
    }
    safe: Dict[str, Any] = {}
    for key, value in context.items():
        if key not in allowed_keys:
            continue
        if key in {"searchMode", "uiSearchMode", "previousSearchMode"} and value not in ("always", "never", "auto"):
            continue
        if key in {"useWebSearch", "uiUseWebSearch", "useRag"} and not isinstance(value, bool):
            continue
        if key == "requestId" and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)):
            continue
        if key in {"attachmentCount", "sourceCount", "clientTimestampMs"} and (type(value) is not int or value < 0):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    return safe


@router.post("/api/v1/share/debug-log")
async def log_share_debug(req: ShareDebugLogRequest, current_user_id: str = Depends(get_current_user)):
    if not re.fullmatch(r"share\.[a-z0-9_.-]{1,96}", req.event):
        raise HTTPException(status_code=400, detail="Invalid share debug event")
    safe_context = _safe_share_debug_context(req.context)
    logger.info(
        "share.backend_debug user_id=%s event=%s context=%s",
        current_user_id,
        req.event,
        json.dumps(safe_context, ensure_ascii=False, sort_keys=True),
    )
    return {"status": "ok"}


@router.post("/api/v1/conversation-history/debug-log")
async def log_conversation_history_debug(
    req: ConversationHistoryDebugLogRequest,
    current_user_id: str | None = Depends(get_optional_current_user),
):
    if not re.fullmatch(r"chat_history_[a-z0-9_]{1,96}", req.event):
        raise HTTPException(status_code=400, detail="Invalid conversation history debug event")
    safe_context = _safe_conversation_history_debug_context(req.context)
    logger.info(
        "conversation_history.backend_debug user_id=%s event=%s context=%s",
        current_user_id or "anonymous",
        req.event,
        json.dumps(safe_context, ensure_ascii=False, sort_keys=True),
    )
    return {"status": "ok"}

@router.post("/api/v1/log_action")
async def log_action(req: ActionLogRequest, current_user_id: str = Depends(get_current_user)):
    """
    接收前端事件 (如點擊燈泡、UI 互動、語音打斷)
    """
    logger.info(
        "client_action_logged user_id=%s action_type=%s",
        current_user_id,
        req.action_type,
    )

    from services.memory.store.service import get_global_store
    store = get_global_store()
    if req.action_type == "compeer_cooldown_reset":
        from config import settings

        if not settings.enable_compeer_dev_controls:
            raise HTTPException(status_code=403, detail="ComPeer dev controls are disabled")
        import services.compeer.runtime as compeer

        deleted = await compeer.clear_cooldown(current_user_id)
        return {"status": "ok", "cooldown_deleted": deleted}

    if store:
        from services.memory.gate import apply_action_gate
        asyncio.create_task(apply_action_gate(store, current_user_id, req.action_type, req.context))

    if req.action_type == "scroll":
        # Pure UI telemetry belongs to behavior_signals only; it must not enter prompt memory.
        pass
    elif req.action_type == "compeer_rejected":
        import services.compeer.runtime as compeer
        target_user = current_user_id
        learner_state = await store.get_learner_state(target_user) if store else "default"
        await compeer.set_cooldown(target_user, state=learner_state)
        print(f"[ComPeer] User '{target_user}' rejected popup, entering cooldown.")
    else:
        # Other client actions are behavior signals unless a reflection pipeline promotes them.
        pass

    return {"status": "ok"}

@router.get("/api/v1/proactive-check")
async def proactive_check_endpoint(current_user_id: str = Depends(get_current_user)):
    user_id = current_user_id
    from services.memory.store.service import get_global_store
    store = get_global_store()
    if store:
        alert_content = await store.get_and_clear_pending_alert(user_id)
        if alert_content:
            print(f"[EDF-LOG] proactive-check endpoint returning alert: {alert_content}")
            return {"has_alert": True, "content": alert_content}
    return {"has_alert": False}
