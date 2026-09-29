"""Per-user spending guard for image generation across backend workers."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time

from redis_client import get_redis

logger = logging.getLogger(__name__)
_IMAGE_LIMIT_PER_MINUTE = 6
_fallback_counts: dict[str, int] = {}
_fallback_lock = asyncio.Lock()


async def consume_image_quota(user_id: str, *, limit: int = _IMAGE_LIMIT_PER_MINUTE) -> bool:
    """Reserve a request in the current minute for an authenticated quota namespace.

    The default preserves the six-image limit; intent routing supplies its own
    limit and namespace. Redis provides a shared limit. A bounded process-local counter protects the
    provider when Redis is unavailable; it does not replace a shared limit.
    """

    window = int(time.time() // 60)
    user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]
    key = f"areqa:image_generation:{user_hash}:{window}"
    try:
        redis = get_redis()
        count = int(await asyncio.wait_for(redis.incr(key), timeout=1.5))
        if count == 1:
            await asyncio.wait_for(redis.expire(key, 120), timeout=1.5)
        return count <= limit
    except Exception as error:
        logger.warning("image_generation.quota_fallback reason=%s", type(error).__name__)
        async with _fallback_lock:
            for old_key in tuple(_fallback_counts):
                if not old_key.endswith(f":{window}"):
                    del _fallback_counts[old_key]
            count = _fallback_counts.get(key, 0) + 1
            _fallback_counts[key] = count
            return count <= limit
