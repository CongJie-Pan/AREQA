import json
import os
import tempfile
import asyncio
from typing import Dict, Any

_store_lock = asyncio.Lock()

class MemoryBudgetExceeded(Exception):
    pass

class MemoryStore:
    def __init__(self, hot_memory_path: str, user_profile_path: str, budget_limit: int = 1000000):
        self.hot_memory_path = hot_memory_path
        self.user_profile_path = user_profile_path
        self.budget_limit = budget_limit
        
        # Ensure files exist
        for path in [self.hot_memory_path, self.user_profile_path]:
            if not os.path.exists(path):
                # ensure directory exists
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({}, f)
                    
    def _atomic_write(self, path: str, data: Dict[str, Any]):
        """Write JSON data atomically."""
        dir_name = os.path.dirname(path) or "."
        fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e
            
    def _read_json(self, path: str) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_hot_memory(self) -> Dict[str, Any]:
        return self._read_json(self.hot_memory_path)
        
    def get_learner_state(self) -> str:
        hot_mem = self.get_hot_memory()
        return hot_mem.get("current_learner_state", "STARTING")

    def get_current_strategy(self) -> str:
        hot_mem = self.get_hot_memory()
        return hot_mem.get("current_strategy", "None")
        
    def get_user_profile(self) -> Dict[str, Any]:
        return self._read_json(self.user_profile_path)
        
    def _check_budget(self, data: Dict[str, Any]):
        """Check if serialized hot memory exceeds the budget."""
        serialized = json.dumps(data, ensure_ascii=False)
        if len(serialized) > self.budget_limit:
            raise MemoryBudgetExceeded(f"Hot memory budget exceeded: {len(serialized)} > {self.budget_limit}")

    def update_hot_memory(self, key: str, value: Any):
        """Update hot memory. Creates or overrides existing key."""
        hot_memory = self.get_hot_memory()
        hot_memory[key] = value
        
        # Enforce cap at 50 for observations to prevent unbounded growth before compaction
        obs_keys = [k for k in hot_memory.keys() if k.startswith("obs_")]
        if len(obs_keys) > 50:
            obs_keys.sort()
            for k in obs_keys[:-50]:
                del hot_memory[k]
                
        self._check_budget(hot_memory)
        self._atomic_write(self.hot_memory_path, hot_memory)

    async def update_hot_memory_async(self, key: str, value: Any):
        """Thread-safe async version — 使用 asyncio.Lock 防止並發競態。"""
        async with _store_lock:
            print(f"[EDF-LOG] update_hot_memory_async: updating key '{key}'")
            hot_memory = self.get_hot_memory()
            hot_memory[key] = value
            
            # Enforce cap at 50 for observations to prevent unbounded growth before compaction
            obs_keys = [k for k in hot_memory.keys() if k.startswith("obs_")]
            if len(obs_keys) > 50:
                obs_keys.sort()
                for k in obs_keys[:-50]:
                    del hot_memory[k]
                    
            self._check_budget(hot_memory)
            self._atomic_write(self.hot_memory_path, hot_memory)
        
    def update_user_profile(self, key: str, value: Any):
        """Update user profile. This is not subject to budget checking."""
        profile = self.get_user_profile()
        profile[key] = value
        self._atomic_write(self.user_profile_path, profile)

    def set_pending_alert(self, user_id: str, content: str):
        # We can store pending alerts in hot_memory or a separate alerts dict.
        # For simplicity, store in hot memory with a specific key.
        print(f"[EDF-LOG] set_pending_alert: setting alert for user '{user_id}': '{content}'")
        alert_key = f"pending_alert_{user_id}"
        hot_memory = self.get_hot_memory()
        hot_memory[alert_key] = content
        self._atomic_write(self.hot_memory_path, hot_memory)
        
    def get_and_clear_pending_alert(self, user_id: str) -> str:
        alert_key = f"pending_alert_{user_id}"
        hot_memory = self.get_hot_memory()
        content = hot_memory.get(alert_key, "")
        if content:
            print(f"[EDF-LOG] get_and_clear_pending_alert: retrieved and clearing alert for '{user_id}': '{content}'")
            del hot_memory[alert_key]
            self._atomic_write(self.hot_memory_path, hot_memory)
        return content

    def clear_all_pending_alerts(self):
        hot_memory = self.get_hot_memory()
        keys_to_delete = [k for k in hot_memory.keys() if k.startswith("pending_alert_")]
        if keys_to_delete:
            for k in keys_to_delete:
                del hot_memory[k]
            self._atomic_write(self.hot_memory_path, hot_memory)
            print(f"[EDF-LOG] Cleared {len(keys_to_delete)} ghost pending alerts on startup.")

_global_store = None

def init_global_store(hot_memory_path: str, user_profile_path: str, budget_limit: int = 1000000):
    global _global_store
    _global_store = MemoryStore(hot_memory_path, user_profile_path, budget_limit)
    return _global_store

def get_global_store() -> MemoryStore:
    return _global_store
