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

async def initialize_daily_schedule(user_id: str, reflection_outputs: list):
    try:
        from gum_integration import gum_instance
        if not gum_instance:
            return
        
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
        return
        
    chat_logs = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    chat_logs.append(json.loads(line))
                except:
                    pass
                    
    if not chat_logs:
        return
        
    reflection_outputs = [f"User had {len(chat_logs)} interactions yesterday."]
    await initialize_daily_schedule(user_id, reflection_outputs)
    
    # 清空 log
    open(log_path, "w").close()

async def daily_scheduler_loop():
    while True:
        now = datetime.now()
        if now.hour == 23 and now.minute == 59:
            await run_reflection_and_initialization("default_user")
            await asyncio.sleep(60) # Wait a minute to avoid retriggering
        else:
            await asyncio.sleep(30)

async def proactive_scheduler_loop():
    while True:
        await asyncio.sleep(60)
        await tick_proactive_schedule("default_user")
