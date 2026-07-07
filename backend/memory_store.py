import json
import asyncio
import logging
from typing import Dict, Any

from redis_client import get_redis

logger = logging.getLogger(__name__)

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

    async def update_user_profile(self, user_id: str, key: str, value: Any):
        profile = await self.get_user_profile(user_id)
        profile[key] = value
        await self.redis.set(f"areqa:user_profile:{user_id}", json.dumps(profile, ensure_ascii=False))
        logger.info(f"[MemoryStore] Updated profile for user {user_id}, key: {key}")

    async def update_hot_memory(self, user_id: str, key: str, value: Any):
        from redis.exceptions import WatchError
        mem_key = f"areqa:hot_memory:{user_id}"
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(mem_key)
                    data = await pipe.get(mem_key)
                    hot_memory = json.loads(data) if data else {}
                    
                    hot_memory[key] = value
                    
                    obs_keys = [k for k in hot_memory.keys() if k.startswith("obs_")]
                    if len(obs_keys) > 50:
                        obs_keys.sort()
                        for k in obs_keys[:-50]:
                            del hot_memory[k]
                            
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

    async def update_hot_memory_async(self, user_id: str, key: str, value: Any):
        # same as above
        await self.update_hot_memory(user_id, key, value)

    async def perform_memory_operation(self, user_id: str, target: str, action: str, content: str, old_text: str = ""):
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
        else:
            await self.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(data, ensure_ascii=False))

    async def set_pending_alert(self, user_id: str, content: str):
        logger.info(f"[EDF-LOG] set_pending_alert: setting alert for user '{user_id}': '{content}'")
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
                    
                    logger.info(f"[EDF-LOG] get_and_clear_pending_alert: retrieved and clearing alert for '{user_id}': '{content}'")
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
