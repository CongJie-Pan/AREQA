import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from gum.gum import gum
from gum.models import Observation, Proposition
from sqlalchemy import select

@pytest.mark.asyncio
async def test_process_batch_avoids_stale_data_error(tmp_path):
    """
    Regression test for StaleDataError when updating propositions with FTS5 triggers.
    Ensures that _attach_obs_if_missing uses raw update() instead of ORM modification.
    """
    # Setup GUM instance with temp db
    test_db = tmp_path / "test_gum.db"
    g = gum(
        user_name="test_user",
        model="gpt-4",
        db_name=str(test_db),
        data_directory=str(tmp_path)
    )
    
    await g.connect_db()
    
    # Create some mock observations
    batch = [
        {"observer_name": "test", "content": "obs1", "content_type": "text"},
        {"observer_name": "test", "content": "obs2", "content_type": "text"}
    ]
    
    # Mock LLM to return IDENTICAL relations
    mock_llm_response = AsyncMock()
    mock_message = AsyncMock()
    mock_message.content = '{"relations": [{"source": 1, "target": [2], "label": "IDENTICAL"}]}'
    mock_choice = AsyncMock()
    mock_choice.message = mock_message
    mock_llm_response.choices = [mock_choice]
    
    # Mock the drafts construction to return something
    async def mock_construct(*args, **kwargs):
        return [
            {"proposition": "User is active", "reasoning": "R1", "confidence": 100},
            {"proposition": "User is active", "reasoning": "R2", "confidence": 100}
        ]
        
    g._construct_propositions = mock_construct
    g.client.chat.completions.create = AsyncMock(return_value=mock_llm_response)
    
    # This will trigger _process_batch -> _handle_identical -> _attach_obs_if_missing
    # If the StaleDataError bug exists, this will raise an exception during the flush in _handle_similar.
    await g._process_batch(batch)
    
    # Verify that the propositions were saved and updated
    async with g._session() as session:
        props = (await session.execute(select(Proposition))).scalars().all()
        assert len(props) > 0

