"""Domain skill generation boundary for PELICAN learning plans."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .domain_catalog import resolve_domain_category
from .domain_skill import DomainCategory, DomainSkill, DomainSkillError, SkillLifecycle
from .generic_skill import build_generic_domain_skill
from .llm import LlmAdapter, LlmUnavailable
from .observability import log_event
from .models import ProposalValidationStatus
from .skill_artifacts import (
    SkillArtifactError,
    load_validated_skill_artifact,
    save_failed_skill_artifact,
    save_validated_skill_artifact,
)
from .skill_loader import SkillLoadError, load_catalog_skill
from .skill_validator import SkillValidationError, validate_domain_skill


class SkillGenerationError(RuntimeError):
    """Raised when a topic cannot safely enter skill generation.

    This exception is reserved for cases that should not receive a generic
        fallback, such as an unknown domain requiring clarification. Known domains
        recover to a generic skill-backed route instead of raising.
    """


@dataclass(frozen=True)
class SkillGenerationAttempt:
    """Safe metadata for one skill-generation proposal attempt."""

    attempt_index: int
    route: str
    validation_status: ProposalValidationStatus
    reason_code: str


@dataclass(frozen=True)
class SkillGenerationResult:
    """Structured skill-generation result including safe attempt metadata."""

    skill: DomainSkill
    route: str
    attempts: tuple[SkillGenerationAttempt, ...]
    used_fallback: bool
    final_reason_code: str


class DomainSkillGenerator:
    """Resolve, generate, and validate domain skills before compilation.

    Checked-in catalog assets are preferred because they are deterministic and
    reviewable. Previously validated runtime artifacts are reused before a new
    model call. Model generation is then bounded to a small repair loop after
    validation failure; raw model output and hidden reasoning are never logged or
    persisted.
    """

    def __init__(self, llm: LlmAdapter | None = None, *, max_retries: int = 3, artifact_root: Path | None = None):
        """Initialize runtime skill generation dependencies.

        Args:
            llm: Optional adapter used for model-backed generation and repair.
            max_retries: Number of repair attempts after the first invalid
                generation. The default allows three repair passes, which is
                enough for schema correction while keeping latency and API cost
                bounded.
            artifact_root: Optional test/deployment override for generated skill
                artifacts. ``None`` uses the MVP local data directory.
        """
        self.llm = llm or LlmAdapter()
        self.max_retries = max_retries
        self.artifact_root = artifact_root

    def generate(self, topic: str, *, force_regenerate: bool = False) -> tuple[DomainSkill, str]:
        """Return the historical tuple contract for existing planner callers."""
        result = self.generate_with_result(topic, force_regenerate=force_regenerate)
        return result.skill, result.route

    def generate_with_result(self, topic: str, *, force_regenerate: bool = False) -> SkillGenerationResult:
        """Return a validated skill and safe route slug for the learner topic.

        The pipeline is catalog-first, cached validated runtime artifact, runtime
        generation with bounded repair, then generic domain fallback. Critical
        structured logs emitted here use event names such as
        ``pelican_skill_cache_hit``, ``pelican_skill_generation_attempt``,
        ``pelican_skill_validation_rejected``, and
        ``pelican_skill_source_selected`` with safe category, route, source, and
        reason-code metadata only. Raw model output is never logged.

        Args:
            topic: Learner-requested topic. It is normalized and bounded before
                routing or artifact filename creation.
            force_regenerate: When true, skip catalog/cache lookup and exercise
                the runtime generation path. Tests use this to verify repair
                logic.

        Returns:
            A ``DomainSkill`` plus a safe source/route string such as
            ``catalog``, ``runtime model route``, or ``generic:humanities``.

        Raises:
            SkillGenerationError: If the topic resolves to an unknown category
                that needs clarification before any safe fallback can be chosen.
        """
        topic_clean = re.sub(r"\s+", " ", topic).strip()[:100] or "預設主題"
        started_at = time.monotonic()
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
                _log_generation_summary(
                    started_at,
                    route="catalog",
                    category=skill.domain_category,
                    skill_id=skill.skill_id,
                    attempt_count=1,
                    rejected_count=0,
                    fallback_used=False,
                    reason_code="catalog_skill_available",
                )
                return SkillGenerationResult(
                    skill=skill,
                    route="catalog",
                    attempts=(
                        SkillGenerationAttempt(1, "catalog", ProposalValidationStatus.ACCEPTED, "catalog_skill_available"),
                    ),
                    used_fallback=False,
                    final_reason_code="catalog_skill_available",
                )
            except SkillLoadError:
                log_event(
                    "pelican_skill_generation_fallback",
                    domain_category=resolution.category.value,
                    route=resolution.route_slug,
                    skill_source="catalog_unavailable",
                    reason_code="catalog_unavailable",
                )
            try:
                skill = load_validated_skill_artifact(topic=topic_clean, root=self.artifact_root)
                skill = _normalize_generated_skill(skill, resolution.category)
                validate_domain_skill(skill)
                log_event(
                    "pelican_skill_cache_hit",
                    skill_id=skill.skill_id,
                    skill_version=skill.version,
                    domain_category=skill.domain_category.value,
                    skill_lifecycle=skill.lifecycle.value,
                    route="runtime_cache",
                    skill_source="validated_runtime_cache",
                    reason_code="validated_artifact_available",
                )
                _log_generation_summary(
                    started_at,
                    route="runtime_cache",
                    category=skill.domain_category,
                    skill_id=skill.skill_id,
                    attempt_count=1,
                    rejected_count=0,
                    fallback_used=False,
                    reason_code="validated_artifact_available",
                )
                return SkillGenerationResult(
                    skill=skill,
                    route="runtime_cache",
                    attempts=(
                        SkillGenerationAttempt(1, "runtime_cache", ProposalValidationStatus.ACCEPTED, "validated_artifact_available"),
                    ),
                    used_fallback=False,
                    final_reason_code="validated_artifact_available",
                )
            except (SkillArtifactError, SkillValidationError, DomainSkillError, ValueError, TypeError) as exc:
                # Cache artifacts are an optimization, not an authority. If a
                # persisted skill no longer passes the current validator, the
                # generator repairs/regenerates instead of silently using it.
                log_event(
                    "pelican_skill_cache_miss",
                    domain_category=resolution.category.value,
                    route=resolution.route_slug,
                    skill_source="validated_runtime_cache",
                    reason_code=type(exc).__name__,
                )

        if resolution.category is DomainCategory.UNKNOWN:
            raise SkillGenerationError("unknown domain requires clarification")
        if not self.llm.available:
            # Known domains must stay skill-backed even offline; falling through
            # to the legacy planner would recreate the one-node-tree failure.
            skill, fallback_route = self._generic_fallback(topic_clean, resolution.category, resolution.route_slug, ("llm_unavailable",))
            _log_generation_summary(
                started_at,
                route=fallback_route,
                category=skill.domain_category,
                skill_id=skill.skill_id,
                attempt_count=1,
                rejected_count=0,
                fallback_used=True,
                reason_code="llm_unavailable",
            )
            return SkillGenerationResult(
                skill=skill,
                route=fallback_route,
                attempts=(
                    SkillGenerationAttempt(1, resolution.route_slug, ProposalValidationStatus.FALLBACK_USED, "llm_unavailable"),
                ),
                used_fallback=True,
                final_reason_code="llm_unavailable",
            )

        route = self.llm.model_route_for_category(resolution.category)
        health = self.llm.check_route_health(route)
        log_event(
            "pelican_skill_api_health_checked",
            domain_category=resolution.category.value,
            route=route,
            model_route=route,
            skill_source="runtime_generation",
            reason_code="|".join(health.reason_codes),
            api_status_code=health.api_status_code,
            api_error_type=health.api_error_type,
        )
        if not health.available:
            failed_attempt = {
                "attempt": 0,
                "stage": "api_health",
                "event": "pelican_skill_api_health_checked",
                "reason_codes": health.reason_codes,
                "api_status_code": health.api_status_code,
                "api_error_type": health.api_error_type,
            }
            save_failed_skill_artifact(
                topic=topic_clean,
                category=resolution.category,
                route=route,
                reason_codes=health.reason_codes,
                attempts=(failed_attempt,),
                root=self.artifact_root,
            )
            skill, fallback_route = self._generic_fallback(topic_clean, resolution.category, route, health.reason_codes)
            _log_generation_summary(
                started_at,
                route=fallback_route,
                category=skill.domain_category,
                skill_id=skill.skill_id,
                attempt_count=1,
                rejected_count=0,
                fallback_used=True,
                reason_code="|".join(health.reason_codes),
            )
            return SkillGenerationResult(
                skill=skill,
                route=fallback_route,
                attempts=(
                    SkillGenerationAttempt(1, route, ProposalValidationStatus.FALLBACK_USED, "|".join(health.reason_codes)),
                ),
                used_fallback=True,
                final_reason_code="|".join(health.reason_codes),
            )

        last_reason_codes: tuple[str, ...] = ("unknown",)
        last_payload: dict | None = None
        failed_attempts: list[dict[str, object]] = []
        for attempt in range(self.max_retries + 1):
            attempt_started_at = time.monotonic()
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
                    elapsed_ms=_elapsed_ms(attempt_started_at),
                )
                attempts = _attempts_from_failed(failed_attempts, route) + (
                    SkillGenerationAttempt(attempt + 1, route, ProposalValidationStatus.ACCEPTED, "validated"),
                )
                _log_generation_summary(
                    started_at,
                    route=route,
                    category=skill.domain_category,
                    skill_id=skill.skill_id,
                    attempt_count=len(attempts),
                    rejected_count=len(failed_attempts),
                    fallback_used=False,
                    reason_code="validated",
                )
                return SkillGenerationResult(
                    skill=skill,
                    route=route,
                    attempts=attempts,
                    used_fallback=False,
                    final_reason_code="validated",
                )
            except (LlmUnavailable, SkillValidationError, DomainSkillError, ValueError, TypeError, SkillGenerationError) as exc:
                last_reason_codes = _reason_codes_for(exc)
                event = _failure_event_for(exc)
                stage = _failure_stage_for(exc)
                failed_attempts.append(
                    {
                        "attempt": attempt + 1,
                        "stage": stage,
                        "event": event,
                        "reason_codes": last_reason_codes,
                        "api_status_code": getattr(exc, "api_status_code", None),
                        "api_error_type": getattr(exc, "api_error_type", None),
                    }
                )
                log_event(
                    event,
                    level=logging.WARNING,
                    domain_category=resolution.category.value,
                    route=route,
                    model_route=route,
                    skill_source="runtime_generation",
                    reason_code="|".join(last_reason_codes),
                    api_status_code=getattr(exc, "api_status_code", None),
                    api_error_type=getattr(exc, "api_error_type", None),
                    elapsed_ms=_elapsed_ms(attempt_started_at),
                )
                if attempt < self.max_retries:
                    log_event(
                        "pelican_skill_repair_attempt",
                        domain_category=resolution.category.value,
                        route=route,
                        model_route=route,
                        skill_source="runtime_generation",
                        reason_code="|".join(last_reason_codes),
                    )

        save_failed_skill_artifact(
            topic=topic_clean,
            category=resolution.category,
            route=route,
            reason_codes=last_reason_codes,
            payload=last_payload,
            attempts=tuple(failed_attempts),
            root=self.artifact_root,
        )
        skill, fallback_route = self._generic_fallback(topic_clean, resolution.category, route, last_reason_codes)
        rejected_attempts = _attempts_from_failed(failed_attempts, route)
        _log_generation_summary(
            started_at,
            route=fallback_route,
            category=skill.domain_category,
            skill_id=skill.skill_id,
            attempt_count=len(rejected_attempts) + 1,
            rejected_count=len(rejected_attempts),
            fallback_used=True,
            reason_code="|".join(last_reason_codes),
        )
        return SkillGenerationResult(
            skill=skill,
            route=fallback_route,
            attempts=rejected_attempts
            + (
                SkillGenerationAttempt(
                    len(failed_attempts) + 1,
                    fallback_route,
                    ProposalValidationStatus.FALLBACK_USED,
                    "|".join(last_reason_codes),
                ),
            ),
            used_fallback=True,
            final_reason_code="|".join(last_reason_codes),
        )

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
            Production adapters use ``generate_domain_skill_payload`` even when
            they inherit its implementation from ``LlmAdapter``. This leaves
            parsing and validation at the generator boundary, where failed raw
            payloads can be safely hashed and validator reason codes can drive
            the next repair attempt. Older test doubles that override only the
            legacy structured method retain their historical behavior.
        """
        adapter_type = type(self.llm)
        payload_api = getattr(adapter_type, "generate_domain_skill_payload", None)
        legacy_api = getattr(adapter_type, "generate_domain_skill", None)
        payload_api_overridden = payload_api is not None and payload_api is not LlmAdapter.generate_domain_skill_payload
        legacy_api_overridden = legacy_api is not None and legacy_api is not LlmAdapter.generate_domain_skill
        if payload_api_overridden or (payload_api is LlmAdapter.generate_domain_skill_payload and not legacy_api_overridden):
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
        return _dedupe_reason_codes(tuple(issue.reason_code for issue in exc.issues)) or ("validation_failed",)
    if isinstance(exc, LlmUnavailable):
        return _llm_reason_codes(exc)
    if isinstance(exc, DomainSkillError):
        return _domain_skill_reason_codes(exc)
    return (type(exc).__name__,)


