import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from backend.services.post_turn_service import PostTurnService


@pytest.mark.asyncio
async def test_queue_post_turn_work_is_non_blocking_and_bounded(caplog):
    """Slow durable dispatch must not delay or outlive its configured bound."""

    caplog.set_level(logging.INFO)
    blocker = asyncio.Event()
    service = PostTurnService()

    async def wait_for_release(**_kwargs):
        await blocker.wait()

    service.dispatch_post_turn_work = AsyncMock(side_effect=wait_for_release)

    task = service.queue_post_turn_work(
        timeout_seconds=0.01,
        run_id="run-1",
        conversation_id="conversation-1",
    )

    assert task.done() is False
    await task
    assert "orchestration.post_turn_timeout" in caplog.text
