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
    response = client.post("/api/start", json={"learner_id": "test_user", "curriculum_id": "cnn"})
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "tree" in data
    assert isinstance(data["tree"], list)
    assert "learning" in data
    assert data["learning"]["phase"] == "diagnosis"
    assert "evidence_count" in data["learning"]

def test_api_start_dynamic() -> None:
    response = client.post("/api/start", json={"learner_id": "dynamic_user"})
    assert response.status_code == 200
    data = response.json()
    assert data["learning"]["phase"] == "onboarding"
    assert data["learning"]["intake_turns"] == 0
    assert data["learning"]["intent"] == "unknown"


def test_api_dynamic_learning_metadata() -> None:
    learner = "deep_learning_user"
    client.post("/api/reset", json={"learner_id": learner})
    client.post("/api/respond", json={"learner_id": learner, "answer": "深度學習"})
    client.post("/api/respond", json={"learner_id": learner, "answer": "想理解原理"})
    response = client.post("/api/respond", json={"learner_id": learner, "answer": "完全沒有基礎"})

    assert response.status_code == 200
    learning = response.json()["learning"]
    assert learning["phase"] == "diagnosis"
    assert learning["skill_id"] == "deep_learning"
    assert learning["domain_category"] == "stem"
    assert learning["intent"] == "conceptual"
    assert learning["level_hint"] == "beginner"
    assert "latest_signal" in learning
    assert learning["current_activity"]["code"] == "diagnostic_selected"
    activity_codes = [item["code"] for item in learning["activity_steps"]]
    assert "skill_loaded" in activity_codes
    assert "skill_validated" in activity_codes
    assert "plan_compiled" in activity_codes
    assert learning["skill_artifact_summary"]["skill_id"] == "deep_learning"
    assert learning["skill_artifact_summary"]["concept_path"]
    assert learning["skill_artifact_summary"]["current_diagnostic_target"]["node_id"] == "math_intuition"


def test_api_progress_snapshot_is_safe_metadata() -> None:
    learner = "progress_user"
    client.post("/api/reset", json={"learner_id": learner})
    client.post("/api/respond", json={"learner_id": learner, "answer": "深度學習"})
    client.post("/api/respond", json={"learner_id": learner, "answer": "想理解原理"})
    client.post("/api/respond", json={"learner_id": learner, "answer": "完全沒有基礎"})
    response = client.post(
        "/api/respond",
        json={"learner_id": learner, "answer": "用來衡量預測與目標之間的差距"},
    )

    progress = response.json()["learning"]["progress_snapshot"]

    assert progress["current_node_id"] is not None
    assert progress["nodes"]
    assert "用來衡量預測與目標之間的差距" not in str(progress)


def test_api_agent_proposals_are_safe_metadata() -> None:
    learner = "proposal_user"
    raw_answer = "深度學習 raw secret should not become proposal payload"
    response = client.post("/api/respond", json={"learner_id": learner, "answer": raw_answer})

    proposals = response.json()["learning"]["agent_proposals"]

    assert proposals
    assert raw_answer not in str(proposals)
    assert "role" in proposals[-1]
    assert "validation_status" in proposals[-1]


def test_api_exposes_safe_tutor_proposal_trace() -> None:
    learner = "tutor_trace_user"
    raw_answer = "我不知道 raw secret should not be copied into proposal trace"
    client.post("/api/reset", json={"learner_id": learner})
    client.post("/api/respond", json={"learner_id": learner, "answer": "深度學習"})
    client.post("/api/respond", json={"learner_id": learner, "answer": "想理解原理"})
    client.post("/api/respond", json={"learner_id": learner, "answer": "完全沒有基礎"})
    response = client.post("/api/respond", json={"learner_id": learner, "answer": raw_answer})

    learning = response.json()["learning"]

    assert learning["tutor_proposal_trace"]
    assert learning["tutor_proposal_trace"][-1]["artifact_type"] == "tutor_proposal"
    assert learning["tutor_proposal_trace"][-1]["pedagogical_move"] == "scaffold"
    assert learning["evidence_response_trace"]
    assert raw_answer not in str(learning["tutor_proposal_trace"])
    assert raw_answer not in str(learning["evidence_response_trace"])


def test_api_methodology_events_are_current_cycle_metadata() -> None:
    learner = "methodology_user"
    client.post("/api/reset", json={"learner_id": learner})
    client.post("/api/respond", json={"learner_id": learner, "answer": "深度學習"})
    client.post("/api/respond", json={"learner_id": learner, "answer": "想理解原理"})
    response = client.post("/api/respond", json={"learner_id": learner, "answer": "完全沒有基礎"})

    learning = response.json()["learning"]

    assert learning["methodology_stages"] == [
        "goal_framing",
        "skill_construction",
        "cognitive_diagnosis",
        "knowledge_state_update",
        "edf_strategy_selection",
        "tutor_response",
    ]
    assert learning["current_cycle_id"]
    assert learning["methodology_events"]
    assert "深度學習" not in str(learning["methodology_events"])


def test_api_respond() -> None:
    client.post("/api/start", json={"learner_id": "test_user", "curriculum_id": "cnn"})
    response = client.post(
        "/api/respond", json={"learner_id": "test_user", "answer": "1000"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "state_changes" in data


def test_api_mode_switching() -> None:
    response = client.post("/api/mode", json={"learner_id": "test_user", "curriculum_id": "cnn", "mode": "rule"})
    assert response.status_code == 200
    assert response.json()["mode"] == "rule"

def test_api_mode_switching_400_format() -> None:
    response = client.post("/api/mode", json={"learner_id": "test_user", "curriculum_id": "cnn", "mode": "invalid"})
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "validation error" in data["detail"].lower()

def test_api_reset_phase() -> None:
    # First advance it
    client.post("/api/start", json={"learner_id": "test_user", "curriculum_id": "cnn"})
    client.post("/api/respond", json={"learner_id": "test_user", "answer": "100"})
    
    # Then reset and check
    response = client.post("/api/reset", json={"learner_id": "test_user", "curriculum_id": "cnn"})
    assert response.status_code == 200
    data = response.json()
    assert "tree" in data
    assert data["learning"]["phase"] == "diagnosis"
    
    # Verify state via internal inspection to ensure phase reset
    import pelican_mvp.server as server_module
    engine = server_module._get_engine("test_user", "cnn")
    assert engine.state.phase == "diagnosis"


def test_api_export_markdown_includes_transcript_and_metadata() -> None:
    learner = "export_user"
    client.post("/api/reset", json={"learner_id": learner})
    client.post("/api/respond", json={"learner_id": learner, "answer": "深度學習"})

    response = client.get("/api/export", params={"learner_id": learner})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    text = response.text
    assert "# PELICAN MVP Conversation Export" in text
    assert "深度學習" in text
    assert "## Knowledge Tree" in text
    assert "## Skill Artifact Summary" in text
    assert "## Recent Engine Activity" in text
    assert "## Methodology Events" in text
    assert "## Agent Proposals" in text
    assert "## Recent Evidence-to-Response Trace" in text
    assert "## Tutor Proposal Trace" in text
    assert "## Learner Progress Snapshot" in text


def test_api_invalid_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from pelican_mvp.engine import PelicanEngine
    from pelican_mvp.state_store import StateStoreError
    
    def raise_error(*args, **kwargs):
        raise StateStoreError("mocked error")
        
    monkeypatch.setattr(PelicanEngine, "start", raise_error)
    response = client.post("/api/start", json={"learner_id": "error_user"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid session state"

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
