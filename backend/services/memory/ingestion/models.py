"""Data contracts and provenance builders for memory ingestion.

These types are re-exported from ``services.memory_ingestion_service`` for
compatibility with GUM integration, turn intake, compaction, and tests. They
represent exact user-authored evidence and sanitized ingestion outcomes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class MemoryEligibilityState(str, Enum):
    """Describe the server-owned outcome of one evidence ingestion."""

    REJECTED = "rejected"
    WORKING_CONTEXT_ONLY = "working_context_only"
    CANDIDATE = "candidate"
    PROMOTION_ELIGIBLE = "promotion_eligible"


@dataclass(frozen=True)
class UserEvidence:
    """Immutable provenance for one exact user-authored message."""

    user_id: str
    message_id: str
    conversation_id: str
    timestamp: str
    raw_message_text: str
    source_role: str = "user"


@dataclass(frozen=True)
class MemoryIngestionResult:
    """Typed policy result returned without exposing model reasoning."""

    state: MemoryEligibilityState
    reason_code: str
    category: str
    candidate_id: str | None = None
    expires_at: str | None = None
    promoted: bool = False


def build_user_evidence(
    user_id: str,
    conversation_id: str,
    raw_message_text: str,
    *,
    message_id: str = "",
    timestamp: str = "",
) -> UserEvidence:
    """Build stable provenance when the transport lacks a message identifier.

    The digest is deterministic for one conversation/message pair, preventing
    background reprocessing from counting the same message twice.
    """

    text = (raw_message_text or "").strip()
    stable_id = message_id or hashlib.sha256(
        f"{user_id}|{conversation_id}|{text}".encode("utf-8")
    ).hexdigest()[:24]
    return UserEvidence(
        user_id=user_id,
        message_id=stable_id,
        conversation_id=conversation_id,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        raw_message_text=text,
        source_role="user",
    )
