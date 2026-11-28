"""Prompt constants and runtime feature schemas for the backend app."""

from __future__ import annotations

from pydantic import BaseModel

# The Teaching Layer owns the base prompts; re-exported for legacy importers.
from services.teaching.prompts import (
    BASE_PERSONA as BASE_PERSONA,
    EVIDENCE_MODE_OVERLAYS as EVIDENCE_MODE_OVERLAYS,
    LEARNING_TECHNIQUE_OVERLAYS as LEARNING_TECHNIQUE_OVERLAYS,
    RESPONSE_POLICY_OVERLAYS as RESPONSE_POLICY_OVERLAYS,
    SYSTEM_PROMPT_FORCE_THINK as SYSTEM_PROMPT_FORCE_THINK,
    SYSTEM_PROMPT_NORMAL as SYSTEM_PROMPT_NORMAL,
    SYSTEM_PROMPT_WITH_RAG as SYSTEM_PROMPT_WITH_RAG,
    SYSTEM_PROMPT_WITH_RAG_THINK as SYSTEM_PROMPT_WITH_RAG_THINK,
)


class RuntimeFeatureResponse(BaseModel):
    """Browser-safe product feature flags exposed at runtime.

    Attributes:
        conversationHistoryDebugLogs: Whether the browser should emit safe
            diagnostics for conversation history loading and switching.

    Compatibility:
        Field names intentionally use the existing frontend camelCase shape so
        older clients do not need response transformation logic.
    """

    conversationHistoryDebugLogs: bool
