import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from backend.gum_integration import (
    init_gum_instance,
    stop_gum_instance,
    push_observation,
    get_all_memory,
    get_suggestions,
    TextObserver,
)
import backend.gum_integration

# STITCH imports
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import insert, select
from gum.models import Base, Proposition, create_fts_table, create_observations_fts
from gum.gum import gum

# Mock proposition class
class MockProposition:
    def __init__(self, id, text, confidence, context_scope=None, event_types=None, target=None, functional_type_seeds=None):
        self.id = id
        self.text = text
        self.confidence = confidence
        self.updated_at = datetime.now()
        self.context_scope = context_scope
        self.event_types = event_types
        self.target = target
        self.functional_type_seeds = functional_type_seeds

@pytest.fixture
def mock_gum_instance():
    instance = MagicMock()
    instance.recent = AsyncMock(return_value=[
        MockProposition(1, "test user likes apples", 0.9, context_scope="Fruit", event_types='["like"]', target="apple", functional_type_seeds='["food"]'),
        MockProposition(2, "test user hates oranges", 0.8),
    ])
    
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"suggestions": ["test suggestion 1", "test suggestion 2"]}'))
    ]
    instance.client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    instance.connect_db = AsyncMock()
    instance.start_update_loop = MagicMock()
    instance.stop_update_loop = AsyncMock()
    
    instance.batcher = MagicMock()
    instance.batcher.start = AsyncMock()
    instance.batcher.stop = AsyncMock()
    return instance

@pytest.mark.asyncio
async def test_init_and_stop_gum_instance():
    with patch("backend.gum_integration.gum") as mock_gum, \
         patch("backend.gum_integration.asyncio.create_task") as mock_create_task:
        mock_instance = MagicMock()
        mock_instance.connect_db = AsyncMock()
        mock_instance.stop_update_loop = AsyncMock()
        mock_instance.batcher.start = AsyncMock()
        mock_instance.batcher.stop = AsyncMock()
        mock_gum.return_value = mock_instance
        
        mock_task = asyncio.Future()
        mock_task.set_result(None)
        mock_task.cancel = MagicMock()
        mock_create_task.return_value = mock_task
        
        instance = await init_gum_instance()
        
        assert instance is mock_instance
        mock_instance.connect_db.assert_called_once()
        mock_instance.start_update_loop.assert_called_once()
        assert mock_create_task.call_count >= 1
        
        await stop_gum_instance()
        mock_instance.stop_update_loop.assert_called_once()
        assert mock_task.cancel.call_count >= 1

@pytest.mark.asyncio
async def test_push_observation():
    # Test pushing when gum_instance is None
    backend.gum_integration.gum_instance = None
    backend.gum_integration.obs_worker = None
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("test observation text")
        # Since gum_instance is None, it should return early and NOT call push_text
        mock_text_observer.push_text.assert_not_called()
        
    # Test pushing when gum_instance is present but no neighbors
    mock_gum = MagicMock()
    mock_gum.query = AsyncMock(return_value=[])
    backend.gum_integration.gum_instance = mock_gum
    
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("test observation text")
        mock_gum.query.assert_called_once_with("test observation text", limit=20)
        mock_text_observer.push_text.assert_called_once_with("test observation text")
        
