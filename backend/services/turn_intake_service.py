"""Own user-turn side effects before response generation.

The streaming controller delegates here so interaction timestamps, trusted
memory ingestion, and conversation-scoped roleplay state remain independently
testable and cannot become incidental SSE responsibilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
import time
from typing import Any


logger = logging.getLogger(__name__)


def normalize_avatar_name(value: str) -> str:
    """Normalize an explicitly requested avatar name."""

    normalized = re.sub(r"\s+", "", (value or "").strip())
    return re.split(r"(?:跟我|和我|與我|來|回答|對話|聊天)", normalized, maxsplit=1)[0]


def chat_avatar_key(conversation_id: str) -> str:
    """Return the conversation-scoped roleplay hot-memory key."""

    return f"chat_avatar:{conversation_id or 'default'}"


def extract_explicit_chat_avatar(message: str) -> str | None:
    """Extract an avatar only from an explicit roleplay command."""

    if any(keyword in message for keyword in ["寫信", "寄信", "信給我", "信件"]):
        return None
    patterns = [
        r"(?:請你|你)?(?:扮演|假扮|飾演|成為)(?P<avatar>[\u4e00-\u9fffA-Za-z·・\s]{2,24})(?:跟我|和我|與我|來|$)",
        r"(?:用|以)(?P<avatar>[\u4e00-\u9fffA-Za-z·・\s]{2,24})(?:的)?(?:身份|口吻|語氣)(?:跟我|和我|與我|回答|對話)",
        r"接下來你是(?P<avatar>[\u4e00-\u9fffA-Za-z·・\s]{2,24})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            avatar = normalize_avatar_name(match.group("avatar"))
            if avatar and avatar not in {"角色", "人物", "老師"}:
                return avatar
    return None


def is_stop_roleplay_request(message: str) -> bool:
    """Return whether the current conversation should leave roleplay."""

    return any(
        keyword in message
        for keyword in [
            "停止扮演", "不要扮演", "不用角色", "回到AREQA",
            "回到 AREQA", "恢復AREQA", "恢復 AREQA",
        ]
    )


@dataclass(frozen=True)
class TurnIntakeResult:
    """Summarize intake without exposing the user message."""

    store_available: bool
    memory_state: str = "not_dispatched"
    memory_reason: str = "store_unavailable"


class TurnIntakeService:
    """Apply non-streaming side effects for exactly one user-authored turn."""

    def __init__(self, client: Any):
        self.client = client

    @staticmethod
    def store_available() -> bool:
        """Return whether intake persistence is configured for this process."""

        from services.memory.store.service import get_global_store

        return get_global_store() is not None

    async def process(
        self,
        *,
        user_id: str,
        conversation_id: str,
        user_message: str,
        run_id: str,
        skip_timestamp: bool = False,
    ) -> TurnIntakeResult:
        """Persist interaction, trusted evidence, and scoped roleplay state."""

        from services.memory.store.service import get_global_store
        from services.compeer_scheduler import set_last_interaction_time
        from services.memory.ingestion.service import (
            build_user_evidence,
            create_memory_ingestion_service,
        )

        if not skip_timestamp:
            try:
                await set_last_interaction_time(user_id, time.time())
            except Exception as exc:
                logger.warning(
                    "orchestration.interaction_timestamp_failed run_id=%s conversation_id=%s reason=%s",
                    run_id,
                    conversation_id,
                    type(exc).__name__,
                )

        store = get_global_store()
        if not store:
            return TurnIntakeResult(False)

        state = "failed"
        reason = "unexpected_error"
        try:
            ingestion = create_memory_ingestion_service(store, client=self.client)
            result = await ingestion.ingest_user_evidence(
                build_user_evidence(user_id, conversation_id, user_message)
            )
            state = result.state.value
            reason = result.reason_code
            logger.info(
                "orchestration.memory_ingestion_dispatched run_id=%s conversation_id=%s outcome=%s reason=%s",
                run_id,
                conversation_id,
                state,
                reason,
            )
        except Exception as exc:
            logger.exception(
                "orchestration.memory_ingestion_failed run_id=%s conversation_id=%s reason=%s",
                run_id,
                conversation_id,
                type(exc).__name__,
            )

        try:
            if is_stop_roleplay_request(user_message):
                hot_memory = await store.get_hot_memory(user_id)
                key = chat_avatar_key(conversation_id)
                if key in hot_memory:
                    from services.memory.hot import remove_typed_entry

                    remove_typed_entry(hot_memory, key)
                    await store.redis.set(
                        f"areqa:hot_memory:{user_id}",
                        json.dumps(hot_memory, ensure_ascii=False),
                    )
            else:
                avatar = extract_explicit_chat_avatar(user_message)
                if avatar:
                    await store.update_hot_memory_async(
                        user_id,
                        chat_avatar_key(conversation_id),
                        avatar,
                        kind="operational_state",
                        source_role="user",
                        prompt_safe=False,
                        cold_export_eligible=False,
                    )
        except Exception as exc:
            logger.exception(
                "orchestration.roleplay_state_failed run_id=%s conversation_id=%s reason=%s",
                run_id,
                conversation_id,
                type(exc).__name__,
            )
        return TurnIntakeResult(True, state, reason)
