import sys
from pathlib import Path
import asyncio
import inspect
import logging
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

logger = logging.getLogger(__name__)

class TextObserver(Observer):
    def __init__(self, name="TextChatObserver"):
        super().__init__(name)
        
    async def push_text(self, text: str, user_id: str = "default_user"):
        # We wrap the text in an Update object
        await self.update_queue.put(Update(content=text, content_type="input_text", user_id=user_id))

    async def start(self):
        pass

    async def stop(self):
        pass
        
    async def _worker(self):
        while True:
            await asyncio.sleep(3600)


# Global instances for multi-user GUM
gum_instances = {}
text_observers = {}
importance_sums = {}
interaction_counts = {}
last_interaction_times: dict[str, datetime] = {}
reflection_locks: dict[str, asyncio.Lock] = {}
obs_worker = None
_gum_init_locks = {}



async def get_gum_instance(user_id: str):
    global gum_instances, text_observers, obs_worker, _gum_init_locks

    if user_id in gum_instances:
        return gum_instances[user_id], text_observers[user_id]

    lock = _gum_init_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _gum_init_locks[user_id] = lock

    async with lock:
        if user_id in gum_instances:
            return gum_instances[user_id], text_observers[user_id]

        print(f"[GUM] Initializing new GUM instance for user {user_id}...")

        safe_user_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in user_id)
        data_dir = str(project_root / "data" / "gum_data" / safe_user_id)
        os.makedirs(data_dir, exist_ok=True)

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        from config import settings

        gum_database_url = os.environ.get("GUM_DATABASE_URL") or os.environ.get("DATABASE_URL")
        gum_db_name = gum_database_url if gum_database_url else f"gum_{user_id}.db"

        new_obs = TextObserver(name=f"TextChatObserver_{user_id}")

        new_gum = gum(
            user_id,
            settings.model_gum,
            new_obs,
            data_directory=data_dir,
            db_name=gum_db_name,
            api_key=api_key,
            api_base="https://openrouter.ai/api/v1",
            min_batch_size=17,
            max_batch_size=20,
            max_wait_seconds=30.0,
        )

        try:
            await new_gum.connect_db()
        except Exception:
            _gum_init_locks.pop(user_id, None)
            raise

        new_gum.start_update_loop()
        if new_gum.batcher:
            await new_gum.batcher.start()

        new_gum.observer = new_obs

        gum_instances[user_id] = new_gum
        text_observers[user_id] = new_obs

        importance_sums[user_id] = 0
        interaction_counts[user_id] = 0

        if obs_worker is None:
            obs_worker = ObservationQueueWorker(process_callback=batch_process_observations, debounce_seconds=3.0)
            await obs_worker.start()

        return gum_instances[user_id], text_observers[user_id]

async def stop_gum_instance():
    global gum_instances, obs_worker, reflection_task, last_interaction_times
    if obs_worker:
        await obs_worker.stop()
        obs_worker = None
    if reflection_task:
        reflection_task.cancel()
        reflection_task = None
    for uid, inst in gum_instances.items():
        if inst:
            if hasattr(inst, "observers"):
                inst.observers = [
                    obs for obs in inst.observers
                    if obs is not None and hasattr(obs, "update_queue")
                ]
            await inst.stop_update_loop()
            if inst.batcher:
                await inst.batcher.stop()
    gum_instances.clear()
    text_observers.clear()
    last_interaction_times.clear()

async def clear_gum_memory(user_id: str = "default_user"):
    """Clear GUM memory from the database for a specific user."""
    global gum_instances, importance_sums, interaction_counts
    # In a fully multi-tenant setup, these globals should be per-user, 
    # but for now we just reset them to prevent pending reflections
    importance_sums.pop(user_id, None)
    interaction_counts.pop(user_id, None)
    last_interaction_times.pop(user_id, None)
    
    gum_instance, _ = await get_gum_instance(user_id)
    if gum_instance:
        try:
            from sqlalchemy import text
            async with gum_instance.Session() as session:
                async with session.begin():
                    # Delete user's observations and propositions
                    await session.execute(
                        text("DELETE FROM observations WHERE user_id = :uid"), 
                        {"uid": user_id}
                    )
                    await session.execute(
                        text("DELETE FROM propositions WHERE user_id = :uid"), 
                        {"uid": user_id}
                    )
            print(f"[GUM] Wiped GUM database entries for user {user_id}.")
        except Exception as e:
            print(f"[GUM] Error clearing memory for user {user_id}: {e}")

