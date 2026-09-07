import pytest
import json
import asyncio
import httpx
import os
import respx
from unittest.mock import patch
from backend.services.orchestration_service import OrchestrationService
from backend.core import ConversationRunState

@pytest.fixture
def mock_orchestrator():
    # Provide None for the constructor arguments that we don't need for this specific test
    return OrchestrationService(None, None, None, None)

@pytest.mark.asyncio
@respx.mock
async def test_perplexity_search_success(mock_orchestrator):
    import os
    with patch.dict(os.environ, {
        "WEB_SEARCH_PROVIDER": "perplexity",
        "PERPLEXITY_API_KEY": "dummy_api_key",
        "WEB_SEARCH_MAX_RESULTS": "15",
        "WEB_SEARCH_CONTEXT_SIZE": "high",
        "ENABLE_WEB_QUERY_REWRITE": "",
        "REDIS_URL": "redis://localhost:0",
    }):
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
        search_route = respx.post("https://api.perplexity.ai/search").respond(
            status_code=200, json=mock_response
        )

        events = []
        run_state = ConversationRunState()
        async for event in mock_orchestrator._node_perplexity_search("測試問題", "test_conv_id", run_state=run_state):
            events.append(event)

        request_payload = json.loads(search_route.calls.last.request.content)
        assert request_payload["query"] == "測試問題"
        assert request_payload["max_results"] == 15
        assert request_payload["search_context_size"] == "high"
            
        assert len(events) == 7

        # Check status searching_dense
        assert "searching_dense" in events[0]
        assert "網路檢索中" in events[0]

        assert "event: tool_started" in events[1]
        assert "event: tool_completed" in events[2]
        assert "測試問題" not in events[1]

        # Check status reranking
        assert "reranking" in events[3]
        assert "篩選與統整" in events[3]
        
        # Check sources event instead of citations
        assert "event: sources" in events[4]
        sources_payload = json.loads(events[4].split("data: ")[1].strip())
        assert len(sources_payload) == 2 # 2 sources
        assert sources_payload[0]["chunk_id"] == "https://example.com/source1"
        assert sources_payload[0]["url"] == "https://example.com/source1"
        assert sources_payload[0]["snippet"] == "Snippet 1"
        assert sources_payload[0]["score"] == 1.0
        assert sources_payload[1]["chunk_id"] == "https://example.com/source2"

        # Check sources_ready status emitted after structured sources
        assert "sources_ready" in events[5]
        assert "已取得 2 筆網路文獻" in events[5]
        
        # Check results_obj marker
        assert events[6] == "event: results_obj\n\n"
        
        assert "https://example.com/source1" in run_state.context_prompt
        assert "Snippet 1" in run_state.context_prompt


@pytest.mark.asyncio
@respx.mock
async def test_perplexity_search_omits_sources_without_valid_url(mock_orchestrator):
    import os
    with patch.dict(os.environ, {
        "WEB_SEARCH_PROVIDER": "perplexity",
        "PERPLEXITY_API_KEY": "dummy_api_key",
        "ENABLE_WEB_QUERY_REWRITE": "",
        "REDIS_URL": "redis://localhost:0",
    }):
        respx.post("https://api.perplexity.ai/search").respond(
            status_code=200,
            json={
                "results": [
                    {
                        "title": "Missing URL",
                        "url": "",
                        "snippet": "This record must not become a citation.",
                    },
                    {
                        "title": "Valid Source",
                        "url": "https://example.com/valid",
                        "snippet": "Usable source text.",
                    },
                    {
                        "title": "Unsafe URL",
                        "url": "javascript:alert(1)",
                        "snippet": "Unsafe protocol.",
                    },
                ]
            },
        )

        events = []
        run_state = ConversationRunState()
        async for event in mock_orchestrator._node_perplexity_search(
            "測試問題",
            "test_conv_id_malformed",
            run_state=run_state,
        ):
            events.append(event)

        sources_event = next(event for event in events if "event: sources" in event)
        sources_payload = json.loads(sources_event.split("data: ")[1].strip())
        assert sources_payload == [{
            "title": "Valid Source",
            "chunk_id": "https://example.com/valid",
            "url": "https://example.com/valid",
            "snippet": "Usable source text.",
            "score": 1.0,
        }]
        assert "Missing URL" not in run_state.context_prompt
        assert "javascript:alert" not in run_state.context_prompt
        assert "[文獻1] Valid Source" in run_state.context_prompt


