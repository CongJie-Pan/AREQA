import json
import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.memory_store import MemoryStore

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    
    store = {}
    
    async def fake_get(key):
        return store.get(key)
        
    async def fake_set(key, val):
        store[key] = val
        
    def fake_set_sync(key, val):
        store[key] = val
        
    redis.get = AsyncMock(side_effect=fake_get)
    redis.set = AsyncMock(side_effect=fake_set)
    
    pipe_mock = AsyncMock()
    pipe_mock.get = AsyncMock(side_effect=fake_get)
    pipe_mock.set = MagicMock(side_effect=fake_set_sync)
    pipe_mock.watch = AsyncMock()
    pipe_mock.multi = MagicMock()
    pipe_mock.execute = AsyncMock()
    transaction_lock = asyncio.Lock()
    
    class PipelineContext:
        def __init__(self, **kwargs):
            self.pipe = pipe_mock
            
        async def __aenter__(self):
            await transaction_lock.acquire()
            return self.pipe
            
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            transaction_lock.release()
            
    redis.pipeline = PipelineContext
    redis._store = store
    redis._pipe_mock = pipe_mock
    return redis

@pytest.fixture
def memory_store(mock_redis):
    with patch("backend.memory_store.get_redis", return_value=mock_redis):
        store = MemoryStore(budget_limit=1000)
        yield store

@pytest.mark.asyncio
async def test_update_hot_memory_isolation(memory_store, mock_redis):
    await memory_store.update_hot_memory("user_a", "key1", "val_a")
    await memory_store.update_hot_memory("user_b", "key1", "val_b")
    
    assert "areqa:hot_memory:user_a" in mock_redis._store
    assert "areqa:hot_memory:user_b" in mock_redis._store
    
    data_a = json.loads(mock_redis._store["areqa:hot_memory:user_a"])
    data_b = json.loads(mock_redis._store["areqa:hot_memory:user_b"])
    
    assert data_a["key1"] == "val_a"
    assert data_b["key1"] == "val_b"


@pytest.mark.asyncio
async def test_learner_state_snapshot_updates_fields_in_one_version(memory_store, mock_redis):
    first = await memory_store.update_learner_state_snapshot(
        "user-1",
        learner_state="STARTING",
        strategy="SCAFFOLD",
        trigger_proactive=False,
    )
    second = await memory_store.update_learner_state_snapshot(
        "user-1",
        learner_state="TINKERING",
        strategy="PROBE",
        trigger_proactive=True,
    )

    snapshot = json.loads(mock_redis._store["areqa:hot_memory:user-1"])
    assert first == 1 and second == 2
    assert snapshot["current_learner_state"] == "TINKERING"
    assert snapshot["current_strategy"] == "PROBE"
    assert snapshot["trigger_proactive"] is True
    assert snapshot["learner_state_version"] == 2
    assert snapshot["learner_state_evaluated_at"]

@pytest.mark.asyncio
async def test_update_user_profile(memory_store, mock_redis):
    await memory_store.update_user_profile("student", "name", "國立臺灣大學中文系三年級")
    
    profile = await memory_store.get_user_profile("student")
    assert profile["name"] == "國立臺灣大學中文系三年級"

@pytest.mark.asyncio
async def test_override_memory(memory_store, mock_redis):
    await memory_store.update_hot_memory("user1", "林黛玉的丫鬟", "雪雁")
    mem1 = await memory_store.get_hot_memory("user1")
    assert mem1["林黛玉的丫鬟"] == "雪雁"
    
    await memory_store.update_hot_memory("user1", "林黛玉的丫鬟", "紫鵑")
    mem2 = await memory_store.get_hot_memory("user1")
    assert mem2["林黛玉的丫鬟"] == "紫鵑"

@pytest.mark.asyncio
async def test_get_learner_state(memory_store, mock_redis):
    state = await memory_store.get_learner_state("user2")
    assert state == "STARTING"
    
    await memory_store.update_hot_memory("user2", "current_learner_state", "CONFUSED")
    state2 = await memory_store.get_learner_state("user2")
    assert state2 == "CONFUSED"


