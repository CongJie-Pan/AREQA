"""Select which model owns the EDF teaching decision, with a shadow mode.

``gemini`` keeps the chat-completions classifier. ``jev`` asks the Decisions
API instead. ``shadow`` serves Gemini and runs Jev beside it; ``jev_shadow``
serves Jev and runs Gemini beside it. Shadow modes log only the labels and
timings of both so the choice can be judged on production traffic.
Each comparison is also kept in a capped Redis list for
``scripts/shadow_policy_report.py``. Shadow ends by itself after
``POLICY_SHADOW_UNTIL`` (an Asia/Taipei date, inclusive).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime
from time import perf_counter
from zoneinfo import ZoneInfo
from typing import Any, Awaitable, Callable

from config import settings
from services.query_policy.learning_guardrails import _apply_learning_and_evidence_guardrails
from services.query_policy.models import ResponsePolicy, default_response_policy
from services.query_policy import shadow_review
from services.query_policy.pdf_guardrails import _apply_attachment_guardrails, _apply_pdf_auto_explain_guardrail
from services.query_policy.teaching_jev import classify_teaching_decision, policy_from_decision, previous_turn

logger = logging.getLogger(__name__)
GeminiClassifier = Callable[[], Awaitable[ResponsePolicy]]

# A shadow comparison waits this long for the slower side before giving up.
_SHADOW_WAIT_SECONDS = 8
# Shadow tasks outlive the request; keep references so they are not collected mid-flight.
_shadow_tasks: set[asyncio.Task] = set()
SHADOW_KEY = "areqa:policy_shadow:v1"
SHADOW_MAX_RECORDS = 5000
SHADOW_TTL_SECONDS = 30 * 24 * 3600
_REDIS_TIMEOUT_SECONDS = 1.5
_TAIPEI = ZoneInfo("Asia/Taipei")
_expiry_logged = False


SHADOW_BACKENDS = ("shadow", "jev_shadow")


def shadow_active(today: date | None = None) -> bool:
    """Return whether shadow comparison still runs; a malformed end date stops it."""

    if settings.policy_classifier_backend not in SHADOW_BACKENDS:
        return False
    until = settings.policy_shadow_until.strip()
    if not until:
        return True
    try:
        end = date.fromisoformat(until)
    except ValueError:
        return False
    return (today or datetime.now(_TAIPEI).date()) <= end


def _move(policy: ResponsePolicy) -> str:
    return f"{policy.learning_mode.value}_{policy.pedagogical_action.value}"


def _guarded(policy: ResponsePolicy, user_msg: str, has_pdf_attachment: bool) -> ResponsePolicy:
    policy = _apply_attachment_guardrails(policy, has_pdf_attachment=has_pdf_attachment)
    policy = _apply_pdf_auto_explain_guardrail(policy, user_msg=user_msg, has_pdf_attachment=has_pdf_attachment)
    return _apply_learning_and_evidence_guardrails(policy, user_msg=user_msg)


async def _jev_policy(client: Any, user_msg: str, chat_history: list, *, has_pdf_attachment: bool) -> ResponsePolicy:
    """Jev's guarded policy. Raises on failure so a comparison records it as a failure, not as a default."""

    started = perf_counter()
    policy = policy_from_decision(await classify_teaching_decision(client, user_msg, previous_turn(chat_history)))
    logger.info(
        "policy.jev_selected move=%s depth=%s duration_ms=%.1f",
        _move(policy), policy.answer_depth.value, (perf_counter() - started) * 1000,
    )
    return _guarded(policy, user_msg, has_pdf_attachment)


def _jev_fallback(exc: BaseException, user_msg: str, has_pdf_attachment: bool) -> ResponsePolicy:
    logger.warning("policy.jev_failed reason=%s", type(exc).__name__)
    return _guarded(default_response_policy(), user_msg, has_pdf_attachment)


async def classify_jev_policy(client: Any, user_msg: str, chat_history: list, *, has_pdf_attachment: bool) -> ResponsePolicy:
    """Return Jev's policy with the classifier's deterministic guardrails; fails soft to the default."""

    try:
        return await _jev_policy(client, user_msg, chat_history, has_pdf_attachment=has_pdf_attachment)
    except Exception as exc:
        return _jev_fallback(exc, user_msg, has_pdf_attachment)


async def _timed(awaitable: Awaitable[ResponsePolicy]) -> tuple[ResponsePolicy | None, str, float]:
    started = perf_counter()
    try:
        policy = await asyncio.wait_for(awaitable, timeout=_SHADOW_WAIT_SECONDS)
        return policy, "ok", (perf_counter() - started) * 1000
    except asyncio.TimeoutError:
        return None, "timeout", (perf_counter() - started) * 1000
    except Exception as exc:
        return None, type(exc).__name__, (perf_counter() - started) * 1000


