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

async def evaluate_importance_gate(event: dict) -> bool:
    """
    Determine probabilistically whether an event should trigger based on its importance.

    Args:
        event (dict): The event dictionary containing an 'importance' score.

    Returns:
        bool: True if the event passes the gate, False otherwise.
    """
    importance = float(event.get("importance", 0.5))
    passed = _facade().random.random() < importance
    logger.info(
        "compeer.importance_evaluated importance=%s passed=%s",
        importance,
        passed,
    )
    return passed

async def tick_proactive_schedule(user_id: str):
    """
    Evaluate and trigger scheduled proactive care events for a user if their time has arrived.

    Legacy schedule files are ignored while mailbox sending is disabled. This
    keeps disabled deployments from repeatedly evaluating due events that cannot
    produce a durable mailbox task.

    Args:
        user_id (str): The unique identifier for the user.
    """
    from config import settings

    if not settings.enable_mailbox_sending:
        logger.debug(
            "compeer.legacy_schedule_skipped user_id=%s reason=mailbox_disabled",
            user_id,
        )
        return

    project_root = _facade().Path(__file__).resolve().parents[2]
    schedule_path = project_root / "data" / "gum_data" / f"schedule_{user_id}.json"

    if not os.path.exists(schedule_path):
        return

    try:
        with open(schedule_path, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception:
        return

    now_dt = datetime.now()
    changed = False

    for event in events:
        if event.get("fired", False):
            continue

        timing_str = event.get("Timing", "")
        if not timing_str:
            continue

        try:
            event_time = datetime.strptime(timing_str, "%H:%M").time()
        except ValueError:
            continue

        event_dt = datetime.combine(now_dt.date(), event_time)

        # 2-minute window
        if abs((now_dt - event_dt).total_seconds()) <= 120:
            if not await _facade().is_in_cooldown(user_id):
                passed = await _facade().evaluate_importance_gate(event)
                if passed:
                    from services.memory.store.service import get_global_store
                    store = get_global_store()
                    if store:
                        content = event.get("Content", "學習狀況還好嗎？")
                        logger.info(
                            "compeer.legacy_schedule_due user_id=%s",
                            user_id,
                        )
                        learner_state = await store.get_learner_state(user_id) if store else "default"
                        edf_policy = await store.get_current_strategy(user_id) if store else "default"
                        from services.memory.gum.runtime import get_hot_memory_snapshot, query_cold_memory_for_context
                        snapshot = await get_hot_memory_snapshot(user_id)
                        allow_topic_specific = _facade().should_allow_topic_specific_care(
                            snapshot,
                            content,
                            trust_event_summary=True,
                        )
                        cold_ctx = await query_cold_memory_for_context(user_id, content) if allow_topic_specific else ""
                        hot_mem = await store.get_hot_memory(user_id)
                        task_id = await _facade().schedule_areqa_care_letter(
                            user_id=user_id,
                            learner_state=learner_state,
                            edf_policy=edf_policy,
                            event_summary=content,
                            hot_memory_snapshot=snapshot,
                            cold_memory_context=cold_ctx,
                            last_compeer_message=hot_mem.get("last_compeer_message", ""),
                            allow_topic_specific=allow_topic_specific,
                        )
                        if not task_id:
                            logger.warning(
                                "compeer.legacy_schedule_not_durable user_id=%s reason=missing_task_id",
                                user_id,
                            )
                            continue
                        await _facade().set_cooldown(user_id, state=learner_state)

            event["fired"] = True
            changed = True

    if changed:
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

async def initialize_daily_schedule(user_id: str, reflection_outputs: list):
    """
    Generate a daily proactive communication schedule based on the user's past reflections.

    Args:
        user_id (str): The unique identifier for the user.
        reflection_outputs (list): A list of insights generated from the previous day's reflections.
    """
    try:
        from services.memory.gum.runtime import get_gum_instance
        gum_instance, _ = await get_gum_instance(user_id)
        if not gum_instance:
            return

        prompt = f"""基於以下昨日的學習反思，請為學生規劃今日的主動關懷排程。
反思紀錄:
{reflection_outputs}

請嚴格回傳 JSON 格式...
"""
        from pydantic import BaseModel
        class ScheduleItem(BaseModel):
            Timing: str
            Content: str
            importance: float
        class ScheduleList(BaseModel):
            events: list[ScheduleItem]

        rsp = await gum_instance.client.chat.completions.create(
            model=gum_instance.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "schedule", "schema": ScheduleList.model_json_schema()}},
            temperature=0.3
        )
        import re
        content = rsp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
        data = json.loads(content)
        events = data.get("events", [])

        project_root = _facade().Path(__file__).resolve().parents[2]
        schedule_path = project_root / "data" / "gum_data" / f"schedule_{user_id}.json"
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[Daily Schedule] Failed to initialize: {e}")

async def run_reflection_and_initialization(user_id: str):
    """
    Execute the reflection process for a user and initialize their schedule for the new day.

    Args:
        user_id (str): The unique identifier for the user.
    """
    try:
        from services.memory.gum.runtime import run_reflection
        insights = await run_reflection(user_id)

        if not insights:
            return

        await _facade().initialize_daily_schedule(user_id, insights)

    except Exception as e:
        print(f"[Daily Scheduler] run_reflection_and_initialization failed: {e}")

async def daily_scheduler_loop():
    """
    Background worker loop that runs daily reflections and schedule initialization
    for all active users.

    A reflection attempt is recorded before running reflection so empty or
    failed-to-produce-insight runs do not retry every minute for the same user.
    """
    while True:
        try:
            if not _facade()._auto_proactive_enabled():
                logger.debug("compeer.daily_scheduler_disabled reason=auto_proactive_disabled")
                await _facade().asyncio.sleep(60)
                continue

            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
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

                for user_id in all_users:
                    hot_mem = await store.get_hot_memory(user_id)
                    last_reflection = hot_mem.get("last_reflection_date")
                    last_attempt = str(hot_mem.get("last_reflection_attempt_at") or "")

                    if last_reflection != today_str:
                        if last_attempt.startswith(today_str):
                            continue
                        if now.hour >= 23 or last_reflection is None:
                            from services.memory.gum.runtime import run_reflection
                            await store.update_hot_memory_async(
                                user_id,
                                "last_reflection_attempt_at",
                                now.isoformat(),
                            )
                            insights = await run_reflection(user_id)
                            if insights:
                                await _facade().initialize_daily_schedule(user_id, insights)
                                await store.update_hot_memory_async(
                                    user_id,
                                    "last_reflection_date",
                                    today_str,
                                )

            await _facade().asyncio.sleep(60)
        except Exception as e:
            await _facade().asyncio.sleep(60)
