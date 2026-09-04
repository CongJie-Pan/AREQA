"""Deterministic visual affordances for educational image retrieval.

This module defines topic patterns that strongly imply a useful educational
visual even when the user does not explicitly ask for an image. It is shared by
visual query rewriting and fallback brief planning so both paths preserve the
same visual intent under model timeouts.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class VisualAffordance:
    """A reusable mapping from educational concepts to expected visuals.

    Args:
        rule_name: Stable rule identifier used in structured logs and tests.
        pattern: Compiled prompt/query pattern. It must avoid overbroad matches
            because rule hits can trigger paid provider preflight.
        search_query: Provider-ready English query with concrete visual terms.
        visual_type: Stable expected visual type used by grounding.
        query_suffix: Fallback suffix appended when the model planner is
            unavailable and the query still needs provider-facing visual terms.
        caption_goal: Pedagogical goal that grounds the image selection.
        reject_if: Candidate traits that should be rejected by grounding.
        preflight_trigger: Whether a rule hit is strong enough to attempt image
            preflight without an explicit visual keyword.
    """

    rule_name: str
    pattern: re.Pattern[str]
    search_query: str
    visual_type: str
    query_suffix: str
    caption_goal: str
    reject_if: tuple[str, ...]
    preflight_trigger: bool = True


_VISUAL_AFFORDANCES: tuple[VisualAffordance, ...] = (
    VisualAffordance(
        rule_name="meta_analysis_forest_plot",
        pattern=re.compile(r"\bmeta[-\s]?analysis\b|統合分析|元分析", re.IGNORECASE),
        search_query="meta analysis forest plot diagram",
        visual_type="forest_plot",
        query_suffix="forest plot meta analysis example",
        caption_goal=(
            "Help the learner connect individual study effect estimates, confidence intervals, "
            "and the pooled estimate in a meta-analysis forest plot."
        ),
        reject_if=(
            "wrong_visual_type",
            "not_meta_analysis",
            "decorative_or_generic_image",
            "product_photo",
            "shopping_page",
            "book_cover",
        ),
    ),
    VisualAffordance(
        rule_name="systematic_review_prisma",
        pattern=re.compile(
            r"\bsystematic review\b|系統性文獻回顧|系統性回顧",
            re.IGNORECASE,
        ),
        search_query="systematic review PRISMA flow diagram",
        visual_type="prisma_flow_diagram",
        query_suffix="PRISMA flow diagram systematic review",
        caption_goal=(
            "Help the learner see how records move through screening, eligibility, "
            "and inclusion."
        ),
        reject_if=(
            "wrong_visual_type",
            "not_prisma_diagram",
            "decorative_or_generic_image",
            "product_photo",
            "shopping_page",
            "book_cover",
        ),
    ),
    VisualAffordance(
        rule_name="roc_auc_curve",
        pattern=re.compile(
            r"\bROC\b|\bAUC\b|receiver operating characteristic|受試者工作特徵|曲線下面積",
            re.IGNORECASE,
        ),
        search_query="ROC curve AUC diagnostic test graph",
        visual_type="roc_curve",
        query_suffix="ROC curve AUC diagnostic test graph",
        caption_goal=(
            "Help the learner interpret sensitivity, specificity, and the area under "
            "the ROC curve."
        ),
        reject_if=(
            "wrong_visual_type",
            "not_roc_curve",
            "decorative_or_generic_image",
            "product_photo",
            "shopping_page",
            "book_cover",
        ),
    ),
    VisualAffordance(
        rule_name="kaplan_meier_survival_curve",
        pattern=re.compile(
            r"Kaplan[-\s]?Meier|survival curve|存活曲線|生存曲線",
            re.IGNORECASE,
        ),
        search_query="Kaplan Meier survival curve example",
        visual_type="survival_curve",
        query_suffix="Kaplan Meier survival curve example",
        caption_goal=(
            "Help the learner see survival probability over time and compare groups "
            "on the curve."
        ),
        reject_if=(
            "wrong_visual_type",
            "not_survival_curve",
            "decorative_or_generic_image",
            "product_photo",
            "shopping_page",
            "book_cover",
        ),
    ),
    VisualAffordance(
        rule_name="funnel_plot_publication_bias",
        pattern=re.compile(
            r"funnel plot|publication bias|漏斗圖|發表偏倚|出版偏倚",
            re.IGNORECASE,
        ),
        search_query="funnel plot publication bias meta analysis diagram",
        visual_type="funnel_plot",
        query_suffix="funnel plot publication bias meta analysis",
        caption_goal=(
            "Help the learner understand study-size asymmetry and publication bias "
            "in a funnel plot."
        ),
        reject_if=(
            "wrong_visual_type",
            "not_funnel_plot",
            "decorative_or_generic_image",
            "product_photo",
            "shopping_page",
            "book_cover",
        ),
    ),
)


def match_visual_affordance(text: str) -> VisualAffordance | None:
    """Return the first deterministic visual affordance matching text.

    Args:
        text: User prompt, fallback query, or combined retrieval intent.

    Returns:
        A matching affordance, or ``None`` when the text has no known visual
        affordance. The function performs no logging because callers own their
        privacy boundary and correlation identifiers.
    """

    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        return None
    for affordance in _VISUAL_AFFORDANCES:
        if affordance.pattern.search(normalized):
            return affordance
    return None
