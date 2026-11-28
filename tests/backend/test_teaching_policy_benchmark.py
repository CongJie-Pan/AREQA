from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.benchmark_teaching_policy import (
    CASES,
    DEFAULT_PREDICTION,
    TEACHING_MOVES,
    classify_jev_teaching,
    summarize,
)


def _row(move, depth="DIRECT", status="ok", ms=400, expected=("PRACTICE_HINT",), depths=("DIRECT",)):
    return {"move": move, "depth": depth, "status": status, "ms": ms,
            "expected_moves": list(expected), "expected_depths": list(depths)}


def test_cases_only_expect_offered_moves():
    assert len({case[0] for case in CASES}) == len(CASES)
    for _, moves, _, _, _ in CASES:
        assert moves <= set(TEACHING_MOVES)


def test_late_prediction_is_scored_as_the_default_policy():
    late = _row("PRACTICE_HINT", ms=1200)

    on_time = summarize([late], budget_ms=1500)
    too_late = summarize([late], budget_ms=700)

    assert (on_time["move_correct"], on_time["practice_leaks"]) == (1, 0)
    assert (too_late["move_correct"], too_late["practice_leaks"]) == (0, 1)
    assert DEFAULT_PREDICTION[0].startswith("LEARN_")


def test_failures_and_wrong_modes_count_as_practice_leaks():
    rows = [
        _row("PRACTICE_DIAGNOSTIC_QUESTION", expected=("PRACTICE_HINT", "PRACTICE_DIAGNOSTIC_QUESTION")),
        _row("REFERENCE_ANSWER"),
        _row(None, depth=None, status="timeout", ms=8000),
    ]

    result = summarize(rows, budget_ms=700)

    assert result["practice_cases"] == 3
    assert result["practice_leaks"] == 2
    assert result["mode_correct"] == 1
    assert result["status_counts"] == {"ok": 2, "timeout": 1}


def test_mixed_expectations_are_not_practice_cases_and_incoherent_pairs_are_counted():
    rows = [
        _row("REFERENCE_ANSWER", expected=("REFERENCE_ANSWER", "LEARN_EXPLAIN_PREREQ")),
        _row("PRACTICE_ANSWER", expected=("PRACTICE_HINT",)),
    ]

    result = summarize(rows, budget_ms=700)

    assert result["practice_cases"] == 1
    assert result["incoherent_pairs"] == 1
    assert result["mode_correct"] == 2
    assert result["move_correct"] == 1


@pytest.mark.asyncio
async def test_benchmark_measures_the_production_jev_call():
    client = MagicMock()
    answers = {
        "teaching_move": "PRACTICE_HINT", "task_intent": "ANSWER_EXAM", "answer_depth": "DIRECT",
        "visual_support": "NONE", "evidence_mode": "NONE", "learning_technique": "NONE",
    }
    client.with_options.return_value.post = AsyncMock(
        return_value={"answers": {name: {"choice": label} for name, label in answers.items()}},
    )

    assert await classify_jev_teaching(client, "那下一步呢？", "剛給了提示") == ("PRACTICE_HINT", "DIRECT")
