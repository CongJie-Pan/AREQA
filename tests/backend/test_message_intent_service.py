"""Semantic routing contract, reference validation and safe failure boundaries."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import logging
import pytest
from services import message_intent_service as intents


@pytest.fixture
def classifier(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "SECRET_TEST_KEY")
    create = AsyncMock()
    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
    monkeypatch.setattr(intents, "AsyncOpenAI", Client)
    return create


def reply(value):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))])


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt, intent, reference, attachment_count", [
    ("幫我產圖", "generate_image", "attachments", 1),
    ("请画一只猫", "generate_image", "none", 0),
    ("Create an illustration of a cat", "generate_image", "none", 0),
    ("不要產圖，只寫 prompt", "chat", "none", 1),
    ("為什麼不能產圖", "chat", "none", 0),
    ("請解釋這張圖", "chat", "none", 1),
    ("幫我產圖", "clarify", "none", 0),
])
async def test_provider_decision_contract(classifier, prompt, intent, reference, attachment_count, caplog):
    classifier.return_value = reply({"intent": intent, "reference": reference, "reference_message_id": None})
    with caplog.at_level(logging.INFO):
        result = await intents.classify_message_intent(intents.MessageIntentRequest(prompt=prompt, attachment_count=attachment_count))
    assert result.intent == intent
    request = classifier.call_args.kwargs
    assert json.loads(request["messages"][1]["content"])["prompt"] == prompt
    assert "negation" in request["messages"][0]["content"]
    assert "writing a prompt" in request["messages"][0]["content"]
    assert request["response_format"] == {"type": "json_object"}
    assert prompt not in caplog.text
    assert "SECRET_TEST_KEY" not in caplog.text


@pytest.mark.asyncio
async def test_selects_only_existing_conversation_reference(classifier):
    classifier.return_value = reply({"intent": "generate_image", "reference": "conversation", "reference_message_id": "source"})
    result = await intents.classify_message_intent(intents.MessageIntentRequest(prompt="根據上面畫圖", context=[
        intents.IntentContext(id="source", role="assistant", content="Photosynthesis"),
    ]))
    assert result.reference_message_id == "source"


@pytest.mark.asyncio
@pytest.mark.parametrize("output", [
    {"intent": "generate_image", "reference": "conversation", "reference_message_id": "invented"},
    {"intent": "generate_image", "reference": "attachments"},
    {"intent": "chat", "reference": "attachments"},
    {"intent": "generate_image", "reference": "none", "reference_message_id": "invented"},
    {"intent": "execute_arbitrary_tool", "reference": "none"},
])
async def test_invalid_model_output_cannot_execute(classifier, output):
    classifier.return_value = reply(output)
    with pytest.raises(RuntimeError, match="routing unavailable"):
        await intents.classify_message_intent(intents.MessageIntentRequest(prompt="Draw a cat"))


@pytest.mark.asyncio
async def test_provider_failures_do_not_log_payload(classifier, caplog):
    classifier.side_effect = RuntimeError("PRIVATE_PROVIDER_BODY SECRET_TEST_KEY")
    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError):
        await intents.classify_message_intent(intents.MessageIntentRequest(prompt="PRIVATE_PROMPT"))
    assert "PRIVATE" not in caplog.text
    assert "SECRET_TEST_KEY" not in caplog.text


@pytest.fixture
def intent_api(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import generated_images
    from auth import get_current_user
    app = FastAPI()
    app.include_router(generated_images.router)
    app.dependency_overrides[get_current_user] = lambda: "user-a"
    quota = AsyncMock(return_value=True)
    classify = AsyncMock(return_value=intents.MessageIntent(intent="generate_image", reference="attachments"))
    monkeypatch.setattr(generated_images, "consume_image_quota", quota)
    monkeypatch.setattr(generated_images, "classify_message_intent", classify)
    return TestClient(app), quota, classify


def test_intent_endpoint_validates_and_uses_separate_quota(intent_api):
    client, quota, classify = intent_api
    result = client.post('/api/v1/images/intent', json={"prompt": "幫我產圖", "attachment_count": 1})
    assert result.status_code == 200
    assert result.json()["intent"] == "generate_image"
    quota.assert_awaited_once_with("user-a:intent", limit=30)
    classify.assert_awaited_once()


def test_intent_endpoint_rejects_unbounded_input(intent_api):
    client, quota, classify = intent_api
    assert client.post('/api/v1/images/intent', json={"prompt": "a" * 20001}).status_code == 422
    classify.assert_not_awaited()
    quota.assert_not_awaited()


def test_intent_endpoint_quota_failure_never_calls_provider(intent_api):
    client, quota, classify = intent_api
    quota.return_value = False
    assert client.post('/api/v1/images/intent', json={"prompt": "畫貓"}).status_code == 429
    classify.assert_not_awaited()


def test_intent_endpoint_provider_failure_is_explicit(intent_api):
    client, quota, classify = intent_api
    classify.side_effect = RuntimeError('PRIVATE_PROVIDER_BODY')
    response = client.post('/api/v1/images/intent', json={"prompt": "畫貓"})
    assert response.status_code == 503
    assert 'PRIVATE' not in response.text
