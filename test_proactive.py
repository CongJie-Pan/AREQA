import asyncio
from backend.services.compeer_scheduler import initialize_daily_schedule, tick_proactive_schedule
async def main():
    await initialize_daily_schedule("default_user")
    await tick_proactive_schedule("default_user")
asyncio.run(main())
