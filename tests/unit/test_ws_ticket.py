import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
import sys
from pathlib import Path
from starlette.websockets import WebSocketDisconnect

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from main import app

@pytest.fixture
def mock_store():
    store = MagicMock()
    store.redis = AsyncMock()
    store.redis.getdel.side_effect = [b"user_123", None]
    return store

def test_ws_ticket_getdel(mock_store):
    with patch("memory_store.get_global_store", return_value=mock_store):
        client = TestClient(app)
        
        # First connection should succeed (GETDEL returns user_123)
        # TestClient waits for connection, so it's fine.
        with client.websocket_connect("/api/v1/ws/notifications?ticket=valid_ticket", headers={"origin": "http://localhost:3000"}) as websocket:
            pass
            
        # Second connection should fail with 4001 (GETDEL returns None)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/ws/notifications?ticket=valid_ticket", headers={"origin": "http://localhost:3000"}) as websocket:
                pass
                
        assert exc.value.code == 4001
        assert mock_store.redis.getdel.call_count == 2
