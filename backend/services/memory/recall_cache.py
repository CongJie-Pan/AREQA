"""Short-lived cache for explicit long-term memory recall.

The cache exists only to avoid repeated foreground long-term memory lookups for
the same user/session/query shape. Keys are hashed so logs and metadata never
need to retain raw user text.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ExplicitMemoryCacheEntry:
    """A cached memory-query payload and its expiry timestamp."""

    content: dict[str, str]
    expires_at: float


class ExplicitMemoryCache:
    """Bounded TTL cache for explicit memory recall results."""

    def __init__(self, *, max_entries: int = 256) -> None:
        """Create a bounded in-process cache.

        Args:
            max_entries: Maximum entries retained before oldest-expiring entries
                are removed. This protects long-lived workers from unbounded
                memory growth.
        """

        self._max_entries = max(1, max_entries)
        self._entries: dict[str, ExplicitMemoryCacheEntry] = {}

    def make_key(self, *, user_id: str, conversation_id: str, query: str) -> str:
        """Return a stable privacy-safe key for one recall lookup."""

        digest = hashlib.sha256(
            f"{user_id}|{conversation_id}|{query.strip().lower()}".encode("utf-8")
        ).hexdigest()
        return f"explicit-memory:{digest}"

    def get(self, key: str) -> dict[str, str] | None:
        """Return cached content if present and not expired."""

        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            self._entries.pop(key, None)
            return None
        return dict(entry.content)

    def set(self, key: str, content: Mapping[str, str], *, ttl_seconds: int) -> None:
        """Store memory content for a bounded TTL."""

        if ttl_seconds <= 0:
            return
        self._entries[key] = ExplicitMemoryCacheEntry(
            content={
                "cold": str(content.get("cold") or ""),
                "working": str(content.get("working") or ""),
            },
            expires_at=time.monotonic() + ttl_seconds,
        )
        self._evict_if_needed()

    def clear(self) -> None:
        """Clear all cached entries. Intended for tests and worker resets."""

        self._entries.clear()

    def _evict_if_needed(self) -> None:
        if len(self._entries) <= self._max_entries:
            return
        overflow = len(self._entries) - self._max_entries
        oldest_keys = sorted(
            self._entries,
            key=lambda key: self._entries[key].expires_at,
        )[:overflow]
        for key in oldest_keys:
            self._entries.pop(key, None)


explicit_memory_cache = ExplicitMemoryCache()
