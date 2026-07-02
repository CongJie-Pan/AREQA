import pytest
import time
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import backend.services.compeer_scheduler as compeer
from backend.memory_store import init_global_store

@pytest.fixture(autouse=True)
def reset_cooldown():
    compeer.user_cooldown_until.clear()
    yield
    compeer.user_cooldown_until.clear()

def test_is_in_cooldown_false_when_no_entry():
    assert compeer.is_in_cooldown("default_user") is False

def test_is_in_cooldown_true_within_period():
    compeer.user_cooldown_until["default_user"] = time.time() + 3600
    assert compeer.is_in_cooldown("default_user") is True

def test_is_in_cooldown_false_after_expiry():
    compeer.user_cooldown_until["default_user"] = time.time() - 3600
    assert compeer.is_in_cooldown("default_user") is False

def test_set_cooldown_stores_correct_timestamp():
    compeer.set_cooldown("default_user", state="default")
    expected = time.time() + 1800
    assert abs(compeer.user_cooldown_until["default_user"] - expected) < 5

@pytest.mark.asyncio
async def test_evaluate_importance_gate_passes_high_importance():
    event = {"importance": 0.999}
    passes = 0
    for _ in range(100):
        if await compeer.evaluate_importance_gate(event):
            passes += 1
    assert passes > 90

@pytest.mark.asyncio
async def test_evaluate_importance_gate_fails_low_importance():
    event = {"importance": 0.0}
    for _ in range(10):
        assert await compeer.evaluate_importance_gate(event) is False

@pytest.fixture
def mock_store(tmp_path):
    store_dir = tmp_path / "gum_data"
    store_dir.mkdir()
    from memory_store import init_global_store, get_global_store
    init_global_store(str(store_dir / "hot_memory.json"), str(store_dir / "profile.json"))
    return get_global_store()

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.asyncio.sleep", new_callable=AsyncMock)
@patch("services.connection_manager.ws_manager.broadcast_alert", new_callable=AsyncMock)
@patch("gum_integration.generate_scaffolding_message_via_llm", new_callable=AsyncMock)
@patch("gum_integration.query_cold_memory_for_context", new_callable=AsyncMock)
async def test_trigger_proactive_consumed_from_hot_memory(mock_query, mock_gen, mock_broadcast, mock_sleep, mock_store):
    # Setup hot memory with trigger_proactive = True
    await mock_store.update_hot_memory_async("trigger_proactive", True)
    await mock_store.update_hot_memory_async("current_learner_state", "GIVING_UP")
    
    mock_gen.return_value = "Test Scaffolding Message"
    mock_query.return_value = "Mocked cold context"
    
    # We want proactive_scheduler_loop to run one iteration and then raise an exception to exit the infinite loop
    # In compeer_scheduler, there are two sleeps. We side_effect both.
    mock_sleep.side_effect = [None, Exception("Stop Loop"), Exception("Stop Loop")]
    
    with pytest.raises(Exception, match="Stop Loop"):
        await compeer.proactive_scheduler_loop()

    # Yield to event loop to allow asyncio.create_task to execute
    for _ in range(5):
        await mock_store.update_hot_memory_async("dummy", True)
        
    hot_mem = mock_store.get_hot_memory()
    assert "trigger_proactive" not in hot_mem
    mock_broadcast.assert_called_once_with("default_user", "Test Scaffolding Message")
    assert compeer.is_in_cooldown("default_user") is True

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.asyncio.sleep", new_callable=AsyncMock)
@patch("backend.services.connection_manager.ws_manager.broadcast_alert", new_callable=AsyncMock)
async def test_no_trigger_when_in_cooldown(mock_broadcast, mock_sleep, mock_store):
    await mock_store.update_hot_memory_async("trigger_proactive", True)
    compeer.set_cooldown("default_user", state="MASTERY")
    
    mock_sleep.side_effect = [None, Exception("Stop Loop"), Exception("Stop Loop")]
    
    with pytest.raises(Exception, match="Stop Loop"):
        await compeer.proactive_scheduler_loop()
        
    # Since in cooldown, shouldn't consume trigger or broadcast
    hot_mem = mock_store.get_hot_memory()
    assert "trigger_proactive" in hot_mem
    assert mock_broadcast.called is False
