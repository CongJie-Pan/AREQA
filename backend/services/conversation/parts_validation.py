"""Validate and normalize untrusted PARTS fields and recent context."""

from __future__ import annotations

import re
from typing import Any

from services.conversation.parts_models import PartsContext
from services.query_policy.models import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
)

_CONFIDENCE_VALUES = {"low", "medium", "high"}
_MAX_FIELD_CHARS = 80
_MAX_THEME_CHARS = 56
_MAX_INSTRUCTION_CHARS = 360
_MAX_MISSING_FIELDS = 5
_MAX_RECENT_CONVERSATION_CONTEXT_CHARS = 3600


def clean_recent_conversation_context(value: Any) -> str:
    """Strip citation noise from recent conversation text for rewrite context.

        Args:
            value: A formatted recent conversation string. The orchestration
                service owns selecting the message window and labeling roles.

        Returns:
            A bounded string that preserves role labels, headings, numbered
            lists, and bold subheadings while removing citation markers and
            source-list sections.
        """

    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    citation_heading_pattern = (
        r"(?:^|\n)\s*(?:#{1,6}\s*)?"
        r"(?:文獻來源|參考文獻|資料來源|References|Sources)\b"
        r".*?(?=\n\n(?:User|Assistant):|\Z)"
    )
    text = re.sub(citation_heading_pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"【文獻\s*\d+(?:\s*[,，、]\s*\d+)*】", "", text)
    text = re.sub(r"\[(?:文獻\s*)?\d+(?:\s*[,，]\s*\d+)*\]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= _MAX_RECENT_CONVERSATION_CONTEXT_CHARS:
        return text

    head_chars = _MAX_RECENT_CONVERSATION_CONTEXT_CHARS // 2
    tail_chars = _MAX_RECENT_CONVERSATION_CONTEXT_CHARS - head_chars
    return f"{text[:head_chars]} ... {text[-tail_chars:]}"


def _context_from_payload(
    payload: dict[str, Any],
    fallback: PartsContext,
    user_message: str,
) -> PartsContext:
    """Validate and sanitize untrusted rewrite output."""

    confidence = str(payload.get("confidence") or fallback.confidence).strip().lower()
    if confidence not in _CONFIDENCE_VALUES:
        confidence = fallback.confidence
    missing_fields = payload.get("missing_fields")
    safe_missing_fields: tuple[str, ...] = ()
    if isinstance(missing_fields, list):
        values = []
        for item in missing_fields[:_MAX_MISSING_FIELDS]:
            cleaned = re.sub(r"[^a-zA-Z0-9_:-]", "", str(item))[:40]
            if cleaned:
                values.append(cleaned)
        safe_missing_fields = tuple(values)

    theme = _clean_field(payload.get("theme"), fallback.theme, _MAX_THEME_CHARS)
    if _looks_like_raw_user_message(theme, user_message):
        theme = fallback.theme
    persona = _clean_field(payload.get("persona"), fallback.persona)
    act = _clean_field(payload.get("act"), fallback.act)
    recipient = _clean_field(payload.get("recipient"), fallback.recipient)
    structure = _clean_field(payload.get("structure"), fallback.structure)
    composed_instruction = _clean_field(
        payload.get("composed_instruction"),
        "",
        _MAX_INSTRUCTION_CHARS,
    )
    if not composed_instruction:
        composed_instruction = _compose_instruction(
            persona=persona,
            act=act,
            recipient=recipient,
            theme=theme,
            structure=structure,
        )

    return PartsContext(
        persona=persona,
        act=act,
        recipient=recipient,
        theme=theme,
        structure=structure,
        composed_instruction=composed_instruction,
        confidence=confidence,
        missing_fields=safe_missing_fields or fallback.missing_fields,
    )


def _clean_field(value: Any, fallback: str, max_chars: int = _MAX_FIELD_CHARS) -> str:
    """Collapse untrusted text into one short prompt field."""

    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if not cleaned:
        return fallback
    return cleaned[:max_chars]


def _looks_like_raw_user_message(theme: str, user_message: str) -> bool:
    """Return whether a theme appears to copy too much of the raw request."""

    normalized_theme = re.sub(r"\s+", "", theme)
    normalized_user = re.sub(r"\s+", "", user_message)
    if not normalized_theme or not normalized_user:
        return False
    if normalized_theme == normalized_user:
        return True
    return len(normalized_theme) > 40 and normalized_theme in normalized_user


def _route_name(turn_plan: Any) -> str:
    """Return a safe route name without depending on concrete plan classes."""

    route = getattr(turn_plan, "route", None)
    value = getattr(route, "value", route)
    return str(value or "UNKNOWN")


def _structure_for_policy(policy: ResponsePolicy) -> str:
    """Map current EDF structure and follow-up policy into compact wording."""

    learning_mode = getattr(getattr(policy, "learning_mode", None), "value", "")
    if learning_mode == "PRACTICE":
        return "短回應 + 一個最小提示或診斷問題"
    if policy.answer_depth == AnswerDepth.DIRECT or policy.followup_mode == FollowupMode.NONE:
        return "短回答 + 必要理由，不加引導問題"
    if policy.structure == ResponseStructure.SHORT:
        return "短回答 + 必要補充"
    if policy.structure == ResponseStructure.NOTE_DRAFT:
        return "可保存的筆記段落或列點"
    if policy.structure == ResponseStructure.ARGUMENT:
        return "核心判斷 + 理由 + 取捨"
    return "分步解釋 + 最多一個診斷性追問"


def _compose_instruction(
    *,
    persona: str,
    act: str,
    recipient: str,
    theme: str,
    structure: str,
) -> str:
    """Compose a natural prompt instruction from PARTS fields."""

    return (
        f"你現在的角色是「{persona}」。請為「{recipient}」{act}，"
        f"本回合主題聚焦於「{theme}」。請使用「{structure}」的方式回答。"
    )
