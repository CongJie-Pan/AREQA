import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path

import time as _time

user_cooldown_until: dict[str, float] = {}  # user_id -> Unix timestamp (seconds)
last_interaction_time: dict[str, float] = {}

def is_in_cooldown(user_id: str) -> bool:
    """Return True if the user is within the cooldown period."""
    return _time.time() < user_cooldown_until.get(user_id, 0)

def set_cooldown(user_id: str, state: str = "default") -> None:
    """Set a cooldown period dynamically based on the learner state."""
    COOLDOWN_BY_STATE = {
        "NOT_STARTED": 2.0,
        "GIVING_UP": 0.25,
        "STARTING": 1.0,
        "TINKERING": 0.5,
        "MASTERY": 2.0,
        "default": 0.5
    }
    hours = COOLDOWN_BY_STATE.get(state, COOLDOWN_BY_STATE["default"])
    expire_time = _time.time() + hours * 3600
    user_cooldown_until[user_id] = expire_time
    # Also persist to hot_memory
    from memory_store import get_global_store
    import asyncio
    store = get_global_store()
    if store:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(store.update_hot_memory_async("user_cooldown_until", expire_time))
        except RuntimeError:
            pass

async def evaluate_importance_gate(event: dict) -> bool:
    """
    Evaluate if the event passes the random importance gate.
    """
    importance = float(event.get("importance", 0.5))
    passed = random.random() < importance
    print(f"[EDF-LOG] evaluate_importance_gate: event='{event.get('Content')}', importance={importance}, passed={passed}")
    return passed

async def tick_proactive_schedule(user_id: str):
    """
    Check the proactive schedule for this user.
    """
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
            if not is_in_cooldown(user_id):
                passed = await evaluate_importance_gate(event)
                if passed:
                    from memory_store import get_global_store
                    store = get_global_store()
                    if store:
                        content = event.get("Content", "學習狀況還好嗎？")
                        print(f"[EDF-LOG] tick_proactive_schedule: firing alert for {user_id} with content: {content}")
                        store.set_pending_alert(user_id, content)
                    learner_state = store.get_learner_state() if store else "default"
                    set_cooldown(user_id, state=learner_state)
                
            event["fired"] = True
            changed = True
            
    if changed:
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

