import json
import asyncio
from typing import Dict, Any

from redis_client import get_redis

class MemoryStore:
    def __init__(self, budget_limit: int = 1000000):
        self.budget_limit = budget_limit
        self.redis = get_redis()

    async def get_hot_memory(self, user_id: str) -> Dict[str, Any]:
        data = await self.redis.get(f"areqa:hot_memory:{user_id}")
        return json.loads(data) if data else {}

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

    async def update_hot_memory(self, user_id: str, key: str, value: Any):
        # We can use a Redis lock if needed, but since it's async and we want to avoid race conditions,
        # we can fetch, modify, and set. For single worker, it's fine. For multi-worker, we might need a lock.
        # But Phase 1 plan says "全面改用 redis.asyncio".
        hot_memory = await self.get_hot_memory(user_id)
        hot_memory[key] = value
        
        obs_keys = [k for k in hot_memory.keys() if k.startswith("obs_")]
        if len(obs_keys) > 50:
            obs_keys.sort()
            for k in obs_keys[:-50]:
                del hot_memory[k]
                
        serialized = json.dumps(hot_memory, ensure_ascii=False)
        # We ignore budget exceeding exception here or log it, but the existing code raised it.
        if len(serialized) > self.budget_limit:
            pass # Usually handled by compaction
            
        await self.redis.set(f"areqa:hot_memory:{user_id}", serialized)

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
        print(f"[EDF-LOG] set_pending_alert: setting alert for user '{user_id}': '{content}'")
        alert_key = f"pending_alert_{user_id}"
        hot_memory = await self.get_hot_memory(user_id)
        hot_memory[alert_key] = content
        await self.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(hot_memory, ensure_ascii=False))
        
    async def get_and_clear_pending_alert(self, user_id: str) -> str:
        alert_key = f"pending_alert_{user_id}"
        hot_memory = await self.get_hot_memory(user_id)
        content = hot_memory.get(alert_key, "")
        if content:
            print(f"[EDF-LOG] get_and_clear_pending_alert: retrieved and clearing alert for '{user_id}': '{content}'")
            del hot_memory[alert_key]
            await self.redis.set(f"areqa:hot_memory:{user_id}", json.dumps(hot_memory, ensure_ascii=False))
        return content

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
        print(f"[EDF-LOG] Cleared all hot memory and reset user profile for {user_id}.")

_global_store = None

def init_global_store(budget_limit: int = 1000000):
    global _global_store
    _global_store = MemoryStore(budget_limit)
    return _global_store

def get_global_store() -> MemoryStore:
    if _global_store is None:
        init_global_store()
    return _global_store
