import pytest
from httpx import AsyncClient, ASGITransport
import json
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

import respx
from backend.main import app, get_current_user, get_optional_current_user


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: "default_user"
    app.dependency_overrides[get_optional_current_user] = lambda: "default_user"
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_optional_current_user, None)


@pytest.fixture(autouse=True)
def isolate_stream_memory_dependencies():
    with patch(
        "backend.services.orchestration_service.MemoryQueryTool.execute",
        new_callable=AsyncMock,
        return_value=MagicMock(content={"cold": "", "working": ""}),
    ), patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ):
        yield

@pytest.mark.asyncio
@respx.mock
async def test_sse_streaming_sequence_with_web_search():
    # We patch the rag_service, router_service and suggestion_service instances
    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service') as mock_suggestion, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'), \
         patch.dict('os.environ', {
             "WEB_SEARCH_PROVIDER": "perplexity",
             "PERPLEXITY_API_KEY": "dummy_api_key",
         }):
        
        # Mock Router to ALLOW (though intent routing is disabled by default in actual execution, it's safe to mock)
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        # Mock Suggestion Service
        mock_suggestion.generate_suggestions = AsyncMock(return_value=[])

        # Mock the Perplexity API response
        mock_response = {
            "results": [
                {
                    "title": "Title 1",
                    "url": "https://example.com/source1",
                    "snippet": "Snippet 1"
                },
                {
                    "title": "Title 2",
                    "url": "https://example.com/source2",
                    "snippet": "Snippet 2"
                }
            ]
        }
        respx.post("https://api.perplexity.ai/search").respond(
            status_code=200, json=mock_response
        )
        
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            
            class MockChoice:
                def __init__(self, content):
                    self.delta = MagicMock()
                    self.delta.content = content
                    self.delta.tool_calls = None
                    self.delta.reasoning = None
                    self.delta.reasoning_details = None

            class MockChunk:
                def __init__(self, content):
                    self.choices = [MockChoice(content)]

            class FakeAsyncIterator:
                def __init__(self, chunks):
                    self.chunks = chunks
                    self.index = 0
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    if self.index >= len(self.chunks):
                        raise StopAsyncIteration
                    chunk = self.chunks[self.index]
                    self.index += 1
                    return MockChunk(chunk)

            async def mock_create(*args, **kwargs):
                return FakeAsyncIterator(["這", "是", "測", "試"])
            mock_client.chat.completions.create = mock_create
            mock_openai.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/stream",
                    json={
                        "messages": [{"role": "user", "content": "測試問題"}],
                        "use_rag": False,
                        "use_web_search": True,
                        "force_think": False
                    }
                )
                
                assert response.status_code == 200
                assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
                
                content = b""
                async for chunk in response.aiter_bytes():
                    content += chunk
                    
                text_content = content.decode("utf-8")
                
                # Check for the web search status events
                assert "🌐 網路檢索中..." in text_content
                assert "⚡ 篩選與統整網路資訊..." in text_content
                
                # Check for the RAG bypass - shouldn't have RAG status
                assert "📖 翻閱古籍索引..." not in text_content
                
                # Check for sources
                assert "event: sources" in text_content
                assert "https://example.com/source1" in text_content
                
                # Check for the actual LLM output chunks
                assert "這" in text_content
                assert "是" in text_content
                assert "測" in text_content
                assert "試" in text_content


@pytest.mark.asyncio
@respx.mock
async def test_sse_streaming_sequence_with_explicit_tavily_web_search():
    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service') as mock_suggestion, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'), \
         patch.dict('os.environ', {
             "WEB_SEARCH_PROVIDER": "tavily",
             "TAVILY_API_KEY": "dummy_api_key",
             "TAVILY_WEB_SEARCH_DEPTH": "basic",
             "WEB_SEARCH_MAX_RESULTS": "3",
             "WEB_SEARCH_CONTEXT_SIZE": "medium",
             "ENABLE_WEB_QUERY_REWRITE": "",
             "REDIS_URL": "redis://localhost:0",
         }):
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        mock_suggestion.generate_suggestions = AsyncMock(return_value=[])

        search_route = respx.post("https://api.tavily.com/search").respond(
            status_code=200,
            json={
                "query": "測試最新資料",
                "results": [
                    {
                        "title": "Tavily Result",
                        "url": "https://example.com/tavily-result",
                        "content": "Tavily source excerpt",
                        "score": 0.93,
                    }
                ],
            },
        )

        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()

            class MockChoice:
                def __init__(self, content):
                    self.delta = MagicMock()
                    self.delta.content = content
                    self.delta.tool_calls = None
                    self.delta.reasoning = None
                    self.delta.reasoning_details = None

            class MockChunk:
                def __init__(self, content):
                    self.choices = [MockChoice(content)]

            class FakeAsyncIterator:
                def __init__(self, chunks):
                    self.chunks = chunks
                    self.index = 0
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    if self.index >= len(self.chunks):
                        raise StopAsyncIteration
                    chunk = self.chunks[self.index]
                    self.index += 1
                    return MockChunk(chunk)

            async def mock_create(*args, **kwargs):
                return FakeAsyncIterator(["O", "K"])

            mock_client.chat.completions.create = mock_create
            mock_openai.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/stream",
                    json={
                        "messages": [{"role": "user", "content": "測試最新資料"}],
                        "use_rag": False,
                        "use_web_search": True,
                        "search_mode": "always",
                        "force_think": False,
                    },
                )

        assert response.status_code == 200
        text_content = response.text
        request_payload = json.loads(search_route.calls.last.request.content)
        assert request_payload["query"] == "測試最新資料"
        assert request_payload["search_depth"] == "basic"
        assert request_payload["max_results"] == 3
        assert "🌐 網路檢索中..." in text_content
        assert "已取得 1 筆網路文獻" in text_content
        assert "event: sources" in text_content
        assert "https://example.com/tavily-result" in text_content
        assert "Tavily source excerpt" in text_content
        assert "OK" in text_content
        assert text_content.count("data: [DONE]") == 1