importance_sums = {}
interaction_counts = {}
last_interaction_times = {}

def is_real_gum_batcher(gum_instance) -> bool:
    batcher = getattr(gum_instance, "batcher", None)
    batcher_module = batcher.__class__.__module__ if batcher is not None else ""
    return batcher is not None and hasattr(batcher, "push") and batcher_module.startswith("gum.")

async def push_text_to_gum(gum_instance, text_observer, text: str, user_id: str):
    batcher = getattr(gum_instance, "batcher", None)
    if is_real_gum_batcher(gum_instance):
        batcher.push(
            observer_name=getattr(text_observer, "name", "TextChatObserver"),
            content=text,
            content_type="input_text",
            user_id=user_id,
        )
        return
    await text_observer.push_text(text, user_id=user_id)

async def run_reflection(user_id: str, conversation_id: str = "") -> list[str]:
    """Serialize reflection and flush operations for one user."""
    lock = reflection_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        return await _run_reflection_unlocked(user_id, conversation_id)


async def _run_reflection_unlocked(user_id: str, conversation_id: str = "") -> list[str]:
    global importance_sums, interaction_counts
    gum_instance, text_observer = await get_gum_instance(user_id)
    if not gum_instance:
        return []
    
    try:
        flush_pending = getattr(gum_instance, "flush_pending_observations", None)
        if flush_pending and inspect.iscoroutinefunction(flush_pending):
            await flush_pending()
        obs = await gum_instance.recent_observations(limit=20, user_id=user_id)
        if not obs:
            return []
            
        context = "\n".join([o.content for o in obs])
        prompt = f"請將以下最近的互動紀錄總結為高層次的學習洞察（insights）：\n{context}\n請只根據使用者明確說出的內容產生洞察。AI 回答、教學解釋與模型推論不是使用者事實；不要把模型推論寫成 user profile。請輸出這些學習洞察。"
        
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
        from memory_store import get_global_store
        from memory_gate import apply_reflection_gate
        store = get_global_store()
        for insight in insights:
            print(f"  - {insight}")
            if store:
                await apply_reflection_gate(
                    store,
                    user_id,
                    insight,
                    conversation_id=conversation_id,
                )
            # Reflection output is derived model text. Do not feed it back into
            # the observation stream, otherwise an inference becomes a new fact.
                
        # Archive old observations
        for o in obs:
            await gum_instance.update_observation_status(o.id, "archived")
            
        print(f"[GUM Reflection] Archived {len(obs)} old observations. Resetting counters.")
        importance_sums[user_id] = 0
        interaction_counts[user_id] = 0
        return insights
    except Exception as e:
        print(f"Error in reflection: {e}")
        return []


async def get_pending_observation_count(user_id: str) -> int:
    """Return the durable GUM queue size for diagnostics."""
    gum_instance, _ = await get_gum_instance(user_id)
    batcher = getattr(gum_instance, "batcher", None) if gum_instance else None
    return int(batcher.size()) if batcher and hasattr(batcher, "size") else 0

async def query_memory_for_context(user_query: str, limit: int = 8, user_id: str = "default_user") -> str:
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
    gum_instance, _ = await get_gum_instance(user_id)
    if not gum_instance:
        return ""
    try:
        results = await gum_instance.query(user_query, user_id=user_id, limit=limit)
        memory_lines = []
        from memory_store import get_global_store
        store = get_global_store()
        if store:
            profile = await store.get_user_profile(user_id)
            prefs = profile.get("explicit_memories", [])
            if prefs:
                memory_lines.append("【USER PROFILE (長期)】\n  - " + "\n  - ".join(prefs))
            
            hot = await store.get_hot_memory(user_id)
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

