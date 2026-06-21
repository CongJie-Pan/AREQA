import pytest
import json
from unittest.mock import AsyncMock, patch
from backend.compaction import generate_stitch_tags

@pytest.fixture
def mock_llm_client():
    client = AsyncMock()
    return client

@pytest.mark.asyncio
async def test_stitch_tagger_classification(mock_llm_client):
    # Setup mock response
    mock_response = {
        "refined_content": "使用者分不清賈寶玉和甄寶玉的性格差異",
        "primary_tags": ["ConceptMastery", "ErrorWeakness"],
        "entities": ["賈寶玉", "甄寶玉"],
        "temporal_context": "2026-06-21 對話"
    }
    mock_llm_client.chat.completions.create.return_value.choices = [
        AsyncMock(message=AsyncMock(content=json.dumps(mock_response)))
    ]
    
    result = await generate_stitch_tags(
        llm_client=mock_llm_client,
        model="test-model",
        memory_content="我常常分不清賈寶玉和甄寶玉的性格差異"
    )
    
    assert "ConceptMastery" in result["primary_tags"]
    assert "ErrorWeakness" in result["primary_tags"]

@pytest.mark.asyncio
async def test_stitch_tagger_format(mock_llm_client):
    mock_response = {
        "refined_content": "測試內容",
        "primary_tags": ["LearningGoal"],
        "entities": [],
        "temporal_context": "測試時間"
    }
    mock_llm_client.chat.completions.create.return_value.choices = [
        AsyncMock(message=AsyncMock(content=json.dumps(mock_response)))
    ]
    
    result = await generate_stitch_tags(
        llm_client=mock_llm_client,
        model="test-model",
        memory_content="測試輸入"
    )
    
    assert "refined_content" in result
    assert "primary_tags" in result
    assert "entities" in result
    assert "temporal_context" in result

@pytest.mark.asyncio
async def test_stitch_tagger_fallback(mock_llm_client):
    # Setup mock to return invalid JSON
    mock_llm_client.chat.completions.create.return_value.choices = [
        AsyncMock(message=AsyncMock(content="Invalid JSON response!"))
    ]
    
    # Should fallback gracefully without crashing
    result = await generate_stitch_tags(
        llm_client=mock_llm_client,
        model="test-model",
        memory_content="導致崩潰的異常內容"
    )
    
    assert result["primary_tags"] == ["GeneralPersonal"]
    assert result["refined_content"] == "導致崩潰的異常內容"
