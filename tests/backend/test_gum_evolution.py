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
        MagicMock(message=MagicMock(content='{"should_evolve": true, "actions": ["prune"], "target_ids": [1], "importance_score": 10, "revised_proposition": "Student has mastered loops", "decay_score": 8}'))
    ]
    instance.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    instance.update_status = AsyncMock()
    return instance

@pytest.mark.asyncio
@patch("backend.gum_integration.get_gum_instance", new_callable=AsyncMock)
async def test_memory_evolution_prune(mock_get_gum, mock_gum_instance):
    mock_text_observer = AsyncMock()
    mock_get_gum.return_value = (mock_gum_instance, mock_text_observer)

    # New observation contradicts old memory
    await push_observation("test_user", "Student has mastered loops")

    # Verify evolution check happened
    mock_gum_instance.query.assert_called_once()
    mock_gum_instance.client.chat.completions.create.assert_called_once()

    # Verify pruning action
    mock_gum_instance.update_status.assert_called_once_with(1, "superseded")

    # Verify text was pushed
    mock_text_observer.push_text.assert_called_once_with("Student has mastered loops")

@pytest.mark.asyncio
@patch("backend.gum_integration.get_gum_instance", new_callable=AsyncMock)
async def test_memory_evolution_bm25_fallback_and_markdown(mock_get_gum, mock_gum_instance):
    # Setup BM25 to fail (return empty)
    mock_gum_instance.query = AsyncMock(return_value=[])
    
    # Setup fallback recent memory
    old_mem = MockProposition(2, "Old memory", 0.9)
    mock_gum_instance.recent = AsyncMock(return_value=[old_mem])
    
    # Setup Markdown JSON response
    markdown_json = "```json\n{\"should_evolve\": true, \"actions\": [\"prune\"], \"target_ids\": [2], \"importance_score\": 8, \"revised_proposition\": \"Revised memory\", \"decay_score\": 3}\n```"
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=markdown_json))
    ]
    mock_gum_instance.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    backend.gum_integration.importance_sums = {}
    
    mock_text_observer = AsyncMock()
    mock_get_gum.return_value = (mock_gum_instance, mock_text_observer)

    await push_observation("test_user", "New observation")

    # Verify fallback was triggered
    mock_gum_instance.query.assert_called_once_with("New observation", limit=20)
    mock_gum_instance.recent.assert_called_once_with(limit=20)

    # Verify markdown parsing and pruning
    mock_gum_instance.update_status.assert_called_once_with(2, "superseded")

    # Verify importance sum updated correctly
    assert backend.gum_integration.importance_sums.get("test_user", 0) == 8
