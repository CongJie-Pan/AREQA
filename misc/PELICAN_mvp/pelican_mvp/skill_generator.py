"""Domain skill generation boundary for PELICAN learning plans."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from pathlib import Path

from .domain_catalog import resolve_domain_category
from .domain_skill import DomainCategory, DomainSkill, DomainSkillError, SkillLifecycle
from .generic_skill import build_generic_domain_skill
from .llm import LlmAdapter, LlmUnavailable
from .observability import log_event
from .skill_artifacts import save_failed_skill_artifact, save_validated_skill_artifact
from .skill_loader import SkillLoadError, load_catalog_skill
from .skill_validator import SkillValidationError, validate_domain_skill


class SkillGenerationError(RuntimeError):
    """Raised when a topic cannot safely enter skill generation.

    This exception is reserved for cases that should not receive a generic
    fallback, such as an unknown domain requiring clarification. Known domains
    recover to a generic skill-backed route instead of raising.
    """


class DomainSkillGenerator:
    """Resolve, generate, and validate domain skills before compilation.

    Checked-in catalog assets are preferred because they are deterministic and
    reviewable. Model generation is bounded to one retry after validation failure;
    raw model output and hidden reasoning are never logged or persisted.
    """

    def __init__(self, llm: LlmAdapter | None = None, *, max_retries: int = 1, artifact_root: Path | None = None):
        """Initialize runtime skill generation dependencies.

        Args:
            llm: Optional adapter used for model-backed generation and repair.
            max_retries: Number of repair attempts after the first invalid
                generation. The default allows one repair pass.
            artifact_root: Optional test/deployment override for generated skill
                artifacts. ``None`` uses the MVP local data directory.
        """
        self.llm = llm or LlmAdapter()
        self.max_retries = max_retries
        self.artifact_root = artifact_root

    def generate(self, topic: str, *, force_regenerate: bool = False) -> tuple[DomainSkill, str]:
        """Return a validated skill and safe route slug for the learner topic.

        The pipeline is catalog-first, then runtime generation with bounded
        repair, then generic domain fallback. Critical structured logs emitted
        here use event names such as ``pelican_skill_generation_attempt``,
        ``pelican_skill_validation_rejected``, and
        ``pelican_skill_source_selected`` with safe category, route, source, and
        reason-code metadata only. Raw model output is never logged.

        Args:
            topic: Learner-requested topic. It is normalized and bounded before
                routing or artifact filename creation.
            force_regenerate: When true, skip catalog lookup and exercise the
                runtime generation path. Tests use this to verify repair logic.

        Returns:
            A ``DomainSkill`` plus a safe source/route string such as
            ``catalog``, ``runtime model route``, or ``generic:humanities``.

        Raises:
            SkillGenerationError: If the topic resolves to an unknown category
                that needs clarification before any safe fallback can be chosen.
        """
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
            # Known domains must stay skill-backed even offline; falling through
            # to the legacy planner would recreate the one-node-tree failure.
            return self._generic_fallback(topic_clean, resolution.category, resolution.route_slug, ("llm_unavailable",))

        route = self.llm.model_route_for_category(resolution.category)
        last_reason_codes: tuple[str, ...] = ("unknown",)
        last_payload: dict | None = None
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
                payload = self._generate_payload(
                    topic_clean,
                    resolution.category,
                    route,
                    repair_issues=last_reason_codes if attempt > 0 else (),
                )
                last_payload = payload
                if payload is None:
                    raise SkillGenerationError("empty skill")
                payload["domain_category"] = resolution.category.value
                payload["lifecycle"] = payload.get("lifecycle") or SkillLifecycle.RUNTIME_GENERATED.value
                generated = DomainSkill.from_dict(payload)
                skill = _normalize_generated_skill(generated, resolution.category)
                validate_domain_skill(skill)
                save_validated_skill_artifact(skill, topic=topic_clean, route=route, root=self.artifact_root)
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
            except (LlmUnavailable, SkillValidationError, DomainSkillError, ValueError, TypeError, SkillGenerationError) as exc:
                last_reason_codes = _reason_codes_for(exc)
                log_event(
                    "pelican_skill_validation_rejected",
                    level=logging.WARNING,
                    domain_category=resolution.category.value,
                    route=route,
                    reason_code="|".join(last_reason_codes),
                )
                if attempt < self.max_retries:
                    log_event(
                        "pelican_skill_generation_retry",
                        domain_category=resolution.category.value,
                        route=route,
                        reason_code="|".join(last_reason_codes),
                    )

        save_failed_skill_artifact(
            topic=topic_clean,
            category=resolution.category,
            route=route,
            reason_codes=last_reason_codes,
            payload=last_payload,
            root=self.artifact_root,
        )
        return self._generic_fallback(topic_clean, resolution.category, route, last_reason_codes)

    def _generate_payload(
        self,
        topic: str,
        category: DomainCategory,
        route: str,
        *,
        repair_issues: tuple[str, ...],
    ) -> dict | None:
        """Call the LLM payload API, retaining compatibility with older test doubles.

        Args:
            topic: Normalized topic sent to the model.
            category: Resolved category used for schema routing.
            route: Selected skill-generation model route.
            repair_issues: Validator reason codes from the previous attempt.

        Returns:
            Raw JSON-compatible skill payload, or ``None`` for an empty response.

        Compatibility:
            Older tests and adapters may only override ``generate_domain_skill``.
            The type check intentionally detects whether the newer payload API is
            overridden before falling back to the older structured method.
        """
        if type(self.llm).generate_domain_skill_payload is not LlmAdapter.generate_domain_skill_payload:
            return self.llm.generate_domain_skill_payload(
                topic,
                category,
                model_route=route,
                repair_issues=repair_issues,
            )
        generated = self.llm.generate_domain_skill(topic, category, model_route=route)
        return generated.to_dict() if generated else None

    def _generic_fallback(
        self,
        topic: str,
        category: DomainCategory,
        route: str,
        reason_codes: tuple[str, ...],
    ) -> tuple[DomainSkill, str]:
        """Return a deterministic skill-backed fallback instead of a legacy plan.

        Args:
            topic: Normalized topic that failed runtime generation.
            category: Known domain category used to choose the generic skill.
            route: Last attempted route, retained only for logging context.
            reason_codes: Final safe reason codes explaining why generation did
                not produce a validated skill.

        Returns:
            Generic domain ``DomainSkill`` plus a ``generic:<category>`` source.

        Side Effects:
            Emits ``pelican_skill_source_selected`` so terminal summaries can
            clearly show that the runtime did not silently use a legacy plan.
        """
        skill = build_generic_domain_skill(topic, category)
        validate_domain_skill(skill)
        log_event(
            "pelican_skill_source_selected",
            skill_id=skill.skill_id,
            skill_version=skill.version,
            domain_category=skill.domain_category.value,
            skill_lifecycle=skill.lifecycle.value,
            route=f"generic:{category.value}",
            skill_source="generic_domain_skill",
            reason_code="|".join(reason_codes),
        )
        return skill, f"generic:{category.value}"


def _normalize_generated_skill(skill: DomainSkill, category: DomainCategory) -> DomainSkill:
    """Normalize generated lifecycle/category metadata before validation."""
    lifecycle = (
        SkillLifecycle.VALIDATED_GENERATED
        if skill.lifecycle is SkillLifecycle.APPROVED
        else skill.lifecycle
    )
    if lifecycle is SkillLifecycle.RUNTIME_GENERATED:
        lifecycle = SkillLifecycle.VALIDATED_GENERATED
    return replace(skill, domain_category=category, lifecycle=lifecycle)


def _reason_codes_for(exc: Exception) -> tuple[str, ...]:
    """Extract stable safe reason codes from generation or validation errors."""
    if isinstance(exc, SkillValidationError):
        return tuple(issue.reason_code for issue in exc.issues) or ("validation_failed",)
    return (type(exc).__name__,)
