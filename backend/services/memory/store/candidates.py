"""Cold-candidate lifecycle helpers for ``MemoryStore``.

The mixin owns candidate creation, evidence append, promotion, temporary-goal
completion, and rejection while preserving exact Redis key names and method
contracts from ``memory_store.py``. Structured logs use safe user ids,
candidate ids, categories, counts, and reason codes only.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MemoryStoreCandidateMixin:
    """Manage cold candidate lifecycle and profile promotion transactions."""

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
