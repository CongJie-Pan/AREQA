"""Compile validated domain skills into deterministic session learning plans."""

from __future__ import annotations

import re

from .domain_skill import DomainSkill, IntentType
from .models import DiagnosticQuestion, KnowledgeNode, LearnerIntakeProfile, LearningIntent, LearningPlanSnapshot
from .observability import log_event


class SkillCompileError(ValueError):
    """Raised when a validated skill cannot be compiled for the intake profile."""


INTENT_MAP = {
    LearningIntent.CONCEPTUAL: IntentType.CONCEPTUAL,
    LearningIntent.PROCEDURAL: IntentType.IMPLEMENTATION,
    LearningIntent.IMPLEMENTATION: IntentType.IMPLEMENTATION,
    LearningIntent.PROJECT: IntentType.PROJECT,
    LearningIntent.ASSESSMENT: IntentType.ASSESSMENT,
    LearningIntent.EXPLANATORY: IntentType.CONCEPTUAL,
}


def compile_learning_plan(skill: DomainSkill, profile: LearnerIntakeProfile) -> LearningPlanSnapshot:
    """Compile one validated skill into a session-owned ``LearningPlanSnapshot``.

    Canonical paths are stable by design: the compiler may select which path to
    use from intake, but it must not infer mastery from a goal statement. For an
    uncalibrated learner, the first compiled route is intentionally shallow so
    successor-first diagnosis starts with foundations rather than downstream
    implementation details.
    """
    intent = _resolve_skill_intent(skill, profile)
    path = tuple(skill.canonical_path.get(intent, ()))
    if not path:
        raise SkillCompileError("missing canonical path for intake intent")

    selected_path = _initial_path_for_profile(path, profile, intent, skill)
    foundation_first = _uses_foundation_first_slice(intent, skill, profile)
    prerequisites = {item.concept_id: item for item in skill.prerequisites}
    diagnostics = {item.concept_id: item for item in skill.diagnostic_rules}
    nodes: list[KnowledgeNode] = []
    compiled_diagnostics: list[DiagnosticQuestion] = []
    task_steps: list[dict[str, str]] = []

    for index, concept_id in enumerate(selected_path):
        concept = prerequisites.get(concept_id)
        diagnostic = diagnostics.get(concept_id)
        if concept is None or diagnostic is None:
            raise SkillCompileError("compiled path references missing concept or diagnostic")
        local_prerequisites = (
            ()
            if foundation_first
            else tuple(item for item in concept.prerequisites if item in selected_path)
        )
        nodes.append(
            KnowledgeNode(
                node_id=concept.concept_id,
                label=concept.label,
                prerequisites=local_prerequisites,
                priority=index + 1,
            )
        )
        compiled_diagnostics.append(
            DiagnosticQuestion(
                node_id=concept.concept_id,
                prompt=diagnostic.prompt,
                expected_answer=diagnostic.expected_answer,
                source="skill",
            )
        )
        task_steps.append(
            {
                "step_id": f"practice_{concept.concept_id}",
                "node_id": concept.concept_id,
                "label": concept.label,
                "prompt": f"請用自己的話整理「{concept.label}」的核心想法，並舉一個簡短例子。",
                "expected": diagnostic.expected_answer,
            }
        )

    topic = _normalized_topic(profile.topic) or skill.supported_topics[0]
    plan = LearningPlanSnapshot(
        plan_id=f"{skill.skill_id}:{skill.version}:{intent.value}:{_slug(topic)}",
        topic=topic,
        goal_summary=profile.goal_summary or f"依 {skill.title} 學習 {topic}",
        nodes=tuple(nodes),
        diagnostics=tuple(compiled_diagnostics),
        task_steps=tuple(task_steps),
        skill_id=skill.skill_id,
        skill_version=skill.version,
        skill_lifecycle=skill.lifecycle.value,
        domain_category=skill.domain_category.value,
        model_route=profile.model_route,
        teaching_methodology=skill.teaching_methodology,
        remediation_templates=skill.remediation_templates,
    )
    log_event(
        "pelican_skill_compiled",
        skill_id=skill.skill_id,
        skill_version=skill.version,
        domain_category=skill.domain_category.value,
        skill_lifecycle=skill.lifecycle.value,
        node_count=len(plan.nodes),
        reason_code="compiled",
    )
    return plan


def _resolve_skill_intent(skill: DomainSkill, profile: LearnerIntakeProfile) -> IntentType:
    if profile.intent is LearningIntent.UNKNOWN:
        return skill.intent_types[0]
    intent = INTENT_MAP.get(profile.intent)
    if intent in skill.intent_types:
        return intent
    return skill.intent_types[0]


def _initial_path_for_profile(
    path: tuple[str, ...], profile: LearnerIntakeProfile, intent: IntentType, skill: DomainSkill
) -> tuple[str, ...]:
    """Select the first compiled path without asserting mastery from intake.

    The deep-learning catalog seed keeps calibration-first behavior while
    exposing enough foundation concepts for the learner-facing UI to demonstrate
    an adaptive learning path. Runtime-generated and generic skills keep their
    full path because truncating them would make missing-skill fallbacks look
    like shallow catalog demos.
    """
    if _uses_foundation_first_slice(intent, skill, profile):
        return path[:3]
    return path


def _uses_foundation_first_slice(intent: IntentType, skill: DomainSkill, profile: LearnerIntakeProfile) -> bool:
    """Return whether a path should diagnose early foundations first.

    The deep-learning conceptual catalog path is linear, so preserving its
    prerequisite edges inside a short demo slice would make successor-first
    diagnosis start at the deepest retained node. Flattening this MVP slice keeps
    the first user-facing diagnostic at the intended beginner foundation while
    still exposing multiple follow-up concepts in the session tree.

    Runtime-generated beginner conceptual skills follow the same rule. A
    validated humanities skill for a novice learner should begin with context
    framing rather than the deepest dependent concept; otherwise the UI can look
    like it is asking advanced detail before establishing historical order.
    """
    context_first_methodology = any(
        "context" in key.lower() or "context" in value.lower()
        for key, value in skill.teaching_methodology.items()
    )
    return intent is IntentType.CONCEPTUAL and (
        skill.skill_id == "deep_learning"
        or profile.level_hint == "beginner"
        or context_first_methodology
        or skill.domain_category.value == "humanities"
    )


def _normalized_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic).strip()[:100]


def _slug(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_").lower()
    return normalized[:40] or "topic"
