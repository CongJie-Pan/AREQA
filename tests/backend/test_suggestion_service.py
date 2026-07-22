from services.suggestion_service import SuggestionService


def test_suggestion_service_uses_configured_default_model():
    service = SuggestionService(api_key="")

    assert service.model == "google/gemini-2.5-flash-lite"


def test_suggestion_service_allows_model_override():
    service = SuggestionService(api_key="", model="test/suggestion-model")

    assert service.model == "test/suggestion-model"
