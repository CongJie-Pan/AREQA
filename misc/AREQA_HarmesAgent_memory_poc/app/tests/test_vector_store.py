import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from app.vector_store import VectorStore

@pytest.fixture
def mock_vector_store():
    # Setup mock for OpenAI API
    with patch("app.vector_store.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_response = MagicMock()
        # Mocking an embedding of size 4096 (Qwen3-Embedding-8B default)
        mock_response.data = [MagicMock(embedding=[0.01] * 4096)]
        mock_client.embeddings.create.return_value = mock_response
        MockOpenAI.return_value = mock_client
        
        # Create VectorStore
        store = VectorStore()
        
        # Override DB path for testing
        fd, tmp_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        
        # Re-initialize with temp db
        store.db.close()
        store.db_path = tmp_path
        store._init_db()
        
        yield store
        
        # Teardown
        store.db.close()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def test_demote_and_search(mock_vector_store):
    # Demote a new memory
    mock_vector_store.demote_to_cold_memory("memory", "國小老師張美麗喜歡吃香蕉")
    
    # Assert virtual table was created
    cursor = mock_vector_store.db.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vec_memories'")
    assert cursor.fetchone() is not None
    
    # Assert data was inserted into memory_text
    cursor.execute("SELECT content FROM memory_text")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "國小老師張美麗喜歡吃香蕉"
    
    # Search for it
    results = mock_vector_store.search_cold_memory("張美麗喜歡吃什麼？", top_k=1)
    assert len(results) == 1
    assert "張美麗喜歡吃香蕉" in results[0]

def test_duplicate_demotion_ignored(mock_vector_store):
    mock_vector_store.demote_to_cold_memory("memory", "重複的記憶")
    mock_vector_store.demote_to_cold_memory("memory", "重複的記憶")
    
    cursor = mock_vector_store.db.cursor()
    cursor.execute("SELECT COUNT(*) FROM memory_text")
    count = cursor.fetchone()[0]
    
    # Should only be inserted once
    assert count == 1
