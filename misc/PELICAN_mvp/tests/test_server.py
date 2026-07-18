import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from pelican_mvp.server import app
import pelican_mvp.server as server_module

@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server_module, "data_dir", tmp_path)

client = TestClient(app)


def test_api_start() -> None:
    response = client.post("/api/start", json={"learner_id": "test_user"})
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "tree" in data
    assert isinstance(data["tree"], list)


def test_api_respond() -> None:
    client.post("/api/start", json={"learner_id": "test_user"})
    response = client.post(
        "/api/respond", json={"learner_id": "test_user", "answer": "1000"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "state_changes" in data


def test_api_mode_switching() -> None:
    response = client.post("/api/mode", json={"learner_id": "test_user", "mode": "rule"})
    assert response.status_code == 200
    assert response.json()["mode"] == "rule"

def test_api_mode_switching_400_format() -> None:
    response = client.post("/api/mode", json={"learner_id": "test_user", "mode": "invalid"})
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower() or "mode" in data["detail"].lower()

def test_api_reset_phase() -> None:
    # First advance it
    client.post("/api/start", json={"learner_id": "test_user"})
    client.post("/api/respond", json={"learner_id": "test_user", "answer": "100"})
    
    # Then reset and check
    response = client.post("/api/reset", json={"learner_id": "test_user"})
    assert response.status_code == 200
    data = response.json()
    assert "tree" in data
    
    # Verify state via internal inspection to ensure phase reset
    import pelican_mvp.server as server_module
    engine = server_module._get_engine("test_user")
    assert engine.state.phase == "diagnosis"

def test_server_concurrency() -> None:
    import threading
    import pelican_mvp.server as server_module
    
    # Verify that state_lock is indeed a standard threading lock
    lock_type = type(threading.Lock())
    assert isinstance(server_module.state_lock, lock_type)

def test_static_files() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