@pytest.mark.asyncio
@respx.mock
async def test_sse_streaming_sequence_with_explicit_openrouter_web_search():
    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service') as mock_suggestion, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'), \
         patch.dict('os.environ', {
             "WEB_SEARCH_PROVIDER": "openrouter",
             "OPENROUTER_API_KEY": "dummy_api_key",
             "MODEL_WEB_SEARCH": "google/gemini-3.8-flash",
             "OPENROUTER_WEB_SEARCH_MAX_TOOL_CALLS": "2",
             "WEB_SEARCH_MAX_RESULTS": "3",
             "WEB_SEARCH_CONTEXT_SIZE": "medium",
             "ENABLE_WEB_QUERY_REWRITE": "",
             "REDIS_URL": "redis://localhost:0",
         }):
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        mock_suggestion.generate_suggestions = AsyncMock(return_value=[])

        search_route = respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Search summary.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url_citation": {
                                        "title": "OpenRouter Result",
                                        "url": "https://example.com/openrouter-result",
                                        "content": "Citation excerpt",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()

            class MockChoice:
                def __init__(self, content):
                    self.delta = MagicMock()
                    self.delta.content = content
                    self.delta.tool_calls = None
                    self.delta.reasoning = None
                    self.delta.reasoning_details = None

            class MockChunk:
                def __init__(self, content):
                    self.choices = [MockChoice(content)]

            class FakeAsyncIterator:
                def __init__(self, chunks):
                    self.chunks = chunks
                    self.index = 0
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    if self.index >= len(self.chunks):
                        raise StopAsyncIteration
                    chunk = self.chunks[self.index]
                    self.index += 1
                    return MockChunk(chunk)

            async def mock_create(*args, **kwargs):
                return FakeAsyncIterator(["O", "K"])

            mock_client.chat.completions.create = mock_create
            mock_openai.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/stream",
                    json={
                        "messages": [{"role": "user", "content": "測試最新資料"}],
                        "use_rag": False,
                        "use_web_search": True,
                        "search_mode": "always",
                        "force_think": False,
                    },
                )

        assert response.status_code == 200
        text_content = response.text
        request_payload = json.loads(search_route.calls.last.request.content)
        assert request_payload["model"] == "google/gemini-3.8-flash"
        assert request_payload["stream"] is False
        assert request_payload["tools"][0]["type"] == "openrouter:web_search"
        assert request_payload["tools"][0]["parameters"]["engine"] == "exa"
        assert request_payload["tools"][0]["parameters"]["search_context_size"] == "medium"
        assert "🌐 網路檢索中..." in text_content
        assert "已取得 1 筆網路文獻" in text_content
        assert "event: sources" in text_content
        assert "https://example.com/openrouter-result" in text_content
        assert "Citation excerpt" in text_content
        assert "OK" in text_content
        assert text_content.count("data: [DONE]") == 1

@pytest.mark.asyncio
async def test_sse_streaming_sequence_with_rag_bypasses_web_search():
    # We patch the rag_service to ensure it is called instead of web search
    class MockRagChunk:
        def __init__(self, text, score, chunk_id):
            self.text = text
            self.score = score
            self.chunk_id = chunk_id
            self.source = "test_source"

    class MockRagResults:
        def __init__(self):
            self.final_results = [MockRagChunk("Doc", 0.95, "doc1")]
            self.highest_score = 0.95

    def mock_retrieve_with_events(query):
        yield {"type": "status", "status": "searching_dense", "message": "📖 翻閱古籍索引..."}
        yield {"type": "results", "data": MockRagResults()}

    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service') as mock_suggestion, \
         patch('backend.services.orchestration_service.parse_and_decompose_query', new_callable=AsyncMock) as mock_expand, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.services.orchestration_service.OrchestrationService._node_perplexity_search') as mock_perplexity, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'):
        
        mock_expand.return_value = ["測試問題"]
        mock_rag.retrieve_with_events.side_effect = mock_retrieve_with_events
        mock_rag.score_threshold = 0.3
        
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        mock_suggestion.generate_suggestions = AsyncMock(return_value=[])
        
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            
            class MockChoice:
                def __init__(self, content):
                    self.delta = MagicMock()
                    self.delta.content = content
                    self.delta.tool_calls = None
                    self.delta.reasoning = None
                    self.delta.reasoning_details = None

            class MockChunk:
                def __init__(self, content):
                    self.choices = [MockChoice(content)]

            class FakeAsyncIterator:
                def __init__(self, chunks):
                    self.chunks = chunks
                    self.index = 0
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    if self.index >= len(self.chunks):
                        raise StopAsyncIteration
                    chunk = self.chunks[self.index]
                    self.index += 1
                    return MockChunk(chunk)

            mock_client.chat.completions.create.return_value = FakeAsyncIterator(["R", "A", "G"])
            mock_openai.return_value = mock_client

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/stream",
                    json={
                        "messages": [{"role": "user", "content": "測試問題"}],
                        "use_rag": True,
                        "use_web_search": False,
                        "force_think": False
                    }
                )
                
                assert response.status_code == 200
                content = b"".join([chunk async for chunk in response.aiter_bytes()]).decode("utf-8")
                
                # Should have RAG status
                assert "📖 翻閱古籍索引..." in content
                
                # Should NOT call perplexity node
                mock_perplexity.assert_not_called()
                assert "🌐 網路檢索中..." not in content
