import logging

import pytest
from fastapi.testclient import TestClient

from auth import get_current_user
from backend.main import app


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: "user-1"
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_onboarding_event_logs_fixed_codes_for_drop_off_analysis(client, caplog):
    with caplog.at_level(logging.INFO):
        response = client.post("/api/v1/onboarding/event", json={
            "event": "finished", "mode": "features", "step": "replyMore",
            "outcome": "skipped", "step_index": 2, "step_count": 4,
        })

    assert response.status_code == 200
    assert ("onboarding.event user_id=user-1 event=finished mode=features step=replyMore "
            "step_index=2 step_count=4 outcome=skipped") in caplog.text


@pytest.mark.parametrize("payload", [
    {"event": "finished", "mode": "full", "step": "some free text from a learner"},
    {"event": "clicked_secret", "mode": "full", "step": "ask"},
    {"event": "started", "mode": "full", "step": "ask", "step_index": 99},
])
def test_onboarding_event_rejects_anything_but_known_codes(client, payload):
    assert client.post("/api/v1/onboarding/event", json=payload).status_code in (400, 422)


def test_onboarding_event_requires_sign_in():
    assert TestClient(app).post("/api/v1/onboarding/event", json={
        "event": "started", "mode": "full", "step": "welcome",
    }).status_code in (401, 403)
