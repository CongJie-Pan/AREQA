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

async def _process_proactive_user(store, user_id: str) -> None:
    """Process one user and emit a safe proactive-scheduling preflight event.

    The scheduler records only eligibility metadata so operators can correlate a
    later mailbox task without exposing hot-memory or generated-message content.
    """

    iteration_id = uuid.uuid4().hex
    trigger_proactive = False
    avatar_summon = False
    learner_state = "STARTING"
    active_avatar = None
    cooldown_active = False

    async with _facade()._flag_lock:
        hot_mem = await store.get_hot_memory(user_id)
        if hot_mem.get("avatar_summon_pending"):
            avatar_summon = True
            active_avatar = hot_mem.get("active_avatar")
        else:
            if not _facade()._auto_proactive_enabled():
                logger.debug(
                    "compeer.auto_proactive_disabled user_id=%s source=process_user",
                    user_id,
                )
                return
            cooldown_active = await _facade().is_in_cooldown(user_id)
            if hot_mem.get("trigger_proactive") and not cooldown_active:
                trigger_proactive = True
                learner_state = hot_mem.get("current_learner_state", "STARTING")
                active_avatar = hot_mem.get("active_avatar")

    if avatar_summon and active_avatar:
        from config import settings

        if not settings.enable_mailbox_sending:
            logger.info("compeer.avatar_mail_disabled user_id=%s", user_id)
            return

        from services.memory.gum.runtime import (
            generate_epistolary_letter_via_llm,
            get_hot_memory_snapshot,
            query_cold_memory_for_context,
        )
        from mailbox_store import get_mailbox_store
        snapshot = await get_hot_memory_snapshot(user_id)
        event_summary = f"與 {active_avatar} 進行深度歷史哲學探討"
        cold_ctx = await query_cold_memory_for_context(user_id, event_summary)
        subject, letter_content = await generate_epistolary_letter_via_llm(
            user_id, active_avatar, snapshot, cold_ctx
        )
        mail_data = {
            "id": str(uuid.uuid4()),
            "kind": "avatar_letter",
            "user_id": user_id,
            "active_avatar": active_avatar,
            "sender": active_avatar,
            "recipient": "User",
            "subject": subject,
            "content": letter_content,
            "timestamp": _time.time(),
            "read": False,
            "task_id": _facade()._stable_task_id(
                "letter", user_id, "legacy-avatar-summon", active_avatar
            ),
        }
        task_id = await get_mailbox_store().schedule_delayed_mail(
            user_id=user_id,
            mail_data=mail_data,
            delay_seconds=300,
        )
        if task_id:
            await _facade()._clear_persisted_trigger(store, user_id, "avatar_summon_pending")
        preflight = _facade().evaluate_proactive_preflight(
            trigger_present=False,
            avatar_pending=True,
            cooldown_active=False,
        )
        if not task_id:
            preflight = replace(preflight, block_reason="scheduling_failed")
        _facade()._log_proactive_preflight(
            user_id,
            iteration_id,
            replace(
                preflight,
                scheduling_succeeded=bool(task_id),
                task_id=task_id,
            ),
        )
        await _facade().tick_proactive_schedule(user_id)
        return
    elif trigger_proactive:
        interval_remaining_seconds = await _facade().get_proactive_mail_interval_remaining_seconds(user_id)
        if interval_remaining_seconds:
            logger.info(
                "compeer.proactive_mail_interval_blocked user_id=%s "
                "remaining_seconds=%s source=explicit_trigger",
                user_id,
                interval_remaining_seconds,
            )
            _facade()._log_proactive_preflight(
                user_id,
                iteration_id,
                _facade().evaluate_proactive_preflight(
                    trigger_present=True,
                    cooldown_active=False,
                    proactive_mail_interval_remaining_seconds=interval_remaining_seconds,
                ),
            )
            await _facade().tick_proactive_schedule(user_id)
            return

        daily_limit_reached, daily_sent_count, daily_send_limit = (
            await _facade().has_reached_daily_proactive_limit(user_id)
        )
        if daily_limit_reached:
            _facade()._log_proactive_preflight(
                user_id,
                iteration_id,
                _facade().evaluate_proactive_preflight(
                    trigger_present=True,
                    cooldown_active=False,
                    daily_sent_count=daily_sent_count,
                    daily_send_limit=daily_send_limit,
                ),
            )
            await _facade().tick_proactive_schedule(user_id)
            return

        from services.memory.gum.runtime import get_hot_memory_snapshot, query_cold_memory_for_context

        snapshot = await get_hot_memory_snapshot(user_id)
        event_summary = f"EDF 系統偵測到使用者遭遇學習瓶頸 (狀態: {learner_state})"
        allow_topic_specific = _facade().should_allow_topic_specific_care(snapshot, event_summary)
        cold_ctx = (
            await query_cold_memory_for_context(user_id, event_summary)
            if allow_topic_specific
            else ""
        )
        edf_policy = await store.get_current_strategy(user_id)
        hot_mem = await store.get_hot_memory(user_id)
        task_id = await _facade()._schedule_areqa_care_letter_safely(
            user_id=user_id,
            learner_state=learner_state,
            edf_policy=edf_policy,
            event_summary=event_summary,
            hot_memory_snapshot=snapshot,
            cold_memory_context=cold_ctx,
            last_compeer_message=hot_mem.get("last_compeer_message", ""),
            allow_topic_specific=allow_topic_specific,
        )
        if task_id:
            await _facade().record_daily_proactive_send(user_id)
            await _facade().record_proactive_mail_scheduled(user_id)
            await _facade()._clear_persisted_trigger(store, user_id, "trigger_proactive")
            await _facade().set_cooldown(user_id, state=learner_state)
        preflight = _facade().evaluate_proactive_preflight(
            trigger_present=True,
            cooldown_active=False,
        )
        if not task_id:
            preflight = replace(preflight, block_reason="scheduling_failed")
        _facade()._log_proactive_preflight(
            user_id,
            iteration_id,
            replace(
                preflight,
                scheduling_succeeded=bool(task_id),
                task_id=task_id,
            ),
        )
        await _facade().tick_proactive_schedule(user_id)
        return

    await _facade().tick_proactive_schedule(user_id)

    last_time = await _facade().get_last_interaction_time(user_id)
    inactive_seconds = max(0.0, _time.time() - last_time)
    cooldown_active = await _facade().is_in_cooldown(user_id)
    cooldown_remaining_seconds = (
        await _facade().get_cooldown_remaining_seconds(user_id) if cooldown_active else None
    )
    if cooldown_active or inactive_seconds <= 60:
        _facade()._log_proactive_preflight(
            user_id,
            iteration_id,
            _facade().evaluate_proactive_preflight(
                trigger_present=bool(hot_mem.get("trigger_proactive")),
                avatar_pending=avatar_summon,
                cooldown_active=cooldown_active,
                inactive_seconds=inactive_seconds,
                cooldown_remaining_seconds=cooldown_remaining_seconds,
            ),
        )
        return

    behavior_signals = await store.get_behavior_signals(user_id)
    from config import settings

    recent_scroll_signals = _facade()._collect_recent_scroll_behavior_signals(
        behavior_signals,
        now=_time.time(),
        window_seconds=_facade().PROACTIVE_SCROLL_SIGNAL_WINDOW_SECONDS,
    )
    hot_mem = await store.get_hot_memory(user_id)
    legacy_scroll_keys = [
        key
        for key, value in hot_mem.items()
        if key.startswith("obs_") and "Type: scroll" in str(value)
    ]
    scroll_count = len(recent_scroll_signals)
    signal_source = "behavior_signals"
    if scroll_count == 0 and legacy_scroll_keys:
        scroll_count = len(legacy_scroll_keys)
        signal_source = "legacy_hot_memory"

    behavior_eval_level = (
        logging.INFO
        if scroll_count >= _facade().PROACTIVE_SCROLL_SIGNAL_THRESHOLD
        else logging.DEBUG
    )
    logger.log(
        behavior_eval_level,
        "compeer.behavior_signals_evaluated user_id=%s iteration_id=%s "
        "signal_source=%s behavior_signal_count=%s recent_scroll_count=%s "
        "legacy_scroll_count=%s scroll_count=%s delivery_delay_seconds=%s",
        user_id,
        iteration_id,
        signal_source,
        len(behavior_signals),
        len(recent_scroll_signals),
        len(legacy_scroll_keys),
        scroll_count,
        settings.compeer_delivery_delay_seconds,
    )

    if scroll_count < _facade().PROACTIVE_SCROLL_SIGNAL_THRESHOLD:
        _facade()._log_proactive_preflight(
            user_id,
            iteration_id,
            _facade().evaluate_proactive_preflight(
                trigger_present=False,
                cooldown_active=False,
                inactive_seconds=inactive_seconds,
                scroll_count=scroll_count,
                signal_source=signal_source,
                behavior_signal_count=len(behavior_signals),
                recent_scroll_count=len(recent_scroll_signals),
                legacy_scroll_count=len(legacy_scroll_keys),
                delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
            ),
        )
        return

    daily_limit_reached, daily_sent_count, daily_send_limit = (
        await _facade().has_reached_daily_proactive_limit(user_id)
    )
    if daily_limit_reached:
        _facade()._log_proactive_preflight(
            user_id,
            iteration_id,
            _facade().evaluate_proactive_preflight(
                trigger_present=False,
                cooldown_active=False,
                inactive_seconds=inactive_seconds,
                scroll_count=scroll_count,
                signal_source=signal_source,
                behavior_signal_count=len(behavior_signals),
                recent_scroll_count=len(recent_scroll_signals),
                legacy_scroll_count=len(legacy_scroll_keys),
                delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
                daily_sent_count=daily_sent_count,
                daily_send_limit=daily_send_limit,
            ),
        )
        return

    interval_remaining_seconds = await _facade().get_proactive_mail_interval_remaining_seconds(user_id)
    if interval_remaining_seconds:
        logger.info(
            "compeer.proactive_mail_interval_blocked user_id=%s "
            "remaining_seconds=%s source=behavior_signal",
            user_id,
            interval_remaining_seconds,
        )
        _facade()._log_proactive_preflight(
            user_id,
            iteration_id,
            _facade().evaluate_proactive_preflight(
                trigger_present=False,
                cooldown_active=False,
                inactive_seconds=inactive_seconds,
                scroll_count=scroll_count,
                signal_source=signal_source,
                behavior_signal_count=len(behavior_signals),
                recent_scroll_count=len(recent_scroll_signals),
                legacy_scroll_count=len(legacy_scroll_keys),
                delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
                proactive_mail_interval_remaining_seconds=interval_remaining_seconds,
                daily_sent_count=daily_sent_count,
                daily_send_limit=daily_send_limit,
            ),
        )
        return

    from services.memory.gum.runtime import (
        detect_proactive_event_via_llm,
        get_hot_memory_snapshot,
        query_cold_memory_for_context,
    )

    snapshot = await get_hot_memory_snapshot(user_id)
    event = await detect_proactive_event_via_llm(user_id, snapshot)
    importance_passed = bool(event["has_event"] and event["importance"] >= 0.7)
    if not importance_passed:
        logger.info(
            "compeer.behavior_trigger_rejected user_id=%s iteration_id=%s "
            "signal_source=%s scroll_count=%s reason=importance_gate_failed",
            user_id,
            iteration_id,
            signal_source,
            scroll_count,
        )
        _facade()._log_proactive_preflight(
            user_id,
            iteration_id,
            _facade().evaluate_proactive_preflight(
                trigger_present=False,
                cooldown_active=False,
                inactive_seconds=inactive_seconds,
                scroll_count=scroll_count,
                signal_source=signal_source,
                behavior_signal_count=len(behavior_signals),
                recent_scroll_count=len(recent_scroll_signals),
                legacy_scroll_count=len(legacy_scroll_keys),
                delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
                importance_passed=False,
            ),
        )
        return

    event_summary = event["event_summary"]
    logger.info(
        "compeer.behavior_trigger_eligible user_id=%s iteration_id=%s "
        "signal_source=%s scroll_count=%s delivery_delay_seconds=%s",
        user_id,
        iteration_id,
        signal_source,
        scroll_count,
        settings.compeer_delivery_delay_seconds,
    )
    allow_topic_specific = _facade().should_allow_topic_specific_care(snapshot, event_summary)
    cold_ctx = (
        await query_cold_memory_for_context(user_id, event_summary)
        if allow_topic_specific
        else ""
    )
    learner_state = await store.get_learner_state(user_id)
    task_id = await _facade()._schedule_areqa_care_letter_safely(
        user_id=user_id,
        learner_state=learner_state,
        edf_policy=await store.get_current_strategy(user_id),
        event_summary=event_summary,
        hot_memory_snapshot=snapshot,
        cold_memory_context=cold_ctx,
        last_compeer_message=hot_mem.get("last_compeer_message", ""),
        allow_topic_specific=allow_topic_specific,
    )
    if task_id:
        await _facade().record_daily_proactive_send(user_id)
        await _facade().record_proactive_mail_scheduled(user_id)
        # Consume only after the delayed mailbox intent is durable; otherwise
        # retry needs the same behavior evidence to remain available.
        if signal_source == "behavior_signals":
            consumed_count = await store.consume_behavior_signals(
                user_id,
                recent_scroll_signals,
            )
        else:
            for key in legacy_scroll_keys:
                remove_typed_entry(hot_mem, key)
            await store.redis.set(
                f"areqa:hot_memory:{user_id}",
                json.dumps(hot_mem, ensure_ascii=False),
            )
            consumed_count = len(legacy_scroll_keys)
        logger.info(
            "compeer.behavior_signals_consumed user_id=%s iteration_id=%s "
            "signal_source=%s consumed_count=%s task_id=%s",
            user_id,
            iteration_id,
            signal_source,
            consumed_count,
            task_id,
        )
        await _facade().set_cooldown(user_id, state=learner_state)
    preflight = _facade().evaluate_proactive_preflight(
        trigger_present=False,
        cooldown_active=False,
        inactive_seconds=inactive_seconds,
        scroll_count=scroll_count,
        signal_source=signal_source,
        behavior_signal_count=len(behavior_signals),
        recent_scroll_count=len(recent_scroll_signals),
        legacy_scroll_count=len(legacy_scroll_keys),
        delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
        importance_passed=True,
    )
    if not task_id:
        preflight = replace(preflight, block_reason="scheduling_failed")
    _facade()._log_proactive_preflight(
        user_id,
        iteration_id,
        replace(
            preflight,
            scheduling_succeeded=bool(task_id),
            task_id=task_id,
        ),
    )


