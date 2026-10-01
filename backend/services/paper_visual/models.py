"""Data contracts for paper visual planning.

``PaperVisualPlanItem`` is re-exported from
``services.paper_visual_planner_service`` for compatibility with orchestration
and tests. Field names and defaults are part of the internal planner/renderer
contract and should remain stable without coordinated tests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PaperVisualPlanItem:
    """One model- or fallback-selected visual target for a PDF paper answer.

    Args:
        page_number: One-based page number to render.
        answer_section: Paper-explanation section where the visual should be
            introduced by the main answer model.
        visual_type: Bounded purpose label such as ``architecture`` or
            ``results_table``.
        target_caption: Exact or near-exact figure/table caption from the page
            map. The renderer uses this only for deterministic caption matching;
            it is never treated as geometry.
        teaching_caption: Short user-facing explanation of why this visual helps
            understand the paper.
        rationale: Internal bounded reason for logs/tests and prompt inventory.
        source: ``model`` or ``fallback``.

    Side Effects:
        None.
    """

    page_number: int
    answer_section: str
    visual_type: str
    teaching_caption: str
    rationale: str
    source: str = "model"
    target_caption: str = ""


@dataclass(frozen=True, slots=True)
class _PaperPageContext:
    """Bounded text metadata for one PDF page used by the planner."""

    page_number: int
    text_excerpt: str
    captions: tuple[str, ...]
    section_hint: str