def _domain_skill_reason_codes(exc: DomainSkillError) -> tuple[str, ...]:
    """Map parser failures to bounded schema classes without exposing payload text.

    ``DomainSkill.from_dict`` raises field-specific messages, but model output
    must never enter logs, repair prompts, or artifacts verbatim. The returned
    codes describe only the contract failure class, which is sufficient for a
    subsequent schema-repair prompt and safe for structured telemetry.
    """
    message = str(exc)
    if message.endswith(" is required"):
        return ("missing_required_field",)
    if message.endswith(" must be a non-empty list"):
        return ("invalid_required_list",)
    if message.endswith(" must be an object"):
        return ("invalid_object_field",)
    if message.endswith(" must be a string"):
        return ("invalid_string_field",)
    if message.endswith(" must be a bounded non-empty identifier"):
        return ("invalid_identifier",)
    if message.endswith(" must be bounded non-empty text"):
        return ("invalid_text",)
    return ("domain_skill_schema_invalid",)


def _attempts_from_failed(failed_attempts: list[dict[str, object]], route: str) -> tuple[SkillGenerationAttempt, ...]:
    """Convert persisted failed-attempt metadata into safe result records."""
    attempts: list[SkillGenerationAttempt] = []
    for index, item in enumerate(failed_attempts, start=1):
        reason_codes = item.get("reason_codes", ("unknown",))
        if isinstance(reason_codes, (list, tuple)):
            reason_code = "|".join(str(code)[:80] for code in reason_codes)
        else:
            reason_code = str(reason_codes)[:80]
        attempts.append(
            SkillGenerationAttempt(
                attempt_index=int(item.get("attempt", index)),
                route=route,
                validation_status=ProposalValidationStatus.REJECTED,
                reason_code=reason_code,
            )
        )
    return tuple(attempts)


