import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.gum_integration import (
    detect_proactive_event_via_llm,
    generate_scaffolding_message_via_llm,
    run_reflection
)
import backend.gum_integration as gi

@pytest.fixture(autouse=True)
def mock_gum_instance():
    mock_instance = MagicMock()
    mock_instance.client.chat.completions.create = AsyncMock()
    mock_instance.model = "test-model"
    with patch.object(gi, "gum_instance", mock_instance, create=True), \
         patch("backend.gum_integration.get_gum_instance", new_callable=AsyncMock) as mock_get_gum:
        mock_get_gum.return_value = (mock_instance, AsyncMock())
        yield mock_instance

@pytest.mark.asyncio
async def test_detect_event_returns_no_event_for_normal_browsing(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"has_event": false, "event_summary": "", "importance": 0.0}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    result = await detect_proactive_event_via_llm("test_user", "Snapshot data")
    assert result["has_event"] is False
    assert result["importance"] == 0.0

@pytest.mark.asyncio
async def test_detect_event_returns_event_for_frustrated_user(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"has_event": true, "event_summary": "User stuck on poem", "importance": 0.8}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    result = await detect_proactive_event_via_llm("test_user", "Snapshot data")
    assert result["has_event"] is True
    assert result["importance"] == 0.8
    assert result["event_summary"] == "User stuck on poem"

@pytest.mark.asyncio
async def test_detect_event_handles_llm_timeout_gracefully(mock_gum_instance):
    mock_gum_instance.client.chat.completions.create.side_effect = Exception("Timeout")
    
    result = await detect_proactive_event_via_llm("test_user", "Snapshot data")
    assert result["has_event"] is False
    assert result["importance"] == 0.0

@pytest.mark.asyncio
async def test_generate_scaffolding_returns_string(mock_gum_instance):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='這是一條測試訊息'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    result = await generate_scaffolding_message_via_llm(
        user_id="test_user",
        hot_memory_snapshot="hot",
        cold_memory_context="cold",
        learner_state="NORMAL",
        edf_policy="STRICT"
    )
    assert result == "這是一條測試訊息"

@pytest.mark.asyncio
async def test_run_reflection_returns_insights_list(mock_gum_instance):
    # Mock recent observations
    obs1 = MagicMock(id="1", content="Obs 1")
    obs2 = MagicMock(id="2", content="Obs 2")
    mock_gum_instance.recent_observations = AsyncMock(return_value=[obs1, obs2])
    mock_gum_instance.update_observation_status = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"insights": ["Insight 1", "Insight 2"]}'))]
    mock_gum_instance.client.chat.completions.create.return_value = mock_response
    
    insights = await run_reflection(user_id="test_user")
    
    assert len(insights) == 2
    assert insights[0] == "Insight 1"
    assert mock_gum_instance.update_observation_status.call_count == 2
