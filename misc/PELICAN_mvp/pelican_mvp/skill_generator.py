"""Domain skill generation boundary for PELICAN learning plans."""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from .domain_catalog import resolve_domain_category
from .domain_skill import DomainCategory, DomainSkill, SkillLifecycle
from .llm import LlmAdapter, LlmUnavailable
from .observability import log_event
from .skill_loader import SkillLoadError, load_catalog_skill
from .skill_validator import SkillValidationError, validate_domain_skill


class SkillGenerationError(RuntimeError):
    """Raised when neither catalog nor bounded model generation yields a skill."""


class DomainSkillGenerator:
    """Resolve, generate, and validate domain skills before compilation.

    Checked-in catalog assets are preferred because they are deterministic and
    reviewable. Model generation is bounded to one retry after validation failure;
    raw model output and hidden reasoning are never logged or persisted.
    """

    def __init__(self, llm: LlmAdapter | None = None, *, max_retries: int = 1):
        self.llm = llm or LlmAdapter()
        self.max_retries = max_retries

    def generate(self, topic: str, *, force_regenerate: bool = False) -> tuple[DomainSkill, str]:
        """Return a validated skill and safe route slug for the learner topic."""
        topic_clean = re.sub(r"\s+", " ", topic).strip()[:100] or "預設主題"
        resolution = resolve_domain_category(topic_clean)
        log_event(
            "pelican_skill_route_selected",
            domain_category=resolution.category.value,
            route=resolution.route_slug,
            model_route=self.llm.model_route_for_category(resolution.category) if self.llm.available else "offline",
            reason_code=resolution.reason_code,
        )

        if not force_regenerate:
            try:
                skill = load_catalog_skill(topic_clean)
                log_event(
                    "pelican_skill_source_selected",
                    skill_id=skill.skill_id,
                    skill_version=skill.version,
                    domain_category=skill.domain_category.value,
                    skill_lifecycle=skill.lifecycle.value,
                    route="catalog",
                    skill_source="catalog",
                    reason_code="catalog_skill_available",
                )
                return skill, "catalog"
            except SkillLoadError:
                log_event(
                    "pelican_skill_generation_fallback",
                    domain_category=resolution.category.value,
                    route=resolution.route_slug,
                    skill_source="catalog_unavailable",
                    reason_code="catalog_unavailable",
                )

        if resolution.category is DomainCategory.UNKNOWN:
            raise SkillGenerationError("unknown domain requires clarification")
        if not self.llm.available:
            raise SkillGenerationError("LLM unavailable")

        route = self.llm.model_route_for_category(resolution.category)
        last_error = "unknown"
        for attempt in range(self.max_retries + 1):
            log_event(
                "pelican_skill_generation_attempt",
                domain_category=resolution.category.value,
                route=route,
                model_route=route,
                skill_source="runtime_generation",
                reason_code=f"attempt_{attempt + 1}",
            )
            try:
                generated = self.llm.generate_domain_skill(topic_clean, resolution.category, model_route=route)
                if generated is None:
                    raise SkillGenerationError("empty skill")
                skill = _normalize_generated_skill(generated, resolution.category)
                validate_domain_skill(skill)
                log_event(
                    "pelican_skill_generated",
                    skill_id=skill.skill_id,
                    skill_version=skill.version,
                    skill_lifecycle=skill.lifecycle.value,
                    domain_category=skill.domain_category.value,
                    route=route,
                    model_route=route,
                    skill_source="runtime_generated",
                    reason_code="validated",
                )
                return skill, route
            except (LlmUnavailable, SkillValidationError, ValueError, TypeError, SkillGenerationError) as exc:
                last_error = type(exc).__name__
                log_event(
                    "pelican_skill_validation_rejected",
                    level=logging.WARNING,
                    domain_category=resolution.category.value,
                    route=route,
                    reason_code=last_error,
                )
                if attempt < self.max_retries:
                    log_event(
                        "pelican_skill_generation_retry",
                        domain_category=resolution.category.value,
                        route=route,
                        reason_code=last_error,
                    )

        raise SkillGenerationError(f"skill generation failed: {last_error}")


def _normalize_generated_skill(skill: DomainSkill, category: DomainCategory) -> DomainSkill:
    lifecycle = (
        SkillLifecycle.VALIDATED_GENERATED
        if skill.lifecycle is SkillLifecycle.APPROVED
        else skill.lifecycle
    )
    if lifecycle is SkillLifecycle.RUNTIME_GENERATED:
        lifecycle = SkillLifecycle.VALIDATED_GENERATED
    return replace(skill, domain_category=category, lifecycle=lifecycle)
