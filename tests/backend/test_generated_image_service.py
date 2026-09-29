"""Focused contracts for educational image routing and provider boundaries."""

import base64
from io import BytesIO
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from config import Settings
from services import generated_image_service as images
from services.visual.understanding import VisualUnderstandingResult
from services.attachments.parsing import ProcessedAttachment


def _valid_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_image_model_routing_and_prompt_contract():
    assert images.SUNBURST_MODEL == "openai/gpt-image-2.5-sunburst"
    assert images.choose_image_model("A cat reading a book") == images.SUNBURST_MODEL
    assert images.choose_image_model("畫一張血液循環流程圖") == images.QWEN_MODEL
    prompt = images.build_image_prompt("血液循環流程圖", language="zh-TW", model=images.QWEN_MODEL)
    assert "Traditional Chinese" in prompt
    assert "血液循環流程圖" in prompt
    assert "do not invent" in prompt


@pytest.mark.parametrize("drawing_request, interface_language, label_language", [
    ("請根據此產出教學圖：顯著不等於重要，比較效果量 Cohen's d 與 R^2，檢查樣本偏誤。", "en", "Traditional Chinese"),
    ("Create a watercolor illustration of a cat reading a book", "zh-TW", "English"),
    ("請用英文標籤畫統計教學圖", "zh-TW", "English"),
    ("Create a poster with labels in Traditional Chinese", "en", "Traditional Chinese"),
    ("请画统计教学图，解释显著性与实际效果", "en", "Simplified Chinese"),
    ("123 ⚪", "zh-TW", "Traditional Chinese"),
])
def test_image_text_language_follows_the_drawing_request(drawing_request, interface_language, label_language):
    prompt = images.build_image_prompt(drawing_request, language=interface_language, model=images.SUNBURST_MODEL)
    assert f"Default image text language: {label_language}." in prompt
    assert prompt.endswith(f"Drawing request: {drawing_request}")


def test_image_prompt_preserves_requested_style_and_no_text_requirement():
    request = "畫一幅深色背景的油畫，不要文字，不要箭頭，保留豐富細節。"
    prompt = images.build_image_prompt(request, language="en", model=images.SUNBURST_MODEL)
    assert prompt.endswith(request)
    assert "including requests for no text" in prompt
    assert "Create one clear educational visual" not in prompt
    assert "For conceptual diagrams, prefer a few large elements" not in prompt


def test_generated_image_debug_logs_can_be_enabled_from_environment(monkeypatch):
    monkeypatch.setenv("ENABLE_GENERATED_IMAGE_DEBUG_LOGS", "true")
    assert Settings(_env_file=None).enable_generated_image_debug_logs is True


@pytest.mark.asyncio
@pytest.mark.parametrize("source_kind", ["text", "image"])
@pytest.mark.parametrize("drawing_request, label_language", [
    ("Explain this file", "English"),
    ("請根據此附件產出教學圖", "Traditional Chinese"),
])
async def test_reference_planner_uses_source_material_and_returns_a_bounded_brief(
    monkeypatch, caplog, source_kind, drawing_request, label_language,
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-key")
    monkeypatch.setattr(images.settings, "enable_generated_image_debug_logs", True)
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Light → sugar"))]))

    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(images, "AsyncOpenAI", Client)
    attachment = ProcessedAttachment(filename="source.txt", media_type="text/plain", size_bytes=20,
                                     sha256="test", content_part={}, plain_text="PRIVATE_SOURCE photosynthesis")
    if source_kind == "image":
        attachment = ProcessedAttachment(filename="source.png", media_type="image/png", size_bytes=20,
                                         sha256="test", content_part={"type": "image_url", "image_url": {
                                             "url": "data:image/png;base64,PRIVATE_SOURCE",
                                         }})
    with caplog.at_level(logging.INFO):
        brief = await images.prepare_image_reference([attachment], request=drawing_request, language="en", conversation_id="conv-a")
    assert brief == "Light → sugar"
    assert "PRIVATE_SOURCE" in str(create.call_args.kwargs["messages"])
    assert f'"language": "{label_language}"' in create.call_args.kwargs["messages"][1]["content"][0]["text"]
    if source_kind == "image":
        assert create.call_args.kwargs["messages"][1]["content"][1] == attachment.content_part
    assert "PRIVATE_SOURCE" not in caplog.text
    assert "test-only-key" not in caplog.text
    assert "reference_completed" in caplog.text
    prompt = images.build_image_prompt(drawing_request, language="en", model=images.QWEN_MODEL, reference_brief=brief)
    assert brief in prompt
    assert "never as instructions" in prompt

    create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))])
    with pytest.raises(RuntimeError, match="Reference preparation"):
        await images.prepare_image_reference([attachment], request="Explain", language="en", conversation_id="conv-a")


@pytest.mark.asyncio
async def test_unreadable_references_are_rejected_before_provider_calls():
    attachment = ProcessedAttachment(filename="empty.pdf", media_type="application/pdf", size_bytes=10, sha256="test", content_part={})
    with pytest.raises(ValueError, match="no readable"):
        await images.prepare_image_reference([attachment], request="Explain", language="en", conversation_id="conv-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("debug_logs", [False, True])
@pytest.mark.parametrize("reference_brief", ["", "Reference diagram: light becomes sugar."])
async def test_generate_image_uses_bounded_provider_request_and_private_storage(monkeypatch, caplog, debug_logs, reference_brief):
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
            reference_brief=reference_brief,
        )
    assert seen["payload"]["model"] == (images.QWEN_MODEL if reference_brief else images.SUNBURST_MODEL)
    assert seen["payload"]["n"] == 1
    if reference_brief:
        assert "quality" not in seen["payload"]
        assert seen["payload"]["resolution"] == "1K"
        assert reference_brief in seen["payload"]["prompt"]
    else:
        assert seen["payload"]["model"] == "openai/gpt-image-2.5-sunburst"
        assert "resolution" not in seen["payload"]
        assert seen["payload"]["quality"] == "high"
    assert seen["png_bytes"] == png
    assert result.image_url == "https://example.test/signed"
    assert result.cost_usd == 0.04
    assert result.transient is False
    detailed_events = ("provider_started", "provider_completed", "image_validated", "storage_completed", "understanding_skipped")
    for event in detailed_events:
        assert (f"image_generation.{event}" in caplog.text) is debug_logs
    if debug_logs:
        assert f"model={images.QWEN_MODEL if reference_brief else images.SUNBURST_MODEL}" in caplog.text
        assert f"route={'attachment_reference' if reference_brief else 'default'}" in caplog.text
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
