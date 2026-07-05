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
    from config import settings
    
    gum_instance = gum(
        "default_user",
        settings.model_gum,
        text_observer,
        data_directory=data_dir,
        db_name="gum.db",
        api_key=api_key,
        api_base="https://openrouter.ai/api/v1",
        min_batch_size=17,
        max_batch_size=20,
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

async def clear_gum_memory():
    """Clear all GUM memory from the database."""
    global gum_instance, importance_sum, interaction_count
    importance_sum = 0
    interaction_count = 0
    import shutil
    import os
    
    if gum_instance:
        try:
            await gum_instance.stop_update_loop()
            if gum_instance.batcher:
                await gum_instance.batcher.stop()
                
            if hasattr(gum_instance, 'engine') and gum_instance.engine:
                await gum_instance.engine.dispose()
                gum_instance.engine = None
                gum_instance.Session = None
                
            data_dir = gum_instance._data_directory
            if os.path.exists(data_dir):
                shutil.rmtree(data_dir)
            os.makedirs(data_dir, exist_ok=True)
            
            await gum_instance.connect_db()
            gum_instance.start_update_loop()
            if gum_instance.batcher:
                await gum_instance.batcher.start()
                
            print("[GUM] Completely wiped GUM data directory and recreated it.")
        except Exception as e:
            print(f"[GUM] Error clearing memory directory: {e}")

importance_sum = 0
interaction_count = 0
last_interaction_time = None

async def run_reflection() -> list[str]:
    global importance_sum, interaction_count
    if not gum_instance:
        return []
    try:
        obs = await gum_instance.recent_observations(limit=20)
        if not obs:
            return []
            
        context = "\n".join([o.content for o in obs])
        prompt = f"請將以下最近的互動紀錄總結為高層次的學習洞察（insights）：\n{context}\n請輸出這些學習洞察。"
        
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
        return insights
    except Exception as e:
        print(f"Error in reflection: {e}")
        return []

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
        memory_lines = []
        from memory_store import get_global_store
        store = get_global_store()
        if store:
            profile = store.get_user_profile()
            prefs = profile.get("explicit_memories", [])
            if prefs:
                memory_lines.append("【USER PROFILE (長期)】\n  - " + "\n  - ".join(prefs))
            
            hot = store.get_hot_memory()
            hot_memories = hot.get("explicit_memories", [])
            if hot_memories:
                memory_lines.append("【MEMORY (目前脈絡)】\n  - " + "\n  - ".join(hot_memories))
        
        if results:
            memory_lines.extend([p.text for p, _ in results])
            
        if not memory_lines:
            return ""
            
        memory_block = "\n".join(f"- {line}" for line in memory_lines)
        return f"\n<memory>\n以下是關於使用者的已知記憶，請根據這些記憶來個人化你的回答：\n{memory_block}\n</memory>"
    except Exception as e:
        print(f"[GUM] Error querying memory for context: {e}")
        return ""

obs_worker = None

async def batch_process_observations(items: list[str]):
    global importance_sum, interaction_count, last_interaction_time
    last_interaction_time = datetime.now()
    
    if gum_instance and text_observer:
        combined_text = " | ".join(items)
        try:
            neighbors = await gum_instance.query(combined_text, limit=20)
            if not neighbors:
                recent_props = await gum_instance.recent(limit=20)
                neighbors = [(p, 1.0) for p in recent_props]
    
            if neighbors:
                neighbor_ctx = "\\n".join([f"ID: {p.id}, Text: {p.text}" for p, _ in neighbors])
                prompt = f"""Analyze the new observation against existing memories.
    New observation: {combined_text}
    Existing memories:
    {neighbor_ctx}
    
    Task: 
    1. Determine if the new observation logically CONTRADICTS, UPDATES, or is highly REDUNDANT with any existing memories.
    2. If it is redundant or updates old memories, set should_evolve=true, add 'prune' to actions, and put the old memory IDs to be pruned in target_ids. 
    3. Provide a 'revised_proposition' that merges the new observation and the pruned memories into a single concise, updated statement.
    4. Generate a 'decay_score' (1-10) for this proposition. Transient or temporary actions (e.g. debugging a specific bug) decay fast (score=8-10). Stable facts (e.g. user is a PhD student) decay slowly (score=1-3).
    5. Rate importance 1-10."""
                
                from pydantic import BaseModel, Field
                from gum.schemas import get_schema
                from typing import Optional
                class EvolutionSchema(BaseModel):
                    should_evolve: bool
                    actions: list[str]
                    target_ids: list[int]
                    importance_score: int
                    revised_proposition: Optional[str] = Field(None, description="The merged and updated proposition")
                    decay_score: int = Field(5, description="1-10 score of how fast this memory should decay")
                    
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
                
                final_text = decision.get("revised_proposition") if decision.get("should_evolve") and decision.get("revised_proposition") else combined_text
                final_decay = decision.get("decay_score", 5.0)
            else:
                importance_sum += 5
                final_text = combined_text
                final_decay = 5.0
        except Exception as e:
            print(f"Error in evolution interceptor: {e}")
            importance_sum += 5
            final_text = combined_text
            final_decay = 5.0
    
        await text_observer.push_text(combined_text)
        interaction_count += len(items)
    else:
        combined_text = " | ".join(items)
        
    # Sync to Hot Memory (MemoryStore)
    try:
        from memory_store import get_global_store
        store = get_global_store()
        if store:
            import uuid
            # Add to hot memory with timestamp and uuid to prevent overwriting
            key = f"obs_{datetime.now().timestamp()}_{uuid.uuid4().hex[:8]}"
            store.update_hot_memory(key, {
                "text": final_text, 
                "confidence": 8.0, 
                "decay": float(final_decay), 
                "timestamp": datetime.now().timestamp()
            })
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
    if not store or not gum_instance: return
    
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
            for p in props if getattr(p, "status", "") not in ["deleted", "superseded"]
        ]
        return result
    except Exception as e:
        print(f"Error fetching memory: {e}")
        return []



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
        # Filter out scroll noise and internal states
        meaningful_hot = {
            k: v for k, v in hot_mem.items()
            if not (isinstance(v, dict) and "User Action: scroll" in v.get("text", ""))
            and k not in ("user_cooldown_until", "trigger_proactive", "current_learner_state", "current_strategy", "last_compeer_message")
        }
        # Extract just the text from hot memory items
        hot_texts = [v["text"] if isinstance(v, dict) and "text" in v else str(v) for v in meaningful_hot.values()]
        if hot_texts:
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

