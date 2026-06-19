import sys
from pathlib import Path
import asyncio
import os
from datetime import datetime

# Add misc/gum to sys.path
project_root = Path(__file__).resolve().parents[1]
gum_dir = project_root / "misc" / "gum"
if str(gum_dir) not in sys.path:
    sys.path.insert(0, str(gum_dir))

from gum.gum import gum
from gum.observers import Observer
from gum.schemas import Update

class TextObserver(Observer):
    def __init__(self, name="TextChatObserver"):
        super().__init__(name)
        
    async def push_text(self, text: str):
        # We wrap the text in an Update object
        await self.update_queue.put(Update(content=text, content_type="input_text"))

    async def start(self):
        pass

    async def stop(self):
        pass
        
    async def _worker(self):
        while True:
            await asyncio.sleep(3600)

# Global instances
text_observer = None
gum_instance = None

async def init_gum_instance():
    global gum_instance, text_observer
    text_observer = TextObserver()
    
    # Initialize GUM
    data_dir = str(project_root / "data" / "gum_data")
    os.makedirs(data_dir, exist_ok=True)
    
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    
    gum_instance = gum(
        "default_user",
        "qwen/qwen3-235b-a22b-2507",
        text_observer,
        data_directory=data_dir,
        db_name="gum.db",
        api_key=api_key,
        min_batch_size=1, # Setting to 1 to see immediate results for QA
        max_batch_size=10,
    )
    await gum_instance.connect_db()
    gum_instance.start_update_loop()
    if gum_instance.batcher:
        await gum_instance.batcher.start()
        
    global reflection_task
    reflection_task = asyncio.create_task(run_reflection_loop())
    
    print("GUM instance initialized successfully.")
    return gum_instance

async def stop_gum_instance():
    global gum_instance, reflection_task
    if reflection_task:
        reflection_task.cancel()
    if gum_instance:
        await gum_instance.stop_update_loop()
        if gum_instance.batcher:
            await gum_instance.batcher.stop()

importance_sum = 0
interaction_count = 0
last_interaction_time = None

async def run_reflection():
    global importance_sum, interaction_count
    if not gum_instance:
        return
    try:
        obs = await gum_instance.recent_observations(limit=20)
        if not obs:
            return
            
        context = "\n".join([o.content for o in obs])
        prompt = f"Summarize the following recent interactions into high-level insights:\n{context}\nOutput the insights."
        
        from pydantic import BaseModel
        from gum.schemas import get_schema
        class ReflectionSchema(BaseModel):
            insights: list[str]
            
        rsp = await gum_instance.client.chat.completions.create(
            model=gum_instance.model,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(ReflectionSchema.model_json_schema()),
        )
        import json
        data = json.loads(rsp.choices[0].message.content)
        
        insights = data.get("insights", [])
        print(f"[GUM Reflection] Reflection triggered! Generated {len(insights)} insights:")
        for insight in insights:
            print(f"  - {insight}")
            if text_observer:
                await text_observer.push_text(f"[REFLECTION] {insight}")
                
        # Archive old observations
        for o in obs:
            await gum_instance.update_observation_status(o.id, "archived")
            
        print(f"[GUM Reflection] Archived {len(obs)} old observations. Resetting counters.")
        importance_sum = 0
        interaction_count = 0
    except Exception as e:
        print(f"Error in reflection: {e}")

async def query_memory_for_context(user_query: str, limit: int = 8) -> str:
    """
    Query GUM memory and return a formatted string for System Prompt injection.

    This is the critical bridge between STITCH-filtered memory and the LLM prompt.
    Without this, the STITCH subsystem correctly retrieves memories but never passes
    them to the main LLM, making memory invisible to the AI.

    Args:
        user_query: The user's current message to use as the search query.
        limit: Maximum number of memory propositions to inject.

    Returns:
        A formatted <memory> block string for system prompt injection, or "" if no memory.
    """
    if not gum_instance:
        return ""
    try:
        results = await gum_instance.query(user_query, limit=limit)
        if not results:
            return ""
        lines = [p.text for p, _ in results]
        memory_block = "\n".join(f"- {line}" for line in lines)
        return f"\n<memory>\n以下是關於使用者的已知記憶，請根據這些記憶來個人化你的回答：\n{memory_block}\n</memory>"
    except Exception as e:
        print(f"[GUM] Error querying memory for context: {e}")
        return ""

