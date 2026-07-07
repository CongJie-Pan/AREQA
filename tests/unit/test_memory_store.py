import pytest
import json
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from memory_store import MemoryStore

@pytest.mark.asyncio
async def test_memory_store_isolation():
    mock_redis = AsyncMock()
    
    store_data = {}
    
    async def mock_get(key):
        return store_data.get(key)
        
    async def mock_set(key, value):
        store_data[key] = value
        
    mock_redis.get = mock_get
    mock_redis.set = mock_set
    
    with patch("memory_store.get_redis", return_value=mock_redis):
        store = MemoryStore()
        
        # User A writes data
        await store.update_hot_memory("user_A", "secret_key", "value_A")
        
        # User B reads data
        hot_b = await store.get_hot_memory("user_B")
        
        # Assert User B cannot read User A's data
        assert hot_b == {}
        
        # User A reads data
        hot_a = await store.get_hot_memory("user_A")
        assert hot_a["secret_key"] == "value_A"
