from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI

from services.openrouter_clients import close_chat_clients, get_chat_client


@pytest.mark.asyncio
async def test_chat_stream_reuses_openrouter_transport_until_app_shutdown():
    app = FastAPI()
    other_app = FastAPI()
    first_client = Mock(close=AsyncMock())
    other_client = Mock(close=AsyncMock())
    factory = Mock(side_effect=[first_client, other_client])

    assert get_chat_client(app, factory, "test-key") is first_client
    assert get_chat_client(app, factory, "test-key") is first_client
    assert get_chat_client(other_app, factory, "test-key") is other_client
    assert factory.call_count == 2

    await close_chat_clients(app)
    await close_chat_clients(app)
    first_client.close.assert_awaited_once()
    other_client.close.assert_not_awaited()
    await close_chat_clients(other_app)
    other_client.close.assert_awaited_once()
