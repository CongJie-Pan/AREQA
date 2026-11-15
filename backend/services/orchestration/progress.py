"""Learner-facing turn progress events.

The ``progress`` SSE event carries a stable step code plus optional counts. The
frontend owns the wording (and its translations), so payloads never contain
user text, filenames, prompts or model output.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

PROGRESS_STEPS = frozenset({
    "reading_attachments",
    "analyzing",
    "recalling_memory",
    "planning",
    "visual_planning",
    "visual_understanding",
    "reading_documents",
    "composing",
})


def progress_event(step: str, current: int | None = None, total: int | None = None) -> str:
    """Encode one progress SSE event.

    Args:
        step: One of ``PROGRESS_STEPS``.
        current: Completed units of the step, when countable.
        total: Total units of the step, when countable.

    Returns:
        A complete ``event: progress`` SSE frame.
    """
    if step not in PROGRESS_STEPS:
        raise ValueError(f"unknown progress step: {step}")
    payload: dict[str, object] = {"step": step}
    if total:
        payload["current"] = max(0, min(int(current or 0), int(total)))
        payload["total"] = int(total)
    return f"event: progress\ndata: {json.dumps(payload)}\n\n"


class ProgressRelay:
    """Collect progress from awaited work and replay it as SSE frames.

    Preparation stages are plain coroutines that cannot ``yield`` into the SSE
    stream; they call :meth:`report` and the stream owner drains the frames
    while the work is still running.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def report(self, step: str, current: int | None = None, total: int | None = None) -> None:
        """Queue one progress frame; never raises into the reporting stage."""
        try:
            self._queue.put_nowait(progress_event(step, current, total))
        except ValueError:
            return

    async def drain_while(self, task: asyncio.Future) -> AsyncIterator[str]:
        """Yield queued frames until ``task`` finishes, then flush the rest.

        The task's own result or exception is left for the caller to await.
        """
        while not task.done():
            getter = asyncio.ensure_future(self._queue.get())
            done, _ = await asyncio.wait({task, getter}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                yield getter.result()
            else:
                getter.cancel()
                await asyncio.gather(getter, return_exceptions=True)
        while not self._queue.empty():
            yield self._queue.get_nowait()
