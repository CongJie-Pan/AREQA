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
    with patch("backend.gum_integration.gum") as mock_gum, \
         patch("backend.gum_integration.asyncio.create_task") as mock_create_task:
        mock_instance = MagicMock()
        mock_instance.connect_db = AsyncMock()
        mock_instance.stop_update_loop = AsyncMock()
        mock_instance.batcher.start = AsyncMock()
        mock_instance.batcher.stop = AsyncMock()
        mock_gum.return_value = mock_instance
        
        mock_task = MagicMock()
        mock_create_task.return_value = mock_task
        
        instance = await init_gum_instance()
        
        assert instance is mock_instance
        mock_instance.connect_db.assert_called_once()
        mock_instance.start_update_loop.assert_called_once()
        assert mock_create_task.call_count >= 1
        
        await stop_gum_instance()
        mock_instance.stop_update_loop.assert_called_once()
        mock_task.cancel.assert_called_once()

@pytest.mark.asyncio
async def test_push_observation():
    # Test pushing when gum_instance is None
    backend.gum_integration.gum_instance = None
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("test observation text")
        # Since gum_instance is None, it should return early and NOT call push_text
        mock_text_observer.push_text.assert_not_called()
        
    # Test pushing when gum_instance is present but no neighbors
    mock_gum = MagicMock()
    mock_gum.query = AsyncMock(return_value=[])
    backend.gum_integration.gum_instance = mock_gum
    
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("test observation text")
        mock_gum.query.assert_called_once_with("test observation text", limit=20)
        mock_text_observer.push_text.assert_called_once_with("test observation text")
        
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_push_observation_with_evolution():
    # Test pushing when gum_instance is present and has neighbors
    mock_gum = MagicMock()
    mock_gum.query = AsyncMock(return_value=[
        (MockProposition(1, "User hates apples", 0.9), 1.0)
    ])
    
    # Mock the LLM decision to supersede ID 1
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"should_evolve": true, "actions": ["prune"], "target_ids": [1], "importance_score": 8}'))
    ]
    mock_gum.client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_gum.update_status = AsyncMock()
    
    backend.gum_integration.gum_instance = mock_gum
    
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("User loves apples now")
        
        mock_gum.query.assert_called_once_with("User loves apples now", limit=20)
        # Should call LLM for evolution
        mock_gum.client.chat.completions.create.assert_called_once()
        # Should update status of ID 1 to superseded
        mock_gum.update_status.assert_called_once_with(1, "superseded")
        # Should push the new text
        mock_text_observer.push_text.assert_called_once_with("User loves apples now")
        
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_push_observation_with_evolution_no_prune():
    # Test pushing when gum_instance has neighbors but new topic is unrelated
    mock_gum = MagicMock()
    mock_gum.query = AsyncMock(return_value=[
        (MockProposition(1, "User loves apples", 0.9), 1.0)
    ])
    
    # Mock the LLM decision to NOT supersede (different topic)
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"should_evolve": false, "actions": [], "target_ids": [], "importance_score": 4}'))
    ]
    mock_gum.client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_gum.update_status = AsyncMock()
    
    backend.gum_integration.gum_instance = mock_gum
    
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("User asks about the weather")
        
        mock_gum.query.assert_called_once_with("User asks about the weather", limit=20)
        # Should call LLM for evolution
        mock_gum.client.chat.completions.create.assert_called_once()
        # Should NOT update status since should_evolve is false
        mock_gum.update_status.assert_not_called()
        # Should push the new text
        mock_text_observer.push_text.assert_called_once_with("User asks about the weather")
        
    backend.gum_integration.gum_instance = None

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
