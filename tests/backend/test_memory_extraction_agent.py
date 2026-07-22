import json
from types import SimpleNamespace

import pytest

from backend.services.memory_extraction_agent import (
    LocalMemoryExtractionAgent,
    MemoryExtractionResult,
    OpenRouterMemoryExtractionAgent,
)


class FakeCompletions:
    def __init__(self, content: str | Exception):
        self.content = content

    async def create(self, **kwargs):
        if isinstance(self.content, Exception):
            raise self.content
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content),
                )
            ]
        )


class FakeClient:
    def __init__(self, content: str | Exception):
        self.chat = SimpleNamespace(
            completions=FakeCompletions(content),
        )


@pytest.mark.asyncio
async def test_local_memory_extraction_agent_splits_mixed_prompt_without_provider(caplog):
    caplog.set_level("INFO")
    agent = LocalMemoryExtractionAgent()
    raw_text = (
        "我是高一生，我下週要考高一物理了，但我之前連國中理化都一直不及格，現在好焦慮。\n"
        "你可以教我什麼是牛頓第一運動定律嗎？\n"
        "我偏好你先給我一個具體例子，再解釋抽象概念。"
    )

    result = await agent.extract_candidates(
        user_id="user-a",
        message_id="msg-a",
        conversation_id="conv-a",
        user_text=raw_text,
    )

    assert [candidate.candidate_type for candidate in result.candidates] == [
        "sensitive_context",
        "question",
        "learning_preference",
    ]
    assert result.candidates[-1].text == "我偏好你先給我一個具體例子，再解釋抽象概念。"
    assert "memory.local_extraction_completed" in caplog.text
    assert "candidate_type_counts=learning_preference:1,question:1,sensitive_context:1" in caplog.text
    assert raw_text not in caplog.text


@pytest.mark.asyncio
async def test_memory_extraction_agent_returns_learning_preference_candidate(caplog):
    caplog.set_level("INFO")
    payload = MemoryExtractionResult(
        candidates=[
            {
                "candidate_type": "learning_preference",
                "text": "我偏好你先給我一個具體例子，再解釋抽象概念。",
                "durability": "profile_memory",
                "confidence": 0.96,
                "reason_code": "explicit_learning_preference",
            },
            {
                "candidate_type": "question",
                "text": "你可以教我什麼是牛頓第一運動定律嗎？",
                "durability": "do_not_store",
                "confidence": 0.99,
                "reason_code": "question_not_memory",
            },
            {
                "candidate_type": "sensitive_context",
                "text": "我之前連國中理化都一直不及格，現在好焦慮。",
                "durability": "do_not_store",
                "confidence": 0.95,
                "reason_code": "negative_learning_state_sensitive",
            },
        ]
    )
    agent = OpenRouterMemoryExtractionAgent(
        FakeClient(payload.model_dump_json()),
        "test-model",
    )

    result = await agent.extract_candidates(
        user_id="user-a",
        message_id="msg-a",
        conversation_id="conv-a",
        user_text=(
            "我是高一生，我下週要考高一物理了，但我之前連國中理化都一直不及格，現在好焦慮。\n"
            "你可以教我什麼是牛頓第一運動定律嗎？\n"
            "我偏好你先給我一個具體例子，再解釋抽象概念。"
        ),
    )

    assert [candidate.candidate_type for candidate in result.candidates] == [
        "learning_preference",
        "question",
        "sensitive_context",
    ]
    assert result.candidates[0].durability == "profile_memory"
    assert "memory.extraction_completed" in caplog.text
    assert "candidate_type_counts=learning_preference:1,question:1,sensitive_context:1" in caplog.text
    assert "我偏好" not in caplog.text


@pytest.mark.asyncio
async def test_memory_extraction_agent_fails_closed_on_invalid_json(caplog):
    agent = OpenRouterMemoryExtractionAgent(FakeClient("not-json"), "test-model")

    result = await agent.extract_candidates(
        user_id="user-a",
        message_id="msg-a",
        conversation_id="conv-a",
        user_text="我偏好你先給我一個具體例子，再解釋抽象概念。",
    )

    assert result.candidates == []
    assert "memory.extraction_unavailable" in caplog.text
    assert "我偏好" not in caplog.text


@pytest.mark.asyncio
async def test_memory_extraction_agent_fails_closed_on_provider_error():
    agent = OpenRouterMemoryExtractionAgent(FakeClient(RuntimeError("provider down")), "test-model")

    result = await agent.extract_candidates(
        user_id="user-a",
        message_id="msg-a",
        conversation_id="conv-a",
        user_text="我偏好你先給我一個具體例子，再解釋抽象概念。",
    )

    assert result.candidates == []


def test_memory_extraction_result_rejects_extra_fields():
    payload = {
        "candidates": [
            {
                "candidate_type": "learning_preference",
                "text": "我偏好用具體例子理解抽象概念。",
                "durability": "profile_memory",
                "confidence": 1.0,
                "reason_code": "explicit_learning_preference",
                "unexpected": "blocked",
            }
        ]
    }

    with pytest.raises(Exception):
        MemoryExtractionResult.model_validate(json.loads(json.dumps(payload)))
