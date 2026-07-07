import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
from starlette.websockets import WebSocketDisconnect

sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from main import app

def test_ws_origin_rejection():
    client = TestClient(app)
    
    # Invalid origin should be rejected with 4001
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/ws/notifications?ticket=dummy", headers={"origin": "http://malicious.com"}) as ws:
            pass
            
    assert exc.value.code == 4001
