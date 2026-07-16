from datetime import datetime, timezone
import logging
from unittest.mock import AsyncMock

import pytest

from backend.services.memory_ingestion_service import (
    MemoryEligibilityState,
    MemoryIngestionService,
    UserEvidence,
    create_memory_ingestion_service,
)
from backend.services.memory_semantic_analyzer import SemanticAnalysisResult


def evidence(text: str, *, conversation_id: str = "conv-a", message_id: str = "msg-a") -> UserEvidence:
    return UserEvidence(
        user_id="user-a",
        message_id=message_id,
        conversation_id=conversation_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        raw_message_text=text,
        source_role="user",
    )


@pytest.mark.asyncio
async def test_question_never_reaches_candidate_storage():
    store = AsyncMock()
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(evidence("我偏好什麼學習方法？"))

    assert result.state is MemoryEligibilityState.WORKING_CONTEXT_ONLY
    assert result.reason_code == "interrogative_not_memory_evidence"
    store.append_cold_candidate.assert_not_awaited()
    store.perform_memory_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_sensitive_explicit_request_is_not_durable():
    store = AsyncMock()
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(evidence("請記住我最近很焦慮。"))

    assert result.state is MemoryEligibilityState.REJECTED
    assert result.reason_code == "sensitive_content_not_durable"
    store.append_cold_candidate.assert_not_awaited()
    store.perform_memory_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_passive_preference_has_ninety_day_candidate_lifecycle():
    store = AsyncMock()
    store.get_cold_candidates.return_value = []
    store.append_cold_candidate.return_value = {"hash": "candidate-a"}
    store.promote_cold_candidate.return_value = None
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(evidence("我偏好用具體例子理解抽象概念。"))

    assert result.state is MemoryEligibilityState.CANDIDATE
    assert result.expires_at is not None
    kwargs = store.append_cold_candidate.await_args.kwargs
    assert kwargs["category"] == "passive_preference"
    assert kwargs["evidence"]["message_id"] == "msg-a"
    assert kwargs["evidence"]["source_role"] == "user"


@pytest.mark.asyncio
async def test_shadow_semantic_match_cannot_merge_candidates():
    store = AsyncMock()
    store.get_cold_candidates.return_value = [{
        "user_id": "user-a",
        "hash": "existing",
        "category": "passive_preference",
        "status": "candidate",
        "requires_confirmation": False,
        "canonical_key": "concrete_examples",
        "normalized_text": "first",
    }]
    store.append_cold_candidate.return_value = {"hash": "new"}
    store.promote_cold_candidate.return_value = None
    analyzer = AsyncMock()
    analyzer.analyze.return_value = SemanticAnalysisResult(
        canonical_key="concrete_examples",
        relation="match_existing",
        matched_candidate_id="existing",
        confidence=0.98,
        reason_code="same_preference",
    )
    service = MemoryIngestionService(
        store,
        semantic_analyzer=analyzer,
        semantic_enabled=True,
        semantic_shadow_mode=True,
    )

    await service.ingest_user_evidence(evidence("我偏好用具體例子理解抽象概念。"))

    assert store.append_cold_candidate.await_args.kwargs["candidate_hash_override"] == ""


@pytest.mark.asyncio
async def test_active_semantic_match_only_selects_valid_same_user_candidate():
    store = AsyncMock()
    store.get_cold_candidates.return_value = [{
        "user_id": "user-a",
        "hash": "existing",
        "category": "passive_preference",
        "status": "candidate",
        "requires_confirmation": False,
        "canonical_key": "concrete_examples",
        "normalized_text": "first",
    }]
    store.append_cold_candidate.return_value = {"hash": "existing"}
    store.promote_cold_candidate.return_value = None
    analyzer = AsyncMock()
    analyzer.analyze.return_value = SemanticAnalysisResult(
        canonical_key="concrete_examples",
        relation="match_existing",
        matched_candidate_id="existing",
        confidence=0.98,
        reason_code="same_preference",
    )
    service = MemoryIngestionService(
        store,
        semantic_analyzer=analyzer,
        semantic_enabled=True,
        semantic_shadow_mode=False,
    )

    await service.ingest_user_evidence(evidence("學抽象概念時，我希望先看具體案例再理解原理。"))

    assert store.append_cold_candidate.await_args.kwargs["candidate_hash_override"] == "existing"


