from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.gum_integration as gum_integration
from gum.gum import gum
from gum.models import Base, Proposition


@pytest_asyncio.fixture
async def real_sqlite_gum():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    instance = gum(user_name="test-user", model="test-model", api_key="local-test-key")
    instance.engine = engine
    instance._session = async_sessionmaker(engine, expire_on_commit=False)

    async with instance._session() as session:
        await session.execute(insert(Proposition), [
            {
                "text": "user-a 的長期記憶",
                "reasoning": "regression test",
                "confidence": 9,
                "decay": 2,
                "status": "active",
                "user_id": "user-a",
                "created_at": datetime.now(timezone.utc),
                "revision_group": "user-a-group",
            },
            {
                "text": "user-b 的長期記憶",
                "reasoning": "regression test",
                "confidence": 9,
                "decay": 2,
                "status": "active",
                "user_id": "user-b",
                "created_at": datetime.now(timezone.utc),
                "revision_group": "user-b-group",
            },
        ])
        await session.commit()

    yield instance
    await engine.dispose()


@pytest.mark.asyncio
async def test_real_gum_memory_read_is_scoped_to_requested_user(real_sqlite_gum, monkeypatch):
    async def get_real_instance(_user_id):
        return real_sqlite_gum, None

    monkeypatch.setattr(gum_integration, "get_gum_instance", get_real_instance)

    user_a_memory = await gum_integration.get_all_memory("user-a")
    user_b_memory = await gum_integration.get_all_memory("user-b")

    assert [item["text"] for item in user_a_memory] == ["user-a 的長期記憶"]
    assert [item["text"] for item in user_b_memory] == ["user-b 的長期記憶"]
