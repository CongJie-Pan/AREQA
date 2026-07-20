"""Serializable teaching-skill contracts for the PELICAN MVP.

A domain skill sits above a session knowledge tree. It defines how a subject
should be calibrated, sequenced, diagnosed, remediated, and assessed; a later
compiler turns the validated skill plus learner intake into a session-local
``LearningPlanSnapshot``. Unvalidated model output must never reach diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


MAX_TEXT_LENGTH = 800
MAX_ID_LENGTH = 80
REQUIRED_REMEDIATION_SIGNALS = frozenset({
    "unknown",
    "too_detailed",
    "too_easy",
    "project_goal",
    "assessment_goal",
})


class DomainSkillError(ValueError):
    """Raised when skill payloads cannot be represented safely."""


class DomainCategory(str, Enum):
    """Supported high-level teaching domains for the MVP catalog."""

    STEM = "stem"
    HUMANITIES = "humanities"
    BUSINESS = "business"
    LANGUAGE = "language"
    UNKNOWN = "unknown"


class SkillLifecycle(str, Enum):
    """Lifecycle labels for future reviewed skill governance."""

    RUNTIME_GENERATED = "runtime_generated"
    VALIDATED_GENERATED = "validated_generated"
    APPROVED = "approved"


class IntentType(str, Enum):
    """Learning intents that influence how a skill is compiled later."""

    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    IMPLEMENTATION = "implementation"
    PROJECT = "project"
    ASSESSMENT = "assessment"
    EXPLANATORY = "explanatory"
    BUSINESS_DECISION = "business_decision"
    LANGUAGE_PRACTICE = "language_practice"


@dataclass(frozen=True)
class Prerequisite:
    """One domain concept before it is compiled into a session tree node."""

    concept_id: str
    label: str
    prerequisites: tuple[str, ...] = ()
    description: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Prerequisite":
        """Create a prerequisite record with bounded learner-facing text."""
        return cls(
            concept_id=_required_id(payload, "concept_id"),
            label=_required_text(payload, "label"),
            prerequisites=tuple(_bounded_id(item, "prerequisites") for item in payload.get("prerequisites", ())),
            description=_optional_text(payload, "description"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-safe representation."""
        return {
            "concept_id": self.concept_id,
            "label": self.label,
            "prerequisites": list(self.prerequisites),
            "description": self.description,
        }