async def initialize_daily_schedule(user_id: str, reflection_outputs: list):
    try:
        from gum_integration import gum_instance
        print(f"DEBUG: initialize_daily_schedule called. gum_instance={gum_instance}")
        if not gum_instance:
            print("DEBUG: gum_instance is falsy, returning early")
            return
        print("DEBUG: Calling mock gum_instance...")
        
        prompt = f"""基於以下昨日的學習反思，請為學生規劃今日的主動關懷排程 (包含關心學習進度、挫折安撫等)。
反思紀錄:
{reflection_outputs}

請嚴格回傳 JSON 格式，包含 events 陣列，每個元素包含：
- "Timing": "HH:MM" (例如 "14:30")
- "Content": "預計發送的關心內容"
- "importance": 0.0 到 1.0 之間的數值
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
        print(f"[EDF-LOG] initialize_daily_schedule for {user_id} generated:\n{content}")
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
    """
    Run end-of-day reflection using GUM's semantic compression,
    then generate tomorrow's proactive care schedule based on real insights.
    """
    try:
        from gum_integration import run_reflection
        insights = await run_reflection()

        if not insights:
            print(f"[Daily Scheduler] No insights from GUM reflection, skipping.")
            return

        print(f"[Daily Scheduler] GUM reflection produced {len(insights)} insights for {user_id}.")
        await initialize_daily_schedule(user_id, insights)

    except Exception as e:
        print(f"[Daily Scheduler] run_reflection_and_initialization failed: {e}")

async def daily_scheduler_loop():
    print("[EDF-LOG] Starting daily_scheduler_loop background task.")
    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            from memory_store import get_global_store
            store = get_global_store()
            if store:
                hot_mem = store.get_hot_memory()
                last_reflection = hot_mem.get("last_reflection_date")
                
                if last_reflection != today_str:
                    # Run reflection if it's past 23:00, OR if we missed it completely (e.g. restarting after skipping a day)
                    if now.hour >= 23 or last_reflection is None:
                        await run_reflection_and_initialization("default_user")
                        await store.update_hot_memory_async("last_reflection_date", today_str)
            
            await asyncio.sleep(60)
        except Exception as e:
            print(f"[EDF-LOG] daily_scheduler_loop error: {e}")
            await asyncio.sleep(60)

_send_lock = None
_flag_lock = None

async def proactive_scheduler_loop():
    print("[EDF-LOG] Starting proactive_scheduler_loop background task.")
    global _send_lock, _flag_lock
    if _send_lock is None:
        _send_lock = asyncio.Lock()
    if _flag_lock is None:
        _flag_lock = asyncio.Lock()
    while True:
        try:
            async with _send_lock:
                user_id = "default_user"
                from memory_store import get_global_store
                store = get_global_store()
                if store and not is_in_cooldown(user_id):
                    # Consume flag safely
                    trigger_proactive = False
                    learner_state = "STARTING"
                    async with _flag_lock:
                        hot_mem = store.get_hot_memory()
                        if hot_mem.get("trigger_proactive"):
                            trigger_proactive = True
                            learner_state = hot_mem.get("current_learner_state", "STARTING")
                            # 消費信號，防止重複觸發
                            del hot_mem["trigger_proactive"]
                            store._atomic_write(store.hot_memory_path, hot_mem)

                    if trigger_proactive:
                        print(f"[ComPeer] trigger_proactive detected! learner_state={learner_state}")
                        from gum_integration import (
                            generate_scaffolding_message_via_llm,
                            get_hot_memory_snapshot,
                            query_cold_memory_for_context
                        )
                        snapshot = get_hot_memory_snapshot()
                        event_summary = f"EDF 系統偵測到使用者遭遇學習瓶頸 (狀態: {learner_state})"
                        cold_ctx = await query_cold_memory_for_context(event_summary)
                        edf_policy = store.get_current_strategy()

                        message = await generate_scaffolding_message_via_llm(
                            hot_memory_snapshot=snapshot,
                            cold_memory_context=cold_ctx,
                            learner_state=learner_state,
                            edf_policy=edf_policy,
                            event_summary=event_summary,
                            last_compeer_message=hot_mem.get("last_compeer_message", "")
                        )

                        await store.update_hot_memory_async("last_compeer_message", message)

                        from services.connection_manager import ws_manager
                        asyncio.create_task(ws_manager.broadcast_alert(user_id, message))
                        set_cooldown(user_id, state=learner_state)

            # --- 原有路徑：定時排程事件 ---
            await tick_proactive_schedule(user_id)
            
            # --- Check for frustration signs (like continuous scrolling) ---
            from time import time
            if "default_user" not in last_interaction_time:
                last_interaction_time["default_user"] = time()
                
            last_time = last_interaction_time["default_user"]
            
            if not is_in_cooldown(user_id) and (time() - last_time > 60):
                if store:
                    hot_mem = store.get_hot_memory()
                    scroll_count = 0
                    for k, v in hot_mem.items():
                        if k.startswith("obs_") and "Type: scroll" in str(v):
                            scroll_count += 1
                    
                    if scroll_count >= 6:
                        keys_to_delete = [k for k, v in hot_mem.items() if k.startswith("obs_") and "Type: scroll" in str(v)]
                        for k in keys_to_delete:
                            del hot_mem[k]
                        store._atomic_write(store.hot_memory_path, hot_mem)

                        from gum_integration import (
                            detect_proactive_event_via_llm,
                            generate_scaffolding_message_via_llm,
                            get_hot_memory_snapshot,
                            query_cold_memory_for_context
                        )
                        snapshot = get_hot_memory_snapshot()
                        event = await detect_proactive_event_via_llm(snapshot)

                        if not event["has_event"]:
                            print("[ComPeer] Event detector: normal browsing, staying silent.")
                        elif event["importance"] >= 0.7:
                            cold_ctx = await query_cold_memory_for_context(event["event_summary"])
                            learner_state = store.get_learner_state()
                            edf_policy = store.get_current_strategy()

                            message = await generate_scaffolding_message_via_llm(
                                hot_memory_snapshot=snapshot,
                                cold_memory_context=cold_ctx,
                                learner_state=learner_state,
                                edf_policy=edf_policy,
                                event_summary=event["event_summary"],
                                last_compeer_message=hot_mem.get("last_compeer_message", "")
                            )

                            await store.update_hot_memory_async("last_compeer_message", message)

                            from services.connection_manager import ws_manager
                            asyncio.create_task(ws_manager.broadcast_alert(user_id, message))
                            set_cooldown(user_id, state=learner_state)
                            print(f"[ComPeer] Scaffolding alert sent. importance={event['importance']:.2f}")
                        else:
                            print(f"[ComPeer] Importance gate not passed ({event['importance']:.2f}), skipping.")
                                
            await asyncio.sleep(10) # Check every 10 seconds for real-time responsiveness
        except Exception as e:
            print(f"[EDF-LOG] proactive_scheduler_loop error: {e}")
            await asyncio.sleep(10)
