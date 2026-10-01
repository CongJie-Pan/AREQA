"""Build provider options and tool schemas without starting a stream."""

from __future__ import annotations

import re
from typing import Any

from config import settings
from services.conversation.image_generation import IMAGE_TOOL
from services.conversation.language import resolve_answer_language

_OPENROUTER_SESSION_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")


def build_stream_request(*, force_think: bool, repetition_penalty: float,
                         conversation_id: str, messages: list[dict[str, Any]],
                         interface_language: str, last_user_msg: str):
    """Return the model, provider options, tool schemas and PDF-presence flag.

    Args:
        force_think: Select the reasoning model and reasoning budget.
        repetition_penalty: Caller-supplied generation control.
        conversation_id: Input for a bounded provider session identifier.
        messages: Provider-ready messages, inspected only for PDF parts.
        interface_language: Fallback language for generated image labels.
        last_user_msg: User text used for language resolution, never logged.

    Returns:
        A tuple of model name, extra request body, tool definitions and PDF flag.
    """
    target_model = settings.model_main_thinking if force_think else settings.model_main_instruct
    extra_body = {"repetition_penalty": repetition_penalty}
    session_id = _openrouter_session_id(conversation_id)
    if settings.enable_openrouter_main_session_id and session_id:
        extra_body["session_id"] = session_id
    if settings.enable_openrouter_main_latency_routing:
        extra_body["provider"] = {
            "preferred_max_latency": {
                "p90": settings.openrouter_main_preferred_latency_p90_seconds,
            }
        }
    has_pdf = any(
        isinstance(message.get("content"), list)
        and any(
            part.get("type") == "file"
            for part in message["content"]
            if isinstance(part, dict)
        )
        for message in messages
    )
    if has_pdf:
        extra_body["plugins"] = [{"id": "file-parser", "pdf": {"engine": "native"}}]
    if force_think:
        extra_body["reasoning"] = {"enabled": True, "max_tokens": 512}

    image_tool = {
        **IMAGE_TOOL,
        "function": {
            **IMAGE_TOOL["function"],
            "description": IMAGE_TOOL["function"]["description"] + (
                " For this turn, preserve the full source content when compiling the drawing specification. "
                "Image label language: " + resolve_answer_language(interface_language, last_user_msg, prefer_query_language=True) + "."
            ),
        },
    }
    tools = [image_tool, {
        "type": "function",
        "function": {
            "name": "send_epistolary_letter",
            "description": "Schedule a requested avatar letter after answering the user in chat.",
            "parameters": {
                "type": "object",
                "properties": {"avatar_name": {"type": "string"}},
                "required": ["avatar_name"],
            },
        },
    }]
    return target_model, extra_body, tools, has_pdf


def _openrouter_session_id(conversation_id: str) -> str:
    """Return a stable OpenRouter session id without exposing raw user content.

    Args:
        conversation_id: Conversation-scoped correlation identifier. This value
            is already used in safe operational logs and should not contain raw
            user text.

    Returns:
        A provider-safe session id suitable for OpenRouter sticky routing. Empty
        or malformed inputs fall back to an empty string so callers can skip the
        optional optimization without failing the stream.
    """

    normalized = _OPENROUTER_SESSION_ID_PATTERN.sub("_", str(conversation_id or "").strip())
    return normalized[:128]