@pytest.mark.asyncio
async def test_unknown_semantic_candidate_override_fails_closed(memory_store, mock_redis):
    candidate = await memory_store.append_cold_candidate(
        "user-1",
        "我偏好用具體例子理解抽象概念。",
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
        candidate_hash_override="unknown-candidate",
        evidence={
            "message_id": "message-1",
            "conversation_id": "conversation-1",
            "timestamp": "2026-07-16T00:00:00+00:00",
            "source_role": "user",
            "message": "我偏好用具體例子理解抽象概念。",
            "quote": "我偏好用具體例子理解抽象概念。",
        },
    )

    assert candidate is None
    assert "areqa:cold_candidates:user-1" not in mock_redis._store


@pytest.mark.asyncio
async def test_candidate_creation_and_correction_emit_structured_events(
    memory_store, caplog
):
    caplog.set_level(logging.INFO)
    await memory_store.append_cold_candidate(
        "user-1",
        "我偏好先看例子。",
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
    )
    await memory_store.perform_memory_operation(
        "user-1",
        "user",
        "remove",
        "",
        old_text="outdated",
        source="explicit_user_request",
    )

    assert "memory.candidate_created" in caplog.text
    assert "memory.correction_applied" in caplog.text


def candidate_evidence(message_id, conversation_id, message):
    return {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "timestamp": "2026-07-16T00:00:00+00:00",
        "source_role": "user",
        "message": message,
        "quote": message,
    }


@pytest.mark.asyncio
async def test_candidate_evidence_event_reports_safe_counts(memory_store, caplog):
    caplog.set_level(logging.INFO)
    message = "我偏好先看具體例子。"
    candidate = await memory_store.append_cold_candidate(
        "user-1",
        message,
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
        conversation_id="conversation-1",
        evidence=candidate_evidence("message-1", "conversation-1", message),
    )
    await memory_store.append_cold_candidate(
        "user-1",
        message,
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
        conversation_id="conversation-1",
        candidate_hash_override=candidate["hash"],
        evidence=candidate_evidence("message-2", "conversation-1", message),
    )

    assert "memory.candidate_evidence_recorded" in caplog.text
    assert "event=duplicate_conversation_ignored" in caplog.text
    assert "evidence_count=1" in caplog.text
    assert message not in caplog.text


@pytest.mark.asyncio
async def test_canonical_preference_promotes_only_after_two_conversations(memory_store):
    canonical_key = "learning_preference:abstract_concepts:concrete_examples"
    first_text = "我偏好用具體例子理解抽象概念。"
    second_text = "學抽象概念時，我希望先看具體案例或實際情境，再理解原理。"
    first = await memory_store.append_cold_candidate(
        "user-1",
        first_text,
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
        normalized_text=canonical_key,
        canonical_key=canonical_key,
        evidence=candidate_evidence("message-1", "conversation-1", first_text),
        conversation_id="conversation-1",
    )
    blocked = await memory_store.promote_cold_candidate(
        "user-1", first["hash"], source="automatic_candidate_promotion"
    )
    second = await memory_store.append_cold_candidate(
        "user-1",
        second_text,
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
        normalized_text=canonical_key,
        canonical_key=canonical_key,
        evidence=candidate_evidence("message-2", "conversation-2", second_text),
        conversation_id="conversation-2",
    )
    promoted = await memory_store.promote_cold_candidate(
        "user-1", second["hash"], source="automatic_candidate_promotion"
    )

    profile = await memory_store.get_user_profile("user-1")
    assert blocked is None
    assert first["hash"] == second["hash"]
    assert promoted["status"] == "promoted"
    assert profile["explicit_memories"] == [second_text]


@pytest.mark.asyncio
async def test_passive_preference_keeps_one_evidence_per_conversation(memory_store):
    canonical_key = "learning_preference:abstract_concepts:concrete_examples"
    first_text = "我偏好用具體例子理解抽象概念。"
    repeated_text = "我真的比較喜歡用實際例子來學抽象概念。"
    first = await memory_store.append_cold_candidate(
        "user-1",
        first_text,
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
        normalized_text=canonical_key,
        canonical_key=canonical_key,
        evidence=candidate_evidence("message-1", "conversation-1", first_text),
        conversation_id="conversation-1",
    )
    repeated = await memory_store.append_cold_candidate(
        "user-1",
        repeated_text,
        category="passive_preference",
        source="verified_user_evidence",
        reason="test",
        normalized_text=canonical_key,
        canonical_key=canonical_key,
        evidence=candidate_evidence("message-2", "conversation-1", repeated_text),
        conversation_id="conversation-1",
    )

    persisted = await memory_store.get_cold_candidates("user-1")
    assert first["hash"] == repeated["hash"]
    assert len(persisted[0]["evidence"]) == 1
    assert persisted[0]["evidence"][0]["message_id"] == "message-1"


