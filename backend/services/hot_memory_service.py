"""Own typed hot-memory metadata and enforce prompt/export boundaries.

Hot memory is operational working state.  The compatibility layer keeps legacy
top-level values readable while storing policy metadata under a reserved key;
this prevents a migration from silently treating old values as user evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Mapping


logger = logging.getLogger(__name__)

TYPED_ENTRIES_KEY = "_typed_entries"


class HotMemoryKind(str, Enum):
    """Classify the purpose and permitted lifecycle of a hot-memory value."""

    USER_EVIDENCE = "user_evidence"
    WORKING_CONTEXT = "working_context"
    MODEL_INFERENCE = "model_inference"
    BEHAVIOR_SIGNAL = "behavior_signal"
    OPERATIONAL_STATE = "operational_state"


@dataclass(frozen=True)
class HotMemoryEntry:
    """Policy metadata for one compatibility-preserved hot-memory value.

    Attributes:
        key: Top-level hot-memory key holding the compatibility value.
        kind: Purpose of the value; only user evidence can be export eligible.
        source_role: Immutable origin role such as ``user`` or ``system``.
        created_at: UTC ISO timestamp for lifecycle evaluation.
        expires_at: Optional UTC ISO expiry timestamp.
        confidence: Advisory confidence; it never authorizes export.
        prompt_safe: Whether the value may be considered for prompt context.
        cold_export_eligible: Whether ingestion may inspect this entry.
        provenance: Immutable user evidence identifiers and original quote.
    """

    key: str
    kind: str
    source_role: str
    created_at: str
    expires_at: str | None
    confidence: float
    prompt_safe: bool
    cold_export_eligible: bool
    provenance: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


_OPERATIONAL_KEYS = {
    "trigger_proactive",
    "avatar_summon_pending",
    "active_avatar",
    "last_compeer_message",
    "user_cooldown_until",
    "proactive_schedule",
    "learner_state_version",
    "learner_state_evaluated_at",
}
_WORKING_KEYS = {"current_learner_state", "current_strategy"}
_REQUIRED_PROVENANCE = {
    "message_id",
    "conversation_id",
    "timestamp",
    "source_role",
    "raw_user_text",
    "evidence_quote",
}


def build_user_evidence_provenance(
    *,
    message_id: str,
    conversation_id: str,
    timestamp: str,
    raw_user_text: str,
    evidence_quote: str | None = None,
) -> dict[str, str]:
    """Build complete provenance from exact user-authored evidence.

    The exact message is a valid default quote. Callers may provide a narrower
    quote when only one clause supports the candidate proposition.
    """

    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "timestamp": timestamp,
        "source_role": "user",
        "raw_user_text": raw_user_text,
        "evidence_quote": (
            evidence_quote
            if evidence_quote and evidence_quote.strip()
            else raw_user_text
        ),
    }


def infer_hot_memory_kind(key: str) -> HotMemoryKind:
    """Infer a safe non-exportable default kind for compatibility writers.

    Unknown keys are working context rather than user evidence because a key
    name cannot prove that a user authored the underlying value.
    """

    if key.startswith("obs_"):
        return HotMemoryKind.BEHAVIOR_SIGNAL
    if key.startswith("pending_alert_") or key.startswith("chat_active_avatar:"):
        return HotMemoryKind.OPERATIONAL_STATE
    if key in _OPERATIONAL_KEYS:
        return HotMemoryKind.OPERATIONAL_STATE
    if key in _WORKING_KEYS:
        return HotMemoryKind.WORKING_CONTEXT
    return HotMemoryKind.WORKING_CONTEXT


def build_hot_memory_entry(
    key: str,
    *,
    kind: HotMemoryKind | str | None = None,
    source_role: str = "system",
    created_at: str | None = None,
    expires_at: str | None = None,
    confidence: float = 1.0,
    prompt_safe: bool | None = None,
    cold_export_eligible: bool = False,
    provenance: Mapping[str, Any] | None = None,
) -> HotMemoryEntry:
    """Build policy metadata while enforcing the user-evidence export invariant."""

    resolved_kind = HotMemoryKind(kind or infer_hot_memory_kind(key))
    resolved_provenance = dict(provenance) if provenance else None
    exportable = bool(cold_export_eligible)

    # Export is fail-closed because a generic source label cannot establish
    # user authorship or independent conversation evidence.
    if resolved_kind is not HotMemoryKind.USER_EVIDENCE:
        exportable = False
    elif source_role != "user":
        logger.warning(
            "hot_memory.export_blocked key=%s kind=%s reason=invalid_source_role source_role=%s",
            key,
            resolved_kind.value,
            source_role,
        )
        exportable = False
    elif not has_complete_user_provenance(resolved_provenance):
        missing_fields = [
            field
            for field in sorted(_REQUIRED_PROVENANCE)
            if not str((resolved_provenance or {}).get(field, "")).strip()
        ]
        logger.warning(
            "hot_memory.export_blocked key=%s kind=%s reason=incomplete_provenance missing_fields=%s",
            key,
            resolved_kind.value,
            missing_fields,
        )
        exportable = False

    if prompt_safe is None:
        prompt_safe = resolved_kind in {
            HotMemoryKind.USER_EVIDENCE,
            HotMemoryKind.WORKING_CONTEXT,
        }

    return HotMemoryEntry(
        key=key,
        kind=resolved_kind.value,
        source_role=source_role,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at,
        confidence=float(confidence),
        prompt_safe=bool(prompt_safe),
        cold_export_eligible=exportable,
        provenance=resolved_provenance,
    )


def has_complete_user_provenance(provenance: Mapping[str, Any] | None) -> bool:
    """Return whether immutable provenance is complete and user-originated."""

    if not provenance:
        return False
    if any(not str(provenance.get(field, "")).strip() for field in _REQUIRED_PROVENANCE):
        return False
    return str(provenance.get("source_role", "")).strip() == "user"


def attach_typed_entry(
    hot_memory: dict[str, Any],
    key: str,
    value: Any,
    entry: HotMemoryEntry,
) -> None:
    """Write a compatibility value and its policy metadata atomically in memory."""

    hot_memory[key] = value
    typed_entries = hot_memory.get(TYPED_ENTRIES_KEY)
    if not isinstance(typed_entries, dict):
        typed_entries = {}
        hot_memory[TYPED_ENTRIES_KEY] = typed_entries
    typed_entries[key] = entry.to_dict()
    # logger.info(
    logger.debug(
        "hot_memory.created key=%s kind=%s export_eligible=%s",
        key,
        entry.kind,
        entry.cold_export_eligible,
    )


def remove_typed_entry(hot_memory: dict[str, Any], key: str) -> None:
    """Remove a value and its metadata without affecting unrelated entries."""

    hot_memory.pop(key, None)
    typed_entries = hot_memory.get(TYPED_ENTRIES_KEY)
    if isinstance(typed_entries, dict):
        typed_entries.pop(key, None)


def get_typed_entries(hot_memory: Mapping[str, Any]) -> dict[str, HotMemoryEntry]:
    """Parse typed entries, ignoring malformed metadata and all legacy values."""

    raw_entries = hot_memory.get(TYPED_ENTRIES_KEY)
    if not isinstance(raw_entries, dict):
        return {}
    result: dict[str, HotMemoryEntry] = {}
    for key, raw in raw_entries.items():
        if not isinstance(raw, dict):
            continue
        try:
            result[key] = HotMemoryEntry(**raw)
        except (TypeError, ValueError):
            logger.warning("hot_memory.metadata_invalid key=%s", key)
    return result


def is_expired(entry: HotMemoryEntry, *, now: datetime | None = None) -> bool:
    """Return whether an entry has passed its explicit UTC expiry."""

    if not entry.expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(entry.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    current = now or datetime.now(timezone.utc)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry <= current


def cold_export_entries(hot_memory: Mapping[str, Any]) -> list[tuple[str, Any, HotMemoryEntry]]:
    """Return only non-expired, fully provenanced user-evidence entries."""

    result: list[tuple[str, Any, HotMemoryEntry]] = []
    for key, entry in get_typed_entries(hot_memory).items():
        if is_expired(entry):
            logger.info("hot_memory.expired key=%s kind=%s", key, entry.kind)
            continue
        if (
            entry.kind != HotMemoryKind.USER_EVIDENCE.value
            or not entry.cold_export_eligible
            or not has_complete_user_provenance(entry.provenance)
        ):
            logger.warning(
                "hot_memory.export_blocked key=%s kind=%s reason=policy",
                key,
                entry.kind,
            )
            continue
        logger.info("hot_memory.export_eligible key=%s kind=%s", key, entry.kind)
        result.append((key, hot_memory.get(key), entry))
    return result
