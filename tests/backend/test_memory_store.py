import json
import os
import pytest
from backend.memory_store import MemoryStore, MemoryBudgetExceeded

@pytest.fixture
def temp_memory_store(tmp_path):
    hot_memory_path = tmp_path / "hot_memory.json"
    user_profile_path = tmp_path / "user_profile.json"
    
    # Initialize empty stores
    hot_memory_path.write_text(json.dumps({}))
    user_profile_path.write_text(json.dumps({}))
    
    store = MemoryStore(
        hot_memory_path=str(hot_memory_path),
        user_profile_path=str(user_profile_path),
        budget_limit=1000
    )
    return store, hot_memory_path, user_profile_path

def test_check_budget_success(temp_memory_store):
    store, _, _ = temp_memory_store
    
    # Writing normal amount of data should pass
    store.update_hot_memory("key1", "A" * 500)
    assert len(json.dumps(store.get_hot_memory())) < 1000
    
def test_check_budget_exceeded(temp_memory_store):
    store, _, _ = temp_memory_store
    
    with pytest.raises(MemoryBudgetExceeded):
        store.update_hot_memory("key1", "A" * 1500)

def test_user_profile_isolation(temp_memory_store):
    store, _, _ = temp_memory_store
    
    store.update_user_profile("student", "國立臺灣大學中文系三年級")
    assert store.get_user_profile()["student"] == "國立臺灣大學中文系三年級"
    
    # Overloading hot memory should not affect user profile
    with pytest.raises(MemoryBudgetExceeded):
        store.update_hot_memory("key1", "A" * 1500)
        
    assert store.get_user_profile()["student"] == "國立臺灣大學中文系三年級"

def test_override_memory(temp_memory_store):
    store, _, _ = temp_memory_store
    
    # a=b
    store.update_hot_memory("林黛玉的丫鬟", "雪雁")
    assert store.get_hot_memory()["林黛玉的丫鬟"] == "雪雁"
    
    # a=c (Override)
    store.update_hot_memory("林黛玉的丫鬟", "紫鵑")
    assert store.get_hot_memory()["林黛玉的丫鬟"] == "紫鵑"

def test_atomic_write(temp_memory_store, monkeypatch):
    store, hot_path, _ = temp_memory_store
    
    # Pre-populate
    store.update_hot_memory("test", "data")
    
    # Mock os.replace to simulate failure during atomic write
    monkeypatch.setattr(os, "replace", lambda src, dst: (_ for _ in ()).throw(Exception("Simulated interruption")))
    
    with pytest.raises(Exception):
        store.update_hot_memory("test", "new_data")
        
    # Original file should still be intact and not corrupted
    assert json.loads(hot_path.read_text()) == {"test": "data"}
