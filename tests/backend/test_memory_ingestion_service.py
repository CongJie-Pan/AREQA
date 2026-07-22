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
from backend.services.memory_extraction_agent import (
    MemoryCandidateDraft,
    MemoryExtractionResult,
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


class FakeExtractionAgent:
    def __init__(self, candidates):
        self.candidates = candidates

    async def extract_candidates(self, **kwargs):
        return MemoryExtractionResult(candidates=self.candidates)


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
async def test_mixed_question_prompt_promotes_extracted_learning_preference(caplog):
    caplog.set_level(logging.INFO)
    store = AsyncMock()
    extraction_agent = FakeExtractionAgent([
        MemoryCandidateDraft(
            candidate_type="temporary_context",
            text="我是高一生，下週要考高一物理。",
            durability="working_memory_only",
            confidence=0.93,
            reason_code="temporary_exam_context",
        ),
        MemoryCandidateDraft(
            candidate_type="question",
            text="你可以教我什麼是牛頓第一運動定律嗎？",
            durability="do_not_store",
            confidence=0.98,
            reason_code="question_not_memory",
        ),
        MemoryCandidateDraft(
            candidate_type="sensitive_context",
            text="我之前連國中理化都一直不及格，現在好焦慮。",
            durability="do_not_store",
            confidence=0.96,
            reason_code="negative_learning_state_sensitive",
        ),
        MemoryCandidateDraft(
            candidate_type="learning_preference",
            text="我偏好你先給我一個具體例子，再解釋抽象概念。",
            durability="profile_memory",
            confidence=0.96,
            reason_code="explicit_learning_preference",
        ),
    ])
    service = MemoryIngestionService(store, extraction_agent=extraction_agent)

    raw_text = (
        "我是高一生，我下週要考高一物理了，但我之前連國中理化都一直不及格，現在好焦慮。\n"
        "你可以教我什麼是牛頓第一運動定律嗎？\n"
        "我偏好你先給我一個具體例子，再解釋抽象概念。"
    )

    result = await service.ingest_user_evidence(evidence(raw_text))

    assert result.state is MemoryEligibilityState.PROMOTION_ELIGIBLE
    assert result.reason_code == "extracted_learning_preference_promoted"
    assert result.category == "learning_preference"
    store.perform_memory_operation.assert_awaited_once_with(
        "user-a",
        "user",
        "add",
        "我偏好你先給我一個具體例子，再解釋抽象概念。",
        source="verified_user_evidence",
    )
    store.append_cold_candidate.assert_not_awaited()
    assert "memory.extraction_candidate_promoted" in caplog.text
    assert "memory.extraction_started" not in caplog.text
    assert "memory.extraction_received" not in caplog.text
    assert "memory.extraction_candidate_skipped" not in caplog.text
    assert "reason=non_learning_preference" not in caplog.text
    assert raw_text not in caplog.text
    assert "我偏好你先給我一個具體例子" not in caplog.text


@pytest.mark.asyncio
async def test_extraction_does_not_store_question_or_sensitive_candidate(caplog):
    caplog.set_level(logging.INFO)
    store = AsyncMock()
    extraction_agent = FakeExtractionAgent([
        MemoryCandidateDraft(
            candidate_type="question",
            text="我偏好什麼學習方法？",
            durability="profile_memory",
            confidence=0.99,
            reason_code="question_not_memory",
        ),
        MemoryCandidateDraft(
            candidate_type="learning_preference",
            text="我最近很焦慮。",
            durability="profile_memory",
            confidence=0.99,
            reason_code="sensitive_candidate",
        ),
    ])
    service = MemoryIngestionService(store, extraction_agent=extraction_agent)

    result = await service.ingest_user_evidence(
        evidence("我偏好什麼學習方法？我最近很焦慮。")
    )

    assert result.state is MemoryEligibilityState.REJECTED
    assert result.reason_code == "sensitive_content_not_durable"
    store.perform_memory_operation.assert_not_awaited()
    store.append_cold_candidate.assert_not_awaited()
    assert "memory.extraction_candidate_blocked" in caplog.text
    assert "reason=sensitive_candidate" in caplog.text
    assert "memory.extraction_no_promotion" not in caplog.text
    assert "我最近很焦慮" not in caplog.text


@pytest.mark.asyncio
async def test_low_confidence_extracted_preference_falls_back_to_existing_policy():
    store = AsyncMock()
    extraction_agent = FakeExtractionAgent([
        MemoryCandidateDraft(
            candidate_type="learning_preference",
            text="我偏好你先給我一個具體例子，再解釋抽象概念。",
            durability="profile_memory",
            confidence=0.20,
            reason_code="weak_signal",
        )
    ])
    service = MemoryIngestionService(store, extraction_agent=extraction_agent)

    result = await service.ingest_user_evidence(evidence("你可以教我什麼是牛頓第一運動定律嗎？"))

    assert result.state is MemoryEligibilityState.WORKING_CONTEXT_ONLY
    assert result.reason_code == "interrogative_not_memory_evidence"
    store.perform_memory_operation.assert_not_awaited()
    store.append_cold_candidate.assert_not_awaited()


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
async def test_explicit_first_person_liking_promotes_to_profile_memory():
    store = AsyncMock()
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(
        evidence("我喜歡讀文學作品和賞析，也希望有人可以和我一起討論。")
    )

    assert result.state is MemoryEligibilityState.PROMOTION_ELIGIBLE
    assert result.reason_code == "explicit_self_report_promoted"
    assert result.category == "explicit_self_report"
    assert result.promoted is True
    store.perform_memory_operation.assert_awaited_once_with(
        "user-a",
        "user",
        "add",
        "使用者喜歡讀文學作品和賞析，也希望有人可以和我一起討論",
        source="verified_user_evidence",
    )
    store.append_cold_candidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_first_person_ability_promotes_to_profile_memory():
    store = AsyncMock()
    service = MemoryIngestionService(store)

    result = await service.ingest_user_evidence(evidence("我擅長用比較的方式理解小說。"))

    assert result.state is MemoryEligibilityState.PROMOTION_ELIGIBLE
    assert result.reason_code == "explicit_self_report_promoted"
    store.perform_memory_operation.assert_awaited_once_with(
        "user-a",
        "user",
        "add",
        "使用者擅長用比較的方式理解小說",
        source="verified_user_evidence",
    )
    store.append_cold_candidate.assert_not_awaited()


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
async def test_temporary_goal_completion_retires_match_and_clears_focus(caplog):
    caplog.set_level("INFO")
    store = AsyncMock()
    goal_text = "這個月我想完成牛頓運動定律的複習，請在這段期間協助我安排練習。"
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
    assert "memory.goal_focus_cleared" in caplog.text
    assert "candidate_id=goal-a" in caplog.text
    assert "cleared_keys=current_focus,current_focus_conversation_id" in caplog.text
    assert goal_text not in caplog.text


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


def test_memory_extraction_defaults_to_local_agent_without_external_acknowledgement(
    monkeypatch,
):
    from backend.services import memory_ingestion_service as module

    monkeypatch.setattr(module.settings, "memory_extraction_agent_enabled", True)
    monkeypatch.setattr(
        module.settings,
        "memory_semantic_external_processing_acknowledged",
        False,
    )

    service = create_memory_ingestion_service(AsyncMock(), client=AsyncMock())

    assert service.extraction_agent.__class__.__name__ == "LocalMemoryExtractionAgent"
