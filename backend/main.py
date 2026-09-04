import sys

import asyncio
import json
import re
from typing import List, Dict, Any, Literal, Optional

from fastapi import FastAPI, Request, WebSocket, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from auth import get_current_user, get_optional_current_user
from openai import AsyncOpenAI
import opencc
import os
import time
import uuid
from datetime import datetime, timezone

try:
    from app.bootstrap import configure_logging, create_app, load_environment
    from app import runtime_state as _runtime_state
    from app.prompts import (
        BASE_PERSONA,
        RESPONSE_POLICY_OVERLAYS,
        RuntimeFeatureResponse,
        SYSTEM_PROMPT_FORCE_THINK,
        SYSTEM_PROMPT_NORMAL,
        SYSTEM_PROMPT_WITH_RAG,
        SYSTEM_PROMPT_WITH_RAG_THINK,
    )
except ModuleNotFoundError:
    from backend.app.bootstrap import configure_logging, create_app, load_environment
    from backend.app import runtime_state as _runtime_state
    from backend.app.prompts import (
        BASE_PERSONA,
        RESPONSE_POLICY_OVERLAYS,
        RuntimeFeatureResponse,
        SYSTEM_PROMPT_FORCE_THINK,
        SYSTEM_PROMPT_NORMAL,
        SYSTEM_PROMPT_WITH_RAG,
        SYSTEM_PROMPT_WITH_RAG_THINK,
    )

logger = configure_logging()
PROJECT_ROOT = _runtime_state.PROJECT_ROOT
load_environment(PROJECT_ROOT)

HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_ENDPOINT_URL = os.environ.get("HF_ENDPOINT_URL", "")
HF_REPO_ID = os.environ.get("HF_REPO_ID", "/repository")
_converter = opencc.OpenCC('s2twp')
_resolved_model_name = _runtime_state._resolved_model_name
_thread_pool = _runtime_state._thread_pool
rag_cache = _runtime_state.rag_cache
rag_service = _runtime_state.rag_service


