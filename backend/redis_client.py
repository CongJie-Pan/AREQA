import redis.asyncio as redis
import logging
from urllib.parse import urlparse
from config import settings

logger = logging.getLogger(__name__)

_redis_client = None

def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        logger.info("Successfully connected to Redis.")
    return _redis_client


def _safe_redis_endpoint(redis_url: str) -> str:
    """Return non-secret Redis endpoint metadata for system logs."""

    parsed = urlparse(redis_url or "")
    host = parsed.hostname or "unknown"
    port = f":{parsed.port}" if parsed.port else ""
    db = parsed.path.lstrip("/") or "0"
    scheme = parsed.scheme or "redis"
    return f"{scheme}://{host}{port}/{db}"


async def log_redis_open_status() -> bool:
    """Ping Redis and emit a safe startup status event.

    Creating a Redis client does not prove that the configured cloud Redis is
    reachable. This startup probe verifies the connection without logging
    credentials or user data.
    """

    endpoint = _safe_redis_endpoint(settings.redis_url)
    try:
        await get_redis().ping()
    except Exception as exc:
        logger.warning(
            "system.redis_open_status status=closed endpoint=%s reason=%s",
            endpoint,
            type(exc).__name__,
        )
        return False
    logger.info("system.redis_open_status status=open endpoint=%s", endpoint)
    return True

async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        logger.info("Redis connection closed.")
        _redis_client = None
