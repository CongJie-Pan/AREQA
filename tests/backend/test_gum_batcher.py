import asyncio
import logging

import pytest

import backend.gum_integration  # noqa: F401 - registers the local GUM package path
from gum.batcher import ObservationBatcher
from gum.gum import gum


@pytest.mark.asyncio
async def test_partial_batch_flushes_after_max_wait(tmp_path):
    instance = object.__new__(gum)
    instance.batcher = ObservationBatcher(
        str(tmp_path),
        min_batch_size=3,
        max_batch_size=10,
        max_wait_seconds=0.01,
    )
    instance._batch_processing_lock = asyncio.Lock()
    instance.logger = logging.getLogger("test.gum")
    processed = []

    async def process(batch):
        processed.append(batch)

    instance._process_batch = process
    instance.batcher.push("observer", "one", "input_text", user_id="user-a")
    task = asyncio.create_task(instance._batch_processing_loop())

    try:
        await asyncio.wait_for(
            _wait_until(lambda: len(processed) == 1),
            timeout=0.5,
        )
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(processed[0]) == 1
    assert processed[0][0]["user_id"] == "user-a"


async def _wait_until(predicate):
    while not predicate():
        await asyncio.sleep(0.005)
