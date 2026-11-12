"""Own the OpenRouter connections used by the chat stream for one app lifespan."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from fastapi import FastAPI
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def get_chat_client(app: FastAPI, factory: Callable[..., AsyncOpenAI], api_key: str) -> AsyncOpenAI:
    clients = getattr(app.state, "chat_openrouter_clients", None)
    if clients is None:
        clients = app.state.chat_openrouter_clients = {}
    key = (factory, api_key)
    if key not in clients:
        clients[key] = factory(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=120.0)
    return clients[key]


async def close_chat_clients(app: FastAPI) -> None:
    clients = getattr(app.state, "chat_openrouter_clients", {})
    app.state.chat_openrouter_clients = {}
    results = await asyncio.gather(*(client.close() for client in clients.values()), return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("openrouter.chat_client_close_failed reason=%s", type(result).__name__)
