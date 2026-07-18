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
    store.update_working_memory = AsyncMock()
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
async def test_edf_cannot_reingest_declarative_preference():
    store = MagicMock()
    store.update_learner_state_snapshot = AsyncMock()
    store.update_working_memory = AsyncMock()
    store.get_cold_candidates = AsyncMock(return_value=[])
    store.append_cold_candidate = AsyncMock(return_value={
        "hash": "candidate-hash",
        "conversation_ids": ["conv-b"],
        "requires_confirmation": False,
    })
    store.promote_cold_candidate = AsyncMock(return_value=None)
    state_result = {"learner_state": "TINKERING", "pedagogical_strategy": "引導", "trigger_proactive": False}

    with patch("backend.compaction.evaluate_student_state", new=AsyncMock(return_value=state_result)), \
         patch("memory_store.get_global_store", return_value=store):
        await async_evaluate_and_update_state(
            MagicMock(),
            "test-model",
            [{"role": "user", "content": "我偏好用具體例子理解抽象概念。"}],
            "u1",
            "conv-b",
            ingest_memory=True,
        )

    store.append_cold_candidate.assert_not_awaited()
    store.promote_cold_candidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_sensitive_candidate_never_auto_promotes():
    store = MagicMock()
    store.update_learner_state_snapshot = AsyncMock()
    store.get_cold_candidates = AsyncMock(return_value=[])
    store.append_cold_candidate = AsyncMock(return_value={
        "hash": "candidate-hash",
        "conversation_ids": ["conv-a", "conv-b"],
        "requires_confirmation": True,
    })
    store.promote_cold_candidate = AsyncMock()
    state_result = {"learner_state": "STARTING", "pedagogical_strategy": "引導", "trigger_proactive": False}

    with patch("backend.compaction.evaluate_student_state", new=AsyncMock(return_value=state_result)), \
         patch("memory_store.get_global_store", return_value=store):
        await async_evaluate_and_update_state(
            MagicMock(),
            "test-model",
            [{"role": "user", "content": "我最近很焦慮，請記住這件事。"}],
            "u1",
            "conv-b",
        )

    store.append_cold_candidate.assert_not_awaited()
    store.promote_cold_candidate.assert_not_awaited()
