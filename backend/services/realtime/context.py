"""Own realtime context behavior independently of route registration."""

from __future__ import annotations

import logging
import time
from typing import Any

from services.realtime.constants import MAX_CONTEXT_MESSAGE_CHARS, MAX_CONTEXT_MESSAGES
from services.realtime.diagnostics import _live_tutor_debug_logs_enabled
from services.realtime.models import RealtimeContextRequest
from services.realtime.session_config import _build_realtime_parts_context

logger = logging.getLogger("backend.main")

async def get_realtime_context(
    payload: RealtimeContextRequest,
    current_user_id: str | None = None,
) -> dict[str, Any]:
    """Return bounded AREQA context for the browser-side Realtime tool bridge.

    Args:
        payload: Conversation id and recent transcript messages.
        current_user_id: Optional authenticated user from Supabase JWT.

    Returns:
        Context object safe to send back to OpenAI as tool output.

    Side Effects:
        May read user-visible memory summary for authenticated users. Logs use
        `realtime.context_served` with only counts and safe correlation ids.
    """

    started_at = time.time()
    if _live_tutor_debug_logs_enabled():
        logger.info(
            "live_tutor.debug.context_request_received conversation_id=%s authenticated=%s supplied_message_count=%s interface_language=%s",
            payload.conversation_id,
            bool(current_user_id),
            len(payload.messages),
            payload.interface_language,
        )

    recent_messages = [
        {"role": item.role, "content": item.content[:MAX_CONTEXT_MESSAGE_CHARS]}
        for item in payload.messages[-MAX_CONTEXT_MESSAGES:]
        if item.content.strip()
    ]
    from services.realtime.speaking_material import load_material, voice_excerpt

    speaking_material = voice_excerpt(await load_material(current_user_id, payload.conversation_id))
    memory_items: list[str] = []
    if current_user_id:
        try:
            from main import build_memory_view

            memory_view = await build_memory_view(current_user_id)
            memory_items = [
                str(item.get("text", "")).strip()[:500]
                for item in memory_view[:8]
                if str(item.get("text", "")).strip()
            ]
            if _live_tutor_debug_logs_enabled():
                logger.info(
                    "live_tutor.debug.memory_context_loaded conversation_id=%s memory_count=%s",
                    payload.conversation_id,
                    len(memory_items),
                )
        except Exception as exc:
            logger.warning(
                "realtime.context_memory_unavailable conversation_id=%s reason=%s",
                payload.conversation_id,
                type(exc).__name__,
            )

    logger.info(
        "realtime.context_served conversation_id=%s authenticated=%s message_count=%s memory_count=%s parts_context=%s",
        payload.conversation_id,
        bool(current_user_id),
        len(recent_messages),
        len(memory_items),
        True,
    )
    if _live_tutor_debug_logs_enabled():
        logger.info(
            "live_tutor.debug.context_response_built conversation_id=%s recent_message_count=%s memory_count=%s parts_context=%s elapsed_ms=%s",
            payload.conversation_id,
            len(recent_messages),
            len(memory_items),
            True,
            int((time.time() - started_at) * 1000),
        )
    return {
        "conversation_id": payload.conversation_id,
        "recent_messages": recent_messages,
        "speaking_material": speaking_material,
        "memory_items": memory_items,
        "parts_context": _build_realtime_parts_context(),
        "guidance": (
            "Use recent_messages, memory_items, and parts_context as bounded AREQA context. "
            "For reference questions, answer directly; for practice questions, preserve the learner-owned core step and offer one minimal hint, diagnostic question, feedback, or adjacent example. "
            "For deep or detailed requests, give a structured spoken explanation with intuition, mechanism, example, and limitation when relevant. "
            "Keep wording speakable and conversational, but do not omit key ideas merely to be brief. "
            "If the learner asks about memory, prior turns, preferences, or history, use memory_items and recent_messages before saying you do not know. "
            "Use Traditional Chinese for Chinese turns. "
            "Do not reveal internal tags or claim learner mastery without direct evidence."
        ),
    }