@dataclass(frozen=True)
class CalibrationQuestion:
    """A broad intake question used before detailed diagnosis begins."""

    question_id: str
    prompt: str
    intent_targets: tuple[IntentType, ...] = ()
    level_targets: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CalibrationQuestion":
        """Create a calibration question from structured skill data."""
        return cls(
            question_id=_required_id(payload, "question_id"),
            prompt=_required_text(payload, "prompt"),
            intent_targets=tuple(IntentType(item) for item in payload.get("intent_targets", ())),
            level_targets=tuple(_bounded_id(item, "level_targets") for item in payload.get("level_targets", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-safe representation."""
        return {
            "question_id": self.question_id,
            "prompt": self.prompt,
            "intent_targets": [item.value for item in self.intent_targets],
            "level_targets": list(self.level_targets),
        }


@dataclass(frozen=True)
class DiagnosticRule:
    """A one-concept diagnostic template with prompt and answer kept separate."""

    rule_id: str
    concept_id: str
    prompt: str
    expected_answer: str
    tests_single_concept: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DiagnosticRule":
        """Create a diagnostic rule from structured skill data."""
        return cls(
            rule_id=_required_id(payload, "rule_id"),
            concept_id=_required_id(payload, "concept_id"),
            prompt=_required_text(payload, "prompt"),
            expected_answer=_required_text(payload, "expected_answer"),
            tests_single_concept=bool(payload.get("tests_single_concept", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-safe representation."""
        return {
            "rule_id": self.rule_id,
            "concept_id": self.concept_id,
            "prompt": self.prompt,
            "expected_answer": self.expected_answer,
            "tests_single_concept": self.tests_single_concept,
        }


@dataclass(frozen=True)
class TeachingMove:
    """A reusable tutor action allowed for a validated domain skill."""

    move_id: str
    strategy: str
    description: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TeachingMove":
        """Create a teaching move with bounded text fields."""
        return cls(
            move_id=_required_id(payload, "move_id"),
            strategy=_required_id(payload, "strategy"),
            description=_required_text(payload, "description"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-safe representation."""
        return {
            "move_id": self.move_id,
            "strategy": self.strategy,
            "description": self.description,
        }


@dataclass(frozen=True)
class RemediationPath:
    """How the engine should react to a learner signal such as ``too_detailed``."""

    signal: str
    action: str
    target: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RemediationPath":
        """Create a remediation path for required mismatch and goal signals."""
        return cls(
            signal=_required_id(payload, "signal"),
            action=_required_id(payload, "action"),
            target=_required_id(payload, "target"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-safe representation."""
        return {
            "signal": self.signal,
            "action": self.action,
            "target": self.target,
        }


@dataclass(frozen=True)
class AssessmentPolicy:
    """Assessment boundaries, including the legal-education safety boundary."""

    mode: str
    education_only: bool = True
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AssessmentPolicy":
        """Create an assessment policy from structured skill data."""
        return cls(
            mode=_required_id(payload, "mode"),
            education_only=bool(payload.get("education_only", True)),
            notes=_optional_text(payload, "notes"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/YAML-safe representation."""
        return {
            "mode": self.mode,
            "education_only": self.education_only,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DomainSkill:
    """Executable teaching policy and domain map for a learning subject."""

    skill_id: str
    version: str
    title: str
    domain_category: DomainCategory
    lifecycle: SkillLifecycle
    supported_topics: tuple[str, ...]
    intent_types: tuple[IntentType, ...]
    prerequisites: tuple[Prerequisite, ...]
    calibration_questions: tuple[CalibrationQuestion, ...]
    canonical_path: dict[IntentType, tuple[str, ...]]
    diagnostic_rules: tuple[DiagnosticRule, ...]
    teaching_moves: tuple[TeachingMove, ...]
    remediation_paths: tuple[RemediationPath, ...]
    assessment_policy: AssessmentPolicy
    safety_notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DomainSkill":
        """Build a strict skill contract from a parsed JSON/YAML-compatible dict."""
        canonical_payload = _required_mapping(payload, "canonical_path")
        return cls(
            skill_id=_required_id(payload, "skill_id"),
            version=_required_id(payload, "version"),
            title=_required_text(payload, "title"),
            domain_category=DomainCategory(_required_id(payload, "domain_category")),
            lifecycle=SkillLifecycle(_required_id(payload, "lifecycle")),
            supported_topics=tuple(_bounded_text(item, "supported_topics") for item in _required_list(payload, "supported_topics")),
            intent_types=tuple(IntentType(item) for item in _required_list(payload, "intent_types")),
            prerequisites=tuple(Prerequisite.from_dict(item) for item in _required_list(payload, "prerequisites")),
            calibration_questions=tuple(
                CalibrationQuestion.from_dict(item) for item in _required_list(payload, "calibration_questions")
            ),
            canonical_path={
                IntentType(key): tuple(_bounded_id(item, f"canonical_path.{key}") for item in value)
                for key, value in canonical_payload.items()
            },
            diagnostic_rules=tuple(DiagnosticRule.from_dict(item) for item in _required_list(payload, "diagnostic_rules")),
            teaching_moves=tuple(TeachingMove.from_dict(item) for item in _required_list(payload, "teaching_moves")),
            remediation_paths=tuple(RemediationPath.from_dict(item) for item in _required_list(payload, "remediation_paths")),
            assessment_policy=AssessmentPolicy.from_dict(_required_mapping(payload, "assessment_policy")),
            safety_notes=tuple(_bounded_text(item, "safety_notes") for item in payload.get("safety_notes", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON/YAML-safe skill representation."""
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "title": self.title,
            "domain_category": self.domain_category.value,
            "lifecycle": self.lifecycle.value,
            "supported_topics": list(self.supported_topics),
            "intent_types": [item.value for item in self.intent_types],
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "calibration_questions": [item.to_dict() for item in self.calibration_questions],
            "canonical_path": {key.value: list(value) for key, value in self.canonical_path.items()},
            "diagnostic_rules": [item.to_dict() for item in self.diagnostic_rules],
            "teaching_moves": [item.to_dict() for item in self.teaching_moves],
            "remediation_paths": [item.to_dict() for item in self.remediation_paths],
            "assessment_policy": self.assessment_policy.to_dict(),
            "safety_notes": list(self.safety_notes),
        }


def _required_mapping(payload: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise DomainSkillError(f"{field_name} is required")
    return value


def _required_list(payload: dict[str, Any], field_name: str) -> list[Any]:
    value = payload.get(field_name)
    if not isinstance(value, list) or not value:
        raise DomainSkillError(f"{field_name} must be a non-empty list")
    return value


def _required_id(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise DomainSkillError(f"{field_name} is required")
    return _bounded_id(value, field_name)


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        raise DomainSkillError(f"{field_name} is required")
    return _bounded_text(value, field_name)


def _optional_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name, "")
    if not isinstance(value, str):
        raise DomainSkillError(f"{field_name} must be a string")
    return _bounded_text(value, field_name, allow_empty=True)


def _bounded_id(value: str, field_name: str) -> str:
    value = value.strip()
    if not value or len(value) > MAX_ID_LENGTH or any(ch.isspace() for ch in value):
        raise DomainSkillError(f"{field_name} must be a bounded non-empty identifier")
    return value


def _bounded_text(value: str, field_name: str, *, allow_empty: bool = False) -> str:
    value = value.strip()
    if (not allow_empty and not value) or len(value) > MAX_TEXT_LENGTH:
        raise DomainSkillError(f"{field_name} must be bounded non-empty text")
    return value
