"""Focused contracts for educational image routing and provider boundaries."""

import base64

import pytest

from services import generated_image_service as images
from services.visual.understanding import VisualUnderstandingResult


def test_image_model_routing_and_prompt_contract():
    assert images.choose_image_model("A cat reading a book") == images.FLARE_MODEL
    assert images.choose_image_model("畫一張血液循環流程圖") == images.QWEN_MODEL
    prompt = images.build_image_prompt("血液循環流程圖", language="zh-TW", model=images.QWEN_MODEL)
    assert "Traditional Chinese" in prompt
    assert "血液循環流程圖" in prompt
    assert "do not invent" in prompt


@pytest.mark.asyncio
async def test_generate_image_uses_bounded_provider_request_and_private_storage(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setattr(images.settings, "enable_visual_understanding", False)
    png = b"\x89PNG\r\n\x1a\n" + b"test-image"
    seen = {}

    class Response:
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

    async def store(self, *, png_bytes, conversation_id, image_id):
        seen.update(png_bytes=png_bytes, conversation_id=conversation_id, image_id=image_id)
        return {"url": "https://example.test/signed", "bucket": "images", "path": "private/image.png", "expires_at": 123}

    monkeypatch.setattr(images.AttachmentImageStorageService, "persist_generated_image", store)
    result = await images.generate_teaching_image(
        "Draw a cat", language="en", conversation_id="conversation-1", image_id="image-1", client_factory=Client,
    )
    assert seen["payload"]["model"] == images.FLARE_MODEL
    assert seen["payload"]["n"] == 1
    assert seen["payload"]["quality"] == "low"
    assert seen["png_bytes"] == png
    assert result.image_url == "https://example.test/signed"
    assert result.cost_usd == 0.04
    assert result.transient is False


@pytest.mark.asyncio
async def test_generate_image_attaches_grounded_vision_summary(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setattr(images.settings, "enable_visual_understanding", True)
    png = b"\x89PNG\r\n\x1a\n" + b"test-image"

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
        "Draw a cat", language="en", conversation_id="conversation-1", image_id="image-1", client_factory=Client,
    )
    assert result.vision_summary == "A cat is sitting beside a book."
    assert result.how_to_read == ("Look at the cat, then the book.",)


@pytest.mark.asyncio
async def test_generate_image_rejects_non_png_provider_output(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setattr(images.settings, "enable_visual_understanding", False)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": base64.b64encode(b"not an image").decode()}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return Response()

    with pytest.raises(ValueError, match="unsupported image"):
        await images.generate_teaching_image(
            "Draw a cat", language="en", conversation_id="conversation-1", image_id="image-1", client_factory=Client,
        )
