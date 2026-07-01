import redis.asyncio as aioredis
import pickle
import logging

logger = logging.getLogger(__name__)

class RagCacheService:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = aioredis.from_url(redis_url)
        self.TTL = 3600  # 1 hour TTL

    async def get(self, fingerprint: str):
        try:
            data = await self.redis.get(f"rag:{fingerprint}")
            return pickle.loads(data) if data else None
        except Exception as e:
            logger.error(f"Error reading from Redis cache: {e}")
            return None

    async def set(self, fingerprint: str, result):
        try:
            await self.redis.setex(f"rag:{fingerprint}", self.TTL, pickle.dumps(result))
        except Exception as e:
            logger.error(f"Error writing to Redis cache: {e}")
