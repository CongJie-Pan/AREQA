from pelican_mvp.curriculum import CURRICULUMS
from pelican_mvp.diagnosis import apply_diagnostic_result, classify_response, next_diagnostic_node
from pelican_mvp.models import KnowledgeStatus, PlanSource, ResponseCategory, SessionState, NodeState

cnn = CURRICULUMS["cnn"]

def new_state() -> SessionState:
    return SessionState(
        "student",
        plan_source=PlanSource.FIXTURE,
        curriculum_id="cnn",
        nodes={node_id: NodeState() for node_id in cnn.nodes},
    )


def test_successor_first_selects_leaf_before_prerequisite() -> None:
    state = new_state()
    assert next_diagnostic_node(state, cnn) == "cnn_conv"


def test_correct_child_marks_prerequisite_mastered() -> None:
    state = new_state()
    changes = apply_diagnostic_result(state, "cnn_pool", "5", ResponseCategory.CORRECT, cnn)

    assert state.nodes["cnn_pool"].status is KnowledgeStatus.MASTERED
    assert state.nodes["nn_basics"].status is KnowledgeStatus.INFERRED_MASTERED
    assert any("由子節點推定" in change for change in changes)


def test_response_categories_cover_known_cases() -> None:
    assert classify_response("8", "8", cnn) is ResponseCategory.CORRECT
    assert classify_response("我不會", "8", cnn) is ResponseCategory.INABILITY
    assert classify_response("我看不懂題意", "8", cnn) is ResponseCategory.DIFFICULTY
    assert classify_response("12", "8", cnn) is ResponseCategory.INCORRECT


def test_qing_history_clue_is_partial_understanding() -> None:
    category = classify_response(
        "和明朝舊官員勾結好後入關",
        "Learner should mention Nurhaci, Hong Taiji, Ming collapse, Wu Sangui, Shanhai Pass, and Dorgon.",
        cnn,
        prompt="請簡述滿洲人是如何崛起並最終入主中原建立清朝的？",
    )

    assert category is ResponseCategory.PARTIAL_CORRECT


def test_partial_answer_updates_partially_mastered_state() -> None:
    state = new_state()
    changes = apply_diagnostic_result(state, "cnn_conv", "接近但不完整", ResponseCategory.PARTIAL_CORRECT, cnn)

    assert state.nodes["cnn_conv"].status is KnowledgeStatus.PARTIALLY_MASTERED
    assert any("partially_mastered" in change for change in changes)
