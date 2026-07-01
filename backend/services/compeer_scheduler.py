import asyncio
import json
import os
import random
from datetime import datetime
from pathlib import Path

# Global flag for user cooldown (True = can send, False = cooldown)
user_flag = {}
last_interaction_time = {}

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
            if user_flag.get(user_id, True):
                passed = await evaluate_importance_gate(event)
                if passed:
                    from memory_store import get_global_store
                    store = get_global_store()
                    if store:
                        content = event.get("Content", "學習狀況還好嗎？")
                        print(f"[EDF-LOG] tick_proactive_schedule: firing alert for {user_id} with content: {content}")
                        store.set_pending_alert(user_id, content)
                    user_flag[user_id] = False
                
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
    project_root = Path(__file__).resolve().parents[2]
    log_path = project_root / "data" / "gum_data" / f"reflection_log_{user_id}.jsonl"
    
    if not os.path.exists(log_path):
        print(f"DEBUG: log_path does not exist: {log_path}")
        return
    print(f"DEBUG: Found log_path: {log_path}")
        
    chat_logs = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    chat_logs.append(json.loads(line))
                except:
                    pass
                    
    if not chat_logs:
        print(f"DEBUG: chat_logs is empty for {log_path}")
        return
        
    reflection_outputs = [f"User had {len(chat_logs)} interactions yesterday."]
    await initialize_daily_schedule(user_id, reflection_outputs)
    
    # 清空 log
    open(log_path, "w").close()

async def daily_scheduler_loop():
    print("[EDF-LOG] Starting daily_scheduler_loop background task.")
    while True:
        try:
            now = datetime.now()
            if now.hour == 23 and now.minute == 59:
                await run_reflection_and_initialization("default_user")
                await asyncio.sleep(60) # Wait a minute to avoid retriggering
            else:
                await asyncio.sleep(30)
        except Exception as e:
            print(f"[EDF-LOG] daily_scheduler_loop error: {e}")
            await asyncio.sleep(60)

async def proactive_scheduler_loop():
    print("[EDF-LOG] Starting proactive_scheduler_loop background task.")
    while True:
        try:
            # We assume a default user "default_user" for this example
            await tick_proactive_schedule("default_user")
            
            # Check for frustration signs (like continuous scrolling) if not in cooldown
            from time import time
            last_time = last_interaction_time.get("default_user", time())
            if user_flag.get("default_user", True) and (time() - last_time > 120):
                from memory_store import get_global_store
                store = get_global_store()
                if store:
                    # `get_hot_memory()` returns a sync dictionary snapshot
                    hot_mem = store.get_hot_memory()
                    scroll_count = 0
                    for k, v in hot_mem.items():
                        if k.startswith("obs_") and "Type: scroll" in str(v):
                            scroll_count += 1
                    
                    if scroll_count >= 6:
                        print("[EDF-LOG] Detected high scroll activity! Setting PROBE_UNDERSTANDING.")
                        
                        # Set alert directly in hot_mem dictionary before writing
                        hot_mem[f"pending_alert_default_user"] = "AREQA發現你好像來回看了幾遍，有哪邊覺得不太清楚，需要我幫忙梳理嗎？"
                        user_flag["default_user"] = False # Put into cooldown
                        
                        # Clean up those scrolls to avoid re-triggering immediately
                        keys_to_delete = [k for k, v in hot_mem.items() if k.startswith("obs_") and "Type: scroll" in str(v)]
                        for k in keys_to_delete:
                            del hot_mem[k]
                            
                        # Write back once with both the alert added and the scrolls deleted
                        store._atomic_write(store.hot_memory_path, hot_mem)
                        
                        from backend.services.connection_manager import ws_manager
                        import asyncio
                        asyncio.create_task(
                            ws_manager.broadcast_alert("default_user", hot_mem["pending_alert_default_user"])
                        )
                        
                        print(f"[EDF-LOG] set_pending_alert: setting alert for user 'default_user' and cleared {len(keys_to_delete)} scrolls.")
                                
            await asyncio.sleep(10) # Check every 10 seconds for real-time responsiveness
        except Exception as e:
            print(f"[EDF-LOG] proactive_scheduler_loop error: {e}")
            await asyncio.sleep(10)
