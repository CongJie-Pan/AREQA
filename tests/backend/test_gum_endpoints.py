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


def test_get_memory_endpoint_error():
    with patch("backend.main.get_all_memory") as mock_get_memory:
        mock_get_memory.return_value = []
        response = client.get("/api/v1/memory")
        assert response.status_code == 200
        assert response.json() == {"propositions": []}

def test_delete_memory_endpoint():
    with patch("gum_integration.gum_instance") as mock_gum_instance:
        from unittest.mock import AsyncMock
        mock_gum_instance.update_status = AsyncMock()
        
        response = client.delete("/api/v1/memory/123")
        assert response.status_code == 200
        assert response.json() == {"status": "success"}
        mock_gum_instance.update_status.assert_called_once_with(123, "deleted")

def test_edit_memory_endpoint():
    with patch("gum_integration.gum_instance") as mock_gum_instance:
        from unittest.mock import AsyncMock
        mock_gum_instance.update_text = AsyncMock()
        
        response = client.put("/api/v1/memory/456", json={"text": "Updated text"})
        assert response.status_code == 200
        assert response.json() == {"status": "success"}
        mock_gum_instance.update_text.assert_called_once_with(456, "Updated text")