@pytest.mark.asyncio
async def test_low_confidence_semantic_match_cannot_merge_candidates():
    store = AsyncMock()
    store.get_cold_candidates.return_value = [{
        "user_id": "user-a",
        "hash": "existing",
        "category": "passive_preference",
        "status": "candidate",
        "requires_confirmation": False,
        "canonical_key": "concrete_examples",
        "normalized_text": "first",
    }]
    store.append_cold_candidate.return_value = {"hash": "new"}
    store.promote_cold_candidate.return_value = None
    analyzer = AsyncMock()
    analyzer.analyze.return_value = SemanticAnalysisResult(
        canonical_key="concrete_examples",
        relation="match_existing",
        matched_candidate_id="existing",
        confidence=0.40,
        reason_code="weak_match",
    )
    service = MemoryIngestionService(
        store,
        semantic_analyzer=analyzer,
        semantic_enabled=True,
        semantic_shadow_mode=False,
    )

    await service.ingest_user_evidence(evidence("學抽象概念時，我希望先看具體案例再理解原理。"))

    assert store.append_cold_candidate.await_args.kwargs["candidate_hash_override"] == ""


@pytest.mark.asyncio
async def test_equivalent_preference_uses_deterministic_match_without_semantics(caplog):
    caplog.set_level(logging.INFO)
    canonical_key = "learning_preference:abstract_concepts:concrete_examples"
    store = AsyncMock()
    store.get_cold_candidates.return_value = [{
        "user_id": "user-a",
        "hash": "existing",
        "category": "passive_preference",
        "status": "candidate",
        "requires_confirmation": False,
        "canonical_key": canonical_key,
        "normalized_text": canonical_key,
    }]
    store.append_cold_candidate.return_value = {"hash": "existing"}
    store.promote_cold_candidate.return_value = {"hash": "existing"}
    service = MemoryIngestionService(store, semantic_enabled=False)

    result = await service.ingest_user_evidence(
        evidence(
            "學抽象概念時，我希望先看具體案例或實際情境，再理解原理。",
            conversation_id="conv-b",
            message_id="msg-b",
        )
    )

    kwargs = store.append_cold_candidate.await_args.kwargs
    assert kwargs["canonical_key"] == canonical_key
    assert kwargs["candidate_hash_override"] == "existing"
    assert result.promoted is True
    assert "memory.canonical_match_accepted" in caplog.text
    assert "category=passive_preference" in caplog.text
    assert "學抽象概念時" not in caplog.text


@pytest.mark.asyncio
async def test_ambiguous_canonical_match_logs_metadata_without_raw_text(caplog):
    caplog.set_level(logging.WARNING)
    canonical_key = "learning_preference:abstract_concepts:concrete_examples"
    store = AsyncMock()
    store.get_cold_candidates.return_value = [
        {
            "user_id": "user-a",
            "hash": candidate_hash,
            "category": "passive_preference",
            "status": "candidate",
            "requires_confirmation": False,
            "canonical_key": canonical_key,
            "normalized_text": canonical_key,
        }
        for candidate_hash in ("candidate-a", "candidate-b")
    ]
    store.append_cold_candidate.return_value = {"hash": "new"}
    store.promote_cold_candidate.return_value = None
    service = MemoryIngestionService(store, semantic_enabled=False)
    raw_text = "學抽象概念時，我希望先看具體案例或實際情境，再理解原理。"

    await service.ingest_user_evidence(evidence(raw_text))

    assert "memory.canonical_match_rejected" in caplog.text
    assert "reason=ambiguous_candidates" in caplog.text
    assert raw_text not in caplog.text


@pytest.mark.asyncio
async def test_negative_preference_cannot_join_positive_canonical_candidate():
    canonical_key = "learning_preference:abstract_concepts:concrete_examples"
    store = AsyncMock()
    store.get_cold_candidates.return_value = [{
        "user_id": "user-a",
        "hash": "positive",
        "category": "passive_preference",
        "status": "candidate",
        "requires_confirmation": False,
        "canonical_key": canonical_key,
        "normalized_text": canonical_key,
    }]
    store.append_cold_candidate.return_value = {"hash": "negative"}
    store.promote_cold_candidate.return_value = None
    service = MemoryIngestionService(store, semantic_enabled=False)

    await service.ingest_user_evidence(
        evidence("我不喜歡用具體例子理解抽象概念。", message_id="msg-negative")
    )

    kwargs = store.append_cold_candidate.await_args.kwargs
    assert kwargs["canonical_key"] != canonical_key
    assert kwargs["candidate_hash_override"] == ""


