"""Background registry for history summaries computed ahead of need.

``prepare_history`` schedules a summary here once a conversation's context
nears its budget, and waits briefly for an in-flight one before it compacts on
the answer path. Results land in the existing checkpoint caches, so this module
holds only task bookkeeping: at most one job per scope, a failure limit per
scope, and strong task references the event loop would otherwise drop.

The registry is per process. Other workers find finished summaries through the
database checkpoint, and fall back to compacting on the answer path otherwise.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

Scope = tuple[str, str, str, str]
# Same as opencode's PRECOMPUTE_MAX_FAILURES: stop retrying a scope that keeps failing.
MAX_FAILURES = 2


@dataclass(frozen=True, slots=True)
class PrecomputeSettings:
    """Tuning for summaries computed ahead of need.

    Args:
        ratio: Share of the chat budget a prepared context must reach to start one.
        tail_share: Share of the room left after instructions and summary that the
            verbatim tail may fill once a precomputed summary is used.
        wait_seconds: Longest the answer path waits for a summary still running.
        timeout_seconds: Wall-clock allowance for one background summary.
    """

    ratio: float = 0.75
    tail_share: float = 0.5
    wait_seconds: float = 3.0
    timeout_seconds: float = 45.0


_inflight: dict[Scope, tuple[int, asyncio.Task]] = {}
_failures: dict[Scope, int] = {}


def schedule(scope: Scope, target: int, job: Callable[[], Awaitable[bool]], *,
             timeout_seconds: float, conversation_id: str) -> bool:
    """Start ``job`` unless this scope already has one running or failed too often.

    Args:
        scope: Checkpoint scope (user, conversation, model, prompt digest).
        target: Number of history messages the job will cover; for logs only.
        job: Coroutine factory that computes and stores the summary; returns
            False when a stored checkpoint already covered the target.
        timeout_seconds: Total allowance; the job is cancelled after it.
        conversation_id: Identifier for logs; no message content is logged.

    Returns:
        Whether a job was started.
    """
    running = _inflight.get(scope)
    if running is not None and not running[1].done():
        logger.info('history.precompute_skipped conversation_id=%s reason=inflight', conversation_id)
        return False
    if _failures.get(scope, 0) >= MAX_FAILURES:
        logger.info('history.precompute_skipped conversation_id=%s reason=failure_limit', conversation_id)
        return False

    async def runner() -> None:
        started = time.monotonic()
        try:
            worked = await asyncio.wait_for(job(), timeout=timeout_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            _failures[scope] = _failures.get(scope, 0) + 1
            logger.warning('history.precompute_failed conversation_id=%s error_type=%s failures=%d',
                           conversation_id, type(error).__name__, _failures[scope])
            return
        _failures.pop(scope, None)
        if not worked:
            logger.info('history.precompute_skipped conversation_id=%s reason=already_covered', conversation_id)
            return
        logger.info('history.precompute_completed conversation_id=%s covered=%d elapsed_ms=%d',
                    conversation_id, target, int((time.monotonic() - started) * 1000))

    task = asyncio.create_task(runner())
    _inflight[scope] = (target, task)

    def finalize(completed: asyncio.Task) -> None:
        if _inflight.get(scope, (0, None))[1] is completed:
            _inflight.pop(scope, None)
        if not completed.cancelled():
            completed.exception()

    task.add_done_callback(finalize)
    logger.info('history.precompute_scheduled conversation_id=%s target=%d', conversation_id, target)
    return True


async def wait(scope: Scope, timeout_seconds: float) -> int:
    """Wait up to ``timeout_seconds`` for this scope's running job.

    The job is never cancelled here: a summary the answer path stops waiting
    for still finishes and serves the next turn.

    Returns:
        Milliseconds waited; 0 when nothing was running.
    """
    running = _inflight.get(scope)
    if running is None or running[1].done() or timeout_seconds <= 0:
        return 0
    started = time.monotonic()
    await asyncio.wait([running[1]], timeout=timeout_seconds)
    return int((time.monotonic() - started) * 1000)


def reset() -> None:
    """Forget all bookkeeping and cancel running jobs; for tests."""
    for _, task in _inflight.values():
        task.cancel()
    _inflight.clear()
    _failures.clear()
