from io import BytesIO

import httpx
import pytest
from PIL import Image

from backend.services.visual_input_service import VisualInputService


def make_png() -> bytes:
    """Return a small valid PNG payload."""

    buffer = BytesIO()
    Image.new("RGB", (1, 1), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeAsyncClient:
    """httpx.AsyncClient replacement with deterministic responses."""

    response: httpx.Response | Exception = httpx.Response(200, content=make_png())
    last_kwargs = {}

    def __init__(self, *args, **kwargs):
        self.__class__.last_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url):
        if isinstance(self.response, Exception):
            raise self.response
        self.response.request = httpx.Request("GET", url)
        return self.response


@pytest.mark.asyncio
async def test_visual_input_service_converts_remote_image_to_data_uri(monkeypatch, caplog):
    """Selected remote images should follow the attachment data URI path."""

    caplog.set_level("INFO")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = httpx.Response(
        200,
        content=make_png(),
        headers={"content-type": "image/png"},
    )
    service = VisualInputService(timeout_seconds=1.0)

    image_input = await service.prepare_image_part(
        image_url="https://example.edu/forest.png",
        conversation_id="conversation-1",
    )

    assert image_input.source == "data_uri"
    assert image_input.media_type == "image/png"
    assert _FakeAsyncClient.last_kwargs["headers"]["User-Agent"]
    assert image_input.content_part["type"] == "image_url"
    assert image_input.content_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert "visual.input_data_uri_ready" in caplog.text
    assert "https://example.edu/forest.png" not in caplog.text


@pytest.mark.asyncio
async def test_visual_input_service_falls_back_to_remote_url_on_download_failure(monkeypatch, caplog):
    """Download failures should keep visual understanding fail-soft."""

    caplog.set_level("INFO")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.response = httpx.ConnectError("connection failed")
    service = VisualInputService(timeout_seconds=1.0)

    image_input = await service.prepare_image_part(
        image_url="https://example.edu/forest.png",
        conversation_id="conversation-1",
    )

    assert image_input.source == "remote_url"
    assert image_input.content_part == {
        "type": "image_url",
        "image_url": {"url": "https://example.edu/forest.png"},
    }
    assert "visual.input_data_uri_unavailable" in caplog.text
    assert "reason=ConnectError" in caplog.text


@pytest.mark.asyncio
async def test_visual_input_service_logs_http_status_on_download_failure(monkeypatch, caplog):
    """HTTP failures should expose safe status codes without logging full URLs."""

    caplog.set_level("INFO")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    request = httpx.Request("GET", "https://example.edu/blocked.png")
    _FakeAsyncClient.response = httpx.Response(
        403,
        content=b"blocked",
        request=request,
    )
    service = VisualInputService(timeout_seconds=1.0)

    image_input = await service.prepare_image_part(
        image_url="https://example.edu/blocked.png",
        conversation_id="conversation-1",
    )

    assert image_input.source == "remote_url"
    assert "visual.input_data_uri_unavailable" in caplog.text
    assert "reason=HTTPStatusError:403" in caplog.text
    assert "https://example.edu/blocked.png" not in caplog.text
