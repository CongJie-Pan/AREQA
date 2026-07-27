from pelican_mvp.models import LearnerDialogueAct, ResponseCategory, TutoringContext, TutoringStrategy
from pelican_mvp.tutoring import (
    rule_tutor_message,
    select_strategy,
    simulate_strategy_candidates,
    strategy_for_dialogue_act,
)


def test_fast_thinking_uses_response_category() -> None:
    strategy, reason = select_strategy(ResponseCategory.INCORRECT, rounds=1)
    assert strategy is TutoringStrategy.CORRECTION
    assert "fast-thinking" in reason


def test_slow_thinking_activates_after_two_rounds() -> None:
    strategy, reason = select_strategy(ResponseCategory.INABILITY, rounds=2)
    assert strategy is TutoringStrategy.EXPLANATION
    assert "slow-thinking" in reason


def test_slow_thinking_respects_pedagogical_policy() -> None:
    strategy, reason = select_strategy(ResponseCategory.INABILITY, rounds=2, pedagogical_policy="simplify_or_decompose")
    assert strategy is TutoringStrategy.EXPLANATION

    strategy2, _ = select_strategy(ResponseCategory.INCORRECT, rounds=2, pedagogical_policy="correct_and_explain")
    assert strategy2 == TutoringStrategy.CORRECTION


def test_context_strategy_uses_recent_safe_signals() -> None:
    context = TutoringContext(
        category=ResponseCategory.INABILITY,
        rounds=2,
        pedagogical_policy="simplify_or_decompose",
        learner_state="STRUGGLING",
        node_id="math_intuition",
        node_label="數學直覺",
        recent_signals=("unknown", "inability_to_respond"),
    )

    strategy, reason = select_strategy(context)

    assert strategy is TutoringStrategy.EXPLANATION
    assert "slow-thinking" in reason


def test_dialogue_act_strategy_mapping_uses_explicit_tutor_moves() -> None:
    assert strategy_for_dialogue_act(LearnerDialogueAct.TERM_DEFINITION_REQUEST) is TutoringStrategy.CLARIFY_TERM
    assert strategy_for_dialogue_act(LearnerDialogueAct.MICRO_CHECK_CONFUSION) is TutoringStrategy.GIVE_CHOICES
    assert strategy_for_dialogue_act(LearnerDialogueAct.CLARIFICATION_QUESTION) is TutoringStrategy.SHORT_REFRAME
    assert strategy_for_dialogue_act(LearnerDialogueAct.ANSWER_ATTEMPT) is None


def test_dialogue_act_context_uses_dialogue_aware_simulation() -> None:
    context = TutoringContext(
        category=ResponseCategory.OTHER,
        rounds=0,
        pedagogical_policy="give_choices",
        learner_state="CLARIFYING",
        node_id="history_turning_point",
        node_label="turning point",
        dialogue_act="micro_check_confusion",
        repeated_confusion_count=1,
    )

    strategy, reason = select_strategy(context)
    candidates = simulate_strategy_candidates(context)

    assert strategy is TutoringStrategy.GIVE_CHOICES
    assert "edf-dialogue-route" in reason
    assert {candidate.strategy for candidate in candidates} == {
        TutoringStrategy.GIVE_CHOICES,
        TutoringStrategy.SHORT_REFRAME,
        TutoringStrategy.MINI_LESSON,
    }


def test_slow_simulation_candidates_include_scores_gain_and_risk() -> None:
    context = TutoringContext(
        category=ResponseCategory.INCORRECT,
        rounds=2,
        pedagogical_policy="correct_and_explain",
        learner_state="TINKERING",
        node_id="math_intuition",
        node_label="數學直覺",
        recent_signals=("incorrect", "incorrect"),
    )

    candidates = simulate_strategy_candidates(context)

    assert len(candidates) >= 1
    selected = max(candidates, key=lambda item: item.score)
    assert selected.strategy is TutoringStrategy.CORRECTION
    assert 0.0 <= selected.expected_gain <= 1.0
    assert 0.0 <= selected.risk <= 1.0
    assert "gain=" in selected.rationale


from pelican_mvp.curriculum import CURRICULUMS

def test_rule_tutor_message_decomposition() -> None:
    message = rule_tutor_message(TutoringStrategy.DECOMPOSITION, "cnn_conv", "Test Prompt", CURRICULUMS["cnn"])
    assert "絕對值" not in message
    assert "x - 1" not in message
    assert "卷積" in message