async def batch_process_observations(
    user_id: str,
    items: list[str],
    *,
    sync_to_working_memory: bool = True,
    conversation_id: str = "",
):
    global importance_sums, interaction_counts, last_interaction_times
    last_interaction_times[user_id] = datetime.now()
    
    gum_instance, text_observer = await get_gum_instance(user_id)
    
    if gum_instance and text_observer:
        combined_text = " | ".join(items)
        try:
            neighbors = await gum_instance.query(combined_text, user_id=user_id, limit=20)
            if not neighbors:
                recent_props = await gum_instance.recent(user_id=user_id, limit=20)
                neighbors = [(p, 1.0) for p in recent_props]
    
            if neighbors:
                neighbor_ctx = "\\n".join([f"ID: {p.id}, Text: {p.text}" for p, _ in neighbors])
                prompt = f"""Analyze the new observation against existing memories.
    New observation (user-originated input; not proof of a stable user fact): {combined_text}
    Existing memories:
    {neighbor_ctx}
    
    Task: 
    1. Determine if the new observation logically CONTRADICTS, UPDATES, or is highly REDUNDANT with any existing memories.
    2. If it is redundant or updates old memories, set should_evolve=true, add 'prune' to actions, and put the old memory IDs to be pruned in target_ids. 
    3. Provide a 'revised_proposition' that merges the new observation and the pruned memories into a single concise, updated statement.
    4. Generate a 'decay_score' (1-10) for this proposition. Transient or temporary actions (e.g. debugging a specific bug) decay fast (score=8-10). Stable facts (e.g. user is a PhD student) decay slowly (score=1-3).
    5. Rate importance 1-10.
    6. Never turn a teaching conclusion, an answer supplied by the assistant,
       or a temporary learning result into a durable user preference or identity."""
                
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
                
                # print(f"[GUM Evolution] LLM decision: {decision}")
                logger.debug("[GUM Evolution] LLM decision: %s", decision)
                
                importance_sums[user_id] = importance_sums.get(user_id, 0) + decision.get("importance_score", 5)
                
                if decision.get("should_evolve") and "prune" in decision.get("actions", []):
                    target_ids = decision.get("target_ids", [])
                    for t_id in target_ids:
                        await gum_instance.update_status(t_id, "superseded")
                
                final_text = decision.get("revised_proposition") if decision.get("should_evolve") and decision.get("revised_proposition") else combined_text
                final_decay = decision.get("decay_score", 5.0)
            else:
                importance_sums[user_id] = importance_sums.get(user_id, 0) + 5
                final_text = combined_text
                final_decay = 5.0
        except Exception as e:
            print(f"Error in evolution interceptor: {e}")
            importance_sums[user_id] = importance_sums.get(user_id, 0) + 5
            final_text = combined_text
            final_decay = 5.0
    
        if is_real_gum_batcher(gum_instance):
            for item in items:
                await push_text_to_gum(gum_instance, text_observer, item, user_id)
        else:
            await push_text_to_gum(gum_instance, text_observer, combined_text, user_id)
        interaction_counts[user_id] = interaction_counts.get(user_id, 0) + len(items)
    else:
        combined_text = " | ".join(items)
        
    # Sync only semantic learning observations into prompt-visible working memory.
    # Raw UI telemetry is routed by /log_action into behavior_signals instead.
    try:
        from memory_store import get_global_store
        from memory_gate import classify_learning_observation
        store = get_global_store()
        gate = classify_learning_observation(final_text)
        if store and gate.should_prompt and sync_to_working_memory:
            await store.append_learning_observation(
                user_id,
                gate.proposition,
                confidence=8.0,
                decay=float(final_decay),
                conversation_id=conversation_id,
                source="user_message",
            )
    except Exception as e:
        # Expected if budget exceeded, handled below
        pass
        
    await schedule_compaction(user_id)
    
    if importance_sums.get(user_id, 0) >= 100 or interaction_counts.get(user_id, 0) >= 20:
        await schedule_session_reflection(user_id, conversation_id=conversation_id)


