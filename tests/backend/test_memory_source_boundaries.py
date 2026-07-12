import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.compaction import evaluate_student_state
from backend.gum_integration import async_evaluate_and_update_state
from backend.memory_store import InvalidMemorySource, MemoryStore


@pytest.mark.asyncio
async def test_student_state_schema_does_not_request_memory_operations():
    client = MagicMock()
    response = MagicMock()
    response.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"learner_state":"TINKERING",'
                    '"pedagogical_strategy":"用具體例子引導",'
                    '"trigger_proactive":false}'
                )
            )
        )
    ]
    client.chat.completions.create = AsyncMock(return_value=response)

    result = await evaluate_student_state(
        client,
        "test-model",
        [
            {"role": "user", "content": "我不懂牛頓第一定律"},
            {"role": "assistant", "content": "我來用例子說明"},
        ],
    )

    assert result["learner_state"] == "TINKERING"
    assert "memory_operations" not in result
    schema_prompt = client.chat.completions.create.call_args.kwargs["response_format"]
    assert "memory_operations" not in str(schema_prompt)


@pytest.mark.asyncio
async def test_legacy_edf_memory_operations_are_ignored():
    store = MagicMock()
    store.update_learner_state_snapshot = AsyncMock()
    store.perform_memory_operation = AsyncMock()

    state_result = {
        "learner_state": "MASTERY",
        "pedagogical_strategy": "引導遷移",
        "trigger_proactive": False,
        "memory_operations": [
            {
                "target": "user",
                "action": "add",
                "content": "使用者已掌握牛頓第一定律",
            }
        ],
    }

    with patch("backend.compaction.evaluate_student_state", new=AsyncMock(return_value=state_result)), \
         patch("memory_store.get_global_store", return_value=store):
        await async_evaluate_and_update_state(
            MagicMock(),
            "test-model",
            [],
            user_id="u1",
        )

    store.update_learner_state_snapshot.assert_awaited_once()
    store.perform_memory_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_profile_memory_rejects_inferred_source_at_storage_boundary():
    store = MemoryStore.__new__(MemoryStore)

    with pytest.raises(InvalidMemorySource):
        await store.perform_memory_operation(
            "u1",
            "user",
            "add",
            "使用者已掌握牛頓第一定律",
            source="edf_inference",
        )


@pytest.mark.asyncio
async def test_non_sensitive_candidate_with_cross_conversation_evidence_is_promoted():
    store = MagicMock()
    store.update_learner_state_snapshot = AsyncMock()
    store.append_cold_candidate = AsyncMock(return_value={
        "hash": "candidate-hash",
        "conversation_ids": ["conv-a", "conv-b"],
        "requires_confirmation": False,
    })
    store.promote_cold_candidate = AsyncMock()

    candidate = {
        "text": "使用者偏好以具體案例理解概念",
        "normalized_text": "偏好以具體案例理解概念",
        "category": "preference",
        "confidence": 0.9,
        "requires_confirmation": False,
        "evidence": {"message": "請用一個例子說明", "quote": "用一個例子", "message_index": 0},
    }
    state_result = {"learner_state": "TINKERING", "pedagogical_strategy": "引導", "trigger_proactive": False}

    with patch("backend.compaction.evaluate_student_state", new=AsyncMock(return_value=state_result)), \
         patch("memory_store.get_global_store", return_value=store), \
         patch("memory_gate.extract_user_memory_candidates", new=AsyncMock(return_value=[candidate])):
        await async_evaluate_and_update_state(MagicMock(), "test-model", [{"role": "user", "content": "請用一個例子說明"}], "u1", "conv-b")

    store.append_cold_candidate.assert_awaited_once()
    store.promote_cold_candidate.assert_awaited_once_with("u1", "candidate-hash", source="automatic_candidate_promotion")


@pytest.mark.asyncio
async def test_sensitive_candidate_never_auto_promotes():
    store = MagicMock()
    store.update_learner_state_snapshot = AsyncMock()
    store.append_cold_candidate = AsyncMock(return_value={
        "hash": "candidate-hash",
        "conversation_ids": ["conv-a", "conv-b"],
        "requires_confirmation": True,
    })
    store.promote_cold_candidate = AsyncMock()
    candidate = {
        "text": "使用者描述了需確認的個人情況",
        "normalized_text": "需確認的個人情況",
        "category": "personal_context",
        "confidence": 0.9,
        "requires_confirmation": True,
        "evidence": {"message": "這是我的個人情況", "quote": "個人情況", "message_index": 0},
    }
    state_result = {"learner_state": "STARTING", "pedagogical_strategy": "引導", "trigger_proactive": False}

    with patch("backend.compaction.evaluate_student_state", new=AsyncMock(return_value=state_result)), \
         patch("memory_store.get_global_store", return_value=store), \
         patch("memory_gate.extract_user_memory_candidates", new=AsyncMock(return_value=[candidate])):
        await async_evaluate_and_update_state(MagicMock(), "test-model", [{"role": "user", "content": "這是我的個人情況"}], "u1", "conv-b")

    store.promote_cold_candidate.assert_not_awaited()
