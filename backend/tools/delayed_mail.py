from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Callable, Mapping

from .registry import ToolResult


class DelayedMailTool:
    _LETTER_INTENT = re.compile(r"寫信|寄信|信給我|信件|回信")
    _SAFE_AVATAR = re.compile(r"^[\u4e00-\u9fffA-Za-z·・\s]{1,40}$")

    def __init__(self, store_factory: Callable[[], Any]) -> None:
        self._store_factory = store_factory

    async def execute(self, arguments: Mapping[str, Any]) -> ToolResult:
        user_message = str(arguments.get("user_message", ""))
        if not self._LETTER_INTENT.search(user_message):
            raise PermissionError("delayed mail requires explicit user intent")
        avatar_name = str(arguments.get("avatar_name", "")).strip()
        if not avatar_name or not self._SAFE_AVATAR.fullmatch(avatar_name):
            raise ValueError("invalid avatar name")

        user_id = str(arguments["user_id"])
        conversation_id = str(arguments.get("conversation_id", ""))
        task_id = str(arguments["task_id"])
        started = time.monotonic()
        from config import settings

        if not settings.enable_mailbox_sending:
            return ToolResult(
                tool_name="schedule_letter",
                status="disabled",
                content={"task_id": task_id, "avatar_name": avatar_name},
                provenance=(),
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        store = self._store_factory()
        await store.schedule_delayed_mail(
            user_id=user_id,
            mail_data={
                "kind": "avatar_letter",
                "active_avatar": avatar_name,
                "sender": avatar_name,
                "recipient": "User",
                "conversation_id": conversation_id,
                "reply_content": user_message,
                "source_message_hash": hashlib.sha256(
                    user_message.strip().encode("utf-8")
                ).hexdigest()[:24],
                "task_id": task_id,
            },
            delay_seconds=300,
        )
        return ToolResult(
            tool_name="schedule_letter",
            status="ok",
            content={"task_id": task_id, "avatar_name": avatar_name},
            provenance=("mailbox_delayed_tasks",),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
