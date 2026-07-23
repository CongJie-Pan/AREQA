import pytest
from pelican_mvp.learning_memory import LearningMemorySimulator
from pelican_mvp.models import KnowledgeStatus, NodeState, ResponseCategory, SessionState, TurnRecord, Evidence


def create_mock_state() -> SessionState:
    state = SessionState(learner_id="test")
    state.nodes = {
        "n1": NodeState(status=KnowledgeStatus.UNDIAGNOSED),
    }
    state.current_node_id = "n1"
    return state


def test_learning_memory_simulator():
    state = create_mock_state()
    memory = LearningMemorySimulator(max_context_size=2)

    # Simulate first direct evidence
    state.history.append(TurnRecord(prompt="Q1", response="A1", phase="tutoring", node_id="n1", category=ResponseCategory.CORRECT.value, strategy="a", state_changes=[]))
    state.nodes["n1"].evidence.append(Evidence("A1", ResponseCategory.CORRECT.value, True))

    memory.record_direct_evidence(state, "A1", ResponseCategory.CORRECT)
    assert state.memory_snapshot.evidence_count == 1
    assert state.memory_snapshot.working_context_count == 1
    assert memory.get_working_context(state) == []
    assert memory.recent_safe_signals(state) == ("correct",)

    # Simulate second direct evidence
    state.history.append(TurnRecord(prompt="Q2", response="A2", phase="tutoring", node_id="n1", category=ResponseCategory.CORRECT.value, strategy="a", state_changes=[]))
    state.nodes["n1"].evidence.append(Evidence("A2", ResponseCategory.CORRECT.value, True))

    memory.record_direct_evidence(state, "A2", ResponseCategory.CORRECT)
    assert state.memory_snapshot.evidence_count == 2
    assert state.memory_snapshot.working_context_count == 2
    assert memory.get_working_context(state) == []
    assert memory.recent_safe_signals(state) == ("correct", "correct")

    # Simulate third direct evidence (exceeds max_context_size)
    state.history.append(TurnRecord(prompt="Q3", response="A3", phase="tutoring", node_id="n1", category=ResponseCategory.CORRECT.value, strategy="a", state_changes=[]))
    state.nodes["n1"].evidence.append(Evidence("A3", ResponseCategory.CORRECT.value, True))

    memory.record_direct_evidence(state, "A3", ResponseCategory.CORRECT)
    assert state.memory_snapshot.evidence_count == 3
    assert state.memory_snapshot.working_context_count == 2
    assert memory.get_working_context(state) == []
    assert memory.recent_safe_signals(state) == ("correct", "correct")

    # Simulate indirect evidence (should not increase evidence count)
    state.nodes["n1"].evidence.append(Evidence("A3", ResponseCategory.CORRECT.value, False))
    memory.record_direct_evidence(state, "A3", ResponseCategory.CORRECT)
    assert state.memory_snapshot.evidence_count == 3


def test_learning_memory_keeps_edf_inference_separate() -> None:
    state = create_mock_state()
    memory = LearningMemorySimulator(max_context_size=2)

    memory.record_direct_evidence(state, "這太細了吧，我不知道", ResponseCategory.DIFFICULTY, signal="too_detailed")

    assert state.direct_evidence[0].source == "user_message"
    assert state.direct_evidence[0].kind == "USER_EVIDENCE"
    assert state.direct_evidence[0].prompt_safe is False
    assert state.direct_evidence[0].cold_export_eligible is False
    assert state.direct_evidence[0].signal == "too_detailed"
    assert state.edf_snapshot.reason_code == "not_evaluated"
    assert memory.recent_safe_signals(state) == ("too_detailed",)
