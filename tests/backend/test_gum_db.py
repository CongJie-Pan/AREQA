import pytest
import asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from gum.models import Base, Proposition
from gum.gum import gum
import pytest_asyncio

@pytest_asyncio.fixture
async def temp_gum_engine():
    # Use an in-memory SQLite database for testing DB operations
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    # Initialize Gum with this engine
    gum_instance = gum(user_name="test_user", model="test_model")
    gum_instance.engine = engine
    gum_instance._session = session_maker
    
    yield gum_instance
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.mark.asyncio
async def test_update_status_commits_successfully(temp_gum_engine):
    # Insert a proposition
    async with temp_gum_engine._session() as session:
        from sqlalchemy import insert
        from gum.models import Proposition
        result = await session.execute(
            insert(Proposition).values(text="Original Text", confidence=0.8, reasoning="test", status="active", created_at=datetime.now(timezone.utc), revision_group="default").returning(Proposition.id)
        )
        await session.commit()
        prop_id = result.scalar_one()
        
    # Call update_status
    await temp_gum_engine.update_status(prop_id, "deleted")
    
    # Verify the status was updated and committed
    async with temp_gum_engine._session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Proposition).where(Proposition.id == prop_id))
        updated_prop = result.scalar_one_or_none()
        assert updated_prop is not None
        assert updated_prop.status == "deleted"

@pytest.mark.asyncio
async def test_update_text_commits_successfully(temp_gum_engine):
    # Insert a proposition
    async with temp_gum_engine._session() as session:
        from sqlalchemy import insert
        from gum.models import Proposition
        result = await session.execute(
            insert(Proposition).values(text="Old Text", confidence=0.8, reasoning="test", status="active", created_at=datetime.now(timezone.utc), revision_group="default").returning(Proposition.id)
        )
        await session.commit()
        prop_id = result.scalar_one()
        
    # Call update_text
    await temp_gum_engine.update_text(prop_id, "New Text")
    
    # Verify the text was updated and committed
    async with temp_gum_engine._session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Proposition).where(Proposition.id == prop_id))
        updated_prop = result.scalar_one_or_none()
        assert updated_prop is not None
        assert updated_prop.text == "New Text"
