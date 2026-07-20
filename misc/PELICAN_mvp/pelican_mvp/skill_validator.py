"""Validation for PELICAN domain teaching skills."""

from __future__ import annotations

from dataclasses import dataclass

from .domain_skill import DomainCategory, DomainSkill, REQUIRED_REMEDIATION_SIGNALS


@dataclass(frozen=True)
class SkillValidationIssue:
    """A stable, log-safe skill validation failure."""

    reason_code: str
    field: str


class SkillValidationError(ValueError):
    """Raised when a skill is structurally or pedagogically unsafe."""

    def __init__(self, issues: list[SkillValidationIssue]):
        self.issues = issues
        reason_codes = ", ".join(issue.reason_code for issue in issues)
        super().__init__(reason_codes)


def validate_domain_skill(skill: DomainSkill) -> None:
    """Validate a domain skill before it can be compiled into a knowledge tree.

    The validator checks both graph invariants and teaching-safety boundaries.
    Legal knowledge skills are allowed only as education-only content, not legal
    advice. Diagnostic prompts must not embed their expected answers.
    """
    issues: list[SkillValidationIssue] = []
    _validate_unique_ids("prerequisites", [item.concept_id for item in skill.prerequisites], issues)
    _validate_unique_ids("calibration_questions", [item.question_id for item in skill.calibration_questions], issues)
    _validate_unique_ids("diagnostic_rules", [item.rule_id for item in skill.diagnostic_rules], issues)
    _validate_unique_ids("teaching_moves", [item.move_id for item in skill.teaching_moves], issues)

    concept_ids = {item.concept_id for item in skill.prerequisites}
    if not skill.calibration_questions:
        issues.append(SkillValidationIssue("missing_calibration", "calibration_questions"))
    if not skill.canonical_path:
        issues.append(SkillValidationIssue("missing_canonical_path", "canonical_path"))

    for intent in skill.intent_types:
        if intent not in skill.canonical_path:
            issues.append(SkillValidationIssue("missing_intent_path", f"canonical_path.{intent.value}"))

    for prerequisite in skill.prerequisites:
        for prereq_id in prerequisite.prerequisites:
            if prereq_id not in concept_ids:
                issues.append(SkillValidationIssue("unknown_prerequisite", prerequisite.concept_id))
            if prereq_id == prerequisite.concept_id:
                issues.append(SkillValidationIssue("self_prerequisite", prerequisite.concept_id))

    _validate_acyclic(skill, issues)

    for intent, path in skill.canonical_path.items():
        if not path:
            issues.append(SkillValidationIssue("empty_path", f"canonical_path.{intent.value}"))
        for concept_id in path:
            if concept_id not in concept_ids:
                issues.append(SkillValidationIssue("unknown_path_concept", f"canonical_path.{intent.value}"))

    diagnostic_concepts: set[str] = set()
    for diagnostic in skill.diagnostic_rules:
        if diagnostic.concept_id not in concept_ids:
            issues.append(SkillValidationIssue("unknown_diagnostic_concept", diagnostic.rule_id))
        if not diagnostic.tests_single_concept:
            issues.append(SkillValidationIssue("multi_concept_diagnostic", diagnostic.rule_id))
        if _prompt_contains_answer(diagnostic.prompt, diagnostic.expected_answer):
            issues.append(SkillValidationIssue("answer_leaked_in_prompt", diagnostic.rule_id))
        diagnostic_concepts.add(diagnostic.concept_id)

    for concept_id in concept_ids:
        if concept_id not in diagnostic_concepts:
            issues.append(SkillValidationIssue("missing_diagnostic", concept_id))

    remediation_signals = {item.signal for item in skill.remediation_paths}
    missing_signals = REQUIRED_REMEDIATION_SIGNALS - remediation_signals
    for signal in sorted(missing_signals):
        issues.append(SkillValidationIssue("missing_remediation", signal))

    if skill.domain_category is DomainCategory.HUMANITIES and any(_is_legal_topic(topic) for topic in skill.supported_topics):
        if not skill.assessment_policy.education_only:
            issues.append(SkillValidationIssue("legal_policy_not_education_only", "assessment_policy"))
        if "法律諮詢" not in skill.assessment_policy.notes and "legal advice" not in skill.assessment_policy.notes.lower():
            issues.append(SkillValidationIssue("legal_policy_missing_boundary", "assessment_policy.notes"))

    if issues:
        raise SkillValidationError(issues)


def _validate_unique_ids(field: str, identifiers: list[str], issues: list[SkillValidationIssue]) -> None:
    seen: set[str] = set()
    for identifier in identifiers:
        if identifier in seen:
            issues.append(SkillValidationIssue("duplicate_id", field))
        seen.add(identifier)


def _validate_acyclic(skill: DomainSkill, issues: list[SkillValidationIssue]) -> None:
    node_map = {item.concept_id: item for item in skill.prerequisites}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(concept_id: str) -> None:
        if concept_id in visiting:
            issues.append(SkillValidationIssue("cyclic_prerequisite", concept_id))
            return
        if concept_id in visited or concept_id not in node_map:
            return
        visiting.add(concept_id)
        for prerequisite_id in node_map[concept_id].prerequisites:
            visit(prerequisite_id)
        visiting.remove(concept_id)
        visited.add(concept_id)

    for concept_id in node_map:
        visit(concept_id)


def _prompt_contains_answer(prompt: str, expected_answer: str) -> bool:
    normalized_prompt = prompt.casefold()
    answer = expected_answer.casefold().strip()
    return len(answer) >= 3 and answer in normalized_prompt


def _is_legal_topic(topic: str) -> bool:
    return any(token in topic.casefold() for token in ("法律", "law", "legal"))