async def proactive_scheduler_loop():
    """
    Background worker loop that periodically checks for triggers to send proactive
    care letters. It evaluates user inactivity, avatar summons, and learning bottlenecks.
    """
    logger.info("compeer.scheduler_started")
    while True:
        try:
            from config import settings

            if (
                not _facade()._auto_proactive_enabled()
                and not settings.enable_mailbox_sending
            ):
                logger.debug("compeer.scheduler_disabled reason=auto_proactive_disabled")
                await _facade().asyncio.sleep(10)
                continue

            async with _facade()._send_lock:
                from services.memory.store.service import get_global_store
                store = get_global_store()
                if store:
                    redis = store.redis
                    cursor = 0
                    all_users = set()
                    while True:
                        cursor, keys = await redis.scan(cursor, match="areqa:hot_memory:*", count=100)
                        for key in keys:
                            k_str = key
                            all_users.add(k_str.split("areqa:hot_memory:")[1])
                        if cursor == 0:
                            break
                    for user_id in sorted(all_users):
                        try:
                            await _facade()._process_proactive_user(store, user_id)
                        except Exception as exc:
                            logger.warning(
                                "compeer.user_iteration_failed user_id=%s reason=%s",
                                user_id,
                                type(exc).__name__,
                                exc_info=True,
                            )

            await _facade().asyncio.sleep(10)
        except Exception:
            logger.exception("compeer.scheduler_iteration_failed")
            await _facade().asyncio.sleep(10)
