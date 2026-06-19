import pytest
import asyncio
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import insert, select

from gum.models import Base, Proposition, create_fts_table, create_observations_fts
from gum.gum import gum
from gum.db_utils import search_propositions_bm25
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
        result = await session.execute(
            insert(Proposition).values(text="Original Text", confidence=0.8, reasoning="test", status="active", created_at=datetime.now(timezone.utc), revision_group="default").returning(Proposition.id)
        )
        await session.commit()
        prop_id = result.scalar_one()
        
    # Call update_status
    await temp_gum_engine.update_status(prop_id, "deleted")
    
    # Verify the status was updated and committed
    async with temp_gum_engine._session() as session:
        result = await session.execute(select(Proposition).where(Proposition.id == prop_id))
        updated_prop = result.scalar_one_or_none()
        assert updated_prop is not None
        assert updated_prop.status == "deleted"

@pytest.mark.asyncio
async def test_update_text_commits_successfully(temp_gum_engine):
    # Insert a proposition
    async with temp_gum_engine._session() as session:
        result = await session.execute(
            insert(Proposition).values(text="Old Text", confidence=0.8, reasoning="test", status="active", created_at=datetime.now(timezone.utc), revision_group="default").returning(Proposition.id)
        )
        await session.commit()
        prop_id = result.scalar_one()
        
    # Call update_text
    await temp_gum_engine.update_text(prop_id, "New Text")
    
    # Verify the text was updated and committed
    async with temp_gum_engine._session() as session:
        result = await session.execute(select(Proposition).where(Proposition.id == prop_id))
        updated_prop = result.scalar_one_or_none()
        assert updated_prop is not None
        assert updated_prop.text == "New Text"


# --- STITCH Contextual Intent Filtering Tests ---

@pytest_asyncio.fixture
async def temp_gum_with_fts():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(create_fts_table)
        await conn.run_sync(create_observations_fts)
    
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    yield session_maker
    await engine.dispose()

@pytest.mark.asyncio
async def test_stitch_filter_exact_match(temp_gum_with_fts):
    async with temp_gum_with_fts() as session:
        await session.execute(
            insert(Proposition).values(
                text="User is learning Python.", reasoning="test", status="active",
                context_scope="Python Programming", target="Python",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.execute(
            insert(Proposition).values(
                text="User is studying History.", reasoning="test", status="active",
                context_scope="History", target="WW2",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.commit()
        
        selected_labels = {
            "selected_context_scopes": ["Python Programming"],
            "selected_event_types": [],
            "selected_targets": [],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(session, "Python", selected_labels=selected_labels)
        assert len(results) == 1
        assert results[0][0].context_scope == "Python Programming"

@pytest.mark.asyncio
async def test_stitch_filter_multi_field_match(temp_gum_with_fts):
    async with temp_gum_with_fts() as session:
        await session.execute(
            insert(Proposition).values(
                text="User loves fast cars.", reasoning="test", status="active",
                context_scope="Cars", target="Porsche",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.execute(
            insert(Proposition).values(
                text="User hates slow cars.", reasoning="test", status="active",
                context_scope="Cars", target="Bicycle",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.commit()
        
        selected_labels = {
            "selected_context_scopes": ["Cars"],
            "selected_event_types": [],
            "selected_targets": ["Porsche"],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(session, "cars", selected_labels=selected_labels)
        assert len(results) == 2
        assert results[0][0].target == "Porsche"
        assert results[1][0].target == "Bicycle"

@pytest.mark.asyncio
async def test_stitch_filter_no_match_strict(temp_gum_with_fts):
    async with temp_gum_with_fts() as session:
        await session.execute(
            insert(Proposition).values(
                text="User likes dogs.", reasoning="test", status="active",
                context_scope="Pets", target="Dog",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.commit()
        
        selected_labels = {
            "selected_context_scopes": ["中國古典文學"],
            "selected_event_types": [],
            "selected_targets": [],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(session, "dogs", selected_labels=selected_labels)
        assert len(results) == 0

@pytest.mark.asyncio
async def test_stitch_filter_no_labels_selected(temp_gum_with_fts):
    async with temp_gum_with_fts() as session:
        await session.execute(
            insert(Proposition).values(
                text="Random memory.", reasoning="test", status="active",
                context_scope="Random",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.commit()
        
        selected_labels = {
            "selected_context_scopes": [],
            "selected_event_types": [],
            "selected_targets": [],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(session, "memory", selected_labels=selected_labels)
        assert len(results) == 1
        assert "Random memory" in results[0][0].text

@pytest.mark.asyncio
async def test_stitch_backward_compat_legacy_memory(temp_gum_with_fts):
    async with temp_gum_with_fts() as session:
        await session.execute(
            insert(Proposition).values(
                text="Legacy note without labels.", reasoning="test", status="active",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.commit()
        
        empty_selected_labels = {
            "selected_context_scopes": [],
            "selected_event_types": [],
            "selected_targets": [],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(session, "Legacy", selected_labels=empty_selected_labels)
        assert len(results) == 1
        assert "Legacy note" in results[0][0].text

@pytest.mark.asyncio
async def test_stitch_score_boost_proportional(temp_gum_with_fts):
    async with temp_gum_with_fts() as session:
        await session.execute(
            insert(Proposition).values(
                text="Memory 1.", reasoning="test", status="active",
                context_scope="Math", target="Algebra",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.execute(
            insert(Proposition).values(
                text="Memory 2.", reasoning="test", status="active",
                context_scope="Math",
                created_at=datetime.now(timezone.utc), revision_group="default"
            )
        )
        await session.commit()
        
        selected_labels = {
            "selected_context_scopes": ["Math"],
            "selected_event_types": [],
            "selected_targets": ["Algebra"],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(session, "Memory", selected_labels=selected_labels, enable_mmr=False)
        assert len(results) == 2
        assert "Memory 1" in results[0][0].text
        assert "Memory 2" in results[1][0].text
