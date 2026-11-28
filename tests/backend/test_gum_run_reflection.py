import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.memory.gum.runtime import run_reflection
import services.memory.gum.runtime as gi

@pytest.fixture(autouse=True)
def mock_gum_instance():
    mock_instance = MagicMock()
    mock_instance.client.chat.completions.create = AsyncMock()
    mock_instance.model = "test-model"
    with patch.object(gi, "gum_instance", mock_instance, create=True), \
         patch("services.memory.gum.runtime.get_gum_instance", new_callable=AsyncMock) as mock_get_gum:
        mock_get_gum.return_value = (mock_instance, AsyncMock())
        yield mock_instance

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
    
    with patch("services.memory.store.service.get_global_store", return_value=None):
        insights = await run_reflection(user_id="test_user")
    
    assert len(insights) == 2
    assert insights[0] == "Insight 1"
    assert mock_gum_instance.update_observation_status.call_count == 2