async def schedule_session_reflection(user_id: str, *, conversation_id: str = "") -> str | None:
    from job_store import get_agent_job_store

    idempotency_key = (
        f"{user_id}:session_reflection:"
        f"{interaction_counts.get(user_id, 0)}:{int(importance_sums.get(user_id, 0))}"
    )
    job_id = await get_agent_job_store().schedule(
        job_type="session_reflection",
        user_id=user_id,
        payload={"conversation_id": conversation_id},
        idempotency_key=idempotency_key,
    )
    if job_id is None:
        asyncio.create_task(run_reflection(user_id, conversation_id=conversation_id))
    return job_id


async def schedule_compaction(user_id: str) -> str | None:
    from job_store import get_agent_job_store

    idempotency_key = (
        f"{user_id}:memory_compaction:"
        f"{interaction_counts.get(user_id, 0)}:{int(importance_sums.get(user_id, 0))}"
    )
    job_id = await get_agent_job_store().schedule(
        job_type="memory_compaction",
        user_id=user_id,
        payload={},
        idempotency_key=idempotency_key,
    )
    if job_id is None:
        asyncio.create_task(run_compaction(user_id))
    return job_id

async def run_compaction(user_id: str):
    """Expire typed hot state without bypassing trusted memory ingestion.

    Compaction is a storage-lifecycle operation, not an authority for durable
    memory.  User evidence is retained until the ingestion service can evaluate
    it; legacy and inferred values are never re-labelled for export.
    """

    from memory_store import get_global_store
    from services.hot_memory_service import (
        TYPED_ENTRIES_KEY,
        cold_export_entries,
        get_typed_entries,
        is_expired,
        remove_typed_entry,
    )
    from services.memory_ingestion_service import (
        MemoryEligibilityState,
        UserEvidence,
        create_memory_ingestion_service,
    )
    
    store = get_global_store()
    if not store:
        return
    
    hot_mem = await store.get_hot_memory(user_id)
    serialized = json.dumps(hot_mem, ensure_ascii=False)
    
    if len(serialized) <= store.budget_limit:
        return

    logger.info(
        "hot_memory.compaction_started user_id=%s size=%s budget=%s",
        user_id,
        len(serialized),
        store.budget_limit,
    )
    typed_entries = get_typed_entries(hot_mem)
    for key, entry in typed_entries.items():
        if is_expired(entry):
            remove_typed_entry(hot_mem, key)
            logger.info("hot_memory.expired user_id=%s key=%s kind=%s", user_id, key, entry.kind)

    # Phase 2 consumes this validated list through the same ingestion boundary.
    # Merely finding eligible evidence must never trigger a direct cold write.
    eligible = cold_export_entries(hot_mem)
    semantic_client = None
    from config import settings
    if settings.memory_semantic_analysis_enabled:
        gum_instance, _ = await get_gum_instance(user_id)
        semantic_client = getattr(gum_instance, "client", None) if gum_instance else None
    ingestion = create_memory_ingestion_service(store, client=semantic_client)
    for key, _, entry in eligible:
        provenance = entry.provenance or {}
        try:
            result = await ingestion.ingest_user_evidence(
                UserEvidence(
                    user_id=user_id,
                    message_id=str(provenance["message_id"]),
                    conversation_id=str(provenance["conversation_id"]),
                    timestamp=str(provenance["timestamp"]),
                    raw_message_text=str(provenance["raw_user_text"]),
                    source_role=str(provenance["source_role"]),
                )
            )
        except Exception as exc:
            logger.exception(
                "hot_memory.export_handoff_failed user_id=%s key=%s reason=%s retained=true",
                user_id,
                key,
                type(exc).__name__,
            )
            continue
        consumed = result.state in {
            MemoryEligibilityState.CANDIDATE,
            MemoryEligibilityState.PROMOTION_ELIGIBLE,
            MemoryEligibilityState.WORKING_CONTEXT_ONLY,
        } or (
            result.state is MemoryEligibilityState.REJECTED
            and result.reason_code != "candidate_persistence_rejected"
        )
        if consumed:
            # Only terminal policy outcomes or confirmed persistence consume
            # the hot copy; retryable storage rejection retains provenance.
            remove_typed_entry(hot_mem, key)
        logger.info(
            "hot_memory.export_handed_off user_id=%s key=%s state=%s reason=%s",
            user_id,
            key,
            result.state.value,
            result.reason_code,
        )

    if getattr(store, "redis", None) is not None:
        await store.redis.set(
            f"areqa:hot_memory:{user_id}",
            json.dumps(hot_mem, ensure_ascii=False),
        )
    logger.info(
        "hot_memory.compaction_finished user_id=%s eligible_held=%s typed_entries=%s",
        user_id,
        len(eligible),
        len(hot_mem.get(TYPED_ENTRIES_KEY, {})),
    )

