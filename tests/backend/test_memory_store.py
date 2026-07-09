import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.memory_store import MemoryStore

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    
    store = {}
    
    async def fake_get(key):
        return store.get(key)
        
    async def fake_set(key, val):
        store[key] = val
        
    def fake_set_sync(key, val):
        store[key] = val
        
    redis.get = AsyncMock(side_effect=fake_get)
    redis.set = AsyncMock(side_effect=fake_set)
    
    pipe_mock = AsyncMock()
    pipe_mock.get = AsyncMock(side_effect=fake_get)
    pipe_mock.set = MagicMock(side_effect=fake_set_sync)
    pipe_mock.watch = AsyncMock()
    pipe_mock.multi = MagicMock()
    pipe_mock.execute = AsyncMock()
    
    class PipelineContext:
        def __init__(self, **kwargs):
            self.pipe = pipe_mock
            
        async def __aenter__(self):
            return self.pipe
            
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
            
    redis.pipeline = PipelineContext
    redis._store = store
    return redis

@pytest.fixture
def memory_store(mock_redis):
    with patch("backend.memory_store.get_redis", return_value=mock_redis):
        store = MemoryStore(budget_limit=1000)
        yield store

@pytest.mark.asyncio
async def test_update_hot_memory_isolation(memory_store, mock_redis):
    await memory_store.update_hot_memory("user_a", "key1", "val_a")
    await memory_store.update_hot_memory("user_b", "key1", "val_b")
    
    assert "areqa:hot_memory:user_a" in mock_redis._store
    assert "areqa:hot_memory:user_b" in mock_redis._store
    
    data_a = json.loads(mock_redis._store["areqa:hot_memory:user_a"])
    data_b = json.loads(mock_redis._store["areqa:hot_memory:user_b"])
    
    assert data_a["key1"] == "val_a"
    assert data_b["key1"] == "val_b"

@pytest.mark.asyncio
async def test_update_user_profile(memory_store, mock_redis):
    await memory_store.update_user_profile("student", "name", "國立臺灣大學中文系三年級")
    
    profile = await memory_store.get_user_profile("student")
    assert profile["name"] == "國立臺灣大學中文系三年級"

@pytest.mark.asyncio
async def test_override_memory(memory_store, mock_redis):
    await memory_store.update_hot_memory("user1", "林黛玉的丫鬟", "雪雁")
    mem1 = await memory_store.get_hot_memory("user1")
    assert mem1["林黛玉的丫鬟"] == "雪雁"
    
    await memory_store.update_hot_memory("user1", "林黛玉的丫鬟", "紫鵑")
    mem2 = await memory_store.get_hot_memory("user1")
    assert mem2["林黛玉的丫鬟"] == "紫鵑"

@pytest.mark.asyncio
async def test_get_learner_state(memory_store, mock_redis):
    state = await memory_store.get_learner_state("user2")
    assert state == "STARTING"
    
    await memory_store.update_hot_memory("user2", "current_learner_state", "CONFUSED")
    state2 = await memory_store.get_learner_state("user2")
    assert state2 == "CONFUSED"
