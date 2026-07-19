import pytest
from pelican_mvp.models import (
    DiagnosticQuestion,
    KnowledgeNode,
    KnowledgeStatus,
    LearningPlanSnapshot,
    PlanSource,
    SessionState,
    TurnRecord,
)

def test_session_state_from_dict_defaults() -> None:
    payload = {"learner_id": "tester"}
    state = SessionState.from_dict(payload)
    assert state.learner_id == "tester"
    assert state.mode == "rule"
    assert state.phase == "onboarding"
    assert state.plan_source is PlanSource.GENERATED
    assert state.curriculum_id is None
    assert state.completed is False
    assert state.nodes == {}
    assert state.history == []

def test_session_state_from_dict_with_partial_nodes() -> None:
    payload = {
        "learner_id": "tester",
        "nodes": {
            "n1": {
                # missing status and updated_at
                "evidence": [{"response": "a", "category": "correct", "direct": True, "timestamp": "t1"}]
            }
        }
    }
    state = SessionState.from_dict(payload)
    assert state.nodes["n1"].status == KnowledgeStatus.UNDIAGNOSED
    assert len(state.nodes["n1"].evidence) == 1
    assert state.nodes["n1"].updated_at is None

def test_knowledge_status_enum() -> None:
    assert KnowledgeStatus("mastered") == KnowledgeStatus.MASTERED
    with pytest.raises(ValueError):
        KnowledgeStatus("unknown")

def test_turn_record_serialization() -> None:
    record = TurnRecord(
        prompt="p", response="r", phase="ph", node_id="n",
        category="c", strategy="s", state_changes=["change1"]
    )
    assert "change1" in record.state_changes
    assert record.prompt == "p"


def test_session_state_round_trips_generated_plan_snapshot() -> None:
    plan = LearningPlanSnapshot(
        plan_id="binary-search-basics",
        topic="binary search",
        goal_summary="Understand binary search boundaries.",
        nodes=(
            KnowledgeNode("sorted-data", "Sorted data"),
            KnowledgeNode("boundaries", "Boundary updates", ("sorted-data",), 1),
        ),
        diagnostics=(
            DiagnosticQuestion("boundaries", "Why update a boundary?", "discard half"),
        ),
        task_steps=(
            {"step_id": "apply", "node_id": "boundaries", "prompt": "Trace one step", "expected": "move low"},
        ),
    )
    state = SessionState(
        learner_id="tester",
        learning_plan=plan,
        phase="diagnosis",
    )

    restored = SessionState.from_dict(state.to_dict())

    assert restored.learning_plan == plan
    assert restored.plan_source is PlanSource.GENERATED
    assert restored.edf_snapshot.reason_code == "not_evaluated"
    assert restored.memory_snapshot.evidence_count == 0


def test_session_state_treats_legacy_curriculum_as_fixture() -> None:
    state = SessionState.from_dict({"learner_id": "tester", "curriculum_id": "cnn"})

    assert state.plan_source is PlanSource.FIXTURE
    assert state.phase == "diagnosis"
