"""Opt-in review records for the policy shadow experiment.

For allowlisted accounts only (``SHADOW_REVIEW_USER_IDS``, people who agreed to
it), a shadow turn also keeps the question, the previous turn, both decisions,
the served policy and the answer, so disagreements can be judged with their
text. Records live in a separate capped, expiring Redis list and are read only
by ``scripts/shadow_policy_report.py --review``. Text is never logged.

The capture travels in a ContextVar: tasks created during the turn copy the
context, so the classifier and its shadow comparison see it without new
parameters on every call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextvars import ContextVar
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

REVIEW_KEY = "areqa:policy_shadow_review:v1"
REVIEW_MAX_RECORDS = 1000
REVIEW_TTL_SECONDS = 30 * 24 * 3600
_QUERY_CHARS = 2000
_PREVIOUS_CHARS = 500
_ANSWER_CHARS = 4000
_REDIS_TIMEOUT_SECONDS = 1.5

_current: ContextVar["ReviewCapture | None"] = ContextVar("policy_shadow_review", default=None)
_store_tasks: set[asyncio.Task] = set()


def _review_user_ids() -> set[str]:
    return {item.strip() for item in settings.shadow_review_user_ids.split(",") if item.strip()}


def start(user_id: Any, query: str, previous: str) -> "ReviewCapture | None":
    """Begin a capture for this turn when shadow runs and the user opted in; always resets the context."""

    from services.query_policy.policy_backend import shadow_active

    capture = None
    if isinstance(user_id, str) and user_id in _review_user_ids() and shadow_active():
        capture = ReviewCapture(user_id, query, previous)
    _current.set(capture)
    return capture


def current() -> "ReviewCapture | None":
    return _current.get()


class ReviewCapture:
    """Collects one turn; stored once both the answer and any expected comparison are in."""

    def __init__(self, user_id: str, query: str, previous: str) -> None:
        self.user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
        self.query = query[:_QUERY_CHARS]
        self.previous = previous[:_PREVIOUS_CHARS]
        self.comparison: dict | None = None
        self.served: dict | None = None
        self.answer: str | None = None
        self._expects_comparison = False
        self._stored = False

    def expect_comparison(self) -> None:
        self._expects_comparison = True

    def record_served(self, policy: Any, source: str) -> None:
        self.served = {
            "source": source,
            "move": f"{policy.learning_mode.value}_{policy.pedagogical_action.value}",
            "depth": policy.answer_depth.value,
        }

    def add_comparison(self, record: dict) -> None:
        self.comparison = record
        self._maybe_store()

    def finish(self, answer: str) -> None:
        self.answer = (answer or "")[:_ANSWER_CHARS]
        self._maybe_store()

    def _maybe_store(self) -> None:
        if self._stored or self.answer is None or (self._expects_comparison and self.comparison is None):
            return
        self._stored = True
        task = asyncio.create_task(_store(self.to_record()))
        _store_tasks.add(task)
        task.add_done_callback(_store_tasks.discard)

    def to_record(self) -> dict:
        return {
            "ts": int(time.time()),
            "user_hash": self.user_hash,
            "query": self.query,
            "previous": self.previous,
            "comparison": self.comparison,
            "served": self.served,
            "answer": self.answer,
        }


async def _store(record: dict) -> None:
    from redis_client import get_redis

    try:
        pipeline = get_redis().pipeline(transaction=False)
        pipeline.lpush(REVIEW_KEY, json.dumps(record, ensure_ascii=False, sort_keys=True))
        pipeline.ltrim(REVIEW_KEY, 0, REVIEW_MAX_RECORDS - 1)
        pipeline.expire(REVIEW_KEY, REVIEW_TTL_SECONDS)
        await asyncio.wait_for(pipeline.execute(), timeout=_REDIS_TIMEOUT_SECONDS)
        logger.info("policy.shadow_review_stored compared=%s", record["comparison"] is not None)
    except Exception as exc:
        logger.warning("policy.shadow_review_store_failed reason=%s", type(exc).__name__)
