import sys
from pathlib import Path
import asyncio
import os
from datetime import datetime
import json
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
        
    global reflection_task, obs_worker
    reflection_task = asyncio.create_task(run_reflection_loop())
    
    obs_worker = ObservationQueueWorker(process_callback=batch_process_observations, debounce_seconds=3.0)
    await obs_worker.start()
    
    print("GUM instance initialized successfully.")
    return gum_instance

async def stop_gum_instance():
    global gum_instance, reflection_task, obs_worker
    if obs_worker:
        await obs_worker.stop()
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

obs_worker = None

async def batch_process_observations(items: list[str]):
    global importance_sum, interaction_count, last_interaction_time
    last_interaction_time = datetime.now()
    
    if not gum_instance or not text_observer:
        return
        
    combined_text = " | ".join(items)
    
    try:
        neighbors = await gum_instance.query(combined_text, limit=20)
        if not neighbors:
            recent_props = await gum_instance.recent(limit=20)
            neighbors = [(p, 1.0) for p in recent_props]

        if neighbors:
            neighbor_ctx = "\n".join([f"ID: {p.id}, Text: {p.text}" for p, _ in neighbors])
            prompt = f"""Analyze the new observation against existing memories.
New observation: {combined_text}
Existing memories:
{neighbor_ctx}

Task: Determine if the new observation logically CONTRADICTS or explicitly UPDATES any of the existing memories.
- ONLY supersede an old memory if the new observation proves it is now factually incorrect or outdated.
- DO NOT supersede old memories just because the user changed the topic to something else.
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
                for t_id in target_ids:
                    await gum_instance.update_status(t_id, "superseded")
        else:
            importance_sum += 5
    except Exception as e:
        print(f"Error in evolution interceptor: {e}")
        importance_sum += 5

    await text_observer.push_text(combined_text)
    interaction_count += len(items)
    
    # Sync to Hot Memory (MemoryStore)
    try:
        from memory_store import get_global_store
        store = get_global_store()
        if store:
            for item in items:
                # Add to hot memory with timestamp
                store.update_hot_memory(f"obs_{datetime.now().timestamp()}", {"text": item, "confidence": 8.0, "decay": 5.0, "timestamp": datetime.now().timestamp()})
    except Exception as e:
        # Expected if budget exceeded, handled below
        pass
        
    await run_compaction()
    
    if importance_sum >= 100 or interaction_count >= 20:
        asyncio.create_task(run_reflection())

async def run_compaction():
    from memory_store import get_global_store, MemoryBudgetExceeded
    from compaction import calculate_activation_score, generate_stitch_tags, is_user_profile
    from cold_memory import ColdMemoryRetriever
    import os
    from pathlib import Path
    
    store = get_global_store()
    if not store: return
    
    hot_mem = store.get_hot_memory()
    serialized = json.dumps(hot_mem, ensure_ascii=False)
    
    if len(serialized) > store.budget_limit:
        print(f"[Compaction] Budget exceeded ({len(serialized)} > {store.budget_limit}). Starting compaction...")
        # Calculate scores
        scores = []
        for k, v in hot_mem.items():
            if is_user_profile(k):
                continue
            if isinstance(v, dict) and "timestamp" in v:
                age_days = (datetime.now().timestamp() - v["timestamp"]) / 86400.0
                score = calculate_activation_score(v.get("confidence", 5.0), v.get("decay", 5.0), age_days)
                scores.append((k, score, v))
            else:
                scores.append((k, 0.0, v))
                
        # Sort by score ascending (lowest first)
        scores.sort(key=lambda x: x[1])
        
        db_path = str(Path(__file__).resolve().parents[1] / "data" / "gum_data" / "gum.db")
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        cold_retriever = ColdMemoryRetriever(db_path, api_key)
        
        # Evict lowest scored items until under budget
        current_len = len(serialized)
        for k, score, v in scores:
            if current_len <= store.budget_limit * 0.8: # Evict down to 80%
                break
                
            print(f"[Compaction] Evicting {k} (score: {score:.4f})")
            
            # 1. STITCH Tagging
            text_to_tag = v["text"] if isinstance(v, dict) and "text" in v else str(v)
            tags = await generate_stitch_tags(gum_instance.client, gum_instance.model, text_to_tag)
            
            # 2. Save to Cold Memory
            # For simplicity, we just use the STITCH refined text for embedding
            refined = tags.get("refined_content", text_to_tag)
            embed = await cold_retriever.get_embedding(refined)
            
            if embed:
                with cold_retriever._get_conn() as conn:
                    # Insert into propositions (GUM table, or custom if doesn't exist)
                    # To be safe, we insert into our own cold storage table
                    import uuid
                    cursor = conn.execute(
                        "INSERT INTO propositions (text, reasoning, revision_group, context_scope, event_types, target, functional_type_seeds, confidence, decay) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                        (
                            refined, 
                            "Compacted from hot memory.", 
                            str(uuid.uuid4()),
                            tags.get("selected_context_scopes", [""])[0] if tags.get("selected_context_scopes") else None,
                            json.dumps(tags.get("selected_event_types", [])),
                            tags.get("selected_targets", [""])[0] if tags.get("selected_targets") else None,
                            json.dumps(tags.get("selected_functional_type_seeds", [])),
                            v.get("confidence", 8.0) if isinstance(v, dict) else 8.0,
                            v.get("decay", 5.0) if isinstance(v, dict) else 5.0
                        )
                    )
                    doc_id = cursor.lastrowid
                    
                    conn.execute("INSERT INTO propositions_fts (rowid, text) VALUES (?, ?)", (doc_id, refined))
                    
                    import struct
                    embed_bytes = struct.pack(f'{len(embed)}f', *embed)
                    conn.execute("INSERT INTO vec_memory (id, embedding) VALUES (?, ?)", (doc_id, embed_bytes))
                    conn.commit()
            
            # 3. Remove from Hot Memory
            del hot_mem[k]
            current_len = len(json.dumps(hot_mem, ensure_ascii=False))
            
        # Write back hot memory
        store._atomic_write(store.hot_memory_path, hot_mem)
        print("[Compaction] Finished.")

async def push_observation(text: str):
    if obs_worker:
        await obs_worker.push(text)
    else:
        await batch_process_observations([text])

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
        result = [
            {
                "id": str(p.id), 
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
        
        # Add Hot Memory and User Profile as virtual items
        from memory_store import get_global_store
        store = get_global_store()
        if store:
            profile = store.get_user_profile()
            for k, v in profile.items():
                result.append({
                    "id": f"profile:{k}",
                    "text": f"【使用者畫像】{k}: {v}",
                    "confidence": 10.0,
                    "updated_at": None,
                    "context_scope": "user_profile",
                    "event_types": [k],
                    "target": "user",
                    "functional_type_seeds": ["profile"]
                })
                
            hot_mem = store.get_hot_memory()
            for k, v in hot_mem.items():
                text = v["text"] if isinstance(v, dict) and "text" in v else str(v)
                conf = v.get("confidence", 8.0) if isinstance(v, dict) else 8.0
                result.append({
                    "id": f"hot:{k}",
                    "text": f"【近期對話】{text}",
                    "confidence": conf,
                    "updated_at": None,
                    "context_scope": "hot_memory",
                    "event_types": [k],
                    "target": "system",
                    "functional_type_seeds": ["hot_memory"]
                })
                
        return result
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

class ObservationQueueWorker:
    def __init__(self, process_callback, debounce_seconds: float = 3.0):
        self.queue = asyncio.Queue()
        self.process_callback = process_callback
        self.debounce_seconds = debounce_seconds
        self._task = None

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def push(self, observation: str):
        await self.queue.put(observation)

    async def _worker(self):
        while True:
            try:
                # Wait for at least one item
                items = [await self.queue.get()]
                
                # Debounce window
                await asyncio.sleep(self.debounce_seconds)
                
                # Collect any other items that arrived during the window
                while not self.queue.empty():
                    try:
                        items.append(self.queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                        
                # Process the batch
                if items:
                    await self.process_callback(items)
                    
                # Mark as done
                for _ in items:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in ObservationQueueWorker: {e}")
                await asyncio.sleep(1)

def get_hot_memory_snapshot() -> str:
    from memory_store import get_global_store
    import json
    store = get_global_store()
    if not store:
        return ""
    
    # Combine user profile and hot memory for the snapshot
    profile = store.get_user_profile()
    hot_mem = store.get_hot_memory()
    
    parts = []
    if profile:
        parts.append("【使用者畫像 (User Profile)】\n" + json.dumps(profile, ensure_ascii=False, indent=2))
    if hot_mem:
        # Extract just the text from hot memory items
        hot_texts = [v["text"] if isinstance(v, dict) and "text" in v else str(v) for v in hot_mem.values()]
        parts.append("【近期記憶 (Hot Memory)】\n- " + "\n- ".join(hot_texts))
        
    return "\n\n".join(parts)

async def generate_zpd_query_via_llm(client, model, original_query, learner_state):
    prompt = f"""You are an educational AI converting a student's question into a ZPD-aligned search query.
