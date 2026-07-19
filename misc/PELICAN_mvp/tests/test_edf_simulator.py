import pytest
from pelican_mvp.edf_simulator import EdfSimulator
from pelican_mvp.models import KnowledgeStatus, NodeState, ResponseCategory, SessionState, TurnRecord


def create_mock_state() -> SessionState:
    state = SessionState(learner_id="test")
    state.nodes = {
        "n1": NodeState(status=KnowledgeStatus.UNDIAGNOSED),
        "n2": NodeState(status=KnowledgeStatus.UNDIAGNOSED),
    }
    return state


def test_edf_evaluate_initial():
    state = create_mock_state()
    edf = EdfSimulator()
    snapshot = edf.evaluate(state)
    assert snapshot.learner_state == "STARTING"
    assert snapshot.pedagogical_strategy == "probe_understanding"
    assert snapshot.reason_code == "initial_state"
    assert snapshot.evidence_count == 0


def test_edf_evaluate_repeated_difficulty():
    state = create_mock_state()
    from pelican_mvp.models import Evidence

    state.history = [
        TurnRecord(prompt="q", response="a", phase="tutoring", node_id="n1", category=ResponseCategory.DIFFICULTY.value, strategy="a", state_changes=[]),
        TurnRecord(prompt="q", response="a", phase="tutoring", node_id="n1", category=ResponseCategory.DIFFICULTY.value, strategy="a", state_changes=[]),
    ]
    state.nodes["n1"].evidence = [Evidence("a", ResponseCategory.DIFFICULTY.value, True)] * 2

    edf = EdfSimulator()
    snapshot = edf.evaluate(state)
    assert snapshot.learner_state == "STRUGGLING"
    assert snapshot.pedagogical_strategy == "simplify_or_decompose"
    assert snapshot.reason_code == "repeated_difficulty"
    assert snapshot.evidence_count == 2


def test_edf_evaluate_progressing():
    state = create_mock_state()
    from pelican_mvp.models import Evidence

    state.history = [
        TurnRecord(prompt="q", response="a", phase="tutoring", node_id="n1", category=ResponseCategory.CORRECT.value, strategy="a", state_changes=[]),
        TurnRecord(prompt="q", response="a", phase="tutoring", node_id="n1", category=ResponseCategory.CORRECT.value, strategy="a", state_changes=[]),
    ]
    state.nodes["n1"].evidence = [Evidence("a", ResponseCategory.CORRECT.value, True)] * 2

    edf = EdfSimulator()
    snapshot = edf.evaluate(state)
    assert snapshot.learner_state == "PROGRESSING"
    assert snapshot.pedagogical_strategy == "confirm_and_suggest_action"
    assert snapshot.reason_code == "demonstrated_progress"
    assert snapshot.evidence_count == 2


def test_edf_evaluate_sustained_mastery():
    state = create_mock_state()
    from pelican_mvp.models import Evidence

    state.nodes["n1"].status = KnowledgeStatus.MASTERED
    state.nodes["n2"].status = KnowledgeStatus.MASTERED
    state.nodes["n1"].evidence = [Evidence("a", ResponseCategory.CORRECT.value, True)]
    state.nodes["n2"].evidence = [Evidence("a", ResponseCategory.CORRECT.value, True)]

    state.history = [
        TurnRecord(prompt="q", response="a", phase="tutoring", node_id="n1", category=ResponseCategory.CORRECT.value, strategy="a", state_changes=[]),
        TurnRecord(prompt="q", response="a", phase="tutoring", node_id="n2", category=ResponseCategory.CORRECT.value, strategy="a", state_changes=[]),
    ]

    edf = EdfSimulator()
    snapshot = edf.evaluate(state)
    assert snapshot.learner_state == "MASTERY"
    assert snapshot.pedagogical_strategy == "challenge_or_fade"
    assert snapshot.reason_code == "sustained_mastery"
    assert snapshot.evidence_count == 2
