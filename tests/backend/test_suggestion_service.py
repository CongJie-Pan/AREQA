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
    assert "生成 3 個English的延伸問題" in messages[0]["content"]
    assert "必須全程使用English" in messages[0]["content"]
    assert "請務必以English輸出" in messages[1]["content"]
    assert suggestions == [
        "What is Bayes theorem?",
        "How is it used?",
        "Can you show an example?",
    ]
