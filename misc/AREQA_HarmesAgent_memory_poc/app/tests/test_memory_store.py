import os
import tempfile
import pytest
import json
from unittest.mock import patch
from app.memory_store import MemoryStore

@pytest.fixture
def temp_memory_store():
    # 使用臨時資料夾來測試
    with tempfile.TemporaryDirectory() as tmpdir:
        # Patch MEMORY_DIR 使其指向臨時資料夾
        with patch("app.memory_store.MEMORY_DIR", tmpdir):
            store = MemoryStore()
            yield store, tmpdir

def test_basic_crud(temp_memory_store):
    store, _ = temp_memory_store
    
    # 測試新增 (Add)
    res = store.add("user", "Hello World")
    assert res["success"] is True
    assert store.get_raw_memories("user") == ["Hello World"]
    
    # 測試替換 (Replace)
    res = store.replace("user", "Hello World", "Hi World")
    assert res["success"] is True
    assert store.get_raw_memories("user") == ["Hi World"]
    
    # 測試刪除 (Remove)
    res = store.remove("user", "Hi World")
    assert res["success"] is True
    assert store.get_raw_memories("user") == []

def test_character_limit(temp_memory_store):
    store, _ = temp_memory_store
    
    # 為了容易測試，動態修改限制
    store.memory_char_limit = 50
    
    # 新增 40 個字元
    res = store.add("memory", "A" * 40)
    assert res["success"] is True
    
    # 再新增 20 個字元，預期會超過上限而失敗
    res = store.add("memory", "B" * 20)
    assert res["success"] is False
    assert "Memory full" in res.get("error", "")

def test_separator_parsing(temp_memory_store):
    store, _ = temp_memory_store
    
    # 測試惡意分隔符號與換行，驗證 JSONL 的強健性
    malicious_string = "Line1\n§\nLine2"
    res = store.add("memory", malicious_string)
    assert res["success"] is True
    
    memories = store.get_raw_memories("memory")
    assert len(memories) == 1
    assert memories[0] == malicious_string
    
    # 載入快照，確保 Markdown 生成邏輯不會崩潰
    store.load_from_disk()
    snapshot = store.get_snapshot("memory")
    assert "Line1" in snapshot

def test_atomic_write(temp_memory_store):
    store, tmpdir = temp_memory_store
    
    # 預先塞入資料
    store.add("memory", "Original Data")
    path = store._get_path("memory")
    assert os.path.exists(path)
    
    with open(path, "r", encoding="utf-8") as f:
        original_content = f.read()
        
    # Mock os.replace 模擬寫入到一半當機
    def mock_replace(src, dst):
        raise RuntimeError("Simulated crash during atomic write")
        
    with patch("os.replace", side_effect=mock_replace):
        with pytest.raises(RuntimeError):
            store.add("memory", "New Data")
            
    # 驗證原始檔案依然完好無損
    with open(path, "r", encoding="utf-8") as f:
        content_after_crash = f.read()
        
    assert content_after_crash == original_content
