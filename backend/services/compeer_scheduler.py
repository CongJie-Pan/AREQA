import asyncio
import json
import os
import random
import hashlib
from datetime import datetime
from pathlib import Path
import time as _time

from redis_client import get_redis

async def is_in_cooldown(user_id: str) -> bool:
    """Return True if the user is within the cooldown period using Redis."""
    redis = get_redis()
    return await redis.exists(f"areqa:cooldown:{user_id}") > 0

async def set_cooldown(user_id: str, state: str = "default") -> None:
    """Set a cooldown period dynamically based on the learner state using Redis TTL."""
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
    
    redis = get_redis()
    await redis.setex(f"areqa:cooldown:{user_id}", expire_seconds, "1")
    
    # Also persist to hot_memory
    from memory_store import get_global_store
    store = get_global_store()
    if store:
        try:
            expire_time = _time.time() + expire_seconds
            await store.update_hot_memory_async(user_id, "user_cooldown_until", expire_time)
        except Exception as e:
            print(f"[EDF-LOG] Error setting cooldown in hot memory: {e}")

async def evaluate_importance_gate(event: dict) -> bool:
    importance = float(event.get("importance", 0.5))
    passed = random.random() < importance
    print(f"[EDF-LOG] evaluate_importance_gate: event='{event.get('Content')}', importance={importance}, passed={passed}")
    return passed

async def tick_proactive_schedule(user_id: str):
    project_root = Path(__file__).resolve().parents[2]
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
            if not await is_in_cooldown(user_id):
                passed = await evaluate_importance_gate(event)
                if passed:
                    from memory_store import get_global_store
                    store = get_global_store()
                    if store:
                        content = event.get("Content", "學習狀況還好嗎？")
                        print(f"[EDF-LOG] tick_proactive_schedule: firing alert for {user_id} with content: {content}")
                        learner_state = await store.get_learner_state(user_id) if store else "default"
                        edf_policy = await store.get_current_strategy(user_id) if store else "default"
                        from gum_integration import get_hot_memory_snapshot, query_cold_memory_for_context
                        snapshot = await get_hot_memory_snapshot(user_id)
                        cold_ctx = await query_cold_memory_for_context(user_id, content)
                        hot_mem = await store.get_hot_memory(user_id)
                        await schedule_areqa_care_letter(
                            user_id=user_id,
                            learner_state=learner_state,
                            edf_policy=edf_policy,
                            event_summary=content,
                            hot_memory_snapshot=snapshot,
                            cold_memory_context=cold_ctx,
                            last_compeer_message=hot_mem.get("last_compeer_message", ""),
                        )
                        await set_cooldown(user_id, state=learner_state)
                
            event["fired"] = True
            changed = True
            
    if changed:
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

async def initialize_daily_schedule(user_id: str, reflection_outputs: list):
    try:
        from gum_integration import get_gum_instance
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
        
        project_root = Path(__file__).resolve().parents[2]
        schedule_path = project_root / "data" / "gum_data" / f"schedule_{user_id}.json"
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"[Daily Schedule] Failed to initialize: {e}")

async def run_reflection_and_initialization(user_id: str):
    try:
        from gum_integration import run_reflection
        insights = await run_reflection(user_id)

        if not insights:
            return

        await initialize_daily_schedule(user_id, insights)

    except Exception as e:
        print(f"[Daily Scheduler] run_reflection_and_initialization failed: {e}")

async def daily_scheduler_loop():
    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            from memory_store import get_global_store
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
                    
                    if last_reflection != today_str:
                        if now.hour >= 23 or last_reflection is None:
                            await run_reflection_and_initialization(user_id)
                            await store.update_hot_memory_async(user_id, "last_reflection_date", today_str)
            
            await asyncio.sleep(60)
        except Exception as e:
            await asyncio.sleep(60)

_send_lock = asyncio.Lock()
_flag_lock = asyncio.Lock()


def _stable_task_id(prefix: str, user_id: str, *parts: str) -> str:
    raw = "|".join([user_id, *[str(part or "") for part in parts]])
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


async def schedule_areqa_care_letter(
    user_id: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str,
    hot_memory_snapshot: str,
    cold_memory_context: str,
    last_compeer_message: str = "",
):
    from gum_integration import generate_areqa_care_letter_via_llm
    from mailbox_store import get_mailbox_store
    from memory_store import get_global_store

    subject, content = await generate_areqa_care_letter_via_llm(
        user_id=user_id,
        hot_memory_snapshot=hot_memory_snapshot,
        cold_memory_context=cold_memory_context,
        learner_state=learner_state,
        edf_policy=edf_policy,
        event_summary=event_summary,
        last_compeer_message=last_compeer_message,
    )

    date_bucket = datetime.now().strftime("%Y-%m-%d")
    task_id = _stable_task_id("compeer", user_id, event_summary, date_bucket)
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
        delay_seconds=300,
    )

    store = get_global_store()
    if store:
        await store.update_hot_memory_async(user_id, "last_compeer_message", content)

    return task_id

