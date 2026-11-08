"""JSON and multipart share a history transport boundary independent of tokens."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.routes.stream import _validate_history_transport, parse_stream_request


@pytest.mark.asyncio
async def test_json_101_messages_accepted():
    messages = [{'role': 'user', 'content': 'hi'}] * 101
    request = SimpleNamespace(headers={}, json=AsyncMock(return_value={'messages': messages}))
    parsed, uploads = await parse_stream_request(request)
    assert len(parsed.messages) == 101
    assert uploads == []


def test_utf8_history_limit():
    with pytest.raises(HTTPException) as error:
        _validate_history_transport([{'role': 'user', 'content': '中' * 1_500_000}])
    assert error.value.status_code == 413


def test_message_count_limit():
    with pytest.raises(HTTPException):
        _validate_history_transport([{}] * 10_001)
