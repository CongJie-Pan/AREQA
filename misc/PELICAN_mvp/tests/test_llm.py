import pytest
from pelican_mvp.domain_skill import DomainCategory
from pelican_mvp.llm import LlmAdapter, LlmConfig, LlmUnavailable
from pelican_mvp.models import TutoringStrategy
from test_domain_skill import valid_skill_payload

def test_llm_adapter_no_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    adapter = LlmAdapter(config=None)
    assert adapter.available is False
    assert adapter.verified_diagnostic("test") is None
    assert adapter.classify("p", "e", "a") is None
    assert adapter.tutor_response(TutoringStrategy.EXPLANATION, "p", "l") is None
    
    with pytest.raises(LlmUnavailable):
        adapter._json("system", "user")

def test_llm_adapter_import_error_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    original_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("No module named openai")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    
    config = LlmConfig(api_key="test", model="test", base_url="test")
    adapter = LlmAdapter(config=config)
    assert adapter.available is True
    
    with pytest.raises(LlmUnavailable, match="LLM request failed: ImportError"):
        adapter._json("system", "user")

def test_llm_adapter_valid_json_response() -> None:
    class MockMessage:
        content = '{"response": "this is a mock response"}'
    class MockChoice:
        message = MockMessage()
    class MockCompletion:
        choices = [MockChoice()]
    class MockChat:
        completions = type('Obj', (object,), {'create': lambda *args, **kwargs: MockCompletion()})()
    class MockClient:
        chat = MockChat()
    
    config = LlmConfig(api_key="test", model="test", base_url="test")
    adapter = LlmAdapter(config=config)
    adapter._client = MockClient()
    
    res = adapter.tutor_response(TutoringStrategy.EXPLANATION, "prompt", "label")
    assert res == "this is a mock response"


def test_llm_category_model_route_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PELICAN_LLM_MODEL", raising=False)
    monkeypatch.delenv("PELICAN_STEM_MODEL", raising=False)
    config = LlmConfig(api_key="test", model="legacy", base_url="test")
    adapter = LlmAdapter(config=config)

    assert adapter.model_route_for_category(DomainCategory.STEM) == "openai/gpt-5.5"
    assert adapter.model_route_for_category(DomainCategory.HUMANITIES) == "~google/gemini-pro-latest"

    monkeypatch.setenv("PELICAN_LLM_MODEL", "global/model")
    assert adapter.model_route_for_category(DomainCategory.BUSINESS) == "global/model"

    monkeypatch.setenv("PELICAN_STEM_MODEL", "stem/model")
    assert adapter.model_route_for_category(DomainCategory.STEM) == "stem/model"


def test_generate_domain_skill_uses_requested_route() -> None:
    payload = valid_skill_payload()
    payload["lifecycle"] = "runtime_generated"

    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.model_seen = None

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.model_seen = model
            return payload

    adapter = RecordingAdapter()
    skill = adapter.generate_domain_skill("深度學習", DomainCategory.STEM, model_route="stem/model")

    assert adapter.model_seen == "stem/model"
    assert skill is not None
    assert skill.skill_id == "deep_learning"
    assert skill.lifecycle.value == "runtime_generated"


def test_intake_question_uses_domain_route() -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.model_seen = None

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.model_seen = model
            return {"question": "你想從朝代脈絡、人物事件，還是制度文化開始？"}

    adapter = RecordingAdapter()
    question = adapter.intake_question(
        topic="中國歷史",
        domain_category=DomainCategory.HUMANITIES,
        stage="goal",
        model_route="humanities/model",
    )

    assert adapter.model_seen == "humanities/model"
    assert question == "你想從朝代脈絡、人物事件，還是制度文化開始？"
