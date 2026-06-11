import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from backend.gum_integration import (
    init_gum_instance,
    stop_gum_instance,
    push_observation,
    get_all_memory,
    get_suggestions,
    TextObserver,
)
import backend.gum_integration

# Mock proposition class
class MockProposition:
    def __init__(self, id, text, confidence):
        self.id = id
        self.text = text
        self.confidence = confidence
        self.updated_at = datetime.now()

@pytest.fixture
def mock_gum_instance():
    instance = MagicMock()
    instance.recent = AsyncMock(return_value=[
        MockProposition(1, "test user likes apples", 0.9),
        MockProposition(2, "test user hates oranges", 0.8),
    ])
    
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"suggestions": ["test suggestion 1", "test suggestion 2"]}'))
    ]
    instance.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    instance.connect_db = AsyncMock()
    instance.start_update_loop = MagicMock()
    instance.stop_update_loop = AsyncMock()
    
    instance.batcher = MagicMock()
    instance.batcher.start = AsyncMock()
    instance.batcher.stop = AsyncMock()
    return instance

@pytest.mark.asyncio
async def test_init_and_stop_gum_instance():
    with patch("backend.gum_integration.gum") as mock_gum:
        mock_instance = MagicMock()
        mock_instance.connect_db = AsyncMock()
        mock_instance.stop_update_loop = AsyncMock()
        mock_instance.batcher.start = AsyncMock()
        mock_instance.batcher.stop = AsyncMock()
        mock_gum.return_value = mock_instance
        
        instance = await init_gum_instance()
        
        assert instance is mock_instance
        mock_instance.connect_db.assert_called_once()
        mock_instance.start_update_loop.assert_called_once()
        
        await stop_gum_instance()
        mock_instance.stop_update_loop.assert_called_once()

@pytest.mark.asyncio
async def test_push_observation():
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("test observation text")
        mock_text_observer.push_text.assert_called_once_with("test observation text")

@pytest.mark.asyncio
async def test_get_all_memory(mock_gum_instance):
    backend.gum_integration.gum_instance = mock_gum_instance
    
    memory = await get_all_memory()
    
    assert len(memory) == 2
    assert memory[0]["id"] == 1
    assert memory[0]["text"] == "test user likes apples"
    assert memory[0]["confidence"] == 0.9
    assert "updated_at" in memory[0]
    mock_gum_instance.recent.assert_called_once_with(limit=100)
    
    # cleanup
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_get_suggestions(mock_gum_instance):
    backend.gum_integration.gum_instance = mock_gum_instance
    
    suggestions = await get_suggestions()
    
    assert len(suggestions) == 2
    assert suggestions[0] == "test suggestion 1"
    assert suggestions[1] == "test suggestion 2"
    mock_gum_instance.client.chat.completions.create.assert_called_once()
    
    # cleanup
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_get_all_memory_no_instance():
    backend.gum_integration.gum_instance = None
    memory = await get_all_memory()
    assert memory == []

@pytest.mark.asyncio
async def test_get_suggestions_no_instance():
    backend.gum_integration.gum_instance = None
    suggestions = await get_suggestions()
    assert suggestions == []
