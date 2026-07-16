from datetime import datetime, timezone
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