async def push_observation(
    user_id: str,
    text: str,
    *,
    sync_to_working_memory: bool = True,
    conversation_id: str = "",
):
    gum_instance, _ = await get_gum_instance(user_id)
    if not gum_instance:
        return
    if obs_worker:
        await obs_worker.push(
            user_id,
            text,
            sync_to_working_memory=sync_to_working_memory,
            conversation_id=conversation_id,
        )
    else:
        await batch_process_observations(
            user_id,
            [text],
            sync_to_working_memory=sync_to_working_memory,
            conversation_id=conversation_id,
        )


async def push_reflection_observation(user_id: str, text: str, *, conversation_id: str = ""):
    return await push_observation(
        user_id,
        text,
        sync_to_working_memory=False,
        conversation_id=conversation_id,
    )

async def run_reflection_loop():
    """Background task to run reflection if user is idle for 30 minutes."""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        for user_id in _idle_users_for_reflection(datetime.now()):
            print(f"Idle for 30 minutes, triggering session boundary reflection for {user_id}.")
            await schedule_session_reflection(user_id)


def _idle_users_for_reflection(now: datetime) -> list[str]:
    """Return users whose own idle timer is eligible for reflection."""

    result = []
    for user_id in list(gum_instances.keys()):
        last_seen = last_interaction_times.get(user_id)
        if last_seen is None:
            continue
        idle_time = now - last_seen
        if idle_time.total_seconds() > 1800 and interaction_counts.get(user_id, 0) > 0:
            result.append(user_id)
    return result

reflection_task = None

async def get_all_memory(user_id: str = "default_user") -> list[dict]:
    gum_instance, _ = await get_gum_instance(user_id)
    if not gum_instance:
        return []
    try:
        import json
        props = await gum_instance.recent(user_id=user_id, limit=100)
        result = []
        for p in props:
            if getattr(p, "status", "") in ["deleted", "superseded"]:
                continue
            reasoning = str(getattr(p, "reasoning", "") or "")
            memory_type = "cold_memory" if reasoning.startswith("{\"source\": \"hot_memory_compaction\"") else "legacy_unverified"
            result.append({
                "id": str(p.id),
                "text": p.text,
                "confidence": p.confidence,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                "context_scope": p.context_scope,
                "event_types": json.loads(p.event_types) if p.event_types else [],
                "target": p.target,
                "functional_type_seeds": json.loads(p.functional_type_seeds) if p.functional_type_seeds else [],
                "memory_type": memory_type,
                "source": "hot_memory_compaction" if memory_type == "cold_memory" else "legacy_gum",
            })
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

    async def push(
        self,
        user_id: str,
        observation: str,
        *,
        sync_to_working_memory: bool = True,
        conversation_id: str = "",
    ):
        await self.queue.put({
            "user_id": user_id,
            "observation": observation,
            "sync_to_working_memory": sync_to_working_memory,
            "conversation_id": conversation_id,
        })

    async def _worker(self):
        from collections import defaultdict
        while True:
            try:
                # Wait for at least one item
                first = await self.queue.get()
                
                # We will process per-user. Let's collect items per user.
                items_by_route = defaultdict(list)
                first_key = (
                    first["user_id"],
                    first["sync_to_working_memory"],
                    first["conversation_id"],
                )
                items_by_route[first_key].append(first["observation"])
                
                # Debounce window
                await asyncio.sleep(self.debounce_seconds)
                
                # Collect any other items that arrived during the window
                while not self.queue.empty():
                    try:
                        item = self.queue.get_nowait()
                        route_key = (
                            item["user_id"],
                            item["sync_to_working_memory"],
                            item["conversation_id"],
                        )
                        items_by_route[route_key].append(item["observation"])
                    except asyncio.QueueEmpty:
                        break
                        
                # Process the batch
                for (uid, sync_to_working, conversation_id), items in items_by_route.items():
                    if items:
                        await self.process_callback(
                            uid,
                            items,
                            sync_to_working_memory=sync_to_working,
                            conversation_id=conversation_id,
                        )
                    
                # Mark as done
                total_items = sum(len(v) for v in items_by_route.values())
                for _ in range(total_items):
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in ObservationQueueWorker: {e}")
                await asyncio.sleep(1)

