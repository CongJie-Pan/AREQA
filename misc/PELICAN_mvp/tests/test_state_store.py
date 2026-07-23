import json
from pathlib import Path

import pytest

from pelican_mvp.models import (
    DiagnosticQuestion,
    Evidence,
    KnowledgeNode,
    KnowledgeStatus,
    LearningPlanSnapshot,
    NodeState,
    SessionState,
)
from pelican_mvp.state_store import StateStore, StateStoreError


def test_state_persists_and_loads(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    state = store.new_state("student-1", curriculum_id="cnn")
    state.nodes["cnn_relu"].update(KnowledgeStatus.MASTERED, Evidence("不會", "correct", True))
    store.save(state)

    loaded = store.load_or_create("student-1")

    assert loaded.nodes["cnn_relu"].status is KnowledgeStatus.MASTERED
    assert loaded.nodes["cnn_relu"].evidence[0].response == "不會"


def test_reset_creates_clean_state(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    state = store.new_state("student", curriculum_id="cnn")
    state.nodes["nn_basics"].status = KnowledgeStatus.MASTERED
    store.save(state)

    reset = store.reset("student", curriculum_id="cnn")

    assert all(item.status is KnowledgeStatus.UNDIAGNOSED for item in reset.nodes.values())


@pytest.mark.parametrize("learner_id", ["", "../escape", "bad id", "a" * 65])
def test_invalid_learner_id_is_rejected(tmp_path: Path, learner_id: str) -> None:
    with pytest.raises(ValueError):
        StateStore(tmp_path).new_state(learner_id)


def test_new_default_state_starts_in_onboarding(tmp_path: Path) -> None:
    state = StateStore(tmp_path).new_state("student")

    assert state.phase == "onboarding"
    assert state.curriculum_id is None
    assert state.nodes == {}


def test_generated_plan_nodes_survive_reload_and_reconcile(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    plan = LearningPlanSnapshot(
        plan_id="sql-joins",
        topic="SQL joins",
        goal_summary="Understand left joins.",
        nodes=(
            KnowledgeNode("tables", "Tables"),
            KnowledgeNode("left-join", "Left join", ("tables",)),
        ),
        diagnostics=(DiagnosticQuestion("left-join", "What does LEFT JOIN keep?", "left rows"),),
        task_steps=(
            {"step_id": "join", "node_id": "left-join", "prompt": "Choose a join", "expected": "left join"},
        ),
    )
    state = SessionState(learner_id="student", learning_plan=plan, phase="diagnosis")
    state.nodes["stale"] = NodeState()
    store.save(state)

    loaded = store.load_or_create("student")

    assert set(loaded.nodes) == {"tables", "left-join"}
    assert all(node.status is KnowledgeStatus.UNDIAGNOSED for node in loaded.nodes.values())


def test_invalid_generated_plan_is_rejected_without_logging_raw_content(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = StateStore(tmp_path)
    raw_answer = "private learner answer must never enter logs"
    invalid_payload = {
        "learner_id": "student",
        "plan_source": "generated",
        "phase": "diagnosis",
        "learning_plan": {
            "plan_id": "invalid",
            "topic": "topic",
            "goal_summary": "goal",
            "nodes": [{"node_id": "node", "label": "Node", "prerequisites": ["missing"]}],
            "diagnostics": [],
            "task_steps": [],
        },
        "nodes": {"node": {"evidence": [{"response": raw_answer, "category": "incorrect", "direct": True}]}},
    }
    (tmp_path / "student.json").write_text(json.dumps(invalid_payload), encoding="utf-8")

    with pytest.raises(StateStoreError):
        store.load_or_create("student")

    assert "pelican_state_rejected" in caplog.text
    assert raw_answer not in caplog.text


def test_unsupported_future_schema_is_rejected(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    payload = {"learner_id": "student", "schema_version": 4, "curriculum_id": "cnn"}
    (tmp_path / "student.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StateStoreError, match="unsupported session schema version"):
        store.load_or_create("student")


def test_schema_two_state_is_migrated_to_schema_three(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    payload = {"learner_id": "student", "schema_version": 2, "curriculum_id": "cnn"}
    (tmp_path / "student.json").write_text(json.dumps(payload), encoding="utf-8")

    loaded = store.load_or_create("student")

    assert loaded.schema_version == 3
    assert loaded.methodology_events == []
    assert loaded.agent_proposals == []
    assert loaded.learner_progress.nodes == ()


def test_malformed_methodology_entries_are_dropped_on_load(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    payload = {
        "learner_id": "student",
        "schema_version": 3,
        "curriculum_id": "cnn",
        "methodology_events": [{"event_type": "invalid"}],
        "agent_proposals": [{"role": "invalid"}],
    }
    (tmp_path / "student.json").write_text(json.dumps(payload), encoding="utf-8")

    loaded = store.load_or_create("student")

    assert loaded.methodology_events == []
    assert loaded.agent_proposals == []
