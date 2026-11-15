"""Unit tests for the learner-facing progress relay."""

from __future__ import annotations

import asyncio
import json

import pytest

from services.orchestration.progress import ProgressRelay, progress_event


def _payload(frame: str) -> dict:
    assert frame.startswith("event: progress\n")
    return json.loads(frame.split("data: ", 1)[1])


def test_progress_event_carries_only_step_and_bounded_counts():
    assert _payload(progress_event("composing")) == {"step": "composing"}
    assert _payload(progress_event("visual_understanding", 9, 4)) == {
        "step": "visual_understanding", "current": 4, "total": 4,
    }
    with pytest.raises(ValueError):
        progress_event("free text from a user")


@pytest.mark.asyncio
async def test_relay_streams_frames_while_work_is_still_running():
    relay = ProgressRelay()
    seen_before_finish: list[dict] = []
    release = asyncio.Event()

    async def work():
        relay.report("visual_planning", 1, 3)
        await release.wait()
        relay.report("visual_planning", 3, 3)
        return "prepared"

    task = asyncio.create_task(work())
    frames = []
    async for frame in relay.drain_while(task):
        frames.append(_payload(frame))
        if not task.done():
            seen_before_finish.append(frames[-1])
            release.set()

    assert seen_before_finish == [{"step": "visual_planning", "current": 1, "total": 3}]
    assert frames[-1] == {"step": "visual_planning", "current": 3, "total": 3}
    assert await task == "prepared"


@pytest.mark.asyncio
async def test_relay_ignores_unknown_steps_and_leaves_errors_to_the_caller():
    relay = ProgressRelay()

    async def work():
        relay.report("not-a-step")
        raise RuntimeError("boom")

    task = asyncio.create_task(work())
    frames = [frame async for frame in relay.drain_while(task)]

    assert frames == []
    with pytest.raises(RuntimeError):
        await task


def test_learner_document_count_ignores_coverage_note_and_transcript_parts():
    from services.conversation.attachment_budget import AttachmentPart, CoverageNotePart, DocumentPart
    from services.orchestration.progress import count_learner_documents

    pdf = {"type": "file", "file": {"filename": "a.pdf", "file_data": "data:application/pdf;base64,AA=="}}
    parts = [
        CoverageNotePart({"type": "text", "text": "coverage"}),
        DocumentPart(pdf), DocumentPart(pdf), DocumentPart(pdf),
        {"type": "text", "text": "speaking transcript"},
    ]
    assert count_learner_documents(parts) == 3
    assert count_learner_documents([pdf, AttachmentPart({"type": "text", "text": "notes.txt"})]) == 2
    assert count_learner_documents(None) == 0
