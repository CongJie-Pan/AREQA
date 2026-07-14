from pelican_mvp.curriculum import NODES
from pelican_mvp.diagnosis import apply_diagnostic_result, classify_response, next_diagnostic_node
from pelican_mvp.models import KnowledgeStatus, ResponseCategory, SessionState, NodeState


def new_state() -> SessionState:
    return SessionState("student", nodes={node_id: NodeState() for node_id in NODES})


def test_successor_first_selects_leaf_before_prerequisite() -> None:
    state = new_state()
    assert next_diagnostic_node(state) == "set_intersection"


def test_correct_child_marks_prerequisite_mastered() -> None:
    state = new_state()
    changes = apply_diagnostic_result(state, "set_intersection", "{3,4}", ResponseCategory.CORRECT)

    assert state.nodes["set_intersection"].status is KnowledgeStatus.MASTERED
    assert state.nodes["set_basics"].status is KnowledgeStatus.MASTERED
    assert any("由子節點推定" in change for change in changes)


def test_response_categories_cover_known_cases() -> None:
    assert classify_response("{3,4}", "{3,4}") is ResponseCategory.CORRECT
    assert classify_response("我不會", "{3,4}") is ResponseCategory.INABILITY
    assert classify_response("我看不懂交集", "{3,4}") is ResponseCategory.DIFFICULTY
    assert classify_response("{1,2}", "{3,4}") is ResponseCategory.INCORRECT