async def push_observation(text: str):
    global importance_sum, interaction_count, last_interaction_time
    last_interaction_time = datetime.now()
    
    if not gum_instance or not text_observer:
        return
        
    try:
        neighbors = await gum_instance.query(text, limit=20)
        if not neighbors:
            # Fallback to recent memory since BM25 fails on CJK strings without spaces
            recent_props = await gum_instance.recent(limit=20)
            neighbors = [(p, 1.0) for p in recent_props]

        if neighbors:
            neighbor_ctx = "\n".join([f"ID: {p.id}, Text: {p.text}" for p, _ in neighbors])
            prompt = f"""Analyze the new observation against existing memories.
New observation: {text}
Existing memories:
{neighbor_ctx}

Task: Determine if the new observation logically CONTRADICTS or explicitly UPDATES any of the existing memories.
- ONLY supersede an old memory if the new observation proves it is now factually incorrect or outdated (e.g., user previously said "I don't know X", but now says "I understand X").
- DO NOT supersede old memories just because the user changed the topic to something else. A user can have multiple independent memories at the same time.
- If it supersedes, set should_evolve=true, add 'prune' to actions, and put ONLY the strictly contradicted IDs in target_ids. Otherwise, set should_evolve=false.
Rate importance 1-10."""
            
            from pydantic import BaseModel
            from gum.schemas import get_schema
            class EvolutionSchema(BaseModel):
                should_evolve: bool
                actions: list[str]
                target_ids: list[int]
                importance_score: int
                
            rsp = await gum_instance.client.chat.completions.create(
                model=gum_instance.model,
                messages=[{"role": "user", "content": prompt}],
                response_format=get_schema(EvolutionSchema.model_json_schema()),
            )
            import json
            import re
            content = rsp.choices[0].message.content.strip()
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                content = match.group(0)
            decision = json.loads(content)
            
            print(f"[GUM Evolution] LLM decision: {decision}")
            
            importance_sum += decision.get("importance_score", 5)
            
            if decision.get("should_evolve") and "prune" in decision.get("actions", []):
                target_ids = decision.get("target_ids", [])
                print(f"[GUM Evolution] Superseding old memory IDs: {target_ids}")
                for t_id in target_ids:
                    await gum_instance.update_status(t_id, "superseded")
        else:
            # If still no neighbors (e.g. very first message), default to 5
            importance_sum += 5
    except Exception as e:
        print(f"Error in evolution interceptor: {e}")
        importance_sum += 5

    await text_observer.push_text(text)
    interaction_count += 1
    
    if importance_sum >= 100 or interaction_count >= 20:
        asyncio.create_task(run_reflection())

async def run_reflection_loop():
    """Background task to run reflection if user is idle for 30 minutes."""
    global last_interaction_time
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        if not gum_instance or last_interaction_time is None:
            continue
        
        idle_time = datetime.now() - last_interaction_time
        if idle_time.total_seconds() > 1800 and interaction_count > 0:
            print("Idle for 30 minutes, triggering session boundary reflection.")
            await run_reflection()

reflection_task = None

async def get_all_memory():
    if not gum_instance:
        return []
    try:
        import json
        props = await gum_instance.recent(limit=100)
        return [
            {
                "id": p.id, 
                "text": p.text, 
                "confidence": p.confidence, 
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "context_scope": p.context_scope,
                "event_types": json.loads(p.event_types) if p.event_types else [],
                "target": p.target,
                "functional_type_seeds": json.loads(p.functional_type_seeds) if p.functional_type_seeds else []
            } 
            for p in props
        ]
    except Exception as e:
        print(f"Error fetching memory: {e}")
        return []

async def get_suggestions():
    if not gum_instance:
        return []
    try:
        props = await gum_instance.recent(limit=10)
        if not props:
            return []
        
        from gum.schemas import get_schema
        from pydantic import BaseModel
        
        class SuggestionsResponse(BaseModel):
            suggestions: list[str]
            
        context = "\n".join([f"- {p.text} (confidence: {p.confidence})" for p in props])
        prompt = f"Based on the following facts about the user:\n{context}\n\nGenerate 3 short, engaging, and actionable suggestions for what the user might want to explore next in a classical Chinese literature (like Dream of the Red Chamber) QA system. Make them sound like natural questions the user could click to ask. Output exactly 3 strings in the array."
        
        rsp = await gum_instance.client.chat.completions.create(
            model=gum_instance.model,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(SuggestionsResponse.model_json_schema()),
        )
        import json
        data = json.loads(rsp.choices[0].message.content)
        return data.get("suggestions", [])
    except Exception as e:
        print(f"Error generating suggestions: {e}")
        return []

