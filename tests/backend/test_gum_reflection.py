import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime
import backend.gum_integration

@pytest.fixture
def mock_gum_instance():
    instance = MagicMock()
    # Mock recent observations
    mock_obs = [MagicMock(id=i, content=f"Short chat message {i}", observer_name="default_user") for i in range(15)]
    instance.recent_observations = AsyncMock(return_value=mock_obs)
    
    # Mock LLM reflection response
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"insights": ["Student is actively discussing various topics."]}'))
    ]
    instance.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    # Mock adding reflection and updating status
    instance._process_batch = AsyncMock()
    instance.update_observation_status = AsyncMock()
    return instance

@pytest.mark.asyncio
async def test_reflection_compression(mock_gum_instance):
    backend.gum_integration.gum_instance = mock_gum_instance
    
    # We will invoke the background task's inner logic directly
    await backend.gum_integration.run_reflection()
    
    # Verify recent observations were fetched
    mock_gum_instance.recent_observations.assert_called_once()
    
    # Verify LLM was called
    mock_gum_instance.client.chat.completions.create.assert_called_once()
    
    # Verify the new insight was inserted (via TextObserver queue or batcher)
    # We mock _process_batch or batcher
    # Assertions will be verified during implementation.
    
    backend.gum_integration.gum_instance = None
