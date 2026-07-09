import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from backend.gum_integration import async_evaluate_and_update_state
from backend.memory_store import MemoryStore

@pytest.fixture
def mock_store():
    store = AsyncMock()
    store.get_hot_memory.return_value = {}
    with patch("memory_store.get_global_store", return_value=store):
        yield store

@pytest.mark.asyncio
async def test_avatar_cleared_when_llm_returns_null(mock_store):
    mock_store.get_hot_memory = AsyncMock(return_value={"active_avatar": "柏拉圖"})
    
    with patch("compaction.evaluate_student_state", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = {
            "learner_state": "TINKERING",
            "pedagogical_strategy": "NORMAL",
            "trigger_proactive": False,
            "active_avatar": None
        }
        
        await async_evaluate_and_update_state(MagicMock(), "mock-model", [])
        
        import json
        expected_hot = {}
        mock_store.redis.set.assert_called_with("areqa:hot_memory:default_user", json.dumps(expected_hot, ensure_ascii=False))

@pytest.mark.asyncio
async def test_avatar_not_cleared_when_same_person(mock_store):
    mock_store.get_hot_memory = AsyncMock(return_value={"active_avatar": "柏拉圖"})
    
    with patch("compaction.evaluate_student_state", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = {
            "learner_state": "TINKERING",
            "pedagogical_strategy": "NORMAL",
            "trigger_proactive": False,
            "active_avatar": "柏拉圖"
        }
        
        await async_evaluate_and_update_state(MagicMock(), "mock-model", [])
        
        # It should NOT update active_avatar since it hasn't changed
        call_args_list = mock_store.update_hot_memory_async.call_args_list
        for call in call_args_list:
            args, _ = call
            assert args[1] != "active_avatar"
        assert all(call[0][1] != "avatar_summon_pending" for call in call_args_list)

@pytest.mark.asyncio
async def test_avatar_changes_trigger_new_summon(mock_store):
    mock_store.get_hot_memory = AsyncMock(return_value={"active_avatar": "柏拉圖"})
    
    with patch("compaction.evaluate_student_state", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = {
            "learner_state": "TINKERING",
            "pedagogical_strategy": "NORMAL",
            "trigger_proactive": False,
            "active_avatar": "蘇格拉底"
        }
        
        await async_evaluate_and_update_state(MagicMock(), "mock-model", [])
        
        mock_store.update_hot_memory_async.assert_any_call("default_user", "active_avatar", "蘇格拉底")
        mock_store.update_hot_memory_async.assert_any_call("default_user", "avatar_summon_pending", True)
