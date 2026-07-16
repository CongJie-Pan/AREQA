import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.memory_semantic_analyzer import (
    OpenRouterMemorySemanticAnalyzer,
    SemanticAnalysisRequest,
    SemanticCandidate,
)


def request() -> SemanticAnalysisRequest:
    return SemanticAnalysisRequest(
        user_id="user-a",
        message_id="msg-b",
        category="passive_preference",
        user_text="學抽象概念時，我希望先看具體案例再理解原理。",
        candidates=[
            SemanticCandidate(
                candidate_id="candidate-a",
                category="passive_preference",
                canonical_summary="偏好用具體例子理解抽象概念",
            )
        ],
    )


@pytest.mark.asyncio
async def test_strict_schema_match_is_validated():
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=(
        '{"canonical_key":"concrete_examples","relation":"match_existing",'
        '"matched_candidate_id":"candidate-a","confidence":0.98,'
        '"reason_code":"same_preference"}'
    )))]
    client.chat.completions.create = AsyncMock(return_value=response)
    analyzer = OpenRouterMemorySemanticAnalyzer(client, "google/gemini-2.5-flash-lite")

    result = await analyzer.analyze(request())

    assert result.relation == "match_existing"
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["extra_body"]["provider"]["zdr"] is True
    assert kwargs["extra_body"]["provider"]["allow_fallbacks"] is False


@pytest.mark.asyncio
async def test_cross_candidate_reference_fails_closed():
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=(
        '{"canonical_key":"x","relation":"match_existing",'
        '"matched_candidate_id":"other-user-candidate","confidence":0.99,'
        '"reason_code":"same"}'
    )))]
    client.chat.completions.create = AsyncMock(return_value=response)
    analyzer = OpenRouterMemorySemanticAnalyzer(client, "google/gemini-2.5-flash-lite")

    result = await analyzer.analyze(request())

    assert result.relation == "uncertain"
    assert result.reason_code == "invalid_candidate_reference"


@pytest.mark.asyncio
async def test_invalid_schema_fails_closed():
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content='{"relation":"promote"}'))]
    client.chat.completions.create = AsyncMock(return_value=response)
    analyzer = OpenRouterMemorySemanticAnalyzer(client, "google/gemini-2.5-flash-lite")

    result = await analyzer.analyze(request())

    assert result.relation == "uncertain"
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_timeout_fails_closed():
    client = MagicMock()

    async def slow_response(**kwargs):
        await asyncio.sleep(0.05)

    client.chat.completions.create = AsyncMock(side_effect=slow_response)
    analyzer = OpenRouterMemorySemanticAnalyzer(
        client,
        "google/gemini-2.5-flash-lite",
        timeout_seconds=0.001,
    )

    result = await analyzer.analyze(request())

    assert result.relation == "uncertain"
    assert result.reason_code == "analysis_timeouterror"
