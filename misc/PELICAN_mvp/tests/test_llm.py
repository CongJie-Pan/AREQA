import pytest
from pelican_mvp.llm import LlmAdapter, LlmConfig, LlmUnavailable
from pelican_mvp.models import TutoringStrategy

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