async def get_hot_memory_snapshot(
    user_id: str = "default_user",
    *,
    conversation_id: str = "",
    include_cross_conversation_focus: bool = True,
) -> str:
    from memory_store import get_global_store
    import json
    store = get_global_store()
    if not store:
        return ""
    
    # Combine durable profile facts and prompt-safe working memory.
    profile = await store.get_user_profile(user_id)
    import inspect
    get_working_memory = getattr(store, "get_working_memory", None)
    if inspect.iscoroutinefunction(get_working_memory):
        working_memory = await get_working_memory(user_id)
    else:
        working_memory = {}
    
    parts = []
    if profile:
        parts.append("【使用者畫像 (User Profile)】\n" + json.dumps(profile, ensure_ascii=False, indent=2))

    if working_memory:
        focus = working_memory.get("current_focus")
        focus_conversation_id = working_memory.get("current_focus_conversation_id")
        session_summary = working_memory.get("session_summary")
        summary_conversation_id = working_memory.get("session_summary_conversation_id")
        explicit_memories = working_memory.get("explicit_memories") or []
        recent_points = working_memory.get("recent_learning_points") or []
        if not include_cross_conversation_focus and conversation_id:
            is_same_conversation = bool(focus_conversation_id and focus_conversation_id == conversation_id)
            if not is_same_conversation:
                focus = ""
                explicit_memories = []
                recent_points = []
            if summary_conversation_id != conversation_id:
                session_summary = ""

        if not include_cross_conversation_focus and conversation_id:
            recent_points = [
                point for point in recent_points
                if isinstance(point, dict) and point.get("conversation_id") == conversation_id
            ]

        working_parts = []
        if session_summary:
            working_parts.append(f"Session summary: {session_summary}")
        if focus:
            working_parts.append(f"Current focus: {focus}")
        for memory in explicit_memories[-8:]:
            if memory:
                working_parts.append(f"Explicit memory: {memory}")
        for point in recent_points[-8:]:
            if isinstance(point, dict) and point.get("prompt_safe") is False:
                # logger.info(
                logger.debug(
                    "hot_memory.snapshot_excluded user_id=%s reason=not_prompt_safe",
                    user_id,
                )
                continue
            if isinstance(point, dict) and point.get("text"):
                working_parts.append(point["text"])
            elif isinstance(point, str):
                working_parts.append(point)

        if working_parts:
            parts.append("【工作記憶 (Working Memory)】\n- " + "\n- ".join(working_parts))
        
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

