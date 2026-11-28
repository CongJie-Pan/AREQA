"""Regression: the foreground budget must let a typical EDF classification land.

At 700 ms every measured classification (1.0-1.3 s) timed out, so PRACTICE
turns silently received the default LEARN policy and solved the learner's step.
"""

import asyncio
from types import SimpleNamespace

import pytest

from services.orchestration.response_policy import resolve_response_policy
from services.query_policy.models import (
    AnswerDepth,
    FollowupMode,
    LearningMode,
    PedagogicalAction,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
)

PRACTICE_HINT = ResponsePolicy(
    task_intent=TaskIntent.ANSWER_EXAM,
    answer_depth=AnswerDepth.SCAFFOLDED,
    tone=ResponseTone.TUTORING,
    structure=ResponseStructure.STEP_BY_STEP,
    followup_mode=FollowupMode.REQUIRED,
    learning_mode=LearningMode.PRACTICE,
    pedagogical_action=PedagogicalAction.HINT,
    legacy_policy="PROBE_UNDERSTANDING",
)


def _trace():
    marks = []
    return SimpleNamespace(mark=marks.append, marks=marks)


async def _classify(delay_seconds):
    await asyncio.sleep(delay_seconds)
    return PRACTICE_HINT


@pytest.mark.asyncio
async def test_default_budget_applies_a_typical_classification():
    trace = _trace()

    policy, source, timed_out = await resolve_response_policy(asyncio.create_task(_classify(0.9)), trace, "c1")

    assert (source, timed_out) == ("classifier", False)
    assert policy.learning_mode is LearningMode.PRACTICE
    assert "policy_classifier_finished" in trace.marks


@pytest.mark.asyncio
async def test_slow_classification_still_falls_back_to_default():
    trace = _trace()

    policy, source, timed_out = await resolve_response_policy(
        asyncio.create_task(_classify(1.0)), trace, "c1", timeout_ms=50,
    )

    assert (source, timed_out) == ("timeout_fallback", True)
    assert policy.learning_mode is LearningMode.LEARN
    assert "policy_classifier_timeout" in trace.marks
