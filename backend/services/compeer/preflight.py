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
from services.hot_memory_service import remove_typed_entry

logger = logging.getLogger("services.compeer_scheduler")


def _facade():
    return (
        sys.modules.get("services.compeer_scheduler")
        or sys.modules.get("backend.services.compeer_scheduler")
        or importlib.import_module("services.compeer_scheduler")
    )

def _auto_proactive_enabled() -> bool:
    """Return whether automatic ComPeer proactive scheduling may run."""

    from config import settings

    return bool(settings.enable_compeer_auto_proactive)


@dataclass(frozen=True)
class ProactivePreflight:
    """Describe one proactive scheduling decision using safe metadata only.

    The task ID is the correlation boundary between scheduler and mailbox
    events. Raw hot-memory values, event summaries, and generated mail content
    are intentionally excluded from this result.
    """

    trigger_present: bool
    avatar_pending: bool
    cooldown_active: bool
    inactive_seconds: float | None = None
    scroll_count: int = 0
    signal_source: str = "not_evaluated"
    behavior_signal_count: int = 0
    recent_scroll_count: int = 0
    legacy_scroll_count: int = 0
    delivery_delay_seconds: int | None = None
    cooldown_remaining_seconds: int | None = None
    proactive_mail_interval_remaining_seconds: int | None = None
    daily_sent_count: int | None = None
    daily_send_limit: int | None = None
    importance_passed: bool | None = None
    existing_pending_task: bool = False
    scheduling_succeeded: bool | None = None
    task_id: str | None = None
    block_reason: str | None = None

    @property
    def eligible(self) -> bool:
        """Return whether the preflight permits a scheduling attempt."""

        return self.block_reason is None


def evaluate_proactive_preflight(
    *,
    trigger_present: bool,
    avatar_pending: bool = False,
    cooldown_active: bool = False,
    inactive_seconds: float | None = None,
    scroll_count: int = 0,
    signal_source: str = "not_evaluated",
    behavior_signal_count: int = 0,
    recent_scroll_count: int = 0,
    legacy_scroll_count: int = 0,
    delivery_delay_seconds: int | None = None,
    cooldown_remaining_seconds: int | None = None,
    proactive_mail_interval_remaining_seconds: int | None = None,
    daily_sent_count: int | None = None,
    daily_send_limit: int | None = None,
    importance_passed: bool | None = None,
    existing_pending_task: bool = False,
) -> ProactivePreflight:
    """Evaluate proactive eligibility once without reading or writing user data.

    Explicit avatar summons bypass the ordinary cooldown. Explicit proactive
    triggers bypass inactivity and scroll gates. Behaviour-derived scheduling
    fails closed when its required evidence or importance decision is absent.
    Signal counters and delivery delay are safe observability metadata; they do
    not affect the decision reason.
    """

    reason = None
    if existing_pending_task:
        reason = "existing_pending_task"
    elif (
        proactive_mail_interval_remaining_seconds is not None
        and proactive_mail_interval_remaining_seconds > 0
    ):
        reason = "proactive_mail_interval_active"
    elif avatar_pending:
        reason = None
    elif (
        daily_send_limit is not None
        and daily_send_limit >= 0
        and daily_sent_count is not None
        and daily_sent_count >= daily_send_limit
    ):
        reason = "daily_limit_reached"
    elif cooldown_active:
        reason = "cooldown_active"
    elif trigger_present:
        reason = None
    elif inactive_seconds is not None and inactive_seconds <= 60:
        reason = "inactivity_threshold"
    elif scroll_count == 0:
        reason = "absent_trigger"
    elif scroll_count < 6:
        reason = "insufficient_scroll_evidence"
    elif importance_passed is not True:
        reason = "importance_gate_failed"

    return ProactivePreflight(
        trigger_present=trigger_present,
        avatar_pending=avatar_pending,
        cooldown_active=cooldown_active,
        inactive_seconds=inactive_seconds,
        scroll_count=scroll_count,
        signal_source=signal_source,
        behavior_signal_count=behavior_signal_count,
        recent_scroll_count=recent_scroll_count,
        legacy_scroll_count=legacy_scroll_count,
        delivery_delay_seconds=delivery_delay_seconds,
        cooldown_remaining_seconds=cooldown_remaining_seconds,
        proactive_mail_interval_remaining_seconds=proactive_mail_interval_remaining_seconds,
        daily_sent_count=daily_sent_count,
        daily_send_limit=daily_send_limit,
        importance_passed=importance_passed,
        existing_pending_task=existing_pending_task,
        block_reason=reason,
    )