async def query_cold_memory_for_context(query: str, top_k: int = 5, client=None, model=None) -> str:
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
        
        c = client if client else (gum_instance.client if gum_instance else None)
        m = model if model else (gum_instance.model if gum_instance else "qwen/qwen-turbo")
        if not c:
            from openai import AsyncOpenAI
            c = AsyncOpenAI(api_key=api_key)
            
        zpd_query = await generate_zpd_query_via_llm(c, m, query, learner_state)
        
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
        if state_res.get("active_avatar"):
            current_avatar = store.get_hot_memory().get("active_avatar")
            if state_res["active_avatar"] != current_avatar:
                print(f"[ComPeer] NEW Active Avatar detected: {state_res['active_avatar']}")
                await store.update_hot_memory_async("active_avatar", state_res["active_avatar"])
                await store.update_hot_memory_async("avatar_summon_pending", True)
        elif state_res.get("active_avatar") is None:
            hot_mem = store.get_hot_memory()
            if "active_avatar" in hot_mem:
                print(f"[ComPeer] Clearing Active Avatar: {hot_mem['active_avatar']}")
                del hot_mem["active_avatar"]
                store._atomic_write(store.hot_memory_path, hot_mem)
        if state_res.get("trigger_proactive"):
            # We flag this for ComPeer to pick up or log it
            print(f"[ComPeer] Proactive trigger needed: {state_res}")
            await store.update_hot_memory_async("trigger_proactive", True)
            
        ops = state_res.get("memory_operations", [])
        if ops:
            for op in ops:
                target = op.get("target")
                action = op.get("action")
                content = op.get("content")
                old_text = op.get("old_text", "")
                if target in ["user", "memory"] and action in ["add", "replace", "remove"] and content:
                    store.perform_memory_operation(target, action, content, old_text)
                    print(f"[EDF-LOG] Executed memory operation: {op}")


