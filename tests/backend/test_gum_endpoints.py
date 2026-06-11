import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.main import app
# Clear startup/shutdown events to prevent TestClient from hanging on GUM DB initialization
app.router.on_startup.clear()
app.router.on_shutdown.clear()

client = TestClient(app)

def test_get_memory_endpoint_success():
    with patch("backend.main.get_all_memory") as mock_get_memory:
        mock_get_memory.return_value = [{"content": "user likes testing", "type": "proposition"}]
        response = client.get("/api/v1/memory")
        assert response.status_code == 200
        assert response.json() == {"propositions": [{"content": "user likes testing", "type": "proposition"}]}

def test_get_suggestions_endpoint_success():
    with patch("backend.main.get_suggestions") as mock_get_suggestions:
        mock_get_suggestions.return_value = [{"topic": "test writing", "reason": "user recently asked about testing"}]
        response = client.get("/api/v1/suggestions")
        assert response.status_code == 200
        assert response.json() == {"suggestions": [{"topic": "test writing", "reason": "user recently asked about testing"}]}

def test_get_memory_endpoint_error():
    with patch("backend.main.get_all_memory") as mock_get_memory:
        mock_get_memory.return_value = []
        response = client.get("/api/v1/memory")
        assert response.status_code == 200
        assert response.json() == {"propositions": []}
