"""Behavior-signal storage helpers for ``MemoryStore``.

The mixin owns the ``areqa:behavior_signals:{user_id}`` Redis list contract.
Logs are intentionally omitted because these methods can run frequently and the
stored telemetry may include UI context that should not be echoed to terminals.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict


class MemoryStoreBehaviorMixin:
    """Persist and consume user-scoped behavior signals atomically."""

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
