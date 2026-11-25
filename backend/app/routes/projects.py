"""Project memory API: rebuild the profile from project conversations or revise it on request."""

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from auth import get_current_user
from config import settings
from services.conversation.collaboration import bearer_token
from services.conversation.projects import (
    ProjectContext,
    ProjectUnavailable,
    generate_project_memory,
    is_project_id,
    load_project_context,
    load_project_transcript,
    save_project_memory,
)
from services.openrouter_clients import get_chat_client

router = APIRouter()
logger = logging.getLogger(__name__)


class ReviseMemoryRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=1000)


def _memory_view(context: ProjectContext) -> dict:
    return {
        "summary": context.memory_summary or None,
        "details": context.memory_details,
        "updated_at": context.memory_updated_at,
    }


async def _load_owned_project(request: Request, project_id: str) -> tuple[ProjectContext, str]:
    token = bearer_token(request.headers.get("authorization"))
    if not token or not is_project_id(project_id):
        raise HTTPException(status_code=400, detail="Invalid project")
    context = await load_project_context(project_id, token)
    if context.state == "unknown":
        raise HTTPException(status_code=503, detail="Project unavailable")
    if context.state != "loaded":
        raise HTTPException(status_code=404, detail="Project not found")
    return context, token


def _memory_client(request: Request) -> AsyncOpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Memory model unavailable")
    return get_chat_client(request.app, AsyncOpenAI, api_key)


@router.post("/api/v1/projects/{project_id}/memory/refresh")
async def refresh_project_memory(project_id: str, request: Request, current_user_id: str = Depends(get_current_user)):
    """Rebuild the memory profile from the project's newest conversations."""
    context, token = await _load_owned_project(request, project_id)
    started = time.perf_counter()
    try:
        transcript, conversation_count = await load_project_transcript(project_id, token)
    except ProjectUnavailable as error:
        logger.warning("project.memory_source_failed project_id=%s reason=%s", project_id, error)
        raise HTTPException(status_code=503, detail="Project unavailable") from None
    if not transcript:
        logger.info("project.memory_refresh_skipped project_id=%s reason=no_messages", project_id)
        return {"memory": _memory_view(context), "refreshed": False}

    try:
        summary, details = await generate_project_memory(
            _memory_client(request), settings.model_conversation_summary,
            project_name=context.name, transcript=transcript, previous=context,
        )
        saved = await save_project_memory(project_id, token, summary, details)
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("project.memory_refresh_failed project_id=%s error_type=%s", project_id, type(error).__name__)
        raise HTTPException(status_code=502, detail="Memory update failed") from None
    logger.info(
        "project.memory_refreshed project_id=%s conversations=%d transcript_chars=%d details=%d elapsed_ms=%d",
        project_id, conversation_count, len(transcript), len(details), (time.perf_counter() - started) * 1000,
    )
    return {"memory": _memory_view(saved), "refreshed": True}


@router.post("/api/v1/projects/{project_id}/memory/revise")
async def revise_project_memory(
    project_id: str, payload: ReviseMemoryRequest, request: Request,
    current_user_id: str = Depends(get_current_user),
):
    """Apply the learner's correction ("Tell AREQA what to change") to the current profile."""
    context, token = await _load_owned_project(request, project_id)
    started = time.perf_counter()
    try:
        summary, details = await generate_project_memory(
            _memory_client(request), settings.model_conversation_summary,
            project_name=context.name, transcript="", previous=context, instruction=payload.instruction,
        )
        saved = await save_project_memory(project_id, token, summary, details)
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("project.memory_revise_failed project_id=%s error_type=%s", project_id, type(error).__name__)
        raise HTTPException(status_code=502, detail="Memory update failed") from None
    logger.info(
        "project.memory_revised project_id=%s details=%d elapsed_ms=%d",
        project_id, len(details), (time.perf_counter() - started) * 1000,
    )
    return {"memory": _memory_view(saved)}