@pytest.mark.asyncio
async def test_temporary_goal_completion_retires_match_and_clears_focus():
    store = AsyncMock()
    store.get_cold_candidates.return_value = [{
        "user_id": "user-a",
        "hash": "goal-a",
        "category": "temporary_goal",
        "status": "candidate",
        "requires_confirmation": False,
        "text": "這個月我想完成牛頓運動定律的複習，請在這段期間協助我安排練習。",
    }]
    store.complete_temporary_goal_candidate.return_value = {
        "hash": "goal-a",
        "status": "completed",
        "text": "這個月我想完成牛頓運動定律的複習，請在這段期間協助我安排練習。",
    }
    store.get_working_memory.return_value = {
        "current_focus": "這個月我想完成牛頓運動定律的複習",
    }
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(
        evidence(
            "我已經完成這個月的牛頓運動定律複習目標，請不要再提醒我。",
            message_id="msg-completed",
        )
    )

    assert result.reason_code == "temporary_goal_completed"
    assert result.candidate_id == "goal-a"
    store.complete_temporary_goal_candidate.assert_awaited_once()
    store.update_working_memory.assert_awaited_once_with(
        "user-a",
        {"current_focus": "", "current_focus_conversation_id": ""},
    )
    store.perform_memory_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_temporary_goal_completion_preserves_unrelated_current_focus():
    goal_text = "這個月我想完成牛頓運動定律的複習。"
    store = AsyncMock()
    store.get_cold_candidates.return_value = [{
        "user_id": "user-a",
        "hash": "goal-a",
        "category": "temporary_goal",
        "status": "candidate",
        "requires_confirmation": False,
        "text": goal_text,
    }]
    store.complete_temporary_goal_candidate.return_value = {
        "hash": "goal-a",
        "status": "completed",
        "text": goal_text,
    }
    store.get_working_memory.return_value = {
        "current_focus": "英文作文架構練習",
        "current_focus_conversation_id": "conversation-english",
    }
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(
        evidence("我已經完成這個月的牛頓運動定律複習目標，請不要再提醒我。")
    )

    assert result.reason_code == "temporary_goal_completed"
    store.update_working_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_temporary_goal_completion_without_safe_match_fails_closed():
    store = AsyncMock()
    store.get_cold_candidates.return_value = []
    store.complete_temporary_goal_candidate.return_value = None
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(
        evidence("我已經完成這個月的牛頓運動定律複習目標，請不要再提醒我。")
    )

    assert result.reason_code == "temporary_goal_completion_not_found"
    store.update_working_memory.assert_not_awaited()
    store.perform_memory_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_temporary_goal_completion_with_multiple_matches_is_ambiguous():
    goal = {
        "user_id": "user-a",
        "category": "temporary_goal",
        "status": "candidate",
        "requires_confirmation": False,
        "text": "這個月我想完成牛頓運動定律的複習。",
    }
    store = AsyncMock()
    store.get_cold_candidates.return_value = [
        {**goal, "hash": "goal-a"},
        {**goal, "hash": "goal-b"},
    ]
    store.complete_temporary_goal_candidate.return_value = None
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(
        evidence("我已經完成這個月的牛頓運動定律複習目標，請不要再提醒我。")
    )

    assert result.reason_code == "temporary_goal_completion_ambiguous"
    store.update_working_memory.assert_not_awaited()


def test_external_semantic_processing_requires_explicit_deployment_acknowledgement(
    monkeypatch,
):
    from backend.services import memory_ingestion_service as module

    monkeypatch.setattr(module.settings, "memory_semantic_analysis_enabled", True)
    monkeypatch.setattr(
        module.settings,
        "memory_semantic_external_processing_acknowledged",
        False,
    )

    service = create_memory_ingestion_service(AsyncMock(), client=AsyncMock())

    assert service.semantic_enabled is False
    assert service.semantic_analyzer is None
