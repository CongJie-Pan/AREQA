"""Observation loop helpers for GUM integration.

This module keeps background reflection-loop and observation queue code out of
the public facade while preserving the original runtime state through lazy
access to ``gum_integration``. Logs and prints preserve existing behavior.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import datetime


def _integration_module():
    return (
        sys.modules.get("backend.gum_integration")
        or sys.modules.get("gum_integration")
        or importlib.import_module("gum_integration")
    )

async def run_reflection_loop():
    """Background task to run reflection if user is idle for 30 minutes."""
    while True:
        await asyncio.sleep(300)  # Check every 5 minutes
        for user_id in _idle_users_for_reflection(datetime.now()):
            print(f"Idle for 30 minutes, triggering session boundary reflection for {user_id}.")
            await _integration_module().schedule_session_reflection(user_id)


def _idle_users_for_reflection(now: datetime) -> list[str]:
    """Return users whose own idle timer is eligible for reflection."""

    gum_integration = _integration_module()
    result = []
    for user_id in list(gum_integration.gum_instances.keys()):
        last_seen = gum_integration.last_interaction_times.get(user_id)
        if last_seen is None:
            continue
        idle_time = now - last_seen
        if idle_time.total_seconds() > 1800 and gum_integration.interaction_counts.get(user_id, 0) > 0:
            result.append(user_id)
    return result

reflection_task = None

async def get_all_memory(user_id: str = "default_user") -> list[dict]:
    gum_instance, _ = await _integration_module().get_gum_instance(user_id)
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
