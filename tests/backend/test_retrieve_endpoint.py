import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app

client = TestClient(app)

def test_retrieve_endpoint_success():
    # Mock RAGService
    mock_rag = MagicMock()
    mock_result = MagicMock()
    mock_result.text = "賈寶玉是紅樓夢的主角。"
    mock_result.score = 0.95
    mock_result.source = "紅樓夢"
    mock_result.chunk_id = "chunk_1"
    
    mock_rag.retrieve.return_value = [mock_result]
    
    with patch("backend.main.rag_service", mock_rag):
        response = client.get("/api/v1/retrieve?query=賈寶玉")
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 1
        assert data["results"][0]["text"] == "賈寶玉是紅樓夢的主角。"
        assert data["results"][0]["score"] == 0.95
        assert data["total"] == 1

def test_retrieve_endpoint_no_service():
    with patch("backend.main.rag_service", None):
        response = client.get("/api/v1/retrieve?query=test")
        assert response.status_code == 200
        assert response.json()["error"] == "RAG service not initialized"

def test_retrieve_endpoint_error():
    mock_rag = MagicMock()
    mock_rag.retrieve.side_effect = Exception("FAISS Error")
    
    with patch("backend.main.rag_service", mock_rag):
        response = client.get("/api/v1/retrieve?query=test")
        assert response.status_code == 200
        assert "error" in response.json()
        assert "FAISS Error" in response.json()["error"]
