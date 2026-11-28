"""Opt-in shadow review records: who is captured, when a record is stored, and what it holds."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

import config as runtime_config
from services.query_policy import policy_backend, shadow_review
from services.query_policy.models import default_response_policy
from services.query_policy.policy_backend import classify_with_backend

OPTED_IN = "user-opted-in"
SECRET = "PRIVATE_LEARNER_TEXT"
REAL_REVIEW_STORE = shadow_review._store


@pytest.fixture(autouse=True)
def stored(monkeypatch):
    """Keep tests off Redis; collect review and shadow records instead."""

    reviews, shadows = [], []

    async def store_review(record):
        reviews.append(record)

    async def store_shadow(record):
        shadows.append(record)

    monkeypatch.setattr(shadow_review, "_store", store_review)
    monkeypatch.setattr(policy_backend, "_store", store_shadow)
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "shadow")
    monkeypatch.setattr(runtime_config.settings, "policy_shadow_until", "")
    monkeypatch.setattr(runtime_config.settings, "shadow_review_user_ids", f" {OPTED_IN} , other ")
    return reviews


async def _drain():
    await asyncio.gather(*list(policy_backend._shadow_tasks))
    await asyncio.gather(*list(shadow_review._store_tasks))


def _jev_client():
    answers = {"teaching_move": "PRACTICE_HINT", "task_intent": "ANSWER_EXAM", "answer_depth": "DIRECT",
               "visual_support": "NONE", "evidence_mode": "NONE", "learning_technique": "NONE"}
    client = MagicMock()
    client.with_options.return_value.post = AsyncMock(
        return_value={"answers": {name: {"choice": label} for name, label in answers.items()}},
    )
    return client


@pytest.mark.parametrize(("user_id", "backend", "captured"), [
    (OPTED_IN, "shadow", True),
    ("someone-else", "shadow", False),
    (None, "shadow", False),
    (OPTED_IN, "gemini", False),
    (OPTED_IN, "jev", False),
])
def test_only_opted_in_users_are_captured_while_shadow_runs(monkeypatch, user_id, backend, captured):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", backend)

    capture = shadow_review.start(user_id, "q", "")

    assert (capture is not None) is captured
    assert shadow_review.current() is capture


def test_start_clears_a_previous_turns_capture():
    shadow_review.start(OPTED_IN, "first", "")

    shadow_review.start("someone-else", "second", "")

    assert shadow_review.current() is None


@pytest.mark.asyncio
async def test_record_waits_for_both_the_answer_and_the_comparison(stored):
    capture = shadow_review.start(OPTED_IN, "q", "prev")
    capture.expect_comparison()

    capture.finish("answer")
    await _drain()
    assert stored == []

    capture.add_comparison({"gemini_move": "LEARN_EXPLAIN_PREREQ", "jev_move": "PRACTICE_HINT"})
    capture.add_comparison({"duplicate": True})
    await _drain()
    (record,) = stored
    assert record["answer"] == "answer"
    assert record["comparison"]["jev_move"] == "PRACTICE_HINT"


@pytest.mark.asyncio
async def test_turn_without_a_classifier_is_stored_on_answer(stored):
    capture = shadow_review.start(OPTED_IN, "q", "")
    capture.record_served(default_response_policy(), "default")

    capture.finish("answer")
    await _drain()

    (record,) = stored
    assert record["comparison"] is None
    assert record["served"] == {"source": "default", "move": "LEARN_EXPLAIN_PREREQ", "depth": "SCAFFOLDED"}


@pytest.mark.asyncio
async def test_record_bounds_text_and_hashes_the_user(stored):
    capture = shadow_review.start(OPTED_IN, "q" * 3000, "p" * 900)

    capture.finish("a" * 5000)
    await _drain()

    (record,) = stored
    assert (len(record["query"]), len(record["previous"]), len(record["answer"])) == (2000, 500, 4000)
    assert OPTED_IN not in repr(record)
    assert len(record["user_hash"]) == 16


@pytest.mark.asyncio
async def test_shadow_comparison_reaches_the_turns_capture(stored):
    """Integration: the classifier task inherits the capture and completes it."""

    capture = shadow_review.start(OPTED_IN, SECRET, "")
    served = default_response_policy()

    result = await classify_with_backend(AsyncMock(return_value=served), _jev_client(), SECRET, [])
    capture.record_served(result, "classifier")
    capture.finish("the answer")
    await _drain()

    (record,) = stored
    assert record["query"] == SECRET
    assert (record["comparison"]["gemini_move"], record["comparison"]["jev_move"]) == ("LEARN_EXPLAIN_PREREQ", "PRACTICE_HINT")
    assert record["served"]["source"] == "classifier"


@pytest.mark.asyncio
async def test_review_store_logs_no_text(monkeypatch, caplog):
    import redis_client

    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[1, True, True])
    monkeypatch.setattr(redis_client, "get_redis", lambda: MagicMock(pipeline=MagicMock(return_value=pipeline)))

    with caplog.at_level(logging.INFO, logger=shadow_review.__name__):
        await REAL_REVIEW_STORE({"query": SECRET, "answer": SECRET, "comparison": None})

    pipeline.ltrim.assert_called_once_with(shadow_review.REVIEW_KEY, 0, shadow_review.REVIEW_MAX_RECORDS - 1)
    pipeline.expire.assert_called_once_with(shadow_review.REVIEW_KEY, shadow_review.REVIEW_TTL_SECONDS)
    assert "policy.shadow_review_stored compared=False" in caplog.text
    assert SECRET not in caplog.text
