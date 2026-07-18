from pelican_mvp.models import ResponseCategory, TutoringStrategy
from pelican_mvp.tutoring import rule_tutor_message, select_strategy


def test_fast_thinking_uses_response_category() -> None:
    strategy, reason = select_strategy(ResponseCategory.INCORRECT, rounds=1)
    assert strategy is TutoringStrategy.CORRECTION
    assert "fast-thinking" in reason


def test_slow_thinking_activates_after_two_rounds() -> None:
    strategy, reason = select_strategy(ResponseCategory.INABILITY, rounds=2)
    assert strategy is TutoringStrategy.DECOMPOSITION
    assert "slow-thinking" in reason


from pelican_mvp.curriculum import CURRICULUMS

def test_rule_tutor_message_decomposition() -> None:
    message = rule_tutor_message(TutoringStrategy.DECOMPOSITION, "cnn_conv", "Test Prompt", CURRICULUMS["cnn"])
    assert "絕對值" not in message
    assert "x - 1" not in message
    assert "卷積" in message

