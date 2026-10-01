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
    _SECTION_KEYWORDS,
    _SECTION_LABELS,
)
from services.paper_visual.models import PaperVisualPlanItem, _PaperPageContext

logger = logging.getLogger(__name__)



def _sanitize_plan_items(
    raw_items: list[dict[str, Any]],
    pages: tuple[_PaperPageContext, ...],
    max_visuals: int,
    *,
    source: str,
) -> tuple[PaperVisualPlanItem, ...]:
    """Validate model plan output against available pages and bounds."""

    available_pages = {page.page_number for page in pages}
    selected: list[PaperVisualPlanItem] = []
    seen_pages: set[int] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            page_number = int(item.get("page_number"))
        except (TypeError, ValueError):
            continue
        if page_number not in available_pages or page_number in seen_pages:
            continue
        seen_pages.add(page_number)
        page = next((candidate_page for candidate_page in pages if candidate_page.page_number == page_number), None)
        selected.append(
            PaperVisualPlanItem(
                page_number=page_number,
                answer_section=_normalize_answer_section(
                    item.get("answer_section"),
                    visual_type=item.get("visual_type"),
                    target_caption=item.get("target_caption"),
                ),
                visual_type=_bounded_visual_type(item.get("visual_type")),
                target_caption=_bounded_target_caption(item.get("target_caption"), page),
                teaching_caption=_bounded_text(
                    item.get("teaching_caption"),
                    "這張圖是理解論文方法或結果的關鍵視覺線索。",
                    180,
                ),
                rationale=_bounded_text(item.get("rationale"), "planner_selected", 160),
                source=source,
            )
        )
        if len(selected) >= max_visuals:
            break
    return tuple(selected)


def _bounded_text(value: Any, fallback: str, max_length: int) -> str:
    """Return normalized bounded text for planner-owned metadata."""

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return (text or fallback)[:max_length]


def _normalize_answer_section(
    value: Any,
    *,
    visual_type: Any = "",
    target_caption: Any = "",
) -> str:
    """Map model-produced placement labels to stable paper sections.

        Args:
            value: Raw planner ``answer_section`` value, which may contain
                internal labels such as ``model``.
            visual_type: Optional visual-purpose label used as a secondary
                signal when the section text is underspecified.
            target_caption: Optional caption text selected by the planner.

        Returns:
            One of the bounded Traditional Chinese section labels used by the
            paper explanation UI and prompt inventory.

        Side Effects:
            None. This validation boundary prevents arbitrary model labels from
            leaking into user-facing attachment captions.
        """

    raw_text = _bounded_text(value, "", 80)
    if raw_text in _SECTION_LABELS:
        return raw_text
    normalized = f"{raw_text} {visual_type or ''} {target_caption or ''}".lower()
    for label, keywords in _SECTION_KEYWORDS:
        if any(keyword in normalized for keyword in keywords):
            return label
    return "論文重點圖解"


def _bounded_visual_type(value: Any) -> str:
    """Return allowlisted visual purpose label."""

    visual_type = str(value or "").strip().lower()
    allowed = {
        "architecture",
        "method_diagram",
        "results_chart",
        "results_table",
        "main_results_table",
        "ablation_table",
        "mechanism",
        "other",
    }
    return visual_type if visual_type in allowed else "other"


def _bounded_target_caption(value: Any, page: _PaperPageContext | None) -> str:
    """Return a caption that is present or plausibly represented on the page."""

    text = _bounded_text(value, "", 220)
    if not text or page is None:
        return ""
    normalized_text = _normalize_caption_match_text(text)
    for caption in page.captions:
        normalized_caption = _normalize_caption_match_text(caption)
        if normalized_text in normalized_caption or normalized_caption in normalized_text:
            return caption[:220]
    return text


def _normalize_caption_match_text(value: str) -> str:
    """Normalize caption text for conservative planner-output validation."""

    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value.lower()).strip()
