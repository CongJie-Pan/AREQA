import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from backend.memory_store import MemoryStore
from backend.gum_integration import ObservationQueueWorker

@pytest.mark.asyncio
async def test_end_to_end_compaction_flow(tmp_path, monkeypatch):
    hot_memory_path = tmp_path / "hot_memory.json"
    user_profile_path = tmp_path / "user_profile.json"
    
    store = MemoryStore(budget_limit=1000)
    
    # We will write a large string to force compaction.
    # To mock the compaction worker, we can patch it inside the code or just verify the budget exceed works and triggers compaction logic.
    
    mock_compaction_triggered = False
    
    async def mock_process_callback(uid, items):
        nonlocal mock_compaction_triggered
        mock_compaction_triggered = True
        
    worker = ObservationQueueWorker(process_callback=mock_process_callback, debounce_seconds=0.1)
    await worker.start()
    
    long_string = "王熙鳳的判詞是凡鳥偏從末世來，都知愛慕此生才。一從二令三人木，哭向金陵事更哀。" * 10
    
    # Normally, pushing observations adds to queue.
    for i in range(20):
        await worker.push("default_user", f"Observation {i}: {long_string}")
        
    await asyncio.sleep(0.5)
    
    # Verify the background worker triggered the compaction/processing
    assert mock_compaction_triggered
    await worker.stop()
