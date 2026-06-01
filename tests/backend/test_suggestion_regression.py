import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
import asyncio

from backend.main import app
from src.main.python.services.suggestion_service import SuggestionService

@pytest.mark.asyncio
async def test_suggestion_service_model_name():
    # Verify the model ID fix (qwen/qwen-2.5-7b-instruct)
    service = SuggestionService(api_key="test_key")
    assert service.model == "qwen/qwen-2.5-7b-instruct", "Model ID should be corrected from qwen/qwen2.5-7b-instruct to qwen/qwen-2.5-7b-instruct"

@pytest.mark.asyncio
async def test_stream_endpoint_emits_suggestions_and_done():
    # Verify backend/main.py correctly bundles suggestions into event: done
    
    with patch('backend.main.rag_service', None), \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service') as mock_suggestion, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'):
        
        # Mock router to ALLOW
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW"})
        
        # Mock suggestions to return a specific list
        mock_suggestions_list = ["問題A？", "問題B？", "問題C？"]
        mock_suggestion.generate_suggestions = AsyncMock(return_value=mock_suggestions_list)
        
        # Patch AsyncOpenAI for the main text generation
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.completions = MagicMock()
            mock_client.completions.create = AsyncMock()

            # Generate dummy text chunk
            class FakeAsyncIterator:
                def __init__(self):
                    self.yielded = False
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    if not self.yielded:
                        self.yielded = True
                        chunk = MagicMock()
                        chunk.choices = [MagicMock(text="這是一個回答")]
                        return chunk
                    raise StopAsyncIteration

            mock_client.completions.create.return_value = FakeAsyncIterator()

            # Mock models.list
            mock_client.models.list = MagicMock()
            future = asyncio.Future()
            future.set_result(MagicMock(data=[MagicMock(id="test-model")]))
            mock_client.models.list.return_value = future
            
            mock_openai.return_value = mock_client
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "測試問題"}],
                    "use_rag": False
                }
                response = await ac.post("/api/v1/stream", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # Assertions
                assert "event: suggestions" in content
                assert json.dumps(mock_suggestions_list, ensure_ascii=False) in content
                
                # Check for event: done bundling the suggestions
                expected_done_data = json.dumps({"suggestions": mock_suggestions_list}, ensure_ascii=False)
                assert f"event: done\ndata: {expected_done_data}\n\n" in content
                
                # Check that it ends with data: [DONE]
                assert "data: [DONE]\n\n" in content
