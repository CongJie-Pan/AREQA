import pytest
import asyncio
from unittest.mock import AsyncMock

# We will mock the batch processor function that would normally be called by the debounce worker
from backend.gum_integration import ObservationQueueWorker

@pytest.fixture
def mock_processor():
    return AsyncMock()

import pytest_asyncio

@pytest_asyncio.fixture
async def worker(mock_processor):
    w = ObservationQueueWorker(process_callback=mock_processor, debounce_seconds=0.1) # Use 0.1s for faster tests
    await w.start()
    yield w
    await w.stop()

@pytest.mark.asyncio
async def test_debounce_multiple_pushes(worker, mock_processor):
    # Push 3 observations quickly
    await worker.push("user1", "obs1")
    await worker.push("user1", "obs2")
    await worker.push("user1", "obs3")
    
    # Wait for debounce window (0.1s) + buffer
    await asyncio.sleep(0.2)
    
    # Should only trigger processor once with all 3 items
    assert mock_processor.call_count == 1
    mock_processor.assert_called_once_with("user1", ["obs1", "obs2", "obs3"])

@pytest.mark.asyncio
async def test_debounce_spaced_pushes(worker, mock_processor):
    # Push 1 observation
    await worker.push("user1", "obs1")
    
    # Wait longer than debounce window (0.1s)
    await asyncio.sleep(0.2)
    
    # Push 2nd observation
    await worker.push("user1", "obs2")
    
    # Wait for second debounce window
    await asyncio.sleep(0.2)
    
    # Should trigger processor twice
    assert mock_processor.call_count == 2
    mock_processor.assert_any_call("user1", ["obs1"])
    mock_processor.assert_any_call("user1", ["obs2"])