async def detect_proactive_event_via_llm(hot_memory_snapshot: str) -> dict:
    """
    Analyze hot memory snapshot to determine if a proactive intervention is warranted.
    """
    if not gum_instance:
        return {"has_event": False, "event_summary": "", "importance": 0.0}

    from pydantic import BaseModel
    from gum.schemas import get_schema

    class EventDetectSchema(BaseModel):
        has_event: bool
        event_summary: str
        importance: float

    prompt = f"""你是一個學習行為分析師。以下是用戶最近的行為與對話快照：
{hot_memory_snapshot}

請判斷：
1. 用戶是否正在面臨「具體的學習挑戰」或「負面情緒（如挫折、困惑、反覆卡住）」？
2. 如果是，給出事件摘要與重要性（0.0–1.0）。
3. 如果只是正常瀏覽或學習進展順暢，請回傳 has_event=false，重要性設為 0。

請嚴格以 JSON 格式回傳。"""

    try:
        from config import settings
        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_policy_classifier,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(EventDetectSchema.model_json_schema()),
            temperature=0.1
        )
        import json as _json
        return _json.loads(rsp.choices[0].message.content)
    except Exception as e:
        print(f"[ComPeer] detect_proactive_event_via_llm failed: {e}")
        return {"has_event": False, "event_summary": "", "importance": 0.0}


async def generate_scaffolding_message_via_llm(
    hot_memory_snapshot: str,
    cold_memory_context: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str = "",
    last_compeer_message: str = "",
    active_avatar: str = None
) -> str:
    """
    Generate a personalized scaffolding message for proactive ComPeer intervention.
    """
    if not gum_instance:
        return "你學習狀況還好嗎？有任何問題都可以問我。"

    strategy_hints = {
        "GIVING_UP":   "語氣溫柔、帶情感支持，先安撫再提問。",
        "RUN_REPEAT":  "提供一個新的切入角度或比喻，引導跳出迴圈。",
        "TINKERING":   "提出一個具體的蘇格拉底式問題，促進深化思考。",
        "MASTERY":     "挑戰性地提出一個反例或更深層的問題。",
        "STARTING":    "提供一個簡短的背景知識錨點，降低門檻。",
    }
    hint = strategy_hints.get(learner_state, "自然地詢問用戶的學習進展。")

    tone_constraint = ""
    if learner_state == "STARTING":
        tone_constraint = "\n【動態表達限制：STARTING 階段】\n注意：使用者目前為初學者（STARTING）。你必須「嚴格降低詞彙難度」，絕對禁止使用未經解釋的進階專有名詞。請用最白話、最生活化的比喻來引導，一次只講一個重點，避免造成認知負荷超載。"
    elif learner_state == "TINKERING":
        tone_constraint = "\n【動態表達限制：TINKERING 階段】\n注意：使用者正在摸索與建構概念（TINKERING）。你可以適度引入專有名詞，但必須伴隨具體例證與解釋。鼓勵思辨，但避免過度拋出艱澀的哲學大哉問而讓使用者不知所措。"

    last_msg_hint = f"\n【禁止重複】上一次已經問過：「{last_compeer_message}」，本次訊息不得與此主題重複。" if last_compeer_message else ""

    if active_avatar:
        roleplay_instruction = f"你現在已被召喚為歷史人物/思想家：「{active_avatar}」。用戶正在學習或探討你的思想。\n請完全沉浸在這個角色中，用{active_avatar}特有的語氣（例如第一人稱、特有的哲學比喻或經典口吻），主動發一句話打斷用戶，丟出一個符合你身份的靈魂拷問或啟發式提問。"
    else:
        roleplay_instruction = "你是 AREQA，一個溫暖且專業的古典文學學習夥伴。\n現在你需要主動關心用戶，根據以下資訊生成一句**精準的**主動關懷訊息。"

    prompt = f"""{roleplay_instruction}

【當前學習行為（Hot Memory）- 用戶正在面臨的狀況】
{hot_memory_snapshot}

【歷史學習背景（Cold Memory）- 僅供參考，若與當前狀況無關請忽略】
{cold_memory_context}

【當前學習者狀態】{learner_state}
【偵測到的挑戰摘要】{event_summary if event_summary else "（無特定事件，基於狀態主動關懷）"}
【建議策略】{hint}{tone_constraint}{last_msg_hint}

要求：
1. **必須絕對聚焦於「當前學習行為（Hot Memory）」與「挑戰摘要」**，針對用戶**現在**正在閱讀或提問的具體知識點給出提示。
2. 歷史學習背景（Cold Memory）僅用於了解用戶程度或過去喜好，**絕不可強行將過去的無關話題（如其他角色）插入當前關懷中**，以免造成上下文斷裂。
3. **對話必須以「引導式詢問」為主，用一個簡單的問題邀請用戶互動。絕對避免單向陳述或自顧自地說教。**
4. 繁體中文，語氣自然，如果扮演角色，請展現強烈的角色魅力，不要像機器人。
5. 長度控制在 60 字以內，直接輸出訊息本身，不要加任何前綴說明。"""

    try:
        from config import settings
        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_gum,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.6
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ComPeer] generate_scaffolding_message_via_llm failed: {e}")
        return "你學習狀況還好嗎？有任何問題都可以問我。"

