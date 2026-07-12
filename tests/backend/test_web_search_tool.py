import json
from unittest.mock import AsyncMock

import pytest

from backend.tools import WebSearchTool


class FakeRedis:
    def __init__(self, cached=None):
        self.cached = cached
        self.get = AsyncMock(return_value=cached)
        self.set = AsyncMock()
        self.aclose = AsyncMock()


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeHttpClient:
    def __init__(self, data):
        self.post = AsyncMock(return_value=FakeResponse(data))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_web_search_cache_hit_skips_external_request():
    cached = json.dumps({"results": [{"url": "https://example.com", "snippet": "cached"}]})
    redis = FakeRedis(cached)

    def fail_http_factory(**kwargs):
        raise AssertionError("HTTP client must not be created on cache hit")

    tool = WebSearchTool(
        redis_factory=lambda *args, **kwargs: redis,
        http_client_factory=fail_http_factory,
    )
    result = await tool.execute({
        "query": "latest",
        "conversation_id": "conversation-1",
        "api_key": "secret",
    })

    assert result.cache_status == "hit"
    assert result.provenance == ("https://example.com",)
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_web_search_bounds_provider_results_and_caches_response():
    redis = FakeRedis()
    http = FakeHttpClient({
        "results": [
            {"url": f"https://example.com/{index}", "snippet": "x" * 20}
            for index in range(5)
        ]
    })
    tool = WebSearchTool(
        max_content_chars=25,
        redis_factory=lambda *args, **kwargs: redis,
        http_client_factory=lambda **kwargs: http,
    )
    result = await tool.execute({
        "query": "latest",
        "conversation_id": "conversation-1",
        "api_key": "secret",
        "max_results": 3,
    })

    assert len(result.content["results"]) == 2
    assert sum(len(item["snippet"]) for item in result.content["results"]) == 25
    assert result.truncated is True
    redis.set.assert_awaited_once()
    assert http.post.await_args.kwargs["json"]["max_results"] == 3


@pytest.mark.asyncio
async def test_web_search_rejects_missing_key_before_network_access():
    tool = WebSearchTool(
        redis_factory=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()),
    )
    with pytest.raises(PermissionError, match="API key"):
        await tool.execute({"query": "latest", "api_key": ""})


@pytest.mark.asyncio
async def test_web_search_cache_is_scoped_by_user_and_conversation():
    first_redis = FakeRedis()
    second_redis = FakeRedis()
    redis_instances = iter([first_redis, second_redis])
    http = FakeHttpClient({"results": []})
    tool = WebSearchTool(
        redis_factory=lambda *args, **kwargs: next(redis_instances),
        http_client_factory=lambda **kwargs: http,
    )
    base = {
        "query": "latest",
        "conversation_id": "same-conversation",
        "api_key": "secret",
    }
    await tool.execute({**base, "user_id": "user-1"})
    await tool.execute({**base, "user_id": "user-2"})

    first_key = first_redis.get.await_args.args[0]
    second_key = second_redis.get.await_args.args[0]
    assert first_key != second_key
