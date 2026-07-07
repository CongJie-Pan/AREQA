import redis.asyncio as redis
import logging
from config import settings

logger = logging.getLogger(__name__)

_redis_client = None

def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        logger.info("Successfully connected to Redis.")
    return _redis_client

async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        logger.info("Redis connection closed.")
        _redis_client = None
