"""Tests for semantic PDF paper visual planning."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.paper_visual_planner_service import (
    PaperVisualPlanItem,
    PaperVisualPlannerService,
)
from backend.services.pdf_visual_extraction_service import PdfVisualExtractionService


fitz = pytest.importorskip("fitz")


def make_two_page_paper_pdf() -> bytes:
    """Create a small paper-like PDF with method and results visuals."""

    document = fitz.open()
    page_1 = document.new_page(width=360, height=260)
    page_1.insert_text((36, 32), "Method Architecture The model uses attention layers.", fontsize=10)
    page_1.draw_rect(fitz.Rect(40, 70, 300, 170), color=(0, 0, 0), width=1)
    page_1.insert_text((42, 200), "Figure 1. Model architecture", fontsize=12)

    page_2 = document.new_page(width=360, height=260)
    page_2.insert_text((36, 32), "Results Experiments BLEU accuracy evaluation benchmark.", fontsize=10)
    page_2.draw_rect(fitz.Rect(40, 72, 300, 178), color=(0, 0, 0), width=1)
    page_2.draw_line((60, 160), (280, 90), color=(0, 0, 1), width=2)
    page_2.insert_text((42, 205), "Table 2. BLEU results on translation benchmarks", fontsize=12)

    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


class _FakePlannerClient:
    """Chat-completions fake that selects the results page."""

    def __init__(self) -> None:
        """Initialize recorded call metadata."""

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.calls: list[dict] = []

    async def _create(self, **kwargs):
        """Return deterministic strict JSON planner output."""

        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"selected_visuals":[{"page_number":2,'
                            '"answer_section":"實驗結果與關鍵數據",'
                            '"visual_type":"results_table",'
                            '"teaching_caption":"這張表呈現 BLEU 結果，是理解論文實驗主張的關鍵。",'
                            '"rationale":"results_table_carries_main_evidence"}]}'
                        )
                    )
                )
            ]
        )


@pytest.mark.asyncio
async def test_paper_visual_planner_model_selects_results_page(caplog):
    """The model planner should return sanitized visual plan items."""

    caplog.set_level("INFO")
    client = _FakePlannerClient()
    service = PaperVisualPlannerService(timeout_seconds=1.0)

    plan = await service.plan_visuals(
        pdf_bytes=make_two_page_paper_pdf(),
        filename="paper.pdf",
        conversation_id="planner-conversation",
        client=client,
        max_visuals=2,
    )

    assert len(plan) == 1
    assert plan[0].page_number == 2
    assert plan[0].visual_type == "results_table"
    assert plan[0].source == "model"
    assert "BLEU" in plan[0].teaching_caption
    assert client.calls[0]["model"]
    assert "paper_visual.planner_completed" in caplog.text
    assert "source=model" in caplog.text
    assert "pages=2" in caplog.text


@pytest.mark.asyncio
async def test_paper_visual_planner_fallback_prioritizes_results_page(caplog):
    """Fallback planning should prefer result-heavy pages when no client exists."""

    caplog.set_level("INFO")
    service = PaperVisualPlannerService()

    plan = await service.plan_visuals(
        pdf_bytes=make_two_page_paper_pdf(),
        filename="paper.pdf",
        conversation_id="fallback-conversation",
        client=None,
        max_visuals=1,
    )

    assert len(plan) == 1
    assert plan[0].page_number == 2
    assert plan[0].source == "fallback"
    assert plan[0].visual_type in {"results_chart", "results_table"}
    assert "source=fallback" in caplog.text


def test_pdf_visual_extraction_respects_planner_page_order():
    """Renderer should render planner-selected pages before heuristic pages."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=2, render_zoom=1.0)
    plan = (
        PaperVisualPlanItem(
            page_number=2,
            answer_section="實驗結果與關鍵數據",
            visual_type="results_table",
            teaching_caption="這張表呈現 BLEU 結果，是理解論文實驗主張的關鍵。",
            rationale="results_table_carries_main_evidence",
        ),
    )

    candidates = service.extract_candidates(
        pdf_bytes=make_two_page_paper_pdf(),
        filename="paper.pdf",
        conversation_id="renderer-conversation",
        visual_plan=plan,
    )

    assert len(candidates) == 1
    assert candidates[0].page_number == 2
    assert candidates[0].selection_source == "planner"
    assert candidates[0].visual_type == "results_table"
    assert "BLEU" in candidates[0].teaching_caption
    assert "實驗結果" in candidates[0].to_image_block().explanatory_caption
    assert candidates[0].teaching_caption in candidates[0].to_image_block().explanatory_caption
