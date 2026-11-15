"""Latency guards for blocking PDF attachment visual preflight.

Production traces showed the attachment visual preflight blocking the first
answer token for ~17 s on a three-PDF turn: paper planner calls ran one PDF at a
time and vision understanding ran two images at a time with no shared budget.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import patch

import pytest

from backend.services.orchestration_service import OrchestrationService
from backend.services.output_image_service import OutputImageService
from backend.services.pdf_visual_extraction_service import PdfVisualCandidate
from backend.services.visual_understanding_agent import VisualUnderstandingResult
from services.paper_visual.planner import PaperVisualPlannerService
from services.pdf_visual.extraction import PdfVisualExtractionService


def _candidate(slot_id: str, page_number: int) -> PdfVisualCandidate:
    return PdfVisualCandidate(
        slot_id=slot_id,
        filename="paper.pdf",
        page_number=page_number,
        image_data_uri="data:image/png;base64,iVBORw0KGgo=",
        width=640,
        height=480,
        caption_hint=f"Figure {page_number}.",
        visual_score=8,
        sha256=f"sha-{page_number}",
        answer_section="實驗結果",
        visual_type="results_table",
        teaching_caption="這張表呈現主要結果。",
    )


class _SlowUnderstandingAgent:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    async def analyze(self, **kwargs):
        await asyncio.sleep(self.delay)
        return VisualUnderstandingResult(
            image_type="chart",
            summary="A chart.",
            visible_elements=("axis",),
            how_to_read=("Read the axis.",),
            confidence="high",
            source="vision_model",
        )


class _PassthroughStorage:
    async def persist_pdf_image_block(self, *, block, conversation_id):
        return block


@pytest.mark.asyncio
async def test_planner_calls_overlap_across_pdfs_while_rendering_stays_serial():
    """Three planner calls of 0.3 s must not add up to 0.9 s; rendering must not overlap."""

    lock = threading.Lock()
    active = 0
    peak = 0
    progress: list[tuple[str, int, int]] = []

    async def slow_plan(self, **kwargs):
        await asyncio.sleep(0.3)
        return ()

    def fake_extract(self, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return []

    sources = [{"filename": f"deck{i}.pdf", "pdf_bytes": b"%PDF-1.4"} for i in range(3)]
    with patch.object(PaperVisualPlannerService, "plan_visuals", slow_plan), \
         patch.object(PdfVisualExtractionService, "extract_candidates", fake_extract):
        started = time.monotonic()
        await OrchestrationService._extract_attachment_visual_candidates(
            sources,
            "latency-conv",
            model_client=object(),
            use_paper_visual_planner=True,
            on_progress=lambda step, current, total: progress.append((step, current, total)),
        )
        elapsed = time.monotonic() - started

    assert elapsed < 0.7, f"planner calls ran serially ({elapsed:.2f}s)"
    assert peak == 1
    assert progress[-1] == ("visual_planning", 3, 3)


@pytest.mark.asyncio
async def test_understanding_runs_all_selected_images_concurrently():
    """Four 0.2 s vision calls finish in about one call's time, not two batches."""

    progress: list[tuple[str, int, int]] = []
    service = OutputImageService(
        understanding_agent=_SlowUnderstandingAgent(0.2),
        attachment_image_storage_service=_PassthroughStorage(),
    )
    started = time.monotonic()
    blocks = await service.prepare_attachment_image_blocks(
        candidates=[_candidate(f"pdf_img_{i}", i) for i in range(1, 5)],
        user_msg="explain",
        conversation_id="latency-conv",
        model_client=object(),
        on_progress=lambda step, current, total: progress.append((step, current, total)),
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.35, f"understanding was batched ({elapsed:.2f}s)"
    assert len(blocks) == 4
    assert all(block.vision_source == "vision_model" for block in blocks.values())
    assert progress[-1] == ("visual_understanding", 4, 4)


@pytest.mark.asyncio
async def test_understanding_deadline_keeps_images_with_planner_captions(caplog):
    """A slow vision model must not hold the answer; images survive without enrichment."""

    caplog.set_level("INFO")
    service = OutputImageService(
        understanding_agent=_SlowUnderstandingAgent(2.0),
        attachment_image_storage_service=_PassthroughStorage(),
    )
    started = time.monotonic()
    blocks = await service.prepare_attachment_image_blocks(
        candidates=[_candidate(f"pdf_img_{i}", i) for i in range(1, 5)],
        user_msg="explain",
        conversation_id="latency-conv",
        model_client=object(),
        deadline=time.monotonic() + 0.2,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 0.6, f"deadline ignored ({elapsed:.2f}s)"
    assert len(blocks) == 4
    assert all("主要結果" in block.explanatory_caption for block in blocks.values())
    assert all(block.vision_source != "vision_model" for block in blocks.values())
    assert "reason=budget_exhausted" in caplog.text


@pytest.mark.asyncio
async def test_expired_deadline_skips_understanding_calls():
    calls = 0

    class _CountingAgent:
        async def analyze(self, **kwargs):
            nonlocal calls
            calls += 1
            return VisualUnderstandingResult(source="vision_model")

    service = OutputImageService(
        understanding_agent=_CountingAgent(),
        attachment_image_storage_service=_PassthroughStorage(),
    )
    blocks = await service.prepare_attachment_image_blocks(
        candidates=[_candidate("pdf_img_1", 1)],
        user_msg="explain",
        conversation_id="latency-conv",
        model_client=object(),
        deadline=time.monotonic() - 1,
    )

    assert calls == 0
    assert list(blocks) == ["pdf_img_1"]
