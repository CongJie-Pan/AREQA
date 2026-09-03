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


def make_multi_caption_page_pdf() -> bytes:
    """Create one page with two captioned visuals to test target matching."""

    document = fitz.open()
    page = document.new_page(width=360, height=420)
    page.draw_rect(fitz.Rect(40, 55, 300, 125), color=(0, 0, 0), width=1)
    page.insert_text((42, 150), "Figure 1. Model architecture", fontsize=12)
    page.draw_rect(fitz.Rect(40, 245, 300, 325), color=(0, 0, 0), width=1)
    page.draw_line((60, 310), (280, 255), color=(0, 0, 1), width=2)
    page.insert_text((42, 350), "Table 2. BLEU results on translation benchmarks", fontsize=12)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def make_cultureconverse_like_pdf() -> bytes:
    """Create a paper-like PDF with overview, dataset, and result captions."""

    document = fitz.open()
    page_1 = document.new_page(width=520, height=420)
    page_1.insert_text((36, 32), "Evaluation Method simulation pipeline and role visibility.", fontsize=10)
    page_1.draw_rect(fitz.Rect(50, 62, 460, 150), color=(0, 0, 0), width=1)
    page_1.insert_text(
        (52, 178),
        "Figure 1: CULTURECONVERSE pipeline expands seeds into blueprints and turn shards.",
        fontsize=10,
    )
    page_1.draw_rect(fitz.Rect(50, 240, 460, 300), color=(0, 0, 0), width=1)
    page_1.insert_text((52, 328), "Table 1: Role-specific visibility during simulation and evaluation.", fontsize=10)

    page_2 = document.new_page(width=520, height=420)
    page_2.insert_text((36, 32), "Experiments dataset statistics and identity breakdown.", fontsize=10)
    page_2.draw_rect(fitz.Rect(50, 72, 460, 210), color=(0, 0, 0), width=1)
    page_2.insert_text((52, 238), "Table 2: Dataset composition and regional identity breakdown.", fontsize=10)

    page_3 = document.new_page(width=520, height=420)
    page_3.insert_text((36, 32), "Results aggregate performance TDQ 3H benchmark.", fontsize=10)
    page_3.draw_rect(fitz.Rect(50, 72, 460, 210), color=(0, 0, 0), width=1)
    page_3.insert_text((52, 238), "Table 4: Aggregate results across evaluated models.", fontsize=10)

    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def make_llm_rubric_like_pdf() -> bytes:
    """Create a PDF shaped like method, judge setup, main results, and ablation."""

    document = fitz.open()
    for index in range(1, 9):
        page = document.new_page(width=520, height=420)
        page.insert_text((36, 32), f"Page {index}", fontsize=9)
        if index == 2:
            page.insert_text((36, 54), "Method framework rubric modeling architecture.", fontsize=10)
            page.draw_rect(fitz.Rect(50, 82, 460, 185), color=(0, 0, 0), width=1)
            page.insert_text((52, 214), "Figure 1. Overview of the LLM-Rubric framework.", fontsize=10)
        elif index == 3:
            page.insert_text((36, 54), "Experiment design dataset and different human judges.", fontsize=10)
            page.draw_rect(fitz.Rect(50, 82, 460, 210), color=(0, 0, 0), width=1)
            page.insert_text((52, 238), "Figure 2. Marginal distributions assigned by different human judges.", fontsize=10)
        elif index == 5:
            page.insert_text((36, 54), "Method qualitative examples and implementation details.", fontsize=10)
            page.draw_rect(fitz.Rect(50, 82, 460, 210), color=(0, 0, 0), width=1)
            page.insert_text((52, 238), "Table 1. Example rubric annotations for one scored episode.", fontsize=10)
        elif index == 7:
            page.insert_text((36, 54), "Results performance predicting overall quality human judges.", fontsize=10)
            page.draw_rect(fitz.Rect(50, 82, 460, 210), color=(0, 0, 0), width=1)
            page.insert_text((52, 238), "Table 1. Performance in predicting overall quality from human judges.", fontsize=10)
        elif index == 8:
            page.insert_text((36, 54), "Ablation results design decisions rubric dimension.", fontsize=10)
            page.draw_rect(fitz.Rect(50, 82, 460, 210), color=(0, 0, 0), width=1)
            page.insert_text((52, 238), "Table 2. Ablation study on rubric dimensions and design decisions.", fontsize=10)

    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def make_fragmented_table_pdf() -> bytes:
    """Create a PDF table represented by many independent drawing rectangles."""

    document = fitz.open()
    page = document.new_page(width=360, height=360)
    page.insert_text((36, 28), "Dataset composition table.", fontsize=9)
    for y in range(70, 191, 24):
        page.draw_line((52, y), (302, y), color=(0, 0, 0), width=1)
    for x in (52, 135, 220, 302):
        page.draw_line((x, 70), (x, 190), color=(0, 0, 0), width=1)
    page.insert_text((54, 220), "Table 2: Dataset composition for benchmark splits.", fontsize=11)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def make_sparse_rule_table_pdf() -> bytes:
    """Create a sparse-rule table like ablation tables in two-column papers."""

    document = fitz.open()
    page = document.new_page(width=520, height=620)
    page.insert_text((330, 72), "Oracle access analysis in the right column.", fontsize=10)
    for y in (70, 86, 262):
        page.draw_line((70, y), (290, y), color=(0, 0, 0), width=1)
    page.insert_text((72, 102), "w/o Q2 0.471 0.279", fontsize=9)
    page.insert_text((72, 126), "w/o Q3 0.573 0.075", fontsize=9)
    page.insert_text((72, 150), "w/o Q4 0.497 0.311", fontsize=9)
    page.insert_text(
        (70, 284),
        "Table 2: Predicting Q0: Ablation study on real conversation data.",
        fontsize=10,
    )
    for y in (346, 374, 484):
        page.draw_line((70, y), (290, y), color=(0, 0, 0), width=1)
    page.draw_line((194, 346), (194, 484), color=(0, 0, 0), width=1)
    page.insert_text((72, 404), "Expected LLM Qi RMSE", fontsize=9)
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
                            '"target_caption":"Table 2. BLEU results on translation benchmarks",'
                            '"teaching_caption":"這張表呈現 BLEU 結果，是理解論文實驗主張的關鍵。",'
                            '"rationale":"results_table_carries_main_evidence"}]}'
                        )
                    )
                )
            ]
        )