async def generate_epistolary_letter_via_llm(
    active_avatar: str,
    hot_memory_snapshot: str,
    cold_memory_context: str
) -> str:
    if not gum_instance:
        return "系統發生錯誤，無法寫信。"
        
    prompt = f"""你現在是「{active_avatar}」。請以第一人稱，寫一封信給正在與你進行思想交流的學習者（User）。
這不是一般的即時對話，而是一封跨時空的信件，因此語氣要具有沉澱感、哲學反思與歷史厚度。

【當前學習行為與近期探討（Hot Memory）】
{hot_memory_snapshot}

【歷史學習背景（Cold Memory）】
{cold_memory_context}

要求：
1. 必須回傳一個 JSON 格式，包含兩個欄位："subject"（信件主旨）與 "content"（信件內容）。
2. "subject" 請擬定一個吸引人且具有哲理的簡短標題。
3. "content" 長度控制在 300 到 500 字之間。針對使用者在對話中展現的疑惑、掙扎或深刻見解，給予回應與更深一層的提問。
4. 充分展現「{active_avatar}」的歷史背景與口吻，不可像 AI 機器人。
5. 排版支援 Markdown，請善用段落讓信件便於閱讀。
6. 結尾請署名，並留下一個發人深省的問題等待對方的回信。

請務必只回傳 JSON 格式，不要包含其他無關的文字。
"""
    try:
        from config import settings
        from pydantic import BaseModel
        
        class LetterSchema(BaseModel):
            subject: str
            content: str
            
        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_gum,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "letter_schema", "schema": LetterSchema.model_json_schema()}},
            max_tokens=800,
            temperature=0.8
        )
        response_text = rsp.choices[0].message.content.strip()
        
        import json
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
            
        data = json.loads(response_text)
        
        subject = data.get("subject", "一封來自遠方的信")
        if not subject or subject.strip() == "":
            subject = "來自遠方的思考"
            
        content = data.get("content", "信件內容未能解碼。")
        
        if isinstance(content, list):
            content = "\n".join(str(c) for c in content)
            
        return subject, content
    except Exception as e:
        print(f"[Mailbox] generate_epistolary_letter_via_llm failed: {e}")
        return "一封未知的信", f"來自{active_avatar}的一封信，因時空亂流未能完整送達。"

async def delayed_reply_writer(mail_id: str, reply_content: str, active_avatar: str, delay_seconds: int = 300):
    import asyncio
    print(f"[Mailbox] delayed_reply_writer started for mail_id {mail_id}, waiting {delay_seconds} seconds...")
    try:
        await asyncio.sleep(delay_seconds)
        
        from mailbox_store import get_mailbox_store
        store = get_mailbox_store()
        
        snapshot = get_hot_memory_snapshot()
        hot_context = f"使用者的回信內容：{reply_content}\n---\n目前對話脈絡：\n{snapshot}"
        
        event_summary = f"使用者回信給 {active_avatar} 探討：{reply_content[:50]}"
        cold_ctx = await query_cold_memory_for_context(event_summary)
        
        subject, letter_content = await generate_epistolary_letter_via_llm(
            active_avatar=active_avatar,
            hot_memory_snapshot=hot_context,
            cold_memory_context=cold_ctx
        )
        
        new_mail_id = store.add_mail(sender=active_avatar, subject=subject, content=letter_content, recipient="User")
        
        from services.connection_manager import ws_manager
        await ws_manager.broadcast_mail_alert(active_avatar)
        print(f"[Mailbox] delayed_reply_writer completed, sent new mail {new_mail_id} from {active_avatar} in response to {mail_id}.")
    except asyncio.CancelledError:
        print(f"[Mailbox] delayed_reply_writer for {mail_id} was cancelled.")
        raise
    except Exception as e:
        print(f"[Mailbox] delayed_reply_writer failed for {mail_id}: {e}")
