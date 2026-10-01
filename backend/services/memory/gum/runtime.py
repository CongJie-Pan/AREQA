"""Single process owner of GUM instances, per-user locks and background workers."""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add misc/gum to sys.path
project_root = Path(__file__).resolve().parents[4]
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

        logger.info("gum.instance_initializing")

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
            logger.info("gum.memory_cleared")
        except Exception as e:
            logger.warning("gum.runtime_failed reason=%s", type(e).__name__)

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
    """Delegate to reflection with the single GUM runtime owner."""
    from services.memory.gum.reflection import run_reflection as impl

    return await impl(sys.modules[__name__], user_id, conversation_id)


async def _run_reflection_unlocked(user_id: str, conversation_id: str = "") -> list[str]:
    """Delegate to reflection with the single GUM runtime owner."""
    from services.memory.gum.reflection import _run_reflection_unlocked as impl

    return await impl(sys.modules[__name__], user_id, conversation_id)


async def get_pending_observation_count(user_id: str) -> int:
    """Delegate to retrieval with the single GUM runtime owner."""
    from services.memory.gum.retrieval import get_pending_observation_count as impl

    return await impl(sys.modules[__name__], user_id)

async def query_memory_for_context(user_query: str, limit: int = 8, user_id: str = "default_user") -> str:
    """Delegate to retrieval with the single GUM runtime owner."""
    from services.memory.gum.retrieval import query_memory_for_context as impl

    return await impl(sys.modules[__name__], user_query, limit, user_id)


async def batch_process_observations(
    user_id: str,
    items: list[str],
    *,
    sync_to_working_memory: bool = True,
    conversation_id: str = "",
):
    """Delegate to ingestion with the single GUM runtime owner."""
    from services.memory.gum.ingestion import batch_process_observations as impl

    return await impl(sys.modules[__name__], user_id, items, sync_to_working_memory=sync_to_working_memory, conversation_id=conversation_id)


async def schedule_session_reflection(user_id: str, *, conversation_id: str = "") -> str | None:
    """Delegate to reflection with the single GUM runtime owner."""
    from services.memory.gum.reflection import schedule_session_reflection as impl

    return await impl(sys.modules[__name__], user_id, conversation_id=conversation_id)


async def schedule_compaction(user_id: str) -> str | None:
    """Delegate to compaction with the single GUM runtime owner."""
    from services.memory.gum.compaction import schedule_compaction as impl

    return await impl(sys.modules[__name__], user_id)

async def run_compaction(user_id: str):
    """Delegate to compaction with the single GUM runtime owner."""
    from services.memory.gum.compaction import run_compaction as impl

    return await impl(sys.modules[__name__], user_id)

async def push_observation(
    user_id: str,
    text: str,
    *,
    sync_to_working_memory: bool = True,
    conversation_id: str = "",
):
    """Delegate to ingestion with the single GUM runtime owner."""
    from services.memory.gum.ingestion import push_observation as impl

    return await impl(sys.modules[__name__], user_id, text, sync_to_working_memory=sync_to_working_memory, conversation_id=conversation_id)


async def push_reflection_observation(user_id: str, text: str, *, conversation_id: str = ""):
    """Delegate to ingestion with the single GUM runtime owner."""
    from services.memory.gum.ingestion import push_reflection_observation as impl

    return await impl(sys.modules[__name__], user_id, text, conversation_id=conversation_id)


from services.memory.gum.worker import ObservationQueueWorker

reflection_task = None

from services.memory.gum.context import (
    async_evaluate_and_update_state as async_evaluate_and_update_state,
)
from services.memory.gum.context import (
    generate_zpd_query_via_llm as generate_zpd_query_via_llm,
)
from services.memory.gum.context import (
    get_hot_memory_snapshot as get_hot_memory_snapshot,
)
from services.memory.gum.context import (
    query_cold_memory_for_context as query_cold_memory_for_context,
)


async def detect_proactive_event_via_llm(user_id: str, hot_memory_snapshot: str) -> dict:
    """Delegate to context with the single GUM runtime owner."""
    from services.memory.gum.context import detect_proactive_event_via_llm as impl

    return await impl(sys.modules[__name__], user_id, hot_memory_snapshot)


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
    """Delegate to context with the single GUM runtime owner."""
    from services.memory.gum.context import generate_scaffolding_message_via_llm as impl

    return await impl(sys.modules[__name__], user_id, hot_memory_snapshot, cold_memory_context, learner_state, edf_policy, event_summary, last_compeer_message, active_avatar)


async def generate_epistolary_letter_via_llm(
    user_id: str,
    active_avatar: str,
    hot_memory_snapshot: str,
    cold_memory_context: str
) -> str:
    """Delegate to letters with the single GUM runtime owner."""
    from services.memory.gum.letters import generate_epistolary_letter_via_llm as impl

    return await impl(sys.modules[__name__], user_id, active_avatar, hot_memory_snapshot, cold_memory_context)


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
    """Delegate to letters with the single GUM runtime owner."""
    from services.memory.gum.letters import generate_areqa_care_letter_via_llm as impl

    return await impl(sys.modules[__name__], user_id, hot_memory_snapshot, cold_memory_context, learner_state, edf_policy, event_summary, last_compeer_message, allow_topic_specific)


from services.memory.gum.letters import delayed_reply_writer as delayed_reply_writer


async def run_reflection_loop():
    """Delegate to observation_queries with the single GUM runtime owner."""
    from services.memory.gum.observation_queries import run_reflection_loop as impl

    return await impl(sys.modules[__name__])


def _idle_users_for_reflection(now: datetime) -> list[str]:
    """Delegate to observation_queries with the single GUM runtime owner."""
    from services.memory.gum.observation_queries import (
        _idle_users_for_reflection as impl,
    )

    return impl(sys.modules[__name__], now)


async def get_all_memory(user_id: str = "default_user") -> list[dict]:
    """Delegate to observation_queries with the single GUM runtime owner."""
    from services.memory.gum.observation_queries import get_all_memory as impl

    return await impl(sys.modules[__name__], user_id)
