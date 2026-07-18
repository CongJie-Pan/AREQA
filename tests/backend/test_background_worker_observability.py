import asyncio

import pytest

from backend.main import _track_background_task


@pytest.mark.asyncio
async def test_background_task_failure_is_logged(caplog):
    """A startup worker that fails before its own logs must still be visible."""

    async def failing_worker():
        raise RuntimeError("boom")

    with caplog.at_level("INFO"):
        task = _track_background_task(
            "failing_worker",
            asyncio.create_task(failing_worker()),
        )
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="boom"):
            await task
        await asyncio.sleep(0)

    assert "background.worker_task_started name=failing_worker" in caplog.text
    assert "background.worker_task_failed name=failing_worker reason=RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_background_task_cancel_is_logged(caplog):
    """Cancellation during shutdown should be distinguishable from failure."""

    async def long_running_worker():
        await asyncio.sleep(60)

    with caplog.at_level("INFO"):
        task = _track_background_task(
            "cancelled_worker",
            asyncio.create_task(long_running_worker()),
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    assert "background.worker_task_started name=cancelled_worker" in caplog.text
    assert "background.worker_task_cancelled name=cancelled_worker" in caplog.text