async def get_last_interaction_time(user_id: str) -> float:
    redis = get_redis()
    val = await redis.get(f"areqa:last_interaction:{user_id}")
    return float(val) if val else _time.time()

async def set_last_interaction_time(user_id: str, timestamp: float):
    redis = get_redis()
    await redis.set(f"areqa:last_interaction:{user_id}", str(timestamp))

async def proactive_scheduler_loop():
    print("[EDF-LOG] Starting proactive_scheduler_loop background task.")
    while True:
        try:
            async with _send_lock:
                from memory_store import get_global_store
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
                        trigger_proactive = False
                        avatar_summon = False
                        learner_state = "STARTING"
                        active_avatar = None
                        
                        async with _flag_lock:
                            hot_mem = await store.get_hot_memory(user_id)
                            if hot_mem.get("avatar_summon_pending"):
                                avatar_summon = True
                                active_avatar = hot_mem.get("active_avatar")
                                del hot_mem["avatar_summon_pending"]
                                await store.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(hot_mem, ensure_ascii=False))
                            elif hot_mem.get("trigger_proactive") and not await is_in_cooldown(user_id):
                                trigger_proactive = True
                                learner_state = hot_mem.get("current_learner_state", "STARTING")
                                active_avatar = hot_mem.get("active_avatar")
                                del hot_mem["trigger_proactive"]
                                await store.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(hot_mem, ensure_ascii=False))

                        if avatar_summon and active_avatar:
                            from gum_integration import generate_epistolary_letter_via_llm, get_hot_memory_snapshot, query_cold_memory_for_context
                            snapshot = await get_hot_memory_snapshot(user_id)
                            event_summary = f"與 {active_avatar} 進行深度歷史哲學探討"
                            cold_ctx = await query_cold_memory_for_context(user_id, event_summary)
                            
                            subject, letter_content = await generate_epistolary_letter_via_llm(user_id, active_avatar, snapshot, cold_ctx)
                            
                            from mailbox_store import get_mailbox_store
                            mb_store = get_mailbox_store()
                            import uuid
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
                                "task_id": _stable_task_id("letter", user_id, "legacy-avatar-summon", active_avatar),
                            }
                            await mb_store.schedule_delayed_mail(user_id=user_id, mail_data=mail_data, delay_seconds=300)
                            
                        elif trigger_proactive:
                            from gum_integration import (
                                get_hot_memory_snapshot,
                                query_cold_memory_for_context
                            )
                            snapshot = await get_hot_memory_snapshot(user_id)
                            event_summary = f"EDF 系統偵測到使用者遭遇學習瓶頸 (狀態: {learner_state})"
                            cold_ctx = await query_cold_memory_for_context(user_id, event_summary)
                            edf_policy = await store.get_current_strategy(user_id)

                            hot_mem = await store.get_hot_memory(user_id)
                            await schedule_areqa_care_letter(
                                user_id=user_id,
                                learner_state=learner_state,
                                edf_policy=edf_policy,
                                event_summary=event_summary,
                                hot_memory_snapshot=snapshot,
                                cold_memory_context=cold_ctx,
                                last_compeer_message=hot_mem.get("last_compeer_message", ""),
                            )
                            await set_cooldown(user_id, state=learner_state)

                        await tick_proactive_schedule(user_id)
                        
                        from time import time
                        last_time = await get_last_interaction_time(user_id)
                        
                        if not await is_in_cooldown(user_id) and (time() - last_time > 60):
                            if store:
                                hot_mem = await store.get_hot_memory(user_id)
                                scroll_count = 0
                                for k, v in hot_mem.items():
                                    if k.startswith("obs_") and "Type: scroll" in str(v):
                                        scroll_count += 1
                                
                                if scroll_count >= 6:
                                    keys_to_delete = [k for k, v in hot_mem.items() if k.startswith("obs_") and "Type: scroll" in str(v)]
                                    for k in keys_to_delete:
                                        del hot_mem[k]
                                    await store.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(hot_mem, ensure_ascii=False))

                                    from gum_integration import (
                                        detect_proactive_event_via_llm,
                                        get_hot_memory_snapshot,
                                        query_cold_memory_for_context
                                    )
                                    snapshot = await get_hot_memory_snapshot(user_id)
                                    event = await detect_proactive_event_via_llm(user_id, snapshot)

                                    if event["has_event"] and event["importance"] >= 0.7:
                                        cold_ctx = await query_cold_memory_for_context(user_id, event["event_summary"])
                                        learner_state = await store.get_learner_state(user_id)
                                        edf_policy = await store.get_current_strategy(user_id)

                                        await schedule_areqa_care_letter(
                                            user_id=user_id,
                                            learner_state=learner_state,
                                            edf_policy=edf_policy,
                                            event_summary=event["event_summary"],
                                            hot_memory_snapshot=snapshot,
                                            cold_memory_context=cold_ctx,
                                            last_compeer_message=hot_mem.get("last_compeer_message", "")
                                        )
                                        await set_cooldown(user_id, state=learner_state)

            await asyncio.sleep(10)
        except Exception as e:
            print(f"[EDF-LOG] proactive_scheduler_loop error: {e}")
            await asyncio.sleep(10)
