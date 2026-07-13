import json
import asyncio
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any

from redis_client import get_redis

logger = logging.getLogger(__name__)

class MemoryBudgetExceeded(Exception):
    pass


class InvalidMemorySource(ValueError):
    """Raised when a caller tries to write profile memory without user evidence."""

class MemoryStore:
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

        entry = {
            "text": text,
            "conversation_id": conversation_id,
            "source": source,
            "confidence": float(confidence),
            "decay": float(decay),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        points.append(entry)
        memory["recent_learning_points"] = points[-12:]
        memory["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set(f"areqa:working_memory:{user_id}", json.dumps(memory, ensure_ascii=False))

    async def get_behavior_signals(self, user_id: str) -> list[Dict[str, Any]]:
        data = await self.redis.get(f"areqa:behavior_signals:{user_id}")
        if not data:
            return []
        parsed = json.loads(data)
        return parsed if isinstance(parsed, list) else []

    async def append_behavior_signal(self, user_id: str, action_type: str, context: Any, *, weight: float = 1.0):
        action_type = (action_type or "").strip()
        if not action_type:
            return

        from redis.exceptions import WatchError
        key = f"areqa:behavior_signals:{user_id}"
        entry = {
            "type": action_type,
            "context": context if isinstance(context, dict) else {},
            "weight": float(weight),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    data = await pipe.get(key)
                    parsed = json.loads(data) if data else []
                    signals = parsed if isinstance(parsed, list) else []
                    signals.append(entry)

                    pipe.multi()
                    pipe.set(key, json.dumps(signals[-50:], ensure_ascii=False))
                    await pipe.execute()
                    break
                except WatchError:
                    continue

    async def get_cold_candidates(self, user_id: str) -> list[Dict[str, Any]]:
        data = await self.redis.get(f"areqa:cold_candidates:{user_id}")
        if not data:
            return []
        parsed = json.loads(data)
        return parsed if isinstance(parsed, list) else []

    async def update_cold_candidate(self, candidate: Dict[str, Any]) -> None:
        """Persist policy metadata without promoting a candidate to profile."""
        user_id = str(candidate.get("user_id", ""))
        candidate_hash = candidate.get("hash")
        if not user_id or not candidate_hash:
            return
        candidates = await self.get_cold_candidates(user_id)
        for index, current in enumerate(candidates):
            if current.get("hash") == candidate_hash:
                candidates[index] = {**current, **candidate}
                break
        await self.redis.set(
            f"areqa:cold_candidates:{user_id}",
            json.dumps(candidates[-100:], ensure_ascii=False),
        )

    async def append_cold_candidate(
        self,
        user_id: str,
        text: str,
        *,
        category: str,
        source: str,
        reason: str,
        confidence: float = 9.0,
        decay: float = 3.0,
        normalized_text: str = "",
        evidence: Dict[str, Any] | None = None,
        source_text: str = "",
        conversation_id: str = "",
        requires_confirmation: bool = False,
    ) -> Dict[str, Any] | None:
        text = (text or "").strip()
        if not text:
            return None

        from redis.exceptions import WatchError
        key = f"areqa:cold_candidates:{user_id}"
        normalized_text = (normalized_text or text).strip()
        candidate_hash = hashlib.sha256(f"{category}|{normalized_text}".encode("utf-8")).hexdigest()[:24]
        now = datetime.now(timezone.utc).isoformat()

        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    data = await pipe.get(key)
                    parsed = json.loads(data) if data else []
                    candidates = parsed if isinstance(parsed, list) else []

                    for candidate in candidates:
                        if candidate.get("hash") == candidate_hash:
                            if candidate.get("status") == "rejected":
                                return candidate
                            candidate["last_seen_at"] = now
                            if conversation_id and conversation_id not in candidate.setdefault("conversation_ids", []):
                                candidate["conversation_ids"].append(conversation_id)
                            if evidence and evidence not in candidate.setdefault("evidence", []):
                                candidate["evidence"].append(evidence)
                            candidate["evidence"] = candidate.get("evidence", [])[-8:]
                            candidate["conversation_ids"] = candidate.get("conversation_ids", [])[-8:]
                            candidate["seen_count"] = len(candidate.get("evidence", [])) or int(candidate.get("seen_count", 1)) + 1
                            pipe.multi()
                            pipe.set(key, json.dumps(candidates[-100:], ensure_ascii=False))
                            await pipe.execute()
                            return candidate

                    candidate = {
                        "user_id": user_id,
                        "hash": candidate_hash,
                        "text": text,
                        "source_text": (source_text or (evidence or {}).get("message", "") or text).strip(),
                        "normalized_text": normalized_text,
                        "category": category,
                        "source": source,
                        "reason": reason,
                        "confidence": float(confidence),
                        "decay": float(decay),
                        "created_at": now,
                        "last_seen_at": now,
                        "seen_count": 1,
                        "conversation_ids": [conversation_id] if conversation_id else [],
                        "evidence": [evidence] if evidence else [],
                        "requires_confirmation": bool(requires_confirmation),
                        "status": "candidate",
                    }
                    candidates.append(candidate)

                    pipe.multi()
                    pipe.set(key, json.dumps(candidates[-100:], ensure_ascii=False))
                    await pipe.execute()
                    return candidate
                except WatchError:
                    continue

    async def promote_cold_candidate(self, user_id: str, candidate_hash: str, *, source: str) -> Dict[str, Any] | None:
        candidates = await self.get_cold_candidates(user_id)
        candidate = next((item for item in candidates if item.get("hash") == candidate_hash), None)
        if not candidate or candidate.get("status") == "rejected":
            return None
        if candidate.get("requires_confirmation") and source != "user_confirmation":
            return None

        from memory_gate import evaluate_memory_retention_policy

        policy = evaluate_memory_retention_policy(candidate)
        if policy.action == "deny":
            candidate["policy_decision"] = policy.action
            candidate["policy_reason"] = policy.reason
            await self.redis.set(
                f"areqa:cold_candidates:{user_id}",
                json.dumps(candidates[-100:], ensure_ascii=False),
            )
            return None
        if policy.action == "candidate_only" and source != "user_confirmation":
            return None

        evidence_quote = ""
        evidence = candidate.get("evidence") or []
        if isinstance(evidence, list) and evidence:
            evidence_quote = str(evidence[-1].get("quote", "")).strip()
        profile_text = evidence_quote or str(candidate.get("source_text", "")).strip()
        if not profile_text:
            return None

        await self.perform_memory_operation(
            user_id,
            "user",
            "add",
            profile_text,
            source="verified_user_evidence",
        )
        candidate["status"] = "promoted"
        candidate["policy_decision"] = policy.action
        candidate["policy_reason"] = policy.reason
        if policy.expires_in_seconds:
            candidate["expires_in_seconds"] = policy.expires_in_seconds
        candidate["promoted_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set(
            f"areqa:cold_candidates:{user_id}",
            json.dumps(candidates[-100:], ensure_ascii=False),
        )
        return candidate

    async def reject_cold_candidate(self, user_id: str, candidate_hash: str) -> Dict[str, Any] | None:
        candidates = await self.get_cold_candidates(user_id)
        candidate = next((item for item in candidates if item.get("hash") == candidate_hash), None)
        if not candidate:
            return None
        candidate["status"] = "rejected"
        candidate["rejected_at"] = datetime.now(timezone.utc).isoformat()
        await self.redis.set(
            f"areqa:cold_candidates:{user_id}",
            json.dumps(candidates[-100:], ensure_ascii=False),
        )
        return candidate

    async def update_user_profile(self, user_id: str, key: str, value: Any):
        profile = await self.get_user_profile(user_id)
        profile[key] = value
        await self.redis.set(f"areqa:user_profile:{user_id}", json.dumps(profile, ensure_ascii=False))
        logger.info(f"[MemoryStore] Updated profile for user {user_id}, key: {key}")

    async def update_hot_memory(self, user_id: str, key: str, value: Any):
        from redis.exceptions import WatchError
        mem_key = f"areqa:hot_memory:{user_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(mem_key)
                    data = await pipe.get(mem_key)
                    hot_memory = json.loads(data) if data else {}
                    
                    hot_memory[key] = value
                    
                    obs_keys = [k for k in hot_memory.keys() if k.startswith("obs_")]
                    if len(obs_keys) > 50:
                        obs_keys.sort()
                        for k in obs_keys[:-50]:
                            del hot_memory[k]
                            
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

    async def update_hot_memory_async(self, user_id: str, key: str, value: Any):
        # same as above
        await self.update_hot_memory(user_id, key, value)

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
                    hot_memory.update({
                        "current_learner_state": learner_state,
                        "current_strategy": strategy,
                        "trigger_proactive": bool(trigger_proactive),
                        "learner_state_version": version,
                        "learner_state_evaluated_at": datetime.now(timezone.utc).isoformat(),
                    })
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

    async def set_pending_alert(self, user_id: str, content: str):
        logger.info(f"[EDF-LOG] set_pending_alert: setting alert for user '{user_id}': '{content}'")
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
                    
                    logger.info(f"[EDF-LOG] get_and_clear_pending_alert: retrieved and clearing alert for '{user_id}': '{content}'")
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
