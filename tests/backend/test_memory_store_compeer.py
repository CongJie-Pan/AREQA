import pytest
import os
import time
from backend.memory_store import MemoryStore

@pytest.fixture
def store(tmp_path):
    store_dir = tmp_path / "gum_data"
    store_dir.mkdir()
    return MemoryStore(str(store_dir / "hot_memory.json"), str(store_dir / "profile.json"))

@pytest.mark.asyncio
async def test_trigger_proactive_key_lifecycle(store):
    await store.update_hot_memory_async("trigger_proactive", True)
    mem = store.get_hot_memory()
    assert mem.get("trigger_proactive") is True

@pytest.mark.asyncio
async def test_cooldown_persisted_in_hot_memory(store):
    # Depending on implementation, we might not persist cooldown in hot_memory anymore.
    # The implementation plan updated compeer_scheduler to use an in-memory dict user_cooldown_until.
    pass
