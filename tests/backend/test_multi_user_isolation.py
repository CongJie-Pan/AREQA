import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from backend.gum_integration import (
    get_gum_instance,
    batch_process_observations,
    run_reflection_loop,
    stop_gum_instance,
    gum_instances,
    text_observers
)
import backend.gum_integration as gi

@pytest.fixture(autouse=True)
def reset_gum_instances():
    gi.gum_instances.clear()
    gi.text_observers.clear()
    gi.importance_sums.clear()
    gi.interaction_counts.clear()
    yield
    gi.gum_instances.clear()
    gi.text_observers.clear()

@pytest.mark.asyncio
async def test_get_gum_instance_multi_user():
    # Test getting instance for user_a
    with patch("backend.gum_integration.gum") as mock_gum:
        mock_instance_a = MagicMock()
        mock_instance_a.connect_db = AsyncMock()
        mock_instance_a.batcher = MagicMock()
        mock_instance_a.batcher.start = AsyncMock()
        mock_gum.return_value = mock_instance_a
        
        g_inst_a, t_obs_a = await get_gum_instance("user_a")
        
        # Second call should return cached instance
        g_inst_a2, t_obs_a2 = await get_gum_instance("user_a")
        assert g_inst_a is g_inst_a2
        assert t_obs_a is t_obs_a2
        
        # Get instance for user_b
        mock_instance_b = MagicMock()
        mock_instance_b.connect_db = AsyncMock()
        mock_instance_b.batcher = MagicMock()
        mock_instance_b.batcher.start = AsyncMock()
        mock_gum.return_value = mock_instance_b
        
        g_inst_b, t_obs_b = await get_gum_instance("user_b")
        assert g_inst_b is not g_inst_a
        
        assert len(gi.gum_instances) == 2
        assert "user_a" in gi.gum_instances
        assert "user_b" in gi.gum_instances

@pytest.mark.asyncio
async def test_batch_process_observations_multi_user_isolation():
    gi.last_interaction_time = None
    
    mock_instance = AsyncMock()
    mock_instance._process_batch = AsyncMock()
    mock_text_obs = AsyncMock()
    
    gi.gum_instances["user_a"] = mock_instance
    gi.text_observers["user_a"] = mock_text_obs

    with patch("backend.gum_integration.get_gum_instance", new_callable=AsyncMock) as mock_get, \
         patch("memory_store.get_global_store") as mock_store:
        mock_get.return_value = (mock_instance, mock_text_obs)
        mock_store_inst = MagicMock()
        mock_store_inst.get_hot_memory = AsyncMock(return_value={})
        mock_store_inst.get_user_profile = AsyncMock(return_value={})
        mock_store_inst.redis = AsyncMock()
        mock_store_inst.budget_limit = 1000
        mock_store.return_value = mock_store_inst
        
        mock_instance.query = AsyncMock(return_value=[])
        mock_instance.recent = AsyncMock(return_value=[])
        
        await batch_process_observations("user_a", ["obs1", "obs2"])
        
        mock_get.assert_called_with("user_a")
        mock_text_obs.push_text.assert_called_once_with("obs1 | obs2")
        
        assert gi.importance_sums.get("user_a") == 5
        assert gi.interaction_counts.get("user_a") == 2

@pytest.mark.asyncio
async def test_stop_gum_instance_stops_all_users():
    mock_instance_a = AsyncMock()
    mock_instance_a.stop_update_loop = AsyncMock()
    mock_instance_a.batcher = AsyncMock()
    
    mock_instance_b = AsyncMock()
    mock_instance_b.stop_update_loop = AsyncMock()
    mock_instance_b.batcher = AsyncMock()
    
    gi.gum_instances["user_a"] = mock_instance_a
    gi.gum_instances["user_b"] = mock_instance_b
    
    mock_obs_worker = AsyncMock()
    gi.obs_worker = mock_obs_worker
    gi.reflection_task = MagicMock()
    mock_reflection_task = gi.reflection_task
    
    await stop_gum_instance()
    
    mock_obs_worker.stop.assert_called_once()
    mock_reflection_task.cancel.assert_called_once()
    assert gi.obs_worker is None
    assert gi.reflection_task is None
    
    mock_instance_a.stop_update_loop.assert_called_once()
    mock_instance_a.batcher.stop.assert_called_once()
    
    mock_instance_b.stop_update_loop.assert_called_once()
    mock_instance_b.batcher.stop.assert_called_once()