@pytest.mark.asyncio
async def test_get_all_memory_with_stitch_tags(mock_gum_instance):
    backend.gum_integration.gum_instance = mock_gum_instance
    memories = await get_all_memory()
    
    assert len(memories) == 2
    
    # Check the first memory with STITCH tags
    m1 = memories[0]
    assert m1["id"] == 1
    assert m1["text"] == "test user likes apples"
    assert m1["context_scope"] == "Fruit"
    assert m1["event_types"] == ["like"]
    assert m1["target"] == "apple"
    assert m1["functional_type_seeds"] == ["food"]
    
    # Check the second memory without STITCH tags
    m2 = memories[1]
    assert m2["id"] == 2
    assert m2["text"] == "test user hates oranges"
    assert m2["context_scope"] is None
    assert m2["event_types"] == []
    assert m2["target"] is None
    assert m2["functional_type_seeds"] == []
        
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_push_observation_with_evolution():
    # Test pushing when gum_instance is present and has neighbors
    mock_gum = MagicMock()
    mock_gum.query = AsyncMock(return_value=[
        (MockProposition(1, "User hates apples", 0.9), 1.0)
    ])
    
    # Mock the LLM decision to supersede ID 1
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"should_evolve": true, "actions": ["prune"], "target_ids": [1], "importance_score": 8}'))
    ]
    mock_gum.client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_gum.update_status = AsyncMock()
    
    backend.gum_integration.gum_instance = mock_gum
    
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("User loves apples now")
        
        mock_gum.query.assert_called_once_with("User loves apples now", limit=20)
        # Should call LLM for evolution
        mock_gum.client.chat.completions.create.assert_called_once()
        # Should update status of ID 1 to superseded
        mock_gum.update_status.assert_called_once_with(1, "superseded")
        # Should push the new text
        mock_text_observer.push_text.assert_called_once_with("User loves apples now")
        
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_push_observation_with_evolution_no_prune():
    # Test pushing when gum_instance has neighbors but new topic is unrelated
    mock_gum = MagicMock()
    mock_gum.query = AsyncMock(return_value=[
        (MockProposition(1, "User loves apples", 0.9), 1.0)
    ])
    
    # Mock the LLM decision to NOT supersede (different topic)
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"should_evolve": false, "actions": [], "target_ids": [], "importance_score": 4}'))
    ]
    mock_gum.client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_gum.update_status = AsyncMock()
    
    backend.gum_integration.gum_instance = mock_gum
    
    with patch("backend.gum_integration.text_observer") as mock_text_observer:
        mock_text_observer.push_text = AsyncMock()
        await push_observation("User asks about the weather")
        
        mock_gum.query.assert_called_once_with("User asks about the weather", limit=20)
        # Should call LLM for evolution
        mock_gum.client.chat.completions.create.assert_called_once()
        # Should NOT update status since should_evolve is false
        mock_gum.update_status.assert_not_called()
        # Should push the new text
        mock_text_observer.push_text.assert_called_once_with("User asks about the weather")
        
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_get_all_memory(mock_gum_instance):
    backend.gum_integration.gum_instance = mock_gum_instance
    
    memory = await get_all_memory()
    
    assert len(memory) == 2
    assert memory[0]["id"] == 1
    assert memory[0]["text"] == "test user likes apples"
    assert memory[0]["confidence"] == 0.9
    assert "updated_at" in memory[0]
    mock_gum_instance.recent.assert_called_once_with(limit=100)
    
    # cleanup
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_get_suggestions(mock_gum_instance):
    backend.gum_integration.gum_instance = mock_gum_instance
    
    suggestions = await get_suggestions()
    
    assert len(suggestions) == 2
    assert suggestions[0] == "test suggestion 1"
    assert suggestions[1] == "test suggestion 2"
    mock_gum_instance.client.chat.completions.create.assert_called_once()
    
    # cleanup
    backend.gum_integration.gum_instance = None

@pytest.mark.asyncio
async def test_get_all_memory_no_instance():
    backend.gum_integration.gum_instance = None
    memory = await get_all_memory()
    assert memory == []

@pytest.mark.asyncio
async def test_get_suggestions_no_instance():
    backend.gum_integration.gum_instance = None
    suggestions = await get_suggestions()
    assert suggestions == []

# --- STITCH Contextual Intent Filtering Integration Tests ---