Student's current learning state: {learner_state}
Original query: {original_query}

If the state is "TINKERING" or "RUN_REPEAT", focus on underlying concepts rather than the exact syntax.
If the state is "STARTING", focus on fundamental definitions.
Otherwise, refine the query to be pedagogical.
Return ONLY the refined query string without any quotes or explanations."""
    try:
        rsp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ZPD Query Gen] Error: {e}")
        return original_query

async def query_cold_memory_for_context(query: str, top_k: int = 5) -> str:
    from cold_memory import ColdMemoryRetriever
    from memory_store import get_global_store
    import os
    from pathlib import Path
    
    db_path = str(Path(__file__).resolve().parents[1] / "data" / "gum_data" / "gum.db")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return ""
        
    try:
        store = get_global_store()
        learner_state = store.get_learner_state() if store else "STARTING"
        
        zpd_query = await generate_zpd_query_via_llm(gum_instance.client, gum_instance.model, query, learner_state)
        
        cold_retriever = ColdMemoryRetriever(db_path, api_key)
        results = await cold_retriever.search(zpd_query, top_k)
        if not results:
            return ""
            
        parts = ["【檢索到的長尾記憶 (Cold Memory)】"]
        for r in results:
            parts.append(f"- {r['text']}")
            
        return "\n".join(parts)
    except Exception as e:
        print(f"[GUM] Error querying cold memory: {e}")
        return ""

async def async_evaluate_and_update_state(client, model, chat_history):
    from compaction import evaluate_student_state
    from memory_store import get_global_store
    
    state_res = await evaluate_student_state(client, model, chat_history)
    store = get_global_store()
    if store:
        await store.update_hot_memory_async("current_learner_state", state_res.get("learner_state", "STARTING"))
        await store.update_hot_memory_async("current_strategy", state_res.get("pedagogical_strategy", "NORMAL"))
        if state_res.get("trigger_proactive"):
            # We flag this for ComPeer to pick up or log it
            print(f"[ComPeer] Proactive trigger needed: {state_res}")
            await store.update_hot_memory_async("trigger_proactive", True)