def _track_background_task(name: str, task: asyncio.Task) -> asyncio.Task:
    """Attach terminal observability to a FastAPI background task.

    Startup creates several infinite workers with `asyncio.create_task()`. If a
    worker fails before its own first log line, the task can otherwise disappear
    without an actionable event. This callback keeps the logs sufficient to
    distinguish "worker never started" from "worker started and later failed".
    """

    logger.info("background.worker_task_started name=%s", name)

    def _log_task_done(done_task: asyncio.Task) -> None:
        if done_task.cancelled():
            logger.info("background.worker_task_cancelled name=%s", name)
            return
        exc = done_task.exception()
        if exc is not None:
            logger.error(
                "background.worker_task_failed name=%s reason=%s",
                name,
                type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            return
        logger.warning("background.worker_task_stopped name=%s", name)

    task.add_done_callback(_log_task_done)
    return task


def get_query_fingerprint(query: str) -> str:
    """Return the legacy RAG cache fingerprint for a query string."""

    return _runtime_state.get_query_fingerprint(query)


src_python_dir = PROJECT_ROOT / "src" / "main" / "python"
if str(src_python_dir) not in sys.path:
    sys.path.insert(0, str(src_python_dir))

from services.router_service import RouterService
from services.suggestion_service import SuggestionService

router_service = RouterService()
suggestion_service = SuggestionService()


def _env_flag(name: str, default: str = "false") -> bool:
    """Read a boolean environment flag using the backend truthy set."""

    return _runtime_state._env_flag(name, default)


def init_rag_service():
    """Initialize and mirror the internal RAG singleton for legacy callers."""

    global rag_service
    if rag_service is not None:
        _runtime_state.rag_service = rag_service
        return rag_service
    _runtime_state.rag_service = None
    rag_service = _runtime_state.init_rag_service()
    return rag_service


app = create_app()

try:
    from app.routes.memory import (
        router as memory_router,
        DeleteBatchRequest,
        EditMemoryRequest,
        batch_delete_memory_endpoint,
        build_memory_view,
        clear_memory_endpoint,
        clear_working_memory_endpoint,
        confirm_candidate_memory_endpoint,
        delete_memory_endpoint,
        edit_memory_endpoint,
        fetch_memory,
        flush_memory_endpoint,
        get_all_memory,
        get_memory_summary,
        memory_debug_endpoint,
        push_observation,
        reject_candidate_memory_endpoint,
        _delete_explicit_profile_memory,
        _find_candidate_memory,
        _find_profile_memory,
        _get_candidate_by_memory_id,
        _memory_source_id,
        _update_explicit_profile_memory,
    )
    from app.routes.mailbox import (
        router as mailbox_router,
        SendMailRequest,
        fetch_mailbox,
        read_mail_endpoint,
        send_mail_endpoint,
        _ensure_mailbox_feature_enabled,
        _mailbox_reply_task_id,
    )
except ModuleNotFoundError:
    from backend.app.routes.memory import (
        router as memory_router,
        DeleteBatchRequest,
        EditMemoryRequest,
        batch_delete_memory_endpoint,
        build_memory_view,
        clear_memory_endpoint,
        clear_working_memory_endpoint,
        confirm_candidate_memory_endpoint,
        delete_memory_endpoint,
        edit_memory_endpoint,
        fetch_memory,
        flush_memory_endpoint,
        get_all_memory,
        get_memory_summary,
        memory_debug_endpoint,
        push_observation,
        reject_candidate_memory_endpoint,
        _delete_explicit_profile_memory,
        _find_candidate_memory,
        _find_profile_memory,
        _get_candidate_by_memory_id,
        _memory_source_id,
        _update_explicit_profile_memory,
    )
    from backend.app.routes.mailbox import (
        router as mailbox_router,
        SendMailRequest,
        fetch_mailbox,
        read_mail_endpoint,
        send_mail_endpoint,
        _ensure_mailbox_feature_enabled,
        _mailbox_reply_task_id,
    )
from mailbox_store import get_mailbox_store

app.include_router(memory_router)
app.include_router(mailbox_router)

try:
    from app.routes.diagnostics import (
        router as diagnostics_router,
        ActionLogRequest,
        MemoryQueryRequest,
        ShareDebugLogRequest,
        classify_dialogue_policy,
        log_action,
        log_share_debug,
        parse_and_decompose_query,
        proactive_check_endpoint,
        reorder_for_attention,
        retrieve_endpoint,
        _safe_share_debug_context,
    )
    from app.routes.notifications import (
        router as notifications_router,
        generate_ws_ticket,
        ws_manager,
        ws_notifications,
    )
    from app.routes.stream import (
        router as stream_router,
        ChatRequest,
        parse_stream_request,
        stream_endpoint,
        _parse_bool,
    )
    from app.routes.title import (
        router as title_router,
        TitleRequest,
        build_title_messages,
        build_title_system_prompt,
        first_user_message_content,
        generate_title_endpoint,
        normalize_generated_title,
    )
except ModuleNotFoundError:
    from backend.app.routes.diagnostics import (
        router as diagnostics_router,
        ActionLogRequest,
        MemoryQueryRequest,
        ShareDebugLogRequest,
        classify_dialogue_policy,
        log_action,
        log_share_debug,
        parse_and_decompose_query,
        proactive_check_endpoint,
        reorder_for_attention,
        retrieve_endpoint,
        _safe_share_debug_context,
    )
    from backend.app.routes.notifications import (
        router as notifications_router,
        generate_ws_ticket,
        ws_manager,
        ws_notifications,
    )
    from backend.app.routes.stream import (
        router as stream_router,
        ChatRequest,
        parse_stream_request,
        stream_endpoint,
        _parse_bool,
    )
    from backend.app.routes.title import (
        router as title_router,
        TitleRequest,
        build_title_messages,
        build_title_system_prompt,
        first_user_message_content,
        generate_title_endpoint,
        normalize_generated_title,
    )

app.include_router(diagnostics_router)
app.include_router(notifications_router)
app.include_router(stream_router)
app.include_router(title_router)


@app.get("/api/v1/features", response_model=RuntimeFeatureResponse)
async def get_runtime_features() -> RuntimeFeatureResponse:
    """Return browser-safe runtime feature flags from backend settings.

    Returns:
        RuntimeFeatureResponse: Public feature state for browser-visible
            mailbox and ComPeer surfaces.

    Side Effects:
        Emits `features.runtime_served` with safe boolean metadata only. The log
        contains no user identifiers, mailbox content, prompts, credentials, or
        tokens because this endpoint is public and not user-scoped.
    """

    from config import settings

    mailbox_enabled = bool(settings.enable_mailbox_feature)
    compeer_enabled = bool(settings.enable_compeer_feature)
    compeer_telemetry_enabled = (
        compeer_enabled and bool(settings.enable_compeer_telemetry)
    )
    logger.info(
        "features.runtime_served mailbox=%s compeer=%s compeer_telemetry=%s",
        mailbox_enabled,
        compeer_enabled,
        compeer_telemetry_enabled,
    )
    return RuntimeFeatureResponse(
        mailbox=mailbox_enabled,
        compeer=compeer_enabled,
        compeerTelemetry=compeer_telemetry_enabled,
    )

MAX_CHAT_MULTIPART_BYTES = 30 * 1024 * 1024

import sqlite3
import sqlalchemy.exc
from fastapi.responses import JSONResponse
from fastapi import Request

@app.middleware("http")
async def chat_attachment_size_limit_middleware(request: Request, call_next):
    """Reject oversized attachment requests before multipart parsing."""
    if request.url.path == "/api/v1/stream":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_CHAT_MULTIPART_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": {
                                "code": "ATTACHMENT_TOTAL_SIZE_EXCEEDED",
                                "message": "附件請求大小超過允許上限。",
                            }
                        },
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
    return await call_next(request)

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
    from job_store import init_agent_job_store
    from redis_client import log_redis_open_status
    
    # Init store
    store = init_global_store(budget_limit=1000000)
    # await store.clear_all_pending_alerts("default_user") # Skipped for multi-tenant
    print("Memory Store initialized successfully.")
    await log_redis_open_status()
    
    init_mailbox_store()
    print("Mailbox Store initialized successfully.")
    init_agent_job_store()
    print("Agent Job Store initialized successfully.")
    
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
    from job_store import agent_job_worker
    
    app.state.proactive_task = _track_background_task(
        "proactive_scheduler_loop",
        asyncio.create_task(proactive_scheduler_loop()),
    )
    app.state.daily_task = _track_background_task(
        "daily_scheduler_loop",
        asyncio.create_task(daily_scheduler_loop()),
    )
    app.state.delayed_mail_worker = _track_background_task(
        "delayed_mail_worker",
        asyncio.create_task(delayed_mail_worker()),
    )
    app.state.agent_job_worker = _track_background_task(
        "agent_job_worker",
        asyncio.create_task(agent_job_worker()),
    )
    from gum_integration import run_reflection_loop
    app.state.reflection_task = _track_background_task(
        "reflection_loop",
        asyncio.create_task(run_reflection_loop()),
    )

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
    if hasattr(app.state, 'reflection_task'):
        app.state.reflection_task.cancel()
    if hasattr(app.state, 'agent_job_worker'):
        app.state.agent_job_worker.cancel()

_local_summary_cache = {}