async def query_cold_memory_for_context(
    user_id: str,
    query: str,
    top_k: int = 5,
    client=None,
    model=None,
    memory_trace=None,
) -> str:
    """Return prompt-safe cold memory context with optional safe trace metadata."""

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
        if memory_trace:
            async with memory_trace.measure("cold_memory_learner_state"):
                learner_state = await store.get_learner_state(user_id) if store else "STARTING"
        else:
            learner_state = await store.get_learner_state(user_id) if store else "STARTING"
        
        c = client
        from config import settings
        m = model if model else settings.model_zpd_query
        if not c:
            from openai import AsyncOpenAI
            c = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
            
        if memory_trace:
            async with memory_trace.measure("cold_memory_zpd_query"):
                zpd_query = await generate_zpd_query_via_llm(c, m, query, learner_state)
        else:
            zpd_query = await generate_zpd_query_via_llm(c, m, query, learner_state)
        
        cold_retriever = ColdMemoryRetriever(db_path, api_key)
        if memory_trace:
            async with memory_trace.measure("cold_memory_search"):
                results = await cold_retriever.search(
                    zpd_query,
                    user_id=user_id,
                    top_k=top_k,
                    memory_trace=memory_trace,
                )
        else:
            results = await cold_retriever.search(zpd_query, user_id=user_id, top_k=top_k)
        if not results:
            return ""
            
        if memory_trace:
            memory_trace.record_step("cold_memory_results", 0, outcome=f"count_{min(len(results), 6)}")
        parts = ["【檢索到的長尾記憶 (Cold Memory)】"]
        for r in results:
            parts.append(f"- {r['text']}")
            
        return "\n".join(parts)
    except Exception as e:
        print(f"[GUM] Error querying cold memory: {e}")
        return ""

async def async_evaluate_and_update_state(
    client,
    model,
    chat_history,
    user_id: str = "default_user",
    conversation_id: str = "",
    ingest_memory: bool = False,
):
    """Evaluate EDF state without creating profile-memory evidence.

    ``ingest_memory`` remains temporarily for worker compatibility, but is
    intentionally ignored. Exact user evidence enters memory only through
    ``TurnIntakeService`` and ``MemoryIngestionService``.
    """
    from compaction import evaluate_student_state
    from memory_store import get_global_store
    
    state_res = await evaluate_student_state(client, model, chat_history)
    store = get_global_store()
    if store:
        await store.update_learner_state_snapshot(
            user_id,
            learner_state=state_res.get("learner_state", "STARTING"),
            strategy=state_res.get("pedagogical_strategy", "NORMAL"),
            trigger_proactive=bool(state_res.get("trigger_proactive")),
        )
        # State evaluation must not summon avatars or affect chat persona.
        # Conversation-scoped roleplay is handled only by explicit chat commands in OrchestrationService.
        if state_res.get("trigger_proactive"):
            # We flag this for ComPeer to pick up or log it
            print(f"[ComPeer] Proactive trigger needed: {state_res}")
            
        # EDF evaluates the learner state only. It must never promote an
        # assistant-generated inference into durable user memory.
        if state_res.get("memory_operations"):
            print("[EDF-LOG] Ignored legacy memory_operations from state evaluation")

        if ingest_memory:
            logger.warning(
                "memory.ingestion_skipped user_id=%s conversation_id=%s reason=edf_boundary",
                user_id,
                conversation_id,
            )


async def detect_proactive_event_via_llm(user_id: str, hot_memory_snapshot: str) -> dict:
    """
    Analyze hot memory snapshot to determine if a proactive intervention is warranted.
    """
    gum_instance, _ = await get_gum_instance(user_id)
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
    user_id: str,
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
    gum_instance, _ = await get_gum_instance(user_id)
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
        roleplay_instruction = "你是 AREQA，一個溫暖且專業的學習陪伴者。\n現在你需要主動關心用戶，根據以下資訊生成一句**精準的**主動關懷訊息。"

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
    user_id: str,
    active_avatar: str,
    hot_memory_snapshot: str,
    cold_memory_context: str
) -> str:
    gum_instance, _ = await get_gum_instance(user_id)
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


