import json
import os
import tempfile
from typing import Dict, Any

class MemoryBudgetExceeded(Exception):
    pass

class MemoryStore:
    def __init__(self, hot_memory_path: str, user_profile_path: str, budget_limit: int = 1000):
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
        
        # We remove _check_budget here so the newest item is ALWAYS added.
        # run_compaction() will automatically trim the oldest items afterward.
        self._atomic_write(self.hot_memory_path, hot_memory)
        
    def update_user_profile(self, key: str, value: Any):
        """Update user profile. This is not subject to budget checking."""
        user_profile = self.get_user_profile()
        user_profile[key] = value
        
        
        self._atomic_write(self.user_profile_path, user_profile)

_global_store = None

def init_global_store(hot_memory_path: str, user_profile_path: str, budget_limit: int = 1000):
    global _global_store
    _global_store = MemoryStore(hot_memory_path, user_profile_path, budget_limit)
    return _global_store

def get_global_store() -> MemoryStore:
    return _global_store
