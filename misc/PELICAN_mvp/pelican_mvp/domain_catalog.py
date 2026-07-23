"""Domain category and model-route resolution for the PELICAN skill runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .domain_skill import DomainCategory


@dataclass(frozen=True)
class DomainResolution:
    """A safe routing result for topic intake before skill loading."""

    category: DomainCategory
    route_slug: str
    reason_code: str
    needs_clarification: bool = False


MODEL_ROUTE_CONFIG = {
    # Reference: docs/tech_docs/API_model_docs/GPT-5.5_-_API_Pricing_&_Benchmarks_OpenRouter.md
    DomainCategory.STEM: "openrouter_gpt_5_5",
    # Reference: docs/tech_docs/API_model_docs/Google_Gemini_Pro_Latest_-_API_Pricing_&_Benchmarks_OpenRouter.md
    DomainCategory.HUMANITIES: "openrouter_gemini_pro_latest",
    DomainCategory.BUSINESS: "openrouter_gemini_pro_latest",
    DomainCategory.LANGUAGE: "openrouter_gemini_pro_latest",
}

_TOPIC_ALIASES: dict[DomainCategory, tuple[str, ...]] = {
    DomainCategory.STEM: (
        "深度學習",
        "機器學習",
        "線性代數",
        "微積分",
        "資料結構",
        "演算法",
        "python",
        "c語言",
        "c language",
        "deep learning",
        "machine learning",
        "linear algebra",
        "calculus",
        "data structures",
        "algorithms",
    ),
    DomainCategory.HUMANITIES: (
        "國學",
        "漢學",
        "歷史",
        "中國春秋時期歷史",
        "春秋時期",
        "春秋五霸",
        "諸侯爭霸",
        "周王室",
        "尊王攘夷",
        "禮崩樂壞",
        "戰國",
        "法律知識",
        "文學",
        "哲學",
        "藝術",
        "電影",
        "history",
        "law",
        "literature",
        "philosophy",
        "art",
        "film",
    ),
    DomainCategory.BUSINESS: ("商業", "金融", "business", "finance"),
    DomainCategory.LANGUAGE: ("語言學習", "language learning", "english", "英文", "日文", "日語"),
}


def resolve_domain_category(topic: str) -> DomainResolution:
    """Resolve a learner topic to a stable MVP domain category or clarification."""
    normalized = _normalize_topic(topic)
    for category, aliases in _TOPIC_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return DomainResolution(
                category=category,
                route_slug=resolve_model_route(category),
                reason_code="matched_topic_alias",
                needs_clarification=False,
            )
    return DomainResolution(
        category=DomainCategory.UNKNOWN,
        route_slug="clarify_before_routing",
        reason_code="unknown_domain",
        needs_clarification=True,
    )


def resolve_model_route(category: DomainCategory) -> str:
    """Return the configured route slug without asserting provider availability."""
    return MODEL_ROUTE_CONFIG.get(category, "clarify_before_routing")


def _normalize_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic).strip().lower()[:120]