class _LooseSectionPlannerClient:
    """Chat-completions fake that returns a raw model-oriented section label."""

    def __init__(self) -> None:
        """Initialize the OpenAI-compatible fake shape."""

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        """Return planner output that needs section normalization."""

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"selected_visuals":[{"page_number":1,'
                            '"answer_section":"model",'
                            '"visual_type":"architecture",'
                            '"target_caption":"Figure 1. Model architecture",'
                            '"teaching_caption":"這張圖呈現方法架構。",'
                            '"rationale":"core_method_diagram"}]}'
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
    assert plan[0].target_caption.startswith("Table 2")
    assert plan[0].source == "model"
    assert "BLEU" in plan[0].teaching_caption
    assert client.calls[0]["model"]
    assert "paper_visual.planner_completed" in caplog.text
    assert "source=model" in caplog.text
    assert "pages=2" in caplog.text


@pytest.mark.asyncio
async def test_paper_visual_planner_normalizes_model_section_label():
    """Planner output should not expose raw internal section labels."""

    service = PaperVisualPlannerService(timeout_seconds=1.0)

    plan = await service.plan_visuals(
        pdf_bytes=make_two_page_paper_pdf(),
        filename="paper.pdf",
        conversation_id="section-conversation",
        client=_LooseSectionPlannerClient(),
        max_visuals=1,
    )

    assert len(plan) == 1
    assert plan[0].answer_section == "研究方法"


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
    assert plan[0].target_caption.startswith("Table 2")
    assert "source=fallback" in caplog.text


@pytest.mark.asyncio
async def test_paper_visual_planner_fallback_prefers_overview_caption_for_broad_explanation():
    """Broad fallback planning should not replace a pipeline figure with a nearby table."""

    service = PaperVisualPlannerService()

    plan = await service.plan_visuals(
        pdf_bytes=make_cultureconverse_like_pdf(),
        filename="cultureconverse.pdf",
        conversation_id="culture-fallback-conversation",
        client=None,
        max_visuals=3,
    )

    assert [item.answer_section for item in plan] == ["研究方法", "實驗設計與過程", "實驗結果"]
    assert plan[0].page_number == 1
    assert plan[0].visual_type == "architecture"
    assert plan[0].target_caption.startswith("Figure 1")
    assert "pipeline" in plan[0].target_caption
    assert plan[1].target_caption.startswith("Table 2")
    assert plan[2].target_caption.startswith("Table 4")


@pytest.mark.asyncio
async def test_paper_visual_planner_fallback_keeps_section_coverage_and_ablation():
    """Broad fallback planning should reserve slots for setup, main results, and ablation."""

    service = PaperVisualPlannerService()

    plan = await service.plan_visuals(
        pdf_bytes=make_llm_rubric_like_pdf(),
        filename="llm-rubric.pdf",
        conversation_id="llm-rubric-fallback-conversation",
        client=None,
        max_visuals=4,
    )

    assert [item.page_number for item in plan] == [2, 3, 7, 8]
    assert [item.answer_section for item in plan] == [
        "研究方法",
        "實驗設計與過程",
        "實驗結果",
        "實驗結果",
    ]
    assert plan[2].visual_type == "main_results_table"
    assert plan[3].visual_type == "ablation_table"


def test_pdf_visual_extraction_respects_planner_page_order():
    """Renderer should render planner-selected pages before heuristic pages."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=2, render_zoom=1.0)
    plan = (
        PaperVisualPlanItem(
            page_number=2,
            answer_section="實驗結果與關鍵數據",
            visual_type="results_table",
            target_caption="Table 2. BLEU results on translation benchmarks",
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
    assert candidates[0].crop_reason == "target_caption_visual_cluster"
    assert candidates[0].visual_type == "results_table"
    assert candidates[0].target_caption.startswith("Table 2")
    assert "BLEU" in candidates[0].teaching_caption
    block = candidates[0].to_image_block()
    assert block.caption.startswith("Table 2")
    assert block.explanatory_caption == ""
    assert block.placement_section == "實驗結果與關鍵數據"
    assert "理解論文實驗主張" in block.planner_hint
    assert "這張圖適合用來說明" not in block.caption
    assert "建議放在" not in block.caption


def test_pdf_visual_extraction_crops_planner_target_caption_on_multi_caption_page():
    """Renderer should prefer the planner-selected caption on pages with multiple visuals."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1, render_zoom=1.0)
    plan = (
        PaperVisualPlanItem(
            page_number=1,
            answer_section="實驗結果與關鍵數據",
            visual_type="results_table",
            target_caption="Table 2. BLEU results on translation benchmarks",
            teaching_caption="這張表呈現 BLEU 結果，是理解論文實驗主張的關鍵。",
            rationale="target_caption_disambiguates_same_page_visuals",
        ),
    )

    candidates = service.extract_candidates(
        pdf_bytes=make_multi_caption_page_pdf(),
        filename="paper.pdf",
        conversation_id="target-caption-conversation",
        visual_plan=plan,
    )

    assert len(candidates) == 1
    assert candidates[0].crop_reason == "target_caption_visual_cluster"
    assert candidates[0].target_caption.startswith("Table 2")
    assert candidates[0].height < 180


def test_pdf_visual_extraction_keeps_full_table_cluster_for_target_caption():
    """Targeted table crops should keep the table body instead of the nearest row only."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1, render_zoom=1.0)
    plan = (
        PaperVisualPlanItem(
            page_number=1,
            answer_section="實驗設計與過程",
            visual_type="results_table",
            target_caption="Table 2: Dataset composition for benchmark splits.",
            teaching_caption="這張表呈現資料集組成。",
            rationale="table_cluster_crop",
        ),
    )

    candidates = service.extract_candidates(
        pdf_bytes=make_fragmented_table_pdf(),
        filename="paper.pdf",
        conversation_id="fragmented-table-conversation",
        visual_plan=plan,
    )

    assert len(candidates) == 1
    assert candidates[0].crop_reason == "target_caption_visual_cluster"
    assert candidates[0].target_caption.startswith("Table 2")
    assert candidates[0].height >= 175


def test_pdf_visual_extraction_keeps_sparse_table_rules_above_target_caption():
    """Sparse table crops should not collapse to the nearest line or right column."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1, render_zoom=1.0)
    plan = (
        PaperVisualPlanItem(
            page_number=1,
            answer_section="實驗結果與消融分析",
            visual_type="ablation_table",
            target_caption="Table 2: Predicting Q0: Ablation study on real conversation data.",
            teaching_caption="這張表呈現消融結果。",
            rationale="sparse_table_rules_crop",
        ),
    )

    candidates = service.extract_candidates(
        pdf_bytes=make_sparse_rule_table_pdf(),
        filename="paper.pdf",
        conversation_id="sparse-table-conversation",
        visual_plan=plan,
    )

    assert len(candidates) == 1
    assert candidates[0].crop_reason == "target_caption_visual_cluster"
    assert candidates[0].target_caption.startswith("Table 2")
    assert candidates[0].height >= 240
    assert candidates[0].width < 330


def test_pdf_visual_extraction_falls_back_when_target_caption_does_not_match():
    """Invalid model captions must not prevent deterministic crop fallback."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1, render_zoom=1.0)
    plan = (
        PaperVisualPlanItem(
            page_number=1,
            answer_section="方法與模型架構",
            visual_type="architecture",
            target_caption="Nonexistent Figure 99. Hallucinated caption",
            teaching_caption="這張圖呈現模型架構。",
            rationale="bad_model_caption",
        ),
    )

    candidates = service.extract_candidates(
        pdf_bytes=make_multi_caption_page_pdf(),
        filename="paper.pdf",
        conversation_id="target-caption-fallback",
        visual_plan=plan,
    )

    assert len(candidates) == 1
    assert candidates[0].crop_reason == "caption_visual_cluster"
    assert candidates[0].target_caption.startswith("Nonexistent Figure 99")
