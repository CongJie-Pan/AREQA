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
gum_instance = None
gum_instances = {}
text_observers = {}
importance_sums = {}
interaction_counts = {}
last_interaction_times: dict[str, datetime] = {}
reflection_locks: dict[str, asyncio.Lock] = {}
obs_worker = None
_gum_init_locks = {}



async def init_gum_instance(user_id: str = "default_user"):
    """Backward-compatible singleton initializer for legacy callers."""
    global gum_instance
    gum_instance, _ = await get_gum_instance(user_id)
    return gum_instance


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
    global gum_instance, gum_instances, obs_worker, reflection_task, last_interaction_times
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
    gum_instance = None

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

try:
    from gum_parts.context_llm import (
        async_evaluate_and_update_state,
        delayed_reply_writer,
        detect_proactive_event_via_llm,
        generate_areqa_care_letter_via_llm,
        generate_epistolary_letter_via_llm,
        generate_scaffolding_message_via_llm,
        generate_zpd_query_via_llm,
        get_hot_memory_snapshot,
        query_cold_memory_for_context,
    )
    from gum_parts.observations import (
        ObservationQueueWorker,
        _idle_users_for_reflection,
        get_all_memory,
        run_reflection_loop,
    )
except ModuleNotFoundError:
    from backend.gum_parts.context_llm import (
        async_evaluate_and_update_state,
        delayed_reply_writer,
        detect_proactive_event_via_llm,
        generate_areqa_care_letter_via_llm,
        generate_epistolary_letter_via_llm,
        generate_scaffolding_message_via_llm,
        generate_zpd_query_via_llm,
        get_hot_memory_snapshot,
        query_cold_memory_for_context,
    )
    from backend.gum_parts.observations import (
        ObservationQueueWorker,
        _idle_users_for_reflection,
        get_all_memory,
        run_reflection_loop,
    )

reflection_task = None
