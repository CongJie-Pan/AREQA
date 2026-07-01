import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services.connection_manager import ConnectionManager
from fastapi import WebSocket

@pytest.fixture
def connection_manager():
    return ConnectionManager()

@pytest.mark.asyncio
async def test_connect(connection_manager):
    mock_ws = AsyncMock(spec=WebSocket)
    await connection_manager.connect("test_user", mock_ws)
    assert mock_ws.accept.called
    assert "test_user" in connection_manager.active
    assert connection_manager.active["test_user"] == mock_ws

@pytest.mark.asyncio
async def test_disconnect(connection_manager):
    mock_ws = AsyncMock(spec=WebSocket)
    await connection_manager.connect("test_user", mock_ws)
    connection_manager.disconnect("test_user")
    assert "test_user" not in connection_manager.active

@pytest.mark.asyncio
async def test_broadcast_alert_active_user(connection_manager):
    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.accept = AsyncMock()
    await connection_manager.connect("test_user", mock_ws)
    await connection_manager.broadcast_alert("test_user", "Test Alert")
    mock_ws.send_json.assert_awaited_once_with({"has_alert": True, "content": "Test Alert"})

@pytest.mark.asyncio
async def test_broadcast_alert_inactive_user(connection_manager):
    # Should not raise exception
    await connection_manager.broadcast_alert("nonexistent_user", "Test Alert")

@pytest.mark.asyncio
async def test_ws_origin_validation():
    from fastapi.testclient import TestClient
    from backend.main import app
    
    # We must use Starlette TestClient with with context to support websocket
    client = TestClient(app)
    
    # Test malicious origin
    from starlette.websockets import WebSocketDisconnect
    
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/ws/notifications", headers={"origin": "http://evil.com"}) as ws:
            ws.receive_text()
    
    assert exc_info.value.code == 1008
