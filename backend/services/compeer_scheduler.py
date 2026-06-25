import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path

# Global flag for user cooldown (True = can send, False = cooldown)
user_flag = {}

async def evaluate_importance_gate(event: dict) -> bool:
    """
    Evaluate if the event passes the random importance gate.
    """
    importance = float(event.get("importance", 0.5))
    return random.random() < importance

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
            if user_flag.get(user_id, True):
                passed = await evaluate_importance_gate(event)
                if passed:
                    from memory_store import get_global_store
                    store = get_global_store()
                    if store:
                        store.set_pending_alert(user_id, event.get("Content", "學習狀況還好嗎？"))
                    user_flag[user_id] = False
                
            event["fired"] = True
            changed = True
            
    if changed:
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

async def proactive_scheduler_loop():
    while True:
        await asyncio.sleep(60)
        await tick_proactive_schedule("default_user")