async def _store(record: dict) -> None:
    """Append one comparison to the capped shadow list; Redis trouble only costs the record."""

    from redis_client import get_redis

    try:
        pipeline = get_redis().pipeline(transaction=False)
        pipeline.lpush(SHADOW_KEY, json.dumps(record, sort_keys=True))
        pipeline.ltrim(SHADOW_KEY, 0, SHADOW_MAX_RECORDS - 1)
        pipeline.expire(SHADOW_KEY, SHADOW_TTL_SECONDS)
        await asyncio.wait_for(pipeline.execute(), timeout=_REDIS_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("policy.shadow_store_failed reason=%s", type(exc).__name__)


async def _compare(
    gemini_side: Awaitable[ResponsePolicy], jev_side: Awaitable[ResponsePolicy], budget_ms: int, *,
    has_pdf_attachment: bool, served: str, review: shadow_review.ReviewCapture | None = None,
) -> None:
    """Time both sides; the served side is a shared future, shielded so this wait cannot cancel it."""

    sides = (gemini_side, jev_side)
    (gemini, gemini_status, gemini_ms), (jev, jev_status, jev_ms) = await asyncio.gather(*(
        _timed(asyncio.shield(side) if isinstance(side, asyncio.Future) else side) for side in sides
    ))
    for side in sides:
        if isinstance(side, asyncio.Future) and not side.done():
            side.cancel()
    # Labels, statuses and timings only: no learner text, user or conversation identifiers.
    record = {
        "ts": int(time.time()),
        "gemini_move": _move(gemini) if gemini else "none",
        "jev_move": _move(jev) if jev else "none",
        "gemini_depth": gemini.answer_depth.value if gemini else "none",
        "jev_depth": jev.answer_depth.value if jev else "none",
        "gemini_status": gemini_status,
        "jev_status": jev_status,
        "gemini_ms": round(gemini_ms, 1),
        "jev_ms": round(jev_ms, 1),
        "budget_ms": budget_ms,
        "has_pdf": has_pdf_attachment,
        "served": served,
    }
    logger.info(
        "policy.shadow_compared gemini_move=%s jev_move=%s gemini_depth=%s jev_depth=%s "
        "agree_mode=%s agree_move=%s gemini_status=%s jev_status=%s gemini_ms=%.1f jev_ms=%.1f "
        "gemini_in_budget=%s jev_in_budget=%s budget_ms=%d served=%s",
        record["gemini_move"], record["jev_move"], record["gemini_depth"], record["jev_depth"],
        bool(gemini and jev and gemini.learning_mode is jev.learning_mode),
        bool(gemini and jev and _move(gemini) == _move(jev)),
        gemini_status, jev_status, gemini_ms, jev_ms,
        gemini_status == "ok" and gemini_ms <= budget_ms, jev_status == "ok" and jev_ms <= budget_ms, budget_ms, served,
    )
    await _store(record)
    if review is not None:
        review.add_comparison(record)


async def classify_with_backend(
    gemini: GeminiClassifier,
    client: Any,
    user_msg: str,
    chat_history: list,
    *,
    has_pdf_attachment: bool = False,
) -> ResponsePolicy:
    """Run the configured policy backend.

    ``gemini`` and ``jev`` serve one side. ``shadow`` serves Gemini and compares Jev;
    ``jev_shadow`` serves Jev and compares Gemini. After ``POLICY_SHADOW_UNTIL`` the
    shadow modes serve their side alone.

    Args:
        gemini: Starts the existing EDF classifier when called.
        client: OpenRouter client shared by both backends.
        user_msg: Current user message; sent to providers, never logged.
        chat_history: Recent messages; Jev receives only the turn before the latest user message.
        has_pdf_attachment: Whether the turn carries a PDF.

    Returns:
        The policy that serves this turn.
    """

    global _expiry_logged
    backend = settings.policy_classifier_backend
    serves_jev = backend in ("jev", "jev_shadow")
    if not shadow_active():
        if backend in SHADOW_BACKENDS and not _expiry_logged:
            _expiry_logged = True
            logger.info("policy.shadow_expired until=%s serving=%s", settings.policy_shadow_until, "jev" if serves_jev else "gemini")
        if serves_jev:
            return await classify_jev_policy(client, user_msg, chat_history, has_pdf_attachment=has_pdf_attachment)
        return await gemini()

    review = shadow_review.current()
    if review is not None:
        review.expect_comparison()
    jev = _jev_policy(client, user_msg, chat_history, has_pdf_attachment=has_pdf_attachment)
    if serves_jev:
        served = asyncio.ensure_future(jev)
        gemini_side, jev_side = gemini(), served
    else:
        served = asyncio.ensure_future(gemini())
        gemini_side, jev_side = served, jev
    comparison = asyncio.create_task(_compare(
        gemini_side,
        jev_side,
        settings.policy_classifier_timeout_ms,
        has_pdf_attachment=has_pdf_attachment,
        served="jev" if serves_jev else "gemini",
        review=review,
    ))
    _shadow_tasks.add(comparison)
    comparison.add_done_callback(_shadow_tasks.discard)
    # Shielded so the foreground timeout leaves the served side running long enough to be measured.
    if not serves_jev:
        return await asyncio.shield(served)
    try:
        return await asyncio.shield(served)
    except Exception as exc:
        return _jev_fallback(exc, user_msg, has_pdf_attachment)
