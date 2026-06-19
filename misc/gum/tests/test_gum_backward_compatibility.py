import pytest
import asyncio
import json
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from gum.models import Base, Proposition, create_fts_table
from gum.db_utils import search_propositions_bm25

def test_legacy_memory_backward_compatibility():
    async def run_test():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(create_fts_table)
            
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        
        async with SessionLocal() as session:
            props = [
                # A legacy memory without STITCH labels (NULL values)
                Proposition(
                    text="User loves to program in Python.",
                    reasoning="Explicit preference.",
                    status="active",
                    revision_group="g1",
                    version=1
                    # context_scope, event_types, target, functional_type_seeds are None
                )
            ]
            session.add_all(props)
            await session.commit()
            
        # Search for Python without matching any labels
        selected_labels = {
            "selected_context_scopes": ["Cooking"],
            "selected_event_types": ["Recipe Request"],
            "selected_targets": ["Cake"],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(
            SessionLocal(),
            user_query="Python programming",
            selected_labels=selected_labels,
            limit=5,
            include_observations=False,
            enable_mmr=False
        )
        
        # The legacy memory should STILL be returned purely via BM25 score
        assert len(results) > 0
        top_prop = results[0][0]
        assert top_prop.text == "User loves to program in Python."
        
        await engine.dispose()
        
    asyncio.run(run_test())
