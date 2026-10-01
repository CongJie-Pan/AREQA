"""Internal ComPeer scheduler implementation module."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time as _time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel
from redis_client import get_redis
from services.memory.hot import remove_typed_entry

logger = logging.getLogger("services.compeer_scheduler")


def _runtime():
    """Resolve the single scheduler runtime after module initialization."""
    from services.compeer import runtime

    return runtime

def has_current_learning_evidence(hot_memory_snapshot: str) -> bool:
    """
    Check if there is current semantic learning evidence in the user's working memory.

    Args:
        hot_memory_snapshot (str): The current snapshot of the user's hot memory.

    Returns:
        bool: True if prompt-visible working memory has semantic content, False otherwise.
    """
    if not hot_memory_snapshot or "【工作記憶" not in hot_memory_snapshot:
        return False

    working_section = hot_memory_snapshot.split("【工作記憶", 1)[1]
    evidence_markers = (
        "Session summary:",
        "Current focus:",
        "Explicit memory:",
    )
    if any(marker in working_section for marker in evidence_markers):
        return True

    return any(line.strip().startswith("- ") and len(line.strip()) > 2 for line in working_section.splitlines())


def is_generic_event_summary(event_summary: str) -> bool:
    """
    Determine if an event summary is purely generic (e.g., generic system alerts)
    rather than specific to a learning topic.

    Args:
        event_summary (str): The text of the event summary.

    Returns:
        bool: True if the summary is generic or empty, False otherwise.
    """
    text = (event_summary or "").strip()
    if not text:
        return True
    return any(marker in text for marker in _runtime()._GENERIC_EVENT_MARKERS)


def should_allow_topic_specific_care(
    hot_memory_snapshot: str,
    event_summary: str,
    *,
    trust_event_summary: bool = False,
) -> bool:
    """
    Determine if a proactive care letter can reference specific learning topics.
    Cold memory alone must not authorize a specific proactive topic unless there
    is current evidence or the event summary is explicitly trusted.

    Args:
        hot_memory_snapshot (str): The current snapshot of the user's hot memory.
        event_summary (str): The text of the event summary.
        trust_event_summary (bool): Whether to trust the event summary as specific context. Defaults to False.

    Returns:
        bool: True if topic-specific care is allowed, False otherwise.
    """
    if has_current_learning_evidence(hot_memory_snapshot):
        return True
    return trust_event_summary and not is_generic_event_summary(event_summary)


def _stable_task_id(prefix: str, user_id: str, *parts: str) -> str:
    """
    Generate a stable, deterministic task ID based on user and task parameters.

    Args:
        prefix (str): A string prefix for the task ID.
        user_id (str): The ID of the user.
        *parts (str): Additional strings to hash into the task ID.

    Returns:
        str: A unique SHA-256 based task ID string.
    """
    raw = "|".join([user_id, *[str(part or "") for part in parts]])
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _parse_behavior_signal_timestamp(signal: dict) -> float | None:
    """Return a UNIX timestamp for one behavior signal when it is trustworthy.

    ComPeer consumes UI telemetry from `behavior_signals` rather than hot
    memory so scroll events stay out of prompt-visible memory. Invalid or
    missing timestamps are ignored because a stale or malformed signal must not
    create a proactive message.

    Args:
        signal: A behavior-signal dictionary persisted by `MemoryStore`.

    Returns:
        A UNIX timestamp in seconds, or `None` when the timestamp is invalid.
    """
    timestamp = signal.get("timestamp") if isinstance(signal, dict) else None
    if isinstance(timestamp, (int, float)):
        return float(timestamp)
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None

    normalized = timestamp.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _collect_recent_scroll_behavior_signals(
    signals: list[dict],
    *,
    now: float,
    window_seconds: float,
) -> list[dict]:
    """Filter recent scroll signals for behavior-derived ComPeer scheduling.

    The scheduler requires enough recent scroll evidence before asking the LLM
    proactive-event detector. This preserves the existing minimum-evidence
    invariant while using the current behavior-signal storage path.

    Args:
        signals: Behavior signals returned by `MemoryStore.get_behavior_signals`.
        now: Current UNIX timestamp in seconds.
        window_seconds: Maximum signal age to consider eligible.

    Returns:
        Scroll signal dictionaries inside the eligible time window.
    """
    recent_scrolls = []
    for signal in signals:
        if not isinstance(signal, dict) or signal.get("type") != "scroll":
            continue
        timestamp = _parse_behavior_signal_timestamp(signal)
        if timestamp is None:
            continue
        if 0 <= now - timestamp <= window_seconds:
            recent_scrolls.append(signal)
    return recent_scrolls


async def schedule_areqa_care_letter(
    user_id: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str,
    hot_memory_snapshot: str,
    cold_memory_context: str,
    last_compeer_message: str = "",
    allow_topic_specific: bool = False,
):
    """
    Generate and schedule a proactive care letter from the ComPeer system via an LLM.

    Args:
        user_id (str): The user's ID.
        learner_state (str): The current learning state of the user.
        edf_policy (str): The pedagogical policy to apply.
        event_summary (str): The summary of the triggering event.
        hot_memory_snapshot (str): The current state of working memory.
        cold_memory_context (str): Relevant long-term memory facts.
        last_compeer_message (str): The last message sent by ComPeer. Defaults to "".
        allow_topic_specific (bool): Whether the letter can reference specific learning topics. Defaults to False.

    Returns:
        str: The task ID of the scheduled letter.
    """
    from services.memory.gum.runtime import generate_areqa_care_letter_via_llm
    from mailbox_store import get_mailbox_store
    from services.memory.store.service import get_global_store
    from config import settings

    if not settings.enable_mailbox_sending:
        logger.info("compeer.mail_scheduling_disabled user_id=%s", user_id)
        return None

    safe_cold_memory_context = cold_memory_context if allow_topic_specific else ""
    subject, content = await generate_areqa_care_letter_via_llm(
        user_id=user_id,
        hot_memory_snapshot=hot_memory_snapshot,
        cold_memory_context=safe_cold_memory_context,
        learner_state=learner_state,
        edf_policy=edf_policy,
        event_summary=event_summary,
        last_compeer_message=last_compeer_message,
        allow_topic_specific=allow_topic_specific,
    )

    date_bucket = datetime.now().strftime("%Y-%m-%d")
    task_id = _runtime()._stable_task_id("compeer", user_id, event_summary, date_bucket)
    mb_store = get_mailbox_store()
    await mb_store.schedule_delayed_mail(
        user_id=user_id,
        mail_data={
            "kind": "compeer_care",
            "sender": "AREQA",
            "recipient": "User",
            "subject": subject,
            "content": content,
            "conversation_id": f"compeer-{date_bucket}",
            "event_hash": hashlib.sha256(event_summary.encode("utf-8")).hexdigest()[:24],
            "task_id": task_id,
        },
        delay_seconds=settings.compeer_delivery_delay_seconds,
    )

    logger.info(
        "compeer.scheduled task_id=%s user_id=%s kind=compeer_care delay_seconds=%s",
        task_id,
        user_id,
        settings.compeer_delivery_delay_seconds,
    )

    return task_id


async def _schedule_areqa_care_letter_safely(**kwargs):
    """Contain one user's scheduling failure so other users still progress."""

    user_id = kwargs.get("user_id", "")
    try:
        return await _runtime().schedule_areqa_care_letter(**kwargs)
    except Exception as exc:
        logger.exception(
            "compeer.schedule_failed user_id=%s reason=%s trigger_retained=true",
            user_id,
            type(exc).__name__,
        )
        from services.memory.store.service import get_global_store

        store = get_global_store()
        if store:
            await store.update_hot_memory_async(
                user_id,
                "compeer_retry_reason",
                type(exc).__name__,
                kind="operational_state",
                prompt_safe=False,
                cold_export_eligible=False,
            )
            await store.update_hot_memory_async(
                user_id,
                "compeer_next_attempt_at",
                _time.time() + 30,
                kind="operational_state",
                prompt_safe=False,
                cold_export_eligible=False,
            )
        return None