def _elapsed_ms(started_at: float) -> int:
    """Return bounded elapsed milliseconds for safe latency logging."""
    return max(0, int((time.monotonic() - started_at) * 1000))


def _log_generation_summary(
    started_at: float,
    *,
    route: str,
    category: DomainCategory,
    skill_id: str,
    attempt_count: int,
    rejected_count: int,
    fallback_used: bool,
    reason_code: str,
) -> None:
    """Emit one safe terminal summary for the full skill-agent generation path."""
    log_event(
        "pelican_skill_generation_summary",
        skill_id=skill_id,
        domain_category=category.value,
        route=route,
        skill_source=route,
        reason_code=reason_code,
        attempt_count=attempt_count,
        rejected_count=rejected_count,
        fallback_used=fallback_used,
        elapsed_ms=_elapsed_ms(started_at),
    )


def _dedupe_reason_codes(reason_codes: tuple[str, ...]) -> tuple[str, ...]:
    """Return reason codes without duplicates while preserving first-seen order."""
    seen: set[str] = set()
    deduped: list[str] = []
    for code in reason_codes:
        if code in seen:
            continue
        seen.add(code)
        deduped.append(code)
    return tuple(deduped)


def _llm_reason_codes(exc: LlmUnavailable) -> tuple[str, ...]:
    """Map LLM failures to safe stable reason codes for logs and artifacts.

    The adapter intentionally hides raw exception text from structured logs. This
    mapper only extracts the public failure class already produced by
    ``LlmAdapter`` so operators can distinguish missing credentials, transport
    errors, imports, timeouts, and JSON parse failures without exposing prompts,
    model output, API keys, or provider response bodies.
    """
    if exc.reason_codes:
        return exc.reason_codes
    message = str(exc)
    if "OPENROUTER_API_KEY is not configured" in message:
        return ("llm_missing_api_key",)
    if message.startswith("LLM request failed:"):
        failure_type = message.split(":", 1)[1].strip().lower()
        failure_type = re.sub(r"[^a-z0-9_]+", "_", failure_type)[:60] or "unknown"
        return ("llm_request_failed", f"llm_{failure_type}")
    return ("llm_unavailable",)


def _failure_event_for(exc: Exception) -> str:
    """Return the structured event name for one failed generation attempt."""
    if isinstance(exc, LlmUnavailable):
        return "pelican_skill_generation_failed"
    if isinstance(exc, SkillValidationError):
        return "pelican_skill_validation_rejected"
    return "pelican_skill_schema_rejected"


def _failure_stage_for(exc: Exception) -> str:
    """Return a safe stage label for failed runtime skill artifacts."""
    if isinstance(exc, LlmUnavailable):
        return "llm_request"
    if isinstance(exc, SkillValidationError):
        return "validation"
    return "schema_parse"
