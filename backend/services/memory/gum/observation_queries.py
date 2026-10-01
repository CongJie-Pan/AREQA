"""Read observations and schedule idle reflection using an injected runtime."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)
from datetime import datetime


async def run_reflection_loop(runtime):
    """Background task to run reflection if user is idle for 30 minutes."""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        for user_id in _idle_users_for_reflection(runtime, datetime.now()):
            logger.info("gum.idle_reflection_scheduled")
            await runtime.schedule_session_reflection(user_id)


def _idle_users_for_reflection(runtime, now: datetime) -> list[str]:
    """Return users whose own idle timer is eligible for reflection."""

    gum_integration = runtime
    result = []
    for user_id in list(gum_integration.gum_instances.keys()):
        last_seen = gum_integration.last_interaction_times.get(user_id)
        if last_seen is None:
            continue
        idle_time = now - last_seen
        if idle_time.total_seconds() > 1800 and gum_integration.interaction_counts.get(user_id, 0) > 0:
            result.append(user_id)
    return result


async def get_all_memory(runtime, user_id: str = "default_user") -> list[dict]:
    gum_instance, _ = await runtime.get_gum_instance(user_id)
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
        logger.warning("gum.observation_queries_failed reason=%s", type(e).__name__)
        return []
