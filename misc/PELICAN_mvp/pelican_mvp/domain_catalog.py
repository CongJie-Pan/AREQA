"""Domain category and model-route resolution for the PELICAN skill runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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
        "歷史",
        "史學",
        "日本史",
        "世界史",
        "二戰",
        "第二次世界大戰",
        "戰後",
        "明治維新",
        "政治史",
        "社會史",
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
        "諸子百家",
        "百家爭鳴",
        "道家",
        "儒家",
        "墨家",
        "法家",
        "名家",
        "陰陽家",
        "兵家",
        "老子",
        "莊子",
        "孔子",
        "孟子",
        "荀子",
        "韓非子",
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


def resolve_domain_category(topic: str, *, artifact_root: Path | None = None) -> DomainResolution:
    """Resolve a learner topic to a stable MVP domain category or clarification.

    Args:
        topic: Learner-provided topic text.
        artifact_root: Optional runtime skill artifact root used by tests and
            local deployments. Deterministic aliases still take precedence.

    Returns:
        A bounded domain resolution. When aliases cannot classify the topic, a
        highly relevant validated runtime skill may supply the domain category
        before the system asks the learner for clarification.
    """
    normalized = _normalize_topic(topic)
    for category, aliases in _TOPIC_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return DomainResolution(
                category=category,
                route_slug=resolve_model_route(category),
                reason_code="matched_topic_alias",
                needs_clarification=False,
            )
    try:
        from .skill_artifacts import SkillArtifactError, find_relevant_validated_skill_artifact_any_category

        skill = find_relevant_validated_skill_artifact_any_category(topic=normalized, root=artifact_root)
        return DomainResolution(
            category=skill.domain_category,
            route_slug=resolve_model_route(skill.domain_category),
            reason_code="matched_validated_skill_artifact",
            needs_clarification=False,
        )
    except (SkillArtifactError, ValueError, TypeError):
        pass
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
