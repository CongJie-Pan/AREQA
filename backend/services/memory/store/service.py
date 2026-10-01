import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from redis_client import get_redis
from services.memory.hot import (
    HotMemoryKind,
    attach_typed_entry,
    build_hot_memory_entry,
    remove_typed_entry,
)
from services.memory.store.behavior import MemoryStoreBehaviorMixin
from services.memory.store.candidates import MemoryStoreCandidateMixin

logger = logging.getLogger(__name__)

class MemoryBudgetExceeded(Exception):
    pass


class InvalidMemorySource(ValueError):
    """Raised when a caller tries to write profile memory without user evidence."""

class MemoryStore(MemoryStoreBehaviorMixin, MemoryStoreCandidateMixin):
    def __init__(self, budget_limit: int = 1000000):
        self.budget_limit = budget_limit
        self.redis = get_redis()

    async def get_hot_memory(self, user_id: str) -> Dict[str, Any]:
        data = await self.redis.get(f"areqa:hot_memory:{user_id}")
        if data:
            logger.debug(f"[MemoryStore] Found memory for user {user_id}")
            return json.loads(data)
        logger.debug(f"[MemoryStore] No memory found for user {user_id}")
        return {}

    async def get_learner_state(self, user_id: str) -> str:
        hot_mem = await self.get_hot_memory(user_id)
        return hot_mem.get("current_learner_state", "STARTING")

    async def get_current_strategy(self, user_id: str) -> str:
        hot_mem = await self.get_hot_memory(user_id)
        return hot_mem.get("current_strategy", "None")

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        data = await self.redis.get(f"areqa:user_profile:{user_id}")
        return json.loads(data) if data else {
            "name": "default_user",
            "explicit_memories": [],
            "implicit_preferences": []
        }

    async def get_working_memory(self, user_id: str) -> Dict[str, Any]:
        data = await self.redis.get(f"areqa:working_memory:{user_id}")
        if data:
            return json.loads(data)
        return {
            "session_summary": "",
            "session_summary_conversation_id": "",
            "current_focus": "",
            "current_focus_conversation_id": "",
            "recent_learning_points": [],
            "explicit_memories": [],
            "updated_at": None,
        }

    async def update_working_memory(self, user_id: str, updates: Dict[str, Any]):
        allowed_keys = {
            "session_summary",
            "session_summary_conversation_id",
            "current_focus",
            "current_focus_conversation_id",
            "recent_learning_points",
            "explicit_memories",
        }
        memory = await self.get_working_memory(user_id)
        for key, value in updates.items():
            if key in allowed_keys:
                memory[key] = value
        memory["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set(f"areqa:working_memory:{user_id}", json.dumps(memory, ensure_ascii=False))
        logger.info(f"[MemoryStore] Updated working memory for user {user_id}: {sorted(updates.keys())}")

    async def clear_working_memory(self, user_id: str):
        await self.redis.delete(f"areqa:working_memory:{user_id}")
        logger.info(f"[MemoryStore] Cleared working memory for user {user_id}.")

    async def append_learning_observation(
        self,
        user_id: str,
        text: str,
        *,
        confidence: float = 8.0,
        decay: float = 5.0,
        conversation_id: str = "",
        source: str = "user_message",
    ):
        text = (text or "").strip()
        if not text:
            return

        memory = await self.get_working_memory(user_id)
        points = memory.get("recent_learning_points", [])
        if not isinstance(points, list):
            points = []

        is_user_evidence = source in {"user", "user_message", "verified_user_evidence"}
        entry = {
            "text": text,
            "conversation_id": conversation_id,
            "source": source,
            "kind": (
                HotMemoryKind.USER_EVIDENCE.value
                if is_user_evidence
                else HotMemoryKind.MODEL_INFERENCE.value
            ),
            "prompt_safe": is_user_evidence,
            "cold_export_eligible": False,
            "confidence": float(confidence),
            "decay": float(decay),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        points.append(entry)
        memory["recent_learning_points"] = points[-12:]
        memory["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set(f"areqa:working_memory:{user_id}", json.dumps(memory, ensure_ascii=False))
    async def update_user_profile(self, user_id: str, key: str, value: Any):
        profile = await self.get_user_profile(user_id)
        profile[key] = value
        await self.redis.set(f"areqa:user_profile:{user_id}", json.dumps(profile, ensure_ascii=False))
        logger.info(f"[MemoryStore] Updated profile for user {user_id}, key: {key}")

    async def update_hot_memory(
        self,
        user_id: str,
        key: str,
        value: Any,
        *,
        kind: HotMemoryKind | str | None = None,
        source_role: str = "system",
        expires_at: str | None = None,
        confidence: float = 1.0,
        prompt_safe: bool | None = None,
        cold_export_eligible: bool = False,
        provenance: Dict[str, Any] | None = None,
    ):
        """Write a hot value with policy metadata while preserving raw-key reads.

        The metadata envelope is authoritative for prompt and export decisions.
        Legacy callers remain compatible, but their writes default to
        non-exportable working or operational state.
        """
        from redis.exceptions import WatchError
        mem_key = f"areqa:hot_memory:{user_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(mem_key)
                    data = await pipe.get(mem_key)
                    hot_memory = json.loads(data) if data else {}
                    
                    entry = build_hot_memory_entry(
                        key,
                        kind=kind,
                        source_role=source_role,
                        expires_at=expires_at,
                        confidence=confidence,
                        prompt_safe=prompt_safe,
                        cold_export_eligible=cold_export_eligible,
                        provenance=provenance,
                    )
                    attach_typed_entry(hot_memory, key, value, entry)
                    
                    obs_keys = [k for k in hot_memory.keys() if k.startswith("obs_")]
                    if len(obs_keys) > 50:
                        obs_keys.sort()
                        for k in obs_keys[:-50]:
                            remove_typed_entry(hot_memory, k)
                            
                    serialized = json.dumps(hot_memory, ensure_ascii=False)
                    if len(serialized) > self.budget_limit:
                        logger.warning(f"[MemoryStore] Memory size {len(serialized)} exceeds budget {self.budget_limit} for user {user_id}")
                        
                    pipe.multi()
                    pipe.set(mem_key, serialized)
                    await pipe.execute()
                    break
                except WatchError:
                    continue
        logger.info(f"[MemoryStore] Updated hot memory for user {user_id}, key: {key}")

    async def update_hot_memory_async(self, user_id: str, key: str, value: Any, **policy):
        """Async compatibility alias for :meth:`update_hot_memory`."""

        await self.update_hot_memory(user_id, key, value, **policy)

    async def update_learner_state_snapshot(
        self,
        user_id: str,
        *,
        learner_state: str,
        strategy: str,
        trigger_proactive: bool,
    ) -> int:
        """Atomically publish one versioned EDF state snapshot."""
        from redis.exceptions import WatchError

        mem_key = f"areqa:hot_memory:{user_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(mem_key)
                    data = await pipe.get(mem_key)
                    hot_memory = json.loads(data) if data else {}
                    version = int(hot_memory.get("learner_state_version", 0)) + 1
                    evaluated_at = datetime.now(timezone.utc).isoformat()
                    typed_values = {
                        "current_learner_state": (learner_state, HotMemoryKind.MODEL_INFERENCE),
                        "current_strategy": (strategy, HotMemoryKind.MODEL_INFERENCE),
                        "trigger_proactive": (bool(trigger_proactive), HotMemoryKind.OPERATIONAL_STATE),
                        "learner_state_version": (version, HotMemoryKind.OPERATIONAL_STATE),
                        "learner_state_evaluated_at": (evaluated_at, HotMemoryKind.OPERATIONAL_STATE),
                    }
                    for key, (value, kind) in typed_values.items():
                        attach_typed_entry(
                            hot_memory,
                            key,
                            value,
                            build_hot_memory_entry(
                                key,
                                kind=kind,
                                source_role="model" if kind is HotMemoryKind.MODEL_INFERENCE else "system",
                                prompt_safe=False,
                                cold_export_eligible=False,
                            ),
                        )
                    pipe.multi()
                    pipe.set(mem_key, json.dumps(hot_memory, ensure_ascii=False))
                    await pipe.execute()
                    logger.info(
                        "[MemoryStore] Published learner state snapshot v%s for user %s",
                        version,
                        user_id,
                    )
                    return version
                except WatchError:
                    continue

    async def perform_memory_operation(
        self,
        user_id: str,
        target: str,
        action: str,
        content: str,
        old_text: str = "",
        *,
        source: str = "internal",
    ):
        if target == "user" and source not in {"explicit_user_request", "user_message", "verified_user_evidence"}:
            raise InvalidMemorySource(
                f"User profile memory requires user evidence, got source={source!r}"
            )
        if target == "user":
            data = await self.get_user_profile(user_id)
            entries = data.get("explicit_memories", [])
        else:
            data = await self.get_hot_memory(user_id)
            entries = data.get("explicit_memories", [])

        if action == "add":
            if content not in entries:
                entries.append(content)
        elif action == "replace":
            for i, e in enumerate(entries):
                if old_text in e:
                    entries[i] = content
                    break
        elif action == "remove":
            entries = [e for e in entries if old_text not in e]

        data["explicit_memories"] = entries
        if target == "user":
            await self.redis.set(f"areqa:user_profile:{user_id}", json.dumps(data, ensure_ascii=False))
            await self.update_working_memory(user_id, {"explicit_memories": entries})
        else:
            await self.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(data, ensure_ascii=False))
            await self.update_working_memory(user_id, {"explicit_memories": entries})
        if action in {"replace", "remove"}:
            logger.info(
                "memory.correction_applied user_id=%s target=%s action=%s source=%s",
                user_id,
                target,
                action,
                source,
            )

    async def set_pending_alert(self, user_id: str, content: str):
        logger.info("memory.pending_alert_set user_id=%s", user_id)
        alert_key = f"pending_alert_{user_id}"
        await self.update_hot_memory(user_id, alert_key, content)
        
    async def get_and_clear_pending_alert(self, user_id: str) -> str:
        from redis.exceptions import WatchError
        alert_key = f"pending_alert_{user_id}"
        mem_key = f"areqa:hot_memory:{user_id}"
        
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(mem_key)
                    data = await pipe.get(mem_key)
                    hot_memory = json.loads(data) if data else {}
                    
                    content = hot_memory.get(alert_key, "")
                    if not content:
                        pipe.unwatch()
                        return ""
                        
                    del hot_memory[alert_key]
                    serialized = json.dumps(hot_memory, ensure_ascii=False)
                    
                    pipe.multi()
                    pipe.set(mem_key, serialized)
                    await pipe.execute()
                    
                    logger.info("memory.pending_alert_cleared user_id=%s", user_id)
                    return content
                except WatchError:
                    continue

    async def clear_all_pending_alerts(self, user_id: str = "default_user"):
        # We don't have a way to know all users easily without scanning. 
        # But we can just clear for the specific user. 
        # Actually, Phase 1 requires multi-tenant, so we should probably scan or not do this.
        # Let's skip for now, or scan for pattern `areqa:hot_memory:*`
        pass
            
    async def clear_all_memory(self, user_id: str):
        """Completely wipe hot memory and reset user profile to defaults."""
        await self.redis.delete(f"areqa:hot_memory:{user_id}")
        await self.redis.delete(f"areqa:working_memory:{user_id}")
        await self.redis.delete(f"areqa:behavior_signals:{user_id}")
        await self.redis.delete(f"areqa:cold_candidates:{user_id}")
        await self.redis.set(f"areqa:user_profile:{user_id}", json.dumps({
            "name": user_id,
            "explicit_memories": [],
            "implicit_preferences": []
        }, ensure_ascii=False))
        logger.info(f"[EDF-LOG] Cleared all hot memory and reset user profile for {user_id}.")

_global_store = None

def init_global_store(budget_limit: int = 1000000):
    global _global_store
    _global_store = MemoryStore(budget_limit)
    return _global_store

def get_global_store() -> MemoryStore:
    if _global_store is None:
        init_global_store()
    return _global_store