@pytest.mark.asyncio
@respx.mock
async def test_perplexity_search_api_failure(mock_orchestrator):
    import os
    with patch.dict(os.environ, {
        "WEB_SEARCH_PROVIDER": "perplexity",
        "PERPLEXITY_API_KEY": "dummy_api_key",
    }):
        # Mock the Perplexity API to return a 500 error
        respx.post("https://api.perplexity.ai/chat/completions").respond(status_code=500)

        events = []
        run_state = ConversationRunState()
        async for event in mock_orchestrator._node_perplexity_search("測試問題", "test_conv_id_fail", run_state=run_state):
            events.append(event)
            
        assert len(events) == 3

        # Check status searching_dense
        assert "searching_dense" in events[0]

        # Check status error fallback
        assert "tool_started" in events[1]
        assert "error" in events[2]
        assert "暫時無法使用" in events[2]
        
        # Check it gracefully fell back
        assert run_state.context_prompt == ""


@pytest.mark.asyncio
async def test_perplexity_search_no_api_key(mock_orchestrator):
    import os
    with patch.dict(os.environ, {
        "WEB_SEARCH_PROVIDER": "perplexity",
        "PERPLEXITY_API_KEY": "",
    }):
        events = []
        run_state = ConversationRunState()
        async for event in mock_orchestrator._node_perplexity_search("測試問題", "test_conv_id_no_key", run_state=run_state):
            events.append(event)
            
        assert len(events) == 2

        # Check status searching_dense
        assert "searching_dense" in events[0]

        # Check status error fallback due to missing key
        assert "error" in events[1]
        assert "未設定網路搜尋服務金鑰" in events[1]
        
        # Check it gracefully fell back
        assert run_state.context_prompt == ""


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_web_search_success_with_url_citations(mock_orchestrator):
    with patch.dict(os.environ, {
        "WEB_SEARCH_PROVIDER": "openrouter",
        "OPENROUTER_API_KEY": "dummy_api_key",
        "MODEL_WEB_SEARCH": "google/gemini-3.8-flash",
        "OPENROUTER_WEB_SEARCH_ENGINE": "auto",
        "OPENROUTER_WEB_SEARCH_MAX_TOOL_CALLS": "2",
        "WEB_SEARCH_MAX_RESULTS": "3",
        "WEB_SEARCH_CONTEXT_SIZE": "medium",
        "ENABLE_WEB_QUERY_REWRITE": "",
        "REDIS_URL": "redis://localhost:0",
    }):
        search_route = respx.post("https://openrouter.ai/api/v1/chat/completions").respond(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "OpenRouter search summary.",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url_citation": {
                                        "title": "OpenRouter Source",
                                        "url": "https://example.com/openrouter",
                                        "content": "OpenRouter citation excerpt.",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

        events = []
        run_state = ConversationRunState()
        async for event in mock_orchestrator._node_perplexity_search(
            "測試問題",
            "test_conv_id_openrouter",
            run_state=run_state,
        ):
            events.append(event)

        request_payload = json.loads(search_route.calls.last.request.content)
        assert request_payload["model"] == "google/gemini-3.8-flash"
        assert request_payload["stream"] is False
        assert request_payload["tools"][0]["type"] == "openrouter:web_search"
        assert request_payload["tools"][0]["parameters"]["engine"] == "auto"
        assert request_payload["tools"][0]["parameters"]["search_context_size"] == "medium"

        sources_event = next(event for event in events if "event: sources" in event)
        sources_payload = json.loads(sources_event.split("data: ")[1].strip())
        assert sources_payload == [{
            "title": "OpenRouter Source",
            "chunk_id": "https://example.com/openrouter",
            "url": "https://example.com/openrouter",
            "snippet": "OpenRouter citation excerpt.",
            "score": 1.0,
        }]
        assert "https://example.com/openrouter" in run_state.context_prompt
        assert "OpenRouter citation excerpt." in run_state.context_prompt
