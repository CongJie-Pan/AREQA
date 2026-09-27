"""Focused contracts for educational image routing and provider boundaries."""

import base64
from io import BytesIO
import logging

import pytest
from PIL import Image

from config import Settings
from services import generated_image_service as images
from services.visual.understanding import VisualUnderstandingResult


def _valid_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_image_model_routing_and_prompt_contract():
    assert images.choose_image_model("A cat reading a book") == images.FLARE_MODEL
    assert images.choose_image_model("畫一張血液循環流程圖") == images.QWEN_MODEL
    prompt = images.build_image_prompt("血液循環流程圖", language="zh-TW", model=images.QWEN_MODEL)
    assert "Traditional Chinese" in prompt
    assert "血液循環流程圖" in prompt
    assert "do not invent" in prompt


def test_generated_image_debug_logs_can_be_enabled_from_environment(monkeypatch):
    monkeypatch.setenv("ENABLE_GENERATED_IMAGE_DEBUG_LOGS", "true")
    assert Settings(_env_file=None).enable_generated_image_debug_logs is True


@pytest.mark.asyncio
@pytest.mark.parametrize("debug_logs", [False, True])
async def test_generate_image_uses_bounded_provider_request_and_private_storage(monkeypatch, caplog, debug_logs):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setattr(images.settings, "enable_visual_understanding", False)
    monkeypatch.setattr(images.settings, "enable_generated_image_debug_logs", debug_logs)
    png = _valid_png()
    seen = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": base64.b64encode(png).decode()}], "usage": {"cost": 0.04}}

    class Client:
        def __init__(self, **kwargs):
            seen["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, json, headers):
            seen.update(url=url, payload=json, headers=headers)
            return Response()

    async def store(self, *, png_bytes, user_id, conversation_id, image_id):
        seen.update(png_bytes=png_bytes, conversation_id=conversation_id, image_id=image_id)
        return {"url": "https://example.test/signed", "bucket": "images", "path": "private/image.png", "expires_at": 123}

    monkeypatch.setattr(images.AttachmentImageStorageService, "persist_generated_image", store)
    with caplog.at_level(logging.INFO, logger=images.logger.name):
        result = await images.generate_teaching_image(
            "Draw a cat", language="en", user_id="user-1", conversation_id="conversation-1", image_id="image-1", client_factory=Client,
        )
    assert seen["payload"]["model"] == images.FLARE_MODEL
    assert seen["payload"]["n"] == 1
    assert seen["payload"]["quality"] == "low"
    assert seen["png_bytes"] == png
    assert result.image_url == "https://example.test/signed"
    assert result.cost_usd == 0.04
    assert result.transient is False
    detailed_events = ("provider_started", "provider_completed", "image_validated", "storage_completed", "understanding_skipped")
    for event in detailed_events:
        assert (f"image_generation.{event}" in caplog.text) is debug_logs
    if debug_logs:
        assert "model=openai/gpt-image-2.5-flare" in caplog.text
        assert "route=default" in caplog.text
        assert "persisted=True" in caplog.text
    assert "Draw a cat" not in caplog.text
    assert "test-only-key" not in caplog.text


@pytest.mark.asyncio
async def test_generate_image_attaches_grounded_vision_summary(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setattr(images.settings, "enable_visual_understanding", True)
    png = _valid_png()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": base64.b64encode(png).decode()}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return Response()

    class VisionClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    async def store(self, **kwargs):
        return None

    async def analyze(self, **kwargs):
        assert kwargs["image_url"].startswith("data:image/png;base64,")
        return VisualUnderstandingResult(
            summary="A cat is sitting beside a book.",
            how_to_read=("Look at the cat, then the book.",),
            confidence="high", source="vision_model",
        )

    monkeypatch.setattr(images.AttachmentImageStorageService, "persist_generated_image", store)
    monkeypatch.setattr(images, "AsyncOpenAI", VisionClient)
    monkeypatch.setattr(images.VisualUnderstandingAgent, "analyze", analyze)
    result = await images.generate_teaching_image(
        "Draw a cat", language="en", user_id="user-1", conversation_id="conversation-1", image_id="image-1", client_factory=Client,
    )
    assert result.vision_summary == "A cat is sitting beside a book."
    assert result.how_to_read == ("Look at the cat, then the book.",)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_bytes, expected_error", [
    (b"not an image", "unsupported image"),
    (b"\x89PNG\r\n\x1a\n" + b"not an image", "invalid PNG"),
])
async def test_generate_image_rejects_invalid_provider_output(monkeypatch, invalid_bytes, expected_error):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setattr(images.settings, "enable_visual_understanding", False)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": base64.b64encode(invalid_bytes).decode()}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return Response()

    with pytest.raises(ValueError, match=expected_error):
        await images.generate_teaching_image(
            "Draw a cat", language="en", user_id="user-1", conversation_id="conversation-1", image_id="image-1", client_factory=Client,
        )
