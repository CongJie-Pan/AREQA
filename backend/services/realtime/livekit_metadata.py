"""Own realtime livekit metadata behavior independently of route registration."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid

from fastapi import HTTPException
from services.realtime.constants import (
    MAX_LIVEKIT_CONTEXT_MESSAGE_CHARS,
    MAX_LIVEKIT_CONTEXT_MESSAGES,
    MAX_LIVEKIT_CONTEXT_TOTAL_CHARS,
    MAX_LIVEKIT_MEMORY_ITEM_CHARS,
    MAX_LIVEKIT_MEMORY_ITEMS,
    MAX_LIVEKIT_TUTOR_PROMPT_CHARS,
)
from services.realtime.models import LiveKitAvatarSessionRequest
from services.realtime.session_config import _build_realtime_parts_context
from services.conversation.tutor_profile import (
    normalize_tutor_profile,
    render_tutor_profile_prompt,
)

logger = logging.getLogger("backend.main")

def _safe_livekit_fragment(value: str, *, fallback: str) -> str:
    """Return a short opaque fragment safe for LiveKit room or identity fields.

    Args:
        value: Untrusted caller-supplied correlation value.
        fallback: Prefix used when the input does not contain safe characters.

    Returns:
        A non-PII ASCII fragment. LiveKit records room names and identities in
        logs, so user-provided text is never copied directly.
    """

    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:32]
    if cleaned:
        return cleaned
    return f"{fallback}-{uuid.uuid4().hex[:12]}"


def _livekit_avatar_session_id() -> str:
    """Return a short opaque id for one LiveKit avatar call lifecycle.

    Returns:
        A random non-PII identifier safe for LiveKit room names and logs.

    Side Effects:
        None.

    Compatibility:
        The id is intentionally not derived from the learner or conversation so
        one browser reconnect cannot inherit stale tracks or agent state from a
        previous room using the same conversation.
    """

    return uuid.uuid4().hex[:16]


def _livekit_avatar_room_name(conversation_id: str, session_id: str | None = None) -> str:
    """Build an opaque room name for one Live Tutor avatar session.

    Args:
        conversation_id: Browser-supplied correlation id. It is hashed before
            it appears in LiveKit metadata.
        session_id: Per-call random id. Supplying it isolates reconnects and
            provider switches that occur inside the same AREQA conversation.

    Returns:
        A non-PII room name safe for LiveKit and logs.

    Side Effects:
        None.
    """

    conversation_digest = hashlib.sha256(str(conversation_id or uuid.uuid4().hex).encode("utf-8")).hexdigest()[:12]
    session_fragment = _safe_livekit_fragment(session_id or _livekit_avatar_session_id(), fallback="session")[:16]
    return f"areqa-live-{conversation_digest}-{session_fragment}"


def _livekit_participant_identity(current_user_id: str | None, conversation_id: str) -> str:
    """Build a non-PII LiveKit participant identity for one browser session."""

    source = current_user_id or uuid.uuid4().hex
    digest = hashlib.sha256(f"{source}:{conversation_id}".encode("utf-8")).hexdigest()[:16]
    return f"learner-{digest}"


async def _livekit_avatar_memory_items(current_user_id: str | None, conversation_id: str) -> list[str]:
    """Return bounded memory context for LiveKit agent dispatch metadata."""

    if not current_user_id:
        return []
    try:
        from main import build_memory_view

        memory_view = await build_memory_view(current_user_id)
        return [
            str(item.get("text", "")).strip()[:MAX_LIVEKIT_MEMORY_ITEM_CHARS]
            for item in memory_view[:MAX_LIVEKIT_MEMORY_ITEMS]
            if str(item.get("text", "")).strip()
        ]
    except Exception as exc:
        logger.warning(
            "livekit.avatar_memory_context_unavailable conversation_id=%s reason=%s",
            conversation_id,
            type(exc).__name__,
        )
        return []


def _livekit_avatar_agent_metadata(
    payload: LiveKitAvatarSessionRequest,
    *,
    session_id: str | None = None,
    memory_items: list[str] | None = None,
    participant_identity: str = "",
) -> str:
    """Return bounded dispatch metadata for the LiveKit avatar agent.

    Args:
        payload: Client request metadata.

    Returns:
        JSON metadata with bounded context and server-authored tutor rules.
        It contains no provider credentials and is never logged.
    """

    context_messages: list[dict[str, str]] = []
    remaining_chars = MAX_LIVEKIT_CONTEXT_TOTAL_CHARS
    for item in payload.messages[-MAX_LIVEKIT_CONTEXT_MESSAGES:]:
        content = item.content.strip()
        if not content or remaining_chars <= 0:
            continue
        bounded_content = content[: min(MAX_LIVEKIT_CONTEXT_MESSAGE_CHARS, remaining_chars)]
        context_messages.append({"role": item.role, "content": bounded_content})
        remaining_chars -= len(bounded_content)

    tutor_profile_prompt = render_tutor_profile_prompt(payload.tutor_profile)
    if len(tutor_profile_prompt) > MAX_LIVEKIT_TUTOR_PROMPT_CHARS:
        logger.warning(
            "livekit.avatar_tutor_profile_too_large tutor_profile=%s prompt_chars=%s limit=%s fallback=openai_realtime",
            normalize_tutor_profile(payload.tutor_profile),
            len(tutor_profile_prompt),
            MAX_LIVEKIT_TUTOR_PROMPT_CHARS,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LIVEKIT_TUTOR_PROFILE_TOO_LARGE",
                "message": "Avatar tutoring profile is temporarily unavailable.",
            },
        )

    return json.dumps(
        {
            "conversation_id": _safe_livekit_fragment(payload.conversation_id, fallback="conversation"),
            "session_id": _safe_livekit_fragment(session_id or _livekit_avatar_session_id(), fallback="session"),
            "participant_identity": participant_identity,
            "interface_language": payload.interface_language,
            "tutor_profile": normalize_tutor_profile(payload.tutor_profile),
            "tutor_profile_prompt": tutor_profile_prompt,
            "provider": "livekit_anam",
            "recent_messages": context_messages,
            "memory_items": [
                item.strip()[:MAX_LIVEKIT_MEMORY_ITEM_CHARS]
                for item in (memory_items or [])[:MAX_LIVEKIT_MEMORY_ITEMS]
                if item.strip()
            ],
            "parts_context": _build_realtime_parts_context(),
        },
        separators=(",", ":"),
    )
