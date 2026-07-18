import pytest
from pelican_mvp.models import SessionState, KnowledgeStatus, TurnRecord

def test_session_state_from_dict_defaults() -> None:
    payload = {"learner_id": "tester"}
    state = SessionState.from_dict(payload)
    assert state.learner_id == "tester"
    assert state.mode == "rule"
    assert state.phase == "diagnosis"
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
