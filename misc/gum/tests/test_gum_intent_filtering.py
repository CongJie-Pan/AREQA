import pytest
import asyncio
import json
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from gum.models import Base, Proposition, create_fts_table
from gum.db_utils import search_propositions_bm25

async def setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(create_fts_table)
        
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    
    async with SessionLocal() as session:
        props = [
            Proposition(
                text="User is learning about Python list comprehensions.",
                reasoning="Explicitly asked a question about it.",
                context_scope="Python Programming",
                event_types=json.dumps(["Questioning", "Learning"]),
                target="list comprehensions",
                functional_type_seeds=json.dumps(["Syntax Help"]),
                status="active",
                revision_group="g1",
                version=1
            ),
            Proposition(
                text="User asked about Napoleon's battle strategies.",
                reasoning="Questioned history details.",
                context_scope="History",
                event_types=json.dumps(["Questioning"]),
                target="Napoleon",
                functional_type_seeds=json.dumps(["Factual Query"]),
                status="active",
                revision_group="g2",
                version=1
            ),
            Proposition(
                text="User likes to code in Python.",
                reasoning="Mentioned it.",
                context_scope="Python Programming",
                event_types=json.dumps(["Statement"]),
                target="Python",
                functional_type_seeds=json.dumps(["Preference"]),
                status="active",
                revision_group="g3",
                version=1
            )
        ]
        session.add_all(props)
        await session.commit()
        
    return engine, SessionLocal()

def test_intent_filtering_matches():
    async def run_test():
        engine, async_session = await setup_db()
        selected_labels = {
            "selected_context_scopes": ["Python Programming"],
            "selected_event_types": ["Learning"],
            "selected_targets": ["list comprehensions"],
            "selected_functional_type_seeds": ["Syntax Help"]
        }
        
        results = await search_propositions_bm25(
            async_session,
            user_query="python list",
            selected_labels=selected_labels,
            limit=5,
            include_observations=False,
            enable_mmr=False
        )
        
        assert len(results) > 0
        top_prop = results[0][0]
        # It should boost the proposition with the most matches (density 4)
        assert top_prop.target == "list comprehensions"
        assert top_prop.context_scope == "Python Programming"
        
        await engine.dispose()
        
    asyncio.run(run_test())

def test_intent_filtering_no_matches():
    async def run_test():
        engine, async_session = await setup_db()
        selected_labels = {
            "selected_context_scopes": ["Cooking"],
            "selected_event_types": ["Recipe Request"],
            "selected_targets": ["Cake"],
            "selected_functional_type_seeds": []
        }
        
        results = await search_propositions_bm25(
            async_session,
            user_query="python",
            selected_labels=selected_labels,
            limit=5,
            include_observations=False,
            enable_mmr=False
        )
        
        # Should return empty since num_matches == 0 for all existing props
        assert len(results) == 0
        
        await engine.dispose()
        
    asyncio.run(run_test())
