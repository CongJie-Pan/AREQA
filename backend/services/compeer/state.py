"""Internal ComPeer scheduler implementation module."""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import logging
import os
import random
import sys
import time as _time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel
from redis_client import get_redis
from services.memory.hot import remove_typed_entry

logger = logging.getLogger("services.compeer_scheduler")


def _facade():
    return (
        sys.modules.get("services.compeer_scheduler")
        or sys.modules.get("backend.services.compeer_scheduler")
        or importlib.import_module("services.compeer_scheduler")
    )

async def _clear_persisted_trigger(store, user_id: str, trigger_key: str) -> None:
    """Clear a trigger only after its delayed-mail intent is durable."""

    async with _facade()._flag_lock:
        hot_memory = await store.get_hot_memory(user_id)
        if not hot_memory.get(trigger_key):
            return
        remove_typed_entry(hot_memory, trigger_key)
        await store.redis.set(
            f"areqa:hot_memory:{user_id}",
            json.dumps(hot_memory, ensure_ascii=False),
        )
    logger.info(
        "compeer.trigger_cleared user_id=%s trigger=%s reason=durable_task_created",
        user_id,
        trigger_key,
    )

async def is_in_cooldown(user_id: str) -> bool:
    """
    Check if the user is currently within a proactive communication cooldown period.

    Args:
        user_id (str): The unique identifier for the user.

    Returns:
        bool: True if the user is in cooldown, False otherwise.
    """
    redis = _facade().get_redis()
    return await redis.exists(f"areqa:cooldown:{user_id}") > 0


async def get_cooldown_remaining_seconds(user_id: str) -> int | None:
    """Return the Redis TTL for the ComPeer cooldown key, if it is active."""

    redis = _facade().get_redis()
    ttl = await redis.ttl(f"areqa:cooldown:{user_id}")
    return ttl if ttl is not None and ttl >= 0 else None


async def clear_cooldown(user_id: str) -> bool:
    """Clear a user's ComPeer cooldown key for development/manual testing."""

    redis = _facade().get_redis()
    deleted = await redis.delete(f"areqa:cooldown:{user_id}")
    logger.info(
        "compeer.cooldown_cleared user_id=%s deleted=%s",
        user_id,
        bool(deleted),
    )
    return bool(deleted)


def _compeer_daily_counter_key(user_id: str, now: datetime | None = None) -> str:
    """Return the UTC daily proactive-mail counter key for a user."""

    current = now or datetime.now(timezone.utc)
    return f"areqa:compeer_daily_count:{current.strftime('%Y-%m-%d')}:{user_id}"


def _compeer_proactive_mail_interval_key(user_id: str) -> str:
    """Return the Redis key that gates proactive mail frequency."""

    return f"areqa:compeer_last_proactive_mail:{user_id}"


def _seconds_until_next_utc_day(now: datetime | None = None) -> int:
    """Return seconds until the next UTC day boundary."""

    current = now or datetime.now(timezone.utc)
    next_day = current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(1, int((next_day - current).total_seconds()))


async def get_daily_proactive_sent_count(user_id: str) -> int:
    """Return how many ComPeer proactive mails have been scheduled today."""

    redis = _facade().get_redis()
    value = await redis.get(_compeer_daily_counter_key(user_id))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def has_reached_daily_proactive_limit(user_id: str) -> tuple[bool, int, int]:
    """Return whether the user has reached the configured daily ComPeer limit."""

    from config import settings

    limit = settings.compeer_daily_proactive_limit
    sent_count = await get_daily_proactive_sent_count(user_id)
    if limit < 0:
        return False, sent_count, limit
    return sent_count >= limit, sent_count, limit


async def record_daily_proactive_send(user_id: str) -> int:
    """Increment the user's UTC daily proactive-mail counter after durable scheduling."""

    redis = _facade().get_redis()
    key = _compeer_daily_counter_key(user_id)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _seconds_until_next_utc_day())
    logger.info(
        "compeer.daily_send_recorded user_id=%s daily_sent_count=%s",
        user_id,
        count,
    )
    return int(count)


async def get_proactive_mail_interval_remaining_seconds(user_id: str) -> int | None:
    """Return remaining seconds before another proactive mail may be scheduled.

    This helper observes only a Redis TTL. Callers may log the safe remaining
    seconds and source path, but must not log raw hot memory, event summaries,
    generated mail content, prompts, or model output.
    """

    from config import settings

    interval_seconds = max(0, int(settings.compeer_proactive_mail_min_interval_seconds))
    if interval_seconds <= 0:
        return None

    redis = _facade().get_redis()
    ttl_fn = getattr(redis, "ttl", None)
    if ttl_fn is None:
        return None
    ttl = await ttl_fn(_compeer_proactive_mail_interval_key(user_id))
    return ttl if isinstance(ttl, int) and ttl > 0 else None


async def record_proactive_mail_scheduled(user_id: str) -> None:
    """Record that one proactive mail intent was durably scheduled.

    This gate is intentionally separate from the short ComPeer cooldown. The
    cooldown controls near-term interaction churn, while this key enforces the
    user-facing product rule that proactive mailbox letters must be spaced out.
    """

    from config import settings

    interval_seconds = max(0, int(settings.compeer_proactive_mail_min_interval_seconds))
    if interval_seconds <= 0:
        return

    redis = _facade().get_redis()
    key = _compeer_proactive_mail_interval_key(user_id)
    setex_fn = getattr(redis, "setex", None)
    if setex_fn is not None:
        await setex_fn(key, interval_seconds, "1")
    else:
        await redis.set(key, "1")
    logger.info(
        "compeer.proactive_mail_interval_recorded user_id=%s interval_seconds=%s",
        user_id,
        interval_seconds,
    )


async def set_cooldown(user_id: str, state: str = "default") -> None:
    """
    Set a communication cooldown period dynamically based on the current learner state.

    Args:
        user_id (str): The unique identifier for the user.
        state (str): The current pedagogical state of the learner. Defaults to "default".
    """
    COOLDOWN_BY_STATE = {
        "NOT_STARTED": 2.0,
        "GIVING_UP": 0.25,
        "STARTING": 1.0,
        "TINKERING": 0.5,
        "MASTERY": 2.0,
        "default": 0.5
    }
    hours = COOLDOWN_BY_STATE.get(state, COOLDOWN_BY_STATE["default"])
    expire_seconds = int(hours * 3600)
    from config import settings

    if settings.compeer_cooldown_override_seconds is not None:
        expire_seconds = max(0, settings.compeer_cooldown_override_seconds)

    redis = _facade().get_redis()
    if expire_seconds <= 0:
        await redis.delete(f"areqa:cooldown:{user_id}")
        logger.info(
            "compeer.cooldown_set user_id=%s learner_state=%s "
            "cooldown_seconds=%s override_active=%s action=cleared",
            user_id,
            state,
            expire_seconds,
            True,
        )
        return

    await redis.setex(f"areqa:cooldown:{user_id}", expire_seconds, "1")
    logger.info(
        "compeer.cooldown_set user_id=%s learner_state=%s "
        "cooldown_seconds=%s override_active=%s",
        user_id,
        state,
        expire_seconds,
        settings.compeer_cooldown_override_seconds is not None,
    )

    # Also persist to hot_memory
    from services.memory.store.service import get_global_store
    store = get_global_store()
    if store:
        try:
            expire_time = _time.time() + expire_seconds
            await store.update_hot_memory_async(user_id, "user_cooldown_until", expire_time)
        except Exception as e:
            print(f"[EDF-LOG] Error setting cooldown in hot memory: {e}")
