import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, text

async def main():
    engine = create_async_engine("sqlite+aiosqlite:///backend/gum.db")
    session_maker = async_sessionmaker(engine)
    async with session_maker() as session:
        result = await session.execute(text("SELECT id, text, status, created_at, updated_at FROM propositions ORDER BY created_at DESC LIMIT 10"))
        rows = result.fetchall()
        for r in rows:
            print(r)

asyncio.run(main())
