import pytest
from httpx import AsyncClient, ASGITransport
import json
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Import the FastAPI app
from backend.main import app

class MockRagChunk:
    def __init__(self, text, score, chunk_id):
        self.text = text
        self.score = score
        self.chunk_id = chunk_id
        self.source = "test_source"

class MockRagResults:
    def __init__(self):
        self.final_results = [
            MockRagChunk("Document content here", 0.95, "test_doc_01")
        ]
        self.highest_score = 0.95

@pytest.mark.asyncio
async def test_sse_streaming_sequence_with_rag():
    # Scenario 1: SSE Streaming sequence with RAG events
    
    def mock_retrieve_with_events(query):
        # Synchronous generator as in the original code
        yield {"type": "status", "status": "searching_dense", "message": "📖 翻閱古籍索引..."}
        yield {"type": "status", "status": "reranking", "message": "⚖️ 比較段落關聯性..."}
        yield {"type": "results", "data": MockRagResults()}
    
    # We patch the rag_service, router_service and suggestion_service instances in the main app
    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service') as mock_suggestion, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'):
        
        mock_rag.retrieve_with_events.side_effect = mock_retrieve_with_events
        mock_rag.score_threshold = 0.3
        
        # Mock Router to ALLOW
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        # Mock Suggestions
        mock_suggestion.generate_suggestions = AsyncMock(return_value=["延伸問題1", "延伸問題2", "延伸問題3"])
        
        # We also need to patch AsyncOpenAI so it doesn't try to call HF endpoint
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.completions = MagicMock()
            mock_client.completions.create = AsyncMock()

            # Setup fake streaming completion
            class FakeAsyncIterator:
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    raise StopAsyncIteration

            mock_client.completions.create.return_value = FakeAsyncIterator()

            # Mock models.list to return a dummy model
            mock_client.models.list = MagicMock()
            mock_client.models.list.return_value = asyncio.Future()
            mock_client.models.list.return_value.set_result(MagicMock(data=[MagicMock(id="test-model")]))
            
            mock_openai.return_value = mock_client
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "賈寶玉是誰？"}],
                    "use_rag": True
                }
                response = await ac.post("/api/v1/stream", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # Check for the sequence of SSE events
                assert "event: metadata" in content
                assert "event: status" in content
                assert "📖 翻閱古籍索引..." in content
                assert "⚖️ 比較段落關聯性..." in content
                assert "event: sources" in content
                assert "test_source" in content
                assert "event: suggestions" in content
                assert "延伸問題1" in content
                assert "data: [DONE]" in content

@pytest.mark.asyncio
async def test_gatekeeper_rejection():
    # Test that the Gatekeeper correctly rejects OOD queries in the stream endpoint
    with patch('backend.main.router_service') as mock_router:
        refusal_msg = "這是數學領域的問題呢..."
        mock_router.check_query_intent = AsyncMock(return_value={
            "action": "DENY", 
            "domain": "數學", 
            "refusal_message": refusal_msg
        })
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            req_data = {
                "messages": [{"role": "user", "content": "1+1等於多少？"}],
                "use_rag": False
            }
            response = await ac.post("/api/v1/stream", json=req_data)
            
            assert response.status_code == 200
            content = response.text
            
            # Check that the refusal message is in the content
            assert refusal_msg in content
            
            # Now we yield a 'routing' status immediately, so we should see event: status
            assert "event: status" in content
            assert '"status": "routing"' in content
            assert '"status": "refused"' in content
            
            # Ensure no Metadata events were sent after rejection
            assert "event: metadata" not in content
            assert "data: [DONE]" in content
