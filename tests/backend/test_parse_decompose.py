import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.main import parse_and_decompose_query

@pytest.mark.asyncio
async def test_parse_and_decompose_query_success():
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock()
    
    # Setup mock response simulating an LLM decomposition with JSON
    mock_chunk = MagicMock()
    mock_chunk.message.content = '''[
        {"query": "王熙鳳 治家策略", "type": "abstract_concept"},
        {"query": "賈探春 治家策略", "type": "abstract_concept"}
    ]'''
    mock_response = MagicMock()
    mock_response.choices = [mock_chunk]
    
    mock_client.chat.completions.create.return_value = mock_response
    
    original_query = "請問王熙鳳與賈探春的治家策略最適當的是？"
    
    # Inject mocked settings into backend.main
    import backend.main
    backend.main.settings = MagicMock(model_policy_classifier="mocked_model")
    
    queries = await parse_and_decompose_query(original_query, mock_client)
    
    # Check that LLM parsing succeeded and extracted exact keywords and types
    assert len(queries) == 2
    assert queries[0]["query"] == "王熙鳳 治家策略"
    assert queries[0]["type"] == "abstract_concept"
    assert queries[1]["query"] == "賈探春 治家策略"
    assert queries[1]["type"] == "abstract_concept"
    
@pytest.mark.asyncio
async def test_parse_and_decompose_query_error_fallback():
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
    
    original_query = "王熙鳳與賈探春的治家策略"
    queries = await parse_and_decompose_query(original_query, mock_client)
    
    # Should fallback to original query with abstract_concept type
    assert len(queries) == 1
    assert queries[0]["query"] == original_query
    assert queries[0]["type"] == "abstract_concept"

@pytest.mark.asyncio
async def test_parse_and_decompose_query_empty_response():
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock()
    
    # Setup mock response simulating an empty LLM response
    mock_chunk = MagicMock()
    mock_chunk.message.content = ""
    mock_response = MagicMock()
    mock_response.choices = [mock_chunk]
    
    mock_client.chat.completions.create.return_value = mock_response
    
    original_query = "王熙鳳與賈探春的治家策略"
    queries = await parse_and_decompose_query(original_query, mock_client)
    
    # Should fallback to original query with abstract_concept type
    assert len(queries) == 1
    assert queries[0]["query"] == original_query
    assert queries[0]["type"] == "abstract_concept"