def _log_proactive_preflight(
    user_id: str,
    iteration_id: str,
    preflight: ProactivePreflight,
) -> None:
    """Emit the allowlisted result of one scheduler preflight.

    Ordinary idle polling for users with no usable trigger is intentionally
    debug-level noise. INFO is reserved for actionable states: visible evidence,
    eligibility, scheduling, cooldown, failures, or non-empty behavior signals.
    """

    log_level = logging.INFO
    if (
        preflight.block_reason
        in {"absent_trigger", "inactivity_threshold", "insufficient_scroll_evidence"}
        and preflight.scroll_count < _facade().PROACTIVE_SCROLL_SIGNAL_THRESHOLD
        and not preflight.trigger_present
        and not preflight.avatar_pending
        and not preflight.existing_pending_task
        and preflight.scheduling_succeeded is None
    ):
        log_level = logging.DEBUG

    logger.log(
        log_level,
        "compeer.preflight_evaluated user_id=%s iteration_id=%s "
        "trigger_present=%s avatar_pending=%s cooldown_active=%s "
        "inactive_seconds=%s scroll_count=%s importance_passed=%s "
        "signal_source=%s behavior_signal_count=%s recent_scroll_count=%s "
        "legacy_scroll_count=%s delivery_delay_seconds=%s "
        "cooldown_remaining_seconds=%s proactive_mail_interval_remaining_seconds=%s "
        "daily_sent_count=%s daily_send_limit=%s "
        "existing_pending_task=%s scheduling_succeeded=%s task_id=%s",
        user_id,
        iteration_id,
        preflight.trigger_present,
        preflight.avatar_pending,
        preflight.cooldown_active,
        (
            round(preflight.inactive_seconds, 3)
            if preflight.inactive_seconds is not None
            else "not_evaluated"
        ),
        preflight.scroll_count,
        preflight.importance_passed,
        preflight.signal_source,
        preflight.behavior_signal_count,
        preflight.recent_scroll_count,
        preflight.legacy_scroll_count,
        (
            preflight.delivery_delay_seconds
            if preflight.delivery_delay_seconds is not None
            else "not_evaluated"
        ),
        (
            preflight.cooldown_remaining_seconds
            if preflight.cooldown_remaining_seconds is not None
            else "not_evaluated"
        ),
        (
            preflight.proactive_mail_interval_remaining_seconds
            if preflight.proactive_mail_interval_remaining_seconds is not None
            else "not_evaluated"
        ),
        (
            preflight.daily_sent_count
            if preflight.daily_sent_count is not None
            else "not_evaluated"
        ),
        (
            preflight.daily_send_limit
            if preflight.daily_send_limit is not None
            else "not_evaluated"
        ),
        preflight.existing_pending_task,
        preflight.scheduling_succeeded,
        preflight.task_id or "none",
    )
    if preflight.block_reason:
        logger.log(
            log_level,
            "compeer.preflight_blocked user_id=%s iteration_id=%s reason=%s "
            "cooldown_remaining_seconds=%s proactive_mail_interval_remaining_seconds=%s "
            "daily_sent_count=%s daily_send_limit=%s",
            user_id,
            iteration_id,
            preflight.block_reason,
            (
                preflight.cooldown_remaining_seconds
                if preflight.cooldown_remaining_seconds is not None
                else "not_evaluated"
            ),
            (
                preflight.proactive_mail_interval_remaining_seconds
                if preflight.proactive_mail_interval_remaining_seconds is not None
                else "not_evaluated"
            ),
            (
                preflight.daily_sent_count
                if preflight.daily_sent_count is not None
                else "not_evaluated"
            ),
            (
                preflight.daily_send_limit
                if preflight.daily_send_limit is not None
                else "not_evaluated"
            ),
        )
