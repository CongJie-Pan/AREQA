"""Plan semantically useful visuals for automatic PDF paper explanations.

The planner reads a bounded structural map of an uploaded PDF and decides which
pages should be rendered as answer visuals. It may use a model for semantic
selection, but rendering and cropping remain owned by ``PdfVisualExtractionService``
so untrusted model output cannot directly control pixels or file system writes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from services.paper_visual.constants import (
    _ABLATION_CAPTION_TERMS,
    _DATASET_CAPTION_TERMS,
    _FALLBACK_SECTION_ORDER,
    _MAIN_RESULT_CAPTION_TERMS,
    _METHOD_TERMS,
    _OVERVIEW_CAPTION_TERMS,
    _REQUIRED_FALLBACK_SECTIONS,
    _RESULT_CAPTION_TERMS,
    _RESULT_TERMS,
)
from services.paper_visual.models import PaperVisualPlanItem, _PaperPageContext

logger = logging.getLogger(__name__)


from services.paper_visual.validation import _sanitize_plan_items


def _fallback_plan(
    pages: tuple[_PaperPageContext, ...],
    max_visuals: int,
) -> tuple[PaperVisualPlanItem, ...]:
    """Select section-diverse teaching visuals without model support.

        The fallback planner runs when the model planner times out or is
        unavailable, so it must be deterministic and cheap. Broad paper
        explanations are read in section order, therefore multiple-visual
        fallbacks prefer an overview/method caption before dataset/setup and
        result captions. Single-visual fallbacks preserve the older
        result-heavy behavior because one image is most useful when it carries
        the paper's key evidence.
        """

    scored = sorted(
        ((_fallback_page_score(page), page) for page in pages),
        key=lambda item: item[0],
        reverse=True,
    )
    if max_visuals <= 1:
        raw_items = [_fallback_item_for_page(page) for score, page in scored if score > 0]
        return _sanitize_plan_items(raw_items, pages, max_visuals, source="fallback")

    candidates = [
        (_fallback_item_for_page(page), page, score)
        for score, page in scored
        if score > 0
    ]
    raw_items: list[dict[str, Any]] = []
    seen_pages: set[int] = set()

    for section in _REQUIRED_FALLBACK_SECTIONS:
        section_candidates = [
            (item, page, score)
            for item, page, score in candidates
            if item["answer_section"] == section and page.page_number not in seen_pages
        ]
        if not section_candidates:
            continue
        item, page, _score = min(section_candidates, key=_fallback_candidate_rank)
        raw_items.append(item)
        seen_pages.add(page.page_number)
        if len(raw_items) >= max_visuals:
            break

    if len(raw_items) < max_visuals:
        fill_candidates = [
            (item, page, score)
            for item, page, score in candidates
            if page.page_number not in seen_pages
        ]
        for item, page, _score in sorted(fill_candidates, key=_fallback_fill_rank):
            raw_items.append(item)
            seen_pages.add(page.page_number)
            if len(raw_items) >= max_visuals:
                break
    return _sanitize_plan_items(raw_items, pages, max_visuals, source="fallback")


def _fallback_candidate_rank(
    item_with_page: tuple[dict[str, Any], _PaperPageContext, int],
) -> tuple[int, int, int, int]:
    """Rank fallback candidates by teaching section, visual specificity, score, and page."""

    item, page, score = item_with_page
    visual_type_priority = {
        "architecture": 0,
        "method_diagram": 1,
        "main_results_table": 0,
        "ablation_table": 1,
        "results_table": 2,
        "results_chart": 3,
        "mechanism": 4,
        "other": 8,
    }
    return (
        _FALLBACK_SECTION_ORDER.get(str(item.get("answer_section") or ""), 9),
        visual_type_priority.get(str(item.get("visual_type") or ""), 8),
        -score,
        page.page_number,
    )


def _fallback_fill_rank(
    item_with_page: tuple[dict[str, Any], _PaperPageContext, int],
) -> tuple[int, int, int]:
    """Rank extra fallback visuals after required section coverage is met."""

    item, page, score = item_with_page
    visual_type_priority = {
        "main_results_table": 0,
        "ablation_table": 1,
        "results_table": 2,
        "results_chart": 3,
        "architecture": 4,
        "method_diagram": 5,
        "mechanism": 6,
        "other": 8,
    }
    return (
        visual_type_priority.get(str(item.get("visual_type") or ""), 8),
        -score,
        page.page_number,
    )


def _fallback_item_for_page(page: _PaperPageContext) -> dict[str, Any]:
    """Build one deterministic planner item from the best caption on a page."""

    target_caption, answer_section, visual_type = _best_fallback_visual(page)
    teaching_caption = _fallback_teaching_caption(answer_section, visual_type)
    return {
        "page_number": page.page_number,
        "answer_section": answer_section,
        "visual_type": visual_type,
        "target_caption": target_caption,
        "teaching_caption": teaching_caption,
        "rationale": "fallback_ranked_by_caption_purpose_and_section_terms",
    }


def _best_fallback_visual(page: _PaperPageContext) -> tuple[str, str, str]:
    """Return ``(caption, section, visual_type)`` for a fallback page.

        The page text often contains references to many figures and tables.
        Caption-level selection prevents a nearby table reference from replacing
        a more useful overview figure on the same page.
        """

    for caption in page.captions:
        caption_text = caption.lower()
        if _is_figure_caption(caption_text) and any(term in caption_text for term in _OVERVIEW_CAPTION_TERMS):
            return caption, "研究方法", "architecture"
    for caption in page.captions:
        caption_text = caption.lower()
        if any(term in caption_text for term in _ABLATION_CAPTION_TERMS):
            visual_type = "ablation_table" if _is_table_caption(caption_text) else "results_chart"
            return caption, "實驗結果", visual_type
    for caption in page.captions:
        caption_text = caption.lower()
        if any(term in caption_text for term in _DATASET_CAPTION_TERMS):
            return caption, "實驗設計與過程", "results_table" if _is_table_caption(caption_text) else "other"
    for caption in page.captions:
        caption_text = caption.lower()
        if any(term in caption_text for term in _MAIN_RESULT_CAPTION_TERMS):
            visual_type = "main_results_table" if _is_table_caption(caption_text) else "results_chart"
            return caption, "實驗結果", visual_type
    for caption in page.captions:
        caption_text = caption.lower()
        if any(term in caption_text for term in _RESULT_CAPTION_TERMS):
            visual_type = "results_table" if _is_table_caption(caption_text) else "results_chart"
            return caption, "實驗結果", visual_type

    text = f"{page.section_hint} {' '.join(page.captions)} {page.text_excerpt}".lower()
    if any(term in text for term in _METHOD_TERMS):
        return _first_caption(page), "研究方法", "method_diagram"
    if any(term in text for term in _RESULT_TERMS):
        caption = _first_caption(page)
        return caption, "實驗結果", "results_table" if _is_table_caption(caption.lower()) else "results_chart"
    return _first_caption(page), "論文重點圖解", "other"


def _is_figure_caption(caption_text: str) -> bool:
    """Return whether normalized caption text names a figure."""

    return bool(re.search(r"\bfig(?:ure)?\.?\s*\d+|圖\s*\d+", caption_text, re.IGNORECASE))


def _is_table_caption(caption_text: str) -> bool:
    """Return whether normalized caption text names a table."""

    return bool(re.search(r"\btable\s*\d+|表\s*\d+", caption_text, re.IGNORECASE))


def _first_caption(page: _PaperPageContext) -> str:
    """Return the first detected caption or an empty target."""

    return page.captions[0] if page.captions else ""


def _fallback_teaching_caption(answer_section: str, visual_type: str) -> str:
    """Return a section-aware teaching caption for fallback visuals."""

    if answer_section == "研究方法":
        return "這張圖呈現論文的方法、架構或核心流程，適合先用來建立整體理解。"
    if answer_section == "實驗設計與過程":
        return "這張圖表呈現資料集、流程或實驗設定，適合用來理解研究如何被建構與執行。"
    if answer_section == "實驗結果":
        return "這張圖表承載論文的實驗結果或關鍵數據，適合用來說明模型表現與作者主張。"
    return "這張圖提供論文中的重要視覺線索，適合搭配段落說明快速理解重點。"


def _fallback_page_score(page: _PaperPageContext) -> int:
    """Return deterministic semantic score for a candidate page."""

    text = f"{page.section_hint} {' '.join(page.captions)} {page.text_excerpt}".lower()
    score = 0
    score += sum(6 for term in _RESULT_TERMS if term in text)
    score += sum(4 for term in _METHOD_TERMS if term in text)
    score += len(page.captions) * 5
    return score