@pytest.mark.asyncio
async def test_concurrent_promotion_commits_profile_exactly_once(memory_store):
    canonical_key = "learning_preference:abstract_concepts:concrete_examples"
    candidate = None
    for index in range(3):
        text = f"preference-{index}"
        candidate = await memory_store.append_cold_candidate(
            "user-1",
            text,
            category="passive_preference",
            source="verified_user_evidence",
            reason="test",
            normalized_text=canonical_key,
            canonical_key=canonical_key,
            evidence=candidate_evidence(
                f"message-{index}",
                f"conversation-{index}",
                text,
            ),
            conversation_id=f"conversation-{index}",
        )

    original_get = memory_store.get_cold_candidates
    both_read = asyncio.Event()
    read_count = 0

    async def synchronized_get(user_id):
        nonlocal read_count
        result = await original_get(user_id)
        read_count += 1
        if read_count >= 2:
            both_read.set()
        await both_read.wait()
        return result

    memory_store.get_cold_candidates = synchronized_get
    before_pipeline_sets = len(memory_store.redis._pipe_mock.set.call_args_list)
    results = await asyncio.gather(
        memory_store.promote_cold_candidate(
            "user-1", candidate["hash"], source="automatic_candidate_promotion"
        ),
        memory_store.promote_cold_candidate(
            "user-1", candidate["hash"], source="automatic_candidate_promotion"
        ),
    )

    profile = await memory_store.get_user_profile("user-1")
    new_pipeline_sets = memory_store.redis._pipe_mock.set.call_args_list[
        before_pipeline_sets:
    ]
    profile_writes = [
        call for call in new_pipeline_sets
        if call.args[0] == "areqa:user_profile:user-1"
    ]
    assert sum(result is not None for result in results) == 1
    assert len(profile_writes) == 1
    assert profile["explicit_memories"] == ["preference-2"]


@pytest.mark.asyncio
async def test_completed_temporary_goal_is_persisted_and_cannot_promote(
    memory_store, caplog
):
    caplog.set_level(logging.INFO)
    goal_text = "這個月我想完成牛頓運動定律的複習。"
    candidate = await memory_store.append_cold_candidate(
        "user-1",
        goal_text,
        category="temporary_goal",
        source="verified_user_evidence",
        reason="test",
        evidence=candidate_evidence("message-1", "conversation-1", goal_text),
        conversation_id="conversation-1",
    )
    completion_text = "我已經完成這個月的牛頓運動定律複習目標，請不要再提醒我。"
    completed = await memory_store.complete_temporary_goal_candidate(
        "user-1",
        candidate["hash"],
        candidate_evidence("message-2", "conversation-1", completion_text),
        reason="explicit_user_completion",
    )
    promoted = await memory_store.promote_cold_candidate(
        "user-1", candidate["hash"], source="automatic_candidate_promotion"
    )

    persisted = await memory_store.get_cold_candidates("user-1")
    profile = await memory_store.get_user_profile("user-1")
    assert completed["status"] == "completed"
    assert persisted[0]["completed_at"]
    assert persisted[0]["completion_evidence"]["message_id"] == "message-2"
    assert persisted[0]["evidence"][-1]["evidence_type"] == "temporary_goal_completion"
    assert promoted is None
    assert profile["explicit_memories"] == []
    assert "memory.temporary_goal_completed" in caplog.text
    assert "status=completed" in caplog.text
    assert "reason=explicit_user_completion" in caplog.text
    assert "evidence_count=2" in caplog.text
    assert "cleared_keys=none" in caplog.text
    assert goal_text not in caplog.text
    assert completion_text not in caplog.text


@pytest.mark.asyncio
async def test_temporary_goal_completion_with_no_candidate_is_safely_blocked(
    memory_store, caplog
):
    caplog.set_level(logging.WARNING)
    result = await memory_store.complete_temporary_goal_candidate(
        "user-1",
        "",
        candidate_evidence("message-2", "conversation-1", "完成目標"),
        reason="temporary_goal_completion_not_found",
    )

    assert result is None
    assert "memory.temporary_goal_completion_blocked" in caplog.text
    assert "完成目標" not in caplog.text
