from types import SimpleNamespace

import pytest

from services.suggestion_service import SuggestionService


def test_suggestion_service_uses_configured_default_model():
    service = SuggestionService(api_key="")

    assert service.model == "google/gemini-2.5-flash-lite"


def test_suggestion_service_allows_model_override():
    service = SuggestionService(api_key="", model="test/suggestion-model")

    assert service.model == "test/suggestion-model"


class _FakeCompletions:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"suggestions": ["What is Bayes theorem?", '
                            '"How is it used?", "Can you show an example?"]}'
                        )
                    )
                )
            ]
        )


@pytest.mark.asyncio
async def test_suggestion_service_uses_latest_query_language_for_english_suggestions():
    completions = _FakeCompletions()
    service = SuggestionService(api_key="", model="test/suggestion-model")
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    suggestions = await service.generate_suggestions(
        user_query="Explain Bayes theorem with a simple example",
        answer_text="Bayes theorem updates probability after new evidence.",
        reranked_results=[],
        interface_language="zh-TW",
    )

    messages = completions.kwargs["messages"]
    assert "Write every question in English" in messages[0]["content"]
    assert "Return English only" in messages[1]["content"]
    assert suggestions == [
        "What is Bayes theorem?",
        "How is it used?",
        "Can you show an example?",
    ]


@pytest.mark.asyncio
async def test_suggestion_service_accepts_concise_english_questions_over_old_limit():
    completions = _FakeCompletions()
    completions.create = _create_response(
        completions,
        '{"suggestions": ["How does this mechanism improve long-range dependency handling?", "Why does the scaling step stabilize attention gradients?", "Can you compare this approach with recurrent models in practice?"]}'
    )
    service = SuggestionService(api_key="", model="test/suggestion-model")
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    suggestions = await service.generate_suggestions(
        user_query="Explain the attention mechanism",
        answer_text="Attention computes weighted relationships between tokens.",
        reranked_results=[],
        interface_language="zh-TW",
    )

    assert len(suggestions) == 3
    assert all(isinstance(item, str) for item in suggestions)


@pytest.mark.asyncio
async def test_suggestion_service_uses_simplified_chinese_prompt_when_query_is_simplified():
    completions = _FakeCompletions()
    service = SuggestionService(api_key="", model="test/suggestion-model")
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    await service.generate_suggestions(
        user_query="请解释这个学习问题",
        answer_text="这是一个简短的回答。",
        reranked_results=[],
        interface_language="zh-TW",
    )

    messages = completions.kwargs["messages"]
    assert "必须全程使用简体中文" in messages[0]["content"]
    assert "请务必以简体中文输出" in messages[1]["content"]


def _create_response(completions, content):
    async def create(**kwargs):
        completions.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    return create
