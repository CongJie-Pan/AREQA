from datetime import datetime, timedelta, timezone

from backend.services.hot_memory_service import (
    HotMemoryKind,
    attach_typed_entry,
    build_hot_memory_entry,
    build_user_evidence_provenance,
    cold_export_entries,
)


def provenance() -> dict[str, str]:
    return build_user_evidence_provenance(
        message_id="message-1",
        conversation_id="conversation-1",
        timestamp=datetime.now(timezone.utc).isoformat(),
        raw_user_text="我偏好先看具體例子。",
    )


def test_only_complete_user_evidence_can_leave_hot_memory():
    hot_memory = {}
    entry = build_hot_memory_entry(
        "evidence-1",
        kind=HotMemoryKind.USER_EVIDENCE,
        source_role="user",
        cold_export_eligible=True,
        provenance=provenance(),
    )
    attach_typed_entry(hot_memory, "evidence-1", "compatibility value", entry)

    exported = cold_export_entries(hot_memory)

    assert len(exported) == 1
    assert exported[0][0] == "evidence-1"


def test_model_inference_and_legacy_values_fail_closed():
    hot_memory = {"legacy": "untyped value"}
    entry = build_hot_memory_entry(
        "model-state",
        kind=HotMemoryKind.MODEL_INFERENCE,
        source_role="assistant",
        cold_export_eligible=True,
        provenance=provenance(),
    )
    attach_typed_entry(hot_memory, "model-state", "inferred mastery", entry)

    assert cold_export_entries(hot_memory) == []


def test_incomplete_user_provenance_logs_missing_fields(caplog):
    build_hot_memory_entry(
        "incomplete-evidence",
        kind=HotMemoryKind.USER_EVIDENCE,
        source_role="user",
        cold_export_eligible=True,
        provenance={"raw_user_text": "我偏好先看例子。"},
    )

    assert "reason=incomplete_provenance" in caplog.text
    assert "evidence_quote" in caplog.text


def test_expired_user_evidence_is_not_exported():
    hot_memory = {}
    entry = build_hot_memory_entry(
        "expired-evidence",
        kind=HotMemoryKind.USER_EVIDENCE,
        source_role="user",
        expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        cold_export_eligible=True,
        provenance=provenance(),
    )
    attach_typed_entry(hot_memory, "expired-evidence", "old preference", entry)

    assert cold_export_entries(hot_memory) == []
