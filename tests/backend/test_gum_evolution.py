import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from backend.gum_integration import push_observation
import backend.gum_integration

class MockProposition:
    def __init__(self, id, text, confidence, status="active"):
        self.id = id
        self.text = text
        self.confidence = confidence
        self.status = status
        self.updated_at = datetime.now()

@pytest.fixture
def mock_gum_instance():
    instance = MagicMock()
    
    # Mock search/recent returning old memory
    old_mem = MockProposition(1, "Student doesn't know loops", 0.9, status="active")
    instance.query = AsyncMock(return_value=[(old_mem, 0.95)])
    
    # Mock LLM evolution response (prune old memory)
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"should_evolve": true, "actions": ["prune"], "target_ids": [1], "importance_score": 10}'))
    ]
    instance.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    instance.update_status = AsyncMock()
    return instance

@pytest.mark.asyncio
async def test_memory_evolution_prune(mock_gum_instance):
    backend.gum_integration.gum_instance = mock_gum_instance
    
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        
        # New observation contradicts old memory
        await push_observation("Student has mastered loops")
        
        # Verify evolution check happened
        mock_gum_instance.query.assert_called_once()
        mock_gum_instance.client.chat.completions.create.assert_called_once()
        
        # Verify pruning action
        mock_gum_instance.update_status.assert_called_once_with(1, "superseded")
        
        # Verify text was pushed
        mock_text_observer.push_text.assert_called_once_with("Student has mastered loops")
        
    backend.gum_integration.gum_instance = None
