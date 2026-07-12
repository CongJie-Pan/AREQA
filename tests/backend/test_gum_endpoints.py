import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from backend.main import app, get_current_user, _memory_source_id
# Clear startup/shutdown events to prevent TestClient from hanging on GUM DB initialization
app.router.on_startup.clear()
app.router.on_shutdown.clear()

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: "default_user"
    yield
    app.dependency_overrides.pop(get_current_user, None)

def test_get_memory_endpoint_success():
    with patch("backend.main.get_all_memory") as mock_get_memory:
        mock_get_memory.return_value = [{"content": "user likes testing", "type": "proposition"}]
        response = client.get("/api/v1/memory")
        assert response.status_code == 200
        assert response.json() == {
            "propositions": [{"content": "user likes testing", "type": "proposition"}],
            "profile_memories": [],
            "candidates": [],
            "learning_state": [{"content": "user likes testing", "type": "proposition"}],
        }


def test_get_memory_endpoint_error():
    with patch("backend.main.get_all_memory") as mock_get_memory:
        mock_get_memory.return_value = []
        response = client.get("/api/v1/memory")
        assert response.status_code == 200
        assert response.json() == {
            "propositions": [],
            "profile_memories": [],
            "candidates": [],
            "learning_state": [],
        }


def test_get_memory_endpoint_merges_profile_and_cold_candidates():
    mock_store = AsyncMock()
    mock_store.get_user_profile.return_value = {"explicit_memories": ["喜歡例子"]}
    mock_store.get_cold_candidates.return_value = [{
        "text": "最近在學習判詞",
        "category": "session_reflection",
        "source": "reflection",
        "confidence": 9.0,
        "created_at": "2026-07-12T00:00:00+00:00",
        "last_seen_at": "2026-07-12T00:01:00+00:00",
        "status": "candidate",
    }]

    with patch("backend.main.get_all_memory", return_value=[{
        "id": "7",
        "text": "喜歡古典文學",
        "confidence": 0.8,
        "updated_at": None,
    }]), patch("memory_store.get_global_store", return_value=mock_store):
        response = client.get("/api/v1/memory")

    assert response.status_code == 200
    propositions = response.json()["propositions"]
    assert {item["text"] for item in propositions} == {
        "喜歡古典文學",
        "喜歡例子",
        "最近在學習判詞",
    }
    assert any(item["id"].startswith("profile:explicit:") for item in propositions)
    assert any(item["id"].startswith("candidate:") for item in propositions)

def test_memory_debug_endpoint_returns_memory_layers():
    mock_store = AsyncMock()
    mock_store.get_user_profile.return_value = {"explicit_memories": ["喜歡例子"]}
    mock_store.get_hot_memory.return_value = {"current_learner_state": "TINKERING"}
    mock_store.get_working_memory.return_value = {"current_focus": "判詞"}
    mock_store.get_behavior_signals.return_value = [{"type": "scroll"}]
    mock_store.get_cold_candidates.return_value = [{"text": "reflection insight"}]

    with patch("memory_store.get_global_store", return_value=mock_store), \
         patch("gum_integration.get_hot_memory_snapshot", new_callable=AsyncMock, return_value="snapshot"):
        response = client.get("/api/v1/memory/debug")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["user_id"] == "default_user"
    assert data["profile"]["explicit_memories"] == ["喜歡例子"]
    assert data["hot_memory"]["current_learner_state"] == "TINKERING"
    assert data["working_memory"]["current_focus"] == "判詞"
    assert data["behavior_signals"] == [{"type": "scroll"}]
    assert data["cold_candidates"] == [{"text": "reflection insight"}]
    assert data["prompt_snapshot"] == "snapshot"

def test_delete_memory_endpoint():
    with patch("gum_integration.get_gum_instance", new_callable=AsyncMock) as mock_get_gum:
        mock_gum_instance = AsyncMock()
        mock_get_gum.return_value = (mock_gum_instance, AsyncMock())
        mock_gum_instance.update_status = AsyncMock()
        
        response = client.delete("/api/v1/memory/123")
        assert response.status_code == 200
        assert response.json() == {"status": "success"}
        mock_get_gum.assert_called_once_with("default_user")
        mock_gum_instance.update_status.assert_called_once_with(123, "deleted")


def test_delete_profile_memory_succeeds_when_working_sync_fails():
    mock_store = AsyncMock()
    mock_store.get_user_profile.return_value = {"explicit_memories": ["測試 profile 記憶"]}
    mock_store.update_working_memory.side_effect = RuntimeError("working cache unavailable")
    memory_id = _memory_source_id("profile:explicit", "測試 profile 記憶")

    with patch("memory_store.get_global_store", return_value=mock_store):
        response = client.delete(f"/api/v1/memory/{memory_id}")

    assert response.status_code == 200
    assert response.json() == {"status": "success"}
    mock_store.redis.set.assert_awaited_once()


def test_delete_profile_memory_returns_404_when_id_is_unknown():
    mock_store = AsyncMock()
    mock_store.get_user_profile.return_value = {"explicit_memories": []}

    with patch("memory_store.get_global_store", return_value=mock_store):
        response = client.delete("/api/v1/memory/profile:explicit:unknown")

    assert response.status_code == 404


def test_clear_working_memory_endpoint():
    mock_store = AsyncMock()

    with patch("memory_store.get_global_store", return_value=mock_store):
        response = client.delete("/api/v1/memory/working")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "cleared": "working_memory"}
    mock_store.clear_working_memory.assert_awaited_once_with("default_user")


def test_confirm_candidate_promotes_with_user_confirmation():
    candidate = {"hash": "candidate-hash", "text": "偏好範例", "status": "candidate", "requires_confirmation": True}
    mock_store = AsyncMock()
    mock_store.get_cold_candidates.return_value = [candidate]
    mock_store.promote_cold_candidate.return_value = {**candidate, "status": "promoted"}
    memory_id = _memory_source_id("candidate", candidate["text"])

    with patch("memory_store.get_global_store", return_value=mock_store):
        response = client.post(f"/api/v1/memory/candidates/{memory_id}/confirm")

    assert response.status_code == 200
    mock_store.promote_cold_candidate.assert_awaited_once_with(
        "default_user", "candidate-hash", source="user_confirmation"
    )


def test_reject_candidate_preserves_suppression_record():
    candidate = {"hash": "candidate-hash", "text": "偏好範例", "status": "candidate"}
    mock_store = AsyncMock()
    mock_store.get_cold_candidates.return_value = [candidate]
    mock_store.reject_cold_candidate.return_value = {**candidate, "status": "rejected"}
    memory_id = _memory_source_id("candidate", candidate["text"])

    with patch("memory_store.get_global_store", return_value=mock_store):
        response = client.post(f"/api/v1/memory/candidates/{memory_id}/reject")

    assert response.status_code == 200
    mock_store.reject_cold_candidate.assert_awaited_once_with("default_user", "candidate-hash")


def test_edit_memory_endpoint():
    with patch("gum_integration.get_gum_instance", new_callable=AsyncMock) as mock_get_gum:
        mock_gum_instance = AsyncMock()
        mock_get_gum.return_value = (mock_gum_instance, AsyncMock())
        mock_gum_instance.update_text = AsyncMock()
        
        response = client.put("/api/v1/memory/456", json={"text": "Updated text"})
        assert response.status_code == 200
        assert response.json() == {"status": "success"}
        mock_get_gum.assert_called_once_with("default_user")
        mock_gum_instance.update_text.assert_called_once_with(456, "Updated text")
