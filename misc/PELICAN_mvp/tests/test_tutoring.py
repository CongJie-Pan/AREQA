from pelican_mvp.models import ResponseCategory, TutoringContext, TutoringStrategy
from pelican_mvp.tutoring import rule_tutor_message, select_strategy


def test_fast_thinking_uses_response_category() -> None:
    strategy, reason = select_strategy(ResponseCategory.INCORRECT, rounds=1)
    assert strategy is TutoringStrategy.CORRECTION
    assert "fast-thinking" in reason


def test_slow_thinking_activates_after_two_rounds() -> None:
    strategy, reason = select_strategy(ResponseCategory.INABILITY, rounds=2)
    assert strategy in (TutoringStrategy.DECOMPOSITION, TutoringStrategy.SIMPLIFICATION)
    assert "slow-thinking" in reason


def test_slow_thinking_respects_pedagogical_policy() -> None:
    strategy, reason = select_strategy(ResponseCategory.INABILITY, rounds=2, pedagogical_policy="simplify_or_decompose")
    assert strategy in (TutoringStrategy.SIMPLIFICATION, TutoringStrategy.DECOMPOSITION)

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

    assert strategy is TutoringStrategy.DECOMPOSITION
    assert "slow-thinking" in reason


from pelican_mvp.curriculum import CURRICULUMS

def test_rule_tutor_message_decomposition() -> None:
    message = rule_tutor_message(TutoringStrategy.DECOMPOSITION, "cnn_conv", "Test Prompt", CURRICULUMS["cnn"])
    assert "絕對值" not in message
    assert "x - 1" not in message
    assert "卷積" in message
