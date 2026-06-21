import asyncio, sys
sys.path.append('backend')
from backend import gum_integration
from backend.memory_store import init_global_store
import os
hot_path = "data/gum_data/hot_memory.json"
prof_path = "data/gum_data/user_profile.json"
init_global_store(hot_path, prof_path)
async def main():
    await gum_integration.init_gum_instance()
    props = await gum_integration.get_all_memory()
    print("COUNT:", len(props))
    print(props)
    await gum_integration.stop_gum_instance()
asyncio.run(main())
