"""GUM workflow with an explicit runtime owner for state and dependencies."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime

logger = logging.getLogger("gum_integration")

async def run_compaction(runtime, user_id: str):
    """Expire typed hot state without bypassing trusted memory ingestion.

    Compaction is a storage-lifecycle operation, not an authority for durable
    memory.  User evidence is retained until the ingestion service can evaluate
    it; legacy and inferred values are never re-labelled for export.
    """

    from services.memory.hot import (
        TYPED_ENTRIES_KEY,
        cold_export_entries,
        get_typed_entries,
        is_expired,
        remove_typed_entry,
    )
    from services.memory.ingestion.service import (
        MemoryEligibilityState,
        UserEvidence,
        create_memory_ingestion_service,
    )
    from services.memory.store.service import get_global_store
    
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
        gum_instance, _ = await runtime.get_gum_instance(user_id)
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


async def schedule_compaction(runtime, user_id: str) -> str | None:
    from job_store import get_agent_job_store

    idempotency_key = (
        f"{user_id}:memory_compaction:"
        f"{runtime.interaction_counts.get(user_id, 0)}:{int(runtime.importance_sums.get(user_id, 0))}"
    )
    job_id = await get_agent_job_store().schedule(
        job_type="memory_compaction",
        user_id=user_id,
        payload={},
        idempotency_key=idempotency_key,
    )
    if job_id is None:
        asyncio.create_task(runtime.run_compaction(user_id))
    return job_id
