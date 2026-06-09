import asyncio
from gum.models import Proposition
from sqlalchemy import inspect

async def main():
    mapper = inspect(Proposition)
    print("Version ID Col:", mapper.version_id_col)

asyncio.run(main())
