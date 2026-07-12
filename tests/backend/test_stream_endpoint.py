import pytest
from httpx import AsyncClient, ASGITransport
import json
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Import the FastAPI app
from backend.main import app, get_current_user


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: "default_user"
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def isolate_stream_memory_dependencies():
    """Stream contract tests must not reuse event-loop-bound global clients."""
    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ), patch("memory_store.get_global_store", return_value=None):
        yield

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
         patch('backend.services.orchestration_service.parse_and_decompose_query', new_callable=AsyncMock) as mock_expand, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'):
        
        mock_expand.return_value = ["賈寶玉是誰？"]
        mock_rag.retrieve_with_events.side_effect = mock_retrieve_with_events
        mock_rag.score_threshold = 0.3
        
        # Mock Router to ALLOW
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        # Mock Suggestions
        mock_suggestion.generate_suggestions = AsyncMock(return_value=["延伸問題1", "延伸問題2", "延伸問題3"])
        
        # We also need to patch AsyncOpenAI so it doesn't try to call HF endpoint
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock()

            # Setup fake streaming completion
            class FakeAsyncIterator:
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    raise StopAsyncIteration

            mock_client.chat.completions.create.return_value = FakeAsyncIterator()
            
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
@pytest.mark.skip(reason="Router feature bypassed by user request")
async def test_gatekeeper_rejection():
    # Test that the Gatekeeper correctly rejects OOD queries in the stream endpoint
    with patch('backend.main.router_service') as mock_router, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval:
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

@pytest.mark.asyncio
async def test_force_think_strips_think_tags_with_spaces():
    # Scenario: The streaming endpoint correctly strips <think> tags even with spaces
    # and doesn't inject pre-filled assistant message for native reasoning models.
    with patch('backend.main.rag_service', None), \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service', None), \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch.dict('os.environ', {'OPENROUTER_API_KEY': 'mock-token'}):
        
        mock_policy.return_value = "NORMAL"
        
        # Mock Router to ALLOW
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock()

            class FakeAsyncIterator:
                def __aiter__(self):
                    self.yielded = False
                    return self
                async def __anext__(self):
                    if not self.yielded:
                        self.yielded = True
                        chunk = MagicMock()
                        chunk.choices = [MagicMock()]
                        chunk.choices[0].delta = MagicMock()
                        chunk.choices[0].delta.content = "這裡有< think >被包含的思考文字< /think >還有正式文字"
                        chunk.choices[0].delta.tool_calls = None
                        chunk.choices[0].delta.reasoning = None
                        chunk.choices[0].delta.reasoning_details = None
                        return chunk
                    raise StopAsyncIteration

            mock_client.chat.completions.create.return_value = FakeAsyncIterator()
            mock_openai.return_value = mock_client
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "測試一下"}],
                    "use_rag": False,
                    "force_think": True
                }
                response = await ac.post("/api/v1/stream", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # 目前串流格式保留原始 chunk 內容，至少要能收到模型輸出
                assert "這裡有" in content
                assert "被包含的思考文字" not in content
                assert "還有正式文字" in content
                
                # 確保 backend 不再對 force_think 進行 assistant role 預填
                call_kwargs = mock_client.chat.completions.create.call_args.kwargs
                messages = call_kwargs['messages']
                has_prefill = any(msg.get("role") == "assistant" for msg in messages)
                assert not has_prefill

@pytest.mark.asyncio
async def test_rag_score_threshold_refusal():
    # Test that the system refuses to answer when RAG highest_score is below effective_threshold
    class LowScoreMockRagResults:
        def __init__(self):
            # is_reranked will be False, so effective_threshold is 0.005
            self.final_results = [
                MockRagChunk("Irrelevant document", 0.001, "test_doc_02")
            ]
            self.highest_score = 0.001

    def mock_retrieve_with_events(query):
        yield {"type": "results", "data": LowScoreMockRagResults()}

    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service', None), \
         patch('backend.services.orchestration_service.parse_and_decompose_query', new_callable=AsyncMock) as mock_expand, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'):
        
        mock_expand.return_value = [{"query": "無關", "type": "abstract_concept"}]
        mock_policy.return_value = "NORMAL"
        mock_rag.retrieve_with_events.side_effect = mock_retrieve_with_events
        mock_rag.score_threshold = 0.0
        
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        # We don't even need to mock OpenAI because it shouldn't be called for generation!
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "無關緊要的問題"}],
                    "use_rag": True
                }
                response = await ac.post("/api/v1/stream", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # Check that it returned the exact RAG refusal message
                assert "AREQA查閱了相關文獻，暫時沒能找到與您問題直接相關的內容" in content
                
                # OpenAI generation (stream) should NOT be called
                for call in mock_openai.return_value.chat.completions.create.call_args_list:
                    assert not call.kwargs.get('stream', False)
