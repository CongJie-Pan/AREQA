import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from backend.gum_integration import async_evaluate_and_update_state
from backend.memory_store import MemoryStore

@pytest.fixture
def mock_store(tmp_path):
    store = MemoryStore(str(tmp_path / "hot.json"), str(tmp_path / "profile.json"))
    with patch("memory_store.get_global_store", return_value=store):
        yield store

@pytest.mark.asyncio
async def test_avatar_cleared_when_llm_returns_null(mock_store):
    hot = mock_store.get_hot_memory()
    hot["active_avatar"] = "柏拉圖"
    mock_store._atomic_write(mock_store.hot_memory_path, hot)
    with patch("compaction.evaluate_student_state", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = {
            "learner_state": "TINKERING",
            "pedagogical_strategy": "NORMAL",
            "trigger_proactive": False,
            "active_avatar": None
        }
        
        await async_evaluate_and_update_state(MagicMock(), "mock-model", [])
        
        hot_mem = mock_store.get_hot_memory()
        assert "active_avatar" not in hot_mem

@pytest.mark.asyncio
async def test_avatar_not_cleared_when_same_person(mock_store):
    hot = mock_store.get_hot_memory()
    hot["active_avatar"] = "柏拉圖"
    mock_store._atomic_write(mock_store.hot_memory_path, hot)
    with patch("compaction.evaluate_student_state", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = {
            "learner_state": "TINKERING",
            "pedagogical_strategy": "NORMAL",
            "trigger_proactive": False,
            "active_avatar": "柏拉圖"
        }
        
        await async_evaluate_and_update_state(MagicMock(), "mock-model", [])
        
        hot_mem = mock_store.get_hot_memory()
        assert hot_mem["active_avatar"] == "柏拉圖"
        assert "avatar_summon_pending" not in hot_mem

@pytest.mark.asyncio
async def test_avatar_changes_trigger_new_summon(mock_store):
    hot = mock_store.get_hot_memory()
    hot["active_avatar"] = "柏拉圖"
    mock_store._atomic_write(mock_store.hot_memory_path, hot)
    with patch("compaction.evaluate_student_state", new_callable=AsyncMock) as mock_eval:
        mock_eval.return_value = {
            "learner_state": "TINKERING",
            "pedagogical_strategy": "NORMAL",
            "trigger_proactive": False,
            "active_avatar": "蘇格拉底"
        }
        
        await async_evaluate_and_update_state(MagicMock(), "mock-model", [])
        
        hot_mem = mock_store.get_hot_memory()
        assert hot_mem["active_avatar"] == "蘇格拉底"
        assert hot_mem["avatar_summon_pending"] is True