@pytest_asyncio.fixture
async def real_gum_instance():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(create_fts_table)
        await conn.run_sync(create_observations_fts)
    
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    # Initialize Gum with this engine
    gum_instance = gum(user_name="test_user", model="test_model")
    gum_instance.engine = engine
    gum_instance.Session = session_maker
    
    yield gum_instance
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.mark.asyncio
async def test_query_with_stitch_intent(real_gum_instance):
    async with real_gum_instance._session() as session:
        await session.execute(
            insert(Proposition).values(
                text="User is learning Python.", reasoning="test", status="active",
                context_scope="Python Programming", target="Python",
                revision_group="test"
            )
        )
        await session.commit()

    with patch.object(real_gum_instance.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({
                "selected_context_scopes": ["Python Programming"],
                "selected_event_types": [],
                "selected_targets": ["Python"],
                "selected_functional_type_seeds": []
            })))]
        )
        
        results = await real_gum_instance.query("tell me about python")
        assert len(results) == 1
        mock_llm.assert_called_once()
        assert results[0][0].context_scope == "Python Programming"

@pytest.mark.asyncio
async def test_query_intent_cache_hit(real_gum_instance):
    async with real_gum_instance._session() as session:
        await session.execute(
            insert(Proposition).values(
                text="User is learning Python.", reasoning="test", status="active",
                context_scope="Python Programming", target="Python",
                revision_group="test"
            )
        )
        await session.commit()

    with patch.object(real_gum_instance.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({
                "selected_context_scopes": ["Python Programming"],
                "selected_event_types": [],
                "selected_targets": ["Python"],
                "selected_functional_type_seeds": []
            })))]
        )
        
        await real_gum_instance.query("tell me about python")
        await real_gum_instance.query("tell me about python") # exactly same query
        
        assert mock_llm.call_count == 1

@pytest.mark.asyncio
async def test_query_intent_cache_miss_on_different_query(real_gum_instance):
    async with real_gum_instance._session() as session:
        await session.execute(
            insert(Proposition).values(
                text="User is learning Python.", reasoning="test", status="active",
                context_scope="Python Programming", target="Python",
                revision_group="test"
            )
        )
        await session.commit()

    with patch.object(real_gum_instance.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps({
                "selected_context_scopes": ["Python Programming"],
                "selected_event_types": [],
                "selected_targets": ["Python"],
                "selected_functional_type_seeds": []
            })))]
        )
        
        await real_gum_instance.query("query 1")
        await real_gum_instance.query("query 2")
        
        assert mock_llm.call_count == 2

@pytest.mark.asyncio
async def test_query_no_labels_in_db_skips_intent(real_gum_instance):
    async with real_gum_instance._session() as session:
        await session.execute(
            insert(Proposition).values(
                text="hello! Just a text without labels.", reasoning="test", status="active",
                revision_group="test"
            )
        )
        await session.commit()

    with patch.object(real_gum_instance.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
        results = await real_gum_instance.query("hello")
        assert len(results) == 1
        mock_llm.assert_not_called()

@pytest.mark.asyncio
async def test_query_stitch_fallback_empty_db(real_gum_instance):
    with patch.object(real_gum_instance.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
        results = await real_gum_instance.query("hello")
        assert len(results) == 0
        mock_llm.assert_not_called()

@pytest.mark.asyncio
async def test_push_observation_stitch_metadata_preserved(real_gum_instance):
    mock_llm_propose = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({
            "propositions": [
                {
                    "proposition": "User is testing STITCH.",
                    "reasoning": "Because they wrote a test.",
                    "context_scope": "Testing",
                    "event_types": ["Validation"],
                    "target": "STITCH",
                    "functional_type_seeds": ["Testing action"],
                    "confidence": 9,
                    "decay": 5
                }
            ]
        })))]
    )
    
    real_gum_instance._filter_propositions = AsyncMock(return_value=([], [], []))
    
    with patch.object(real_gum_instance.client.chat.completions, 'create', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_llm_propose
        
        batch = [{
            "observer_name": "TestObserver",
            "content": "I am writing a test for STITCH",
            "content_type": "input_text"
        }]
        
        await real_gum_instance._process_batch(batch)
        
        async with real_gum_instance._session() as session:
            result = await session.execute(select(Proposition))
            prop = result.scalars().first()
            
            assert prop is not None
            assert prop.text == "User is testing STITCH."
            assert prop.context_scope == "Testing"
            assert prop.target == "STITCH"
            assert "Validation" in prop.event_types
            assert "Testing action" in prop.functional_type_seeds
