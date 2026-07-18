import json
import asyncio
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any

from redis_client import get_redis
from services.hot_memory_service import (
    HotMemoryKind,
    attach_typed_entry,
    build_hot_memory_entry,
)

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

    async def consume_behavior_signals(
        self,
        user_id: str,
        consumed_signals: list[Dict[str, Any]],
    ) -> int:
        """Atomically remove behavior signals after a durable consumer accepts them.

        UI telemetry is stored outside prompt-visible memory under
        `areqa:behavior_signals:{user_id}`. Consumers such as the ComPeer
        scheduler must remove only the exact entries they have accepted so a
        successful scheduling decision cannot be replayed by the same signal
        batch. Malformed or missing storage data fails closed as an empty list.

        Args:
            user_id: The owner of the behavior-signal list.
            consumed_signals: Exact signal dictionaries to remove.

        Returns:
            The number of entries removed from the behavior-signal list.
        """
        if not consumed_signals:
            return 0

        from redis.exceptions import WatchError

        key = f"areqa:behavior_signals:{user_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    data = await pipe.get(key)
                    parsed = json.loads(data) if data else []
                    signals = parsed if isinstance(parsed, list) else []

                    remaining = list(signals)
                    removed = 0
                    for consumed in consumed_signals:
                        for index, signal in enumerate(remaining):
                            if signal == consumed:
                                remaining.pop(index)
                                removed += 1
                                break

                    pipe.multi()
                    pipe.set(key, json.dumps(remaining[-50:], ensure_ascii=False))
                    await pipe.execute()
                    return removed
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
        expires_at: str | None = None,
        canonical_key: str = "",
        candidate_hash_override: str = "",
    ) -> Dict[str, Any] | None:
        """Append immutable user evidence to one expiring cold candidate.

        Semantic matching may select an existing candidate hash, but this
        storage boundary still verifies ownership and de-duplicates message and
        conversation identifiers before evidence can count toward promotion.
        """
        text = (text or "").strip()
        if not text:
            return None

        from redis.exceptions import WatchError
        key = f"areqa:cold_candidates:{user_id}"
        normalized_text = (normalized_text or text).strip()
        candidate_hash = candidate_hash_override or hashlib.sha256(
            f"{category}|{normalized_text}".encode("utf-8")
        ).hexdigest()[:24]
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
                            if candidate.get("user_id") != user_id or candidate.get("category") != category:
                                logger.warning(
                                    "memory.promotion_blocked user_id=%s candidate_id=%s reason=ownership_or_category",
                                    user_id,
                                    candidate_hash,
                                )
                                return None
                            if candidate.get("status") != "candidate":
                                return candidate
                            candidate["last_seen_at"] = now
                            existing_message_ids = {
                                str(item.get("message_id", ""))
                                for item in candidate.setdefault("evidence", [])
                                if isinstance(item, dict)
                            }
                            existing_conversation_ids = {
                                str(item.get("conversation_id", ""))
                                for item in candidate["evidence"]
                                if isinstance(item, dict)
                            }
                            message_id = str((evidence or {}).get("message_id", ""))
                            duplicate_preference_conversation = (
                                category == "passive_preference"
                                and bool(conversation_id)
                                and conversation_id in existing_conversation_ids
                            )
                            if (
                                evidence
                                and message_id
                                and message_id not in existing_message_ids
                                and not duplicate_preference_conversation
                            ):
                                candidate["evidence"].append(evidence)
                                if conversation_id and conversation_id not in candidate.setdefault("conversation_ids", []):
                                    candidate["conversation_ids"].append(conversation_id)
                            candidate["evidence"] = candidate.get("evidence", [])[-8:]
                            candidate["conversation_ids"] = candidate.get("conversation_ids", [])[-8:]
                            candidate["seen_count"] = len(candidate.get("evidence", [])) or int(candidate.get("seen_count", 1)) + 1
                            pipe.multi()
                            pipe.set(key, json.dumps(candidates[-100:], ensure_ascii=False))
                            await pipe.execute()
                            if duplicate_preference_conversation:
                                event = "duplicate_conversation_ignored"
                            elif evidence and message_id in existing_message_ids:
                                event = "duplicate_message_ignored"
                            else:
                                event = "evidence_appended"
                            logger.info(
                                "memory.candidate_evidence_recorded user_id=%s candidate_id=%s category=%s event=%s evidence_count=%s distinct_conversation_count=%s",
                                user_id,
                                candidate_hash,
                                category,
                                event,
                                len(candidate.get("evidence", [])),
                                len(set(candidate.get("conversation_ids", []))),
                            )
                            return candidate

                    # A semantic override may only select an already validated
                    # candidate. It must never become an alternate create API.
                    if candidate_hash_override:
                        logger.warning(
                            "memory.candidate_append_blocked user_id=%s candidate_id=%s reason=unknown_override",
                            user_id,
                            candidate_hash_override,
                        )
                        return None

                    candidate = {
                        "user_id": user_id,
                        "hash": candidate_hash,
                        "text": text,
                        "source_text": (source_text or (evidence or {}).get("message", "") or text).strip(),
                        "normalized_text": normalized_text,
                        "canonical_key": canonical_key or normalized_text,
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
                        "expires_at": expires_at,
                        "status": "candidate",
                    }
                    candidates.append(candidate)

                    pipe.multi()
                    pipe.set(key, json.dumps(candidates[-100:], ensure_ascii=False))
                    await pipe.execute()
                    logger.info(
                        "memory.candidate_created user_id=%s candidate_id=%s category=%s expires=%s evidence_count=%s distinct_conversation_count=%s",
                        user_id,
                        candidate_hash,
                        category,
                        bool(expires_at),
                        len(candidate["evidence"]),
                        len(set(candidate["conversation_ids"])),
                    )
                    return candidate
                except WatchError:
                    continue

    async def promote_cold_candidate(self, user_id: str, candidate_hash: str, *, source: str) -> Dict[str, Any] | None:
        """Atomically promote provenance-complete evidence exactly once.

        Candidate state, profile memory, and its working-memory mirror share one
        Redis transaction. Concurrent callers therefore cannot each publish a
        different profile entry from the same candidate.
        """

        from config import settings
        from redis.exceptions import WatchError

        candidate_key = f"areqa:cold_candidates:{user_id}"
        profile_key = f"areqa:user_profile:{user_id}"
        working_key = f"areqa:working_memory:{user_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(candidate_key, profile_key, working_key)
                    candidate_data = await pipe.get(candidate_key)
                    parsed = json.loads(candidate_data) if candidate_data else []
                    candidates = parsed if isinstance(parsed, list) else []
                    candidate = next(
                        (item for item in candidates if item.get("hash") == candidate_hash),
                        None,
                    )
                    if (
                        candidate is None
                        or candidate.get("user_id") != user_id
                        or candidate.get("status") != "candidate"
                    ):
                        return None
                    if candidate.get("requires_confirmation") and source != "user_confirmation":
                        return None

                    expires_at = str(candidate.get("expires_at") or "")
                    if expires_at:
                        try:
                            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                            if expiry.tzinfo is None:
                                expiry = expiry.replace(tzinfo=timezone.utc)
                        except ValueError:
                            return None
                        if expiry <= datetime.now(timezone.utc):
                            candidate["status"] = "expired"
                            pipe.multi()
                            pipe.set(
                                candidate_key,
                                json.dumps(candidates[-100:], ensure_ascii=False),
                            )
                            await pipe.execute()
                            logger.info(
                                "memory.candidate_expired user_id=%s candidate_id=%s",
                                user_id,
                                candidate_hash,
                            )
                            return None

                    category = str(candidate.get("category", ""))
                    evidence = [
                        item for item in candidate.get("evidence", [])
                        if isinstance(item, dict)
                    ]
                    complete_evidence = [
                        item for item in evidence
                        if all(str(item.get(field, "")).strip() for field in (
                            "message_id",
                            "conversation_id",
                            "timestamp",
                            "source_role",
                            "message",
                            "quote",
                        )) and item.get("source_role") == "user"
                    ]
                    if source != "user_confirmation" and len(complete_evidence) != len(evidence):
                        logger.warning(
                            "memory.promotion_blocked user_id=%s candidate_id=%s reason=incomplete_provenance",
                            user_id,
                            candidate_hash,
                        )
                        return None
                    if category == "temporary_goal":
                        return None
                    if category == "passive_preference" and source != "user_confirmation":
                        conversation_ids = {
                            item["conversation_id"] for item in complete_evidence
                        }
                        message_ids = {item["message_id"] for item in complete_evidence}
                        threshold = max(
                            2,
                            settings.memory_candidate_auto_promote_conversations,
                        )
                        if (
                            len(conversation_ids) < threshold
                            or len(message_ids) < threshold
                        ):
                            logger.warning(
                                "memory.promotion_blocked user_id=%s candidate_id=%s reason=insufficient_independent_evidence",
                                user_id,
                                candidate_hash,
                            )
                            return None
                    elif (
                        category not in {"passive_preference", "stable_fact_candidate"}
                        and source != "user_confirmation"
                    ):
                        return None

                    evidence_quote = str(evidence[-1].get("quote", "")).strip() if evidence else ""
                    profile_text = evidence_quote or str(candidate.get("source_text", "")).strip()
                    if not profile_text:
                        return None

                    profile_data = await pipe.get(profile_key)
                    profile = json.loads(profile_data) if profile_data else {
                        "name": "default_user",
                        "explicit_memories": [],
                        "implicit_preferences": [],
                    }
                    profile_entries = list(profile.get("explicit_memories", []))
                    if profile_text not in profile_entries:
                        profile_entries.append(profile_text)
                    profile["explicit_memories"] = profile_entries

                    working_data = await pipe.get(working_key)
                    working = json.loads(working_data) if working_data else {
                        "session_summary": "",
                        "session_summary_conversation_id": "",
                        "current_focus": "",
                        "current_focus_conversation_id": "",
                        "recent_learning_points": [],
                        "explicit_memories": [],
                        "updated_at": None,
                    }
                    working["explicit_memories"] = profile_entries
                    now = datetime.now(timezone.utc).isoformat()
                    working["updated_at"] = now
                    candidate["status"] = "promoted"
                    candidate["policy_decision"] = "promoted"
                    candidate["policy_reason"] = "verified_user_evidence"
                    candidate["promoted_at"] = now

                    pipe.multi()
                    pipe.set(
                        candidate_key,
                        json.dumps(candidates[-100:], ensure_ascii=False),
                    )
                    pipe.set(profile_key, json.dumps(profile, ensure_ascii=False))
                    pipe.set(working_key, json.dumps(working, ensure_ascii=False))
                    await pipe.execute()
                    logger.info(
                        "memory.profile_promoted user_id=%s candidate_id=%s category=%s evidence_count=%s distinct_conversation_count=%s",
                        user_id,
                        candidate_hash,
                        category,
                        len(complete_evidence),
                        len({item["conversation_id"] for item in complete_evidence}),
                    )
                    return candidate
                except WatchError:
                    continue

    async def complete_temporary_goal_candidate(
        self,
        user_id: str,
        candidate_hash: str,
        evidence: Dict[str, Any],
        *,
        reason: str,
    ) -> Dict[str, Any] | None:
        """Atomically retire one temporary goal using complete user evidence.

        A completed goal remains auditable as lifecycle history but is never
        promoted to profile memory. Missing, ambiguous, or malformed requests
        fail closed and emit metadata-only diagnostics.
        """

        required_fields = (
            "message_id",
            "conversation_id",
            "timestamp",
            "source_role",
            "message",
            "quote",
        )
        safe_reasons = {
            "explicit_user_completion",
            "temporary_goal_completion_not_found",
            "temporary_goal_completion_ambiguous",
            "incomplete_provenance",
        }
        safe_reason = reason if reason in safe_reasons else "invalid_reason"
        if (
            not candidate_hash
            or evidence.get("source_role") != "user"
            or not all(str(evidence.get(field, "")).strip() for field in required_fields)
        ):
            logger.warning(
                "memory.temporary_goal_completion_blocked user_id=%s candidate_id=%s reason=%s",
                user_id,
                candidate_hash or "none",
                safe_reason,
            )
            return None

        from redis.exceptions import WatchError

        key = f"areqa:cold_candidates:{user_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    data = await pipe.get(key)
                    parsed = json.loads(data) if data else []
                    candidates = parsed if isinstance(parsed, list) else []
                    candidate = next(
                        (item for item in candidates if item.get("hash") == candidate_hash),
                        None,
                    )
                    if (
                        candidate is None
                        or candidate.get("user_id") != user_id
                        or candidate.get("category") != "temporary_goal"
                        or candidate.get("status") != "candidate"
                    ):
                        logger.warning(
                            "memory.temporary_goal_completion_blocked user_id=%s candidate_id=%s reason=ownership_category_or_status",
                            user_id,
                            candidate_hash,
                        )
                        return None

                    candidate["status"] = "completed"
                    candidate["completed_at"] = datetime.now(timezone.utc).isoformat()
                    candidate["completion_reason"] = safe_reason
                    candidate["completion_evidence"] = evidence
                    lifecycle_evidence = {
                        **evidence,
                        "evidence_type": "temporary_goal_completion",
                    }
                    evidence_items = candidate.setdefault("evidence", [])
                    existing_message_ids = {
                        str(item.get("message_id", ""))
                        for item in evidence_items
                        if isinstance(item, dict)
                    }
                    if str(evidence["message_id"]) not in existing_message_ids:
                        evidence_items.append(lifecycle_evidence)
                    candidate["evidence"] = evidence_items[-8:]
                    candidate["seen_count"] = len(candidate["evidence"])
                    pipe.multi()
                    pipe.set(key, json.dumps(candidates[-100:], ensure_ascii=False))
                    await pipe.execute()
                    logger.info(
                        "memory.temporary_goal_completed user_id=%s candidate_id=%s status=completed reason=%s evidence_count=%s cleared_keys=%s",
                        user_id,
                        candidate_hash,
                        safe_reason,
                        len(candidate["evidence"]),
                        "none",
                    )
                    return candidate
                except WatchError:
                    continue

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