async def generate_areqa_care_letter_via_llm(
    user_id: str,
    hot_memory_snapshot: str,
    cold_memory_context: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str = "",
    last_compeer_message: str = "",
    allow_topic_specific: bool = False,
) -> tuple[str, str]:
    gum_instance, _ = await get_gum_instance(user_id)
    if not gum_instance:
        return "給你的學習小箋", "我注意到你最近可能有些卡住。先不用急著解決全部問題，回到一個最小的段落或概念就好。你願意告訴我，現在最困住你的是哪一句或哪個想法嗎？"

    safe_cold_memory_context = cold_memory_context if allow_topic_specific else ""
    last_msg_hint = f"\n【避免重複】上一封主動關懷已提過：「{last_compeer_message}」，這封信不得重複同一個問法。" if last_compeer_message else ""
    topic_policy = (
        "【主題證據政策】系統已確認有足夠的近期語意證據。你可以提及 Hot Memory、觸發原因、或相關 Cold Memory 中明確出現的具體學習主題，但不可超出這些證據。"
        if allow_topic_specific
        else (
            "【主題證據政策】系統沒有足夠的近期語意證據支撐具體學習主題。"
            "你必須寫成中性的低壓力關懷短箋，不得提及或暗示任何特定文本、學科、角色、章節或概念。"
            "尤其禁止自行輸出「文言文」、「判詞」、「紅樓夢」、任何角色名，或「昨天你在讀 X」這類具體化時間敘述。"
        )
    )
    prompt = f"""你是 AREQA，一位溫暖、克制、專業的學習陪伴者。請根據學生最近的狀態寫一封非同步關懷信。

【近期學習狀態（Hot Memory）】
{hot_memory_snapshot}

【長期學習背景（Cold Memory，僅供參考）】
{safe_cold_memory_context}

【目前 learner_state】{learner_state}
【目前教學策略】{edf_policy}
【觸發原因】{event_summary or "系統偵測到學生可能需要低壓力關懷"}{last_msg_hint}
{topic_policy}

要求：
1. 寄件人固定是 AREQA，不要扮演任何歷史人物或虛構角色。
2. 必須像 5 分鐘後送達的一封短箋，而不是即時聊天室插話。
3. 內容要回應學生最近卡住、焦慮或長時間停留的狀態；只有在主題證據政策允許時，才可提及具體主題。
4. 長度 120 到 220 字，繁體中文，溫柔但不肉麻，不說教。
5. 結尾只問一個低壓力問題，讓學生可以回信。
6. 嚴格回傳 JSON，包含 "subject" 與 "content"。
"""
    try:
        from config import settings
        from pydantic import BaseModel

        class CareLetterSchema(BaseModel):
            subject: str
            content: str

        rsp = await gum_instance.client.chat.completions.create(
            model=settings.model_gum,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "care_letter_schema", "schema": CareLetterSchema.model_json_schema()}},
            max_tokens=500,
            temperature=0.6,
        )
        response_text = rsp.choices[0].message.content.strip()
        import json
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        data = json.loads(response_text)
        subject = data.get("subject") or "給你的學習小箋"
        content = data.get("content") or "我注意到你最近可能有些卡住。你願意回信告訴我，現在最困住你的是哪一小段嗎？"
        return subject, content
    except Exception as e:
        print(f"[Mailbox] generate_areqa_care_letter_via_llm failed: {e}")
        return "給你的學習小箋", "我注意到你最近可能有些卡住。先不用急著解決全部問題，我們可以只從一個最小的地方開始。你願意回信告訴我，現在最困住你的是哪一句或哪個想法嗎？"

async def delayed_reply_writer(user_id: str, mail_id: str, reply_content: str, active_avatar: str, delay_seconds: int = 300):
    print(f"[Mailbox] delayed_reply_writer started for mail_id {mail_id}, scheduling in {delay_seconds} seconds...")
    try:
        from mailbox_store import get_mailbox_store
        store = get_mailbox_store()
        
        await store.schedule_delayed_mail(user_id, {
            "reply_to_mail_id": mail_id,
            "reply_content": reply_content,
            "active_avatar": active_avatar,
            "conversation_id": mail_id
        }, delay_seconds)
        
        print(f"[Mailbox] delayed_reply_writer completed, scheduled new mail from {active_avatar} in response to {mail_id}.")
    except Exception as e:
        print(f"[Mailbox] delayed_reply_writer failed for {mail_id}: {e}")
