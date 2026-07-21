"""Dynamic learning plan generation and validation."""

from __future__ import annotations

import re
import uuid

from .domain_catalog import resolve_domain_category
from .llm import LlmAdapter
from .models import DiagnosticQuestion, KnowledgeNode, LearnerIntakeProfile, LearningIntent, LearningPlanSnapshot
from .observability import log_event
from .skill_compiler import SkillCompileError, compile_learning_plan
from .skill_generator import DomainSkillGenerator, SkillGenerationError


def validate_learning_plan(plan: LearningPlanSnapshot) -> None:
    """Validate a generated plan for graph invariants and safe metadata."""
    if not plan.nodes:
        raise ValueError("Plan must have at least one node")

    node_ids = set()
    for node in plan.nodes:
        if node.node_id in node_ids:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        if node.node_id in node.prerequisites:
            raise ValueError(f"Node {node.node_id} depends on itself")
        node_ids.add(node.node_id)

    for node in plan.nodes:
        for prereq in node.prerequisites:
            if prereq not in node_ids:
                raise ValueError(f"Unknown prerequisite: {prereq} for node {node.node_id}")

    # Check for cycles
    def has_cycle(current: str, visited: set[str], stack: set[str]) -> bool:
        visited.add(current)
        stack.add(current)
        node = next((n for n in plan.nodes if n.node_id == current), None)
        if node:
            for neighbor in node.prerequisites:
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, stack):
                        return True
                elif neighbor in stack:
                    return True
        stack.remove(current)
        return False

    visited: set[str] = set()
    for node_id in node_ids:
        if node_id not in visited:
            if has_cycle(node_id, visited, set()):
                raise ValueError("Graph contains a cycle")

    for d in plan.diagnostics:
        if d.node_id not in node_ids:
            raise ValueError(f"Diagnostic for unknown node: {d.node_id}")

    for step in plan.task_steps:
        if step.get("node_id") not in node_ids:
            raise ValueError(f"Task step for unknown node: {step.get('node_id')}")
        if not step.get("step_id") or not step.get("prompt") or not step.get("expected"):
            raise ValueError("Task step missing required fields")


class LearningPlanner:
    """Create validated learning plans from intake topics or profiles."""

    def __init__(self, llm: LlmAdapter | None = None):
        """Initialize planner dependencies with deterministic fallback behavior."""
        self.llm = llm or LlmAdapter()
        self.skill_generator = DomainSkillGenerator(self.llm)

    def create_plan(self, topic: str) -> LearningPlanSnapshot:
        """Create a validated learning plan from a topic.

        Args:
            topic: Learner-requested topic before full intake exists.

        Returns:
            A validated learning plan. Resolved domains should be skill-backed
            through catalog, runtime generation, or generic domain fallback.
            Unknown domains may still receive the deterministic two-node fallback
            because the MVP has no safe category policy for them yet.
        """
        topic_clean = re.sub(r"\s+", " ", topic).strip()[:100] or "預設主題"
        profile = LearnerIntakeProfile(topic=topic_clean, goal_summary=f"學習 {topic_clean}")
        return self.create_plan_for_profile(profile)

    def create_plan_for_profile(self, profile: LearnerIntakeProfile) -> LearningPlanSnapshot:
        """Create a plan from intake metadata using validated skills first.

        Domain skills are deterministic teaching assets. They are attempted before
        topic-level LLM planning so a broad subject such as deep learning starts
        from a reviewed foundation route instead of arbitrary implementation
        detail. Invalid runtime skill assets fail into a deterministic
        skill-backed generic domain route, never the legacy topic-level LLM plan.
        """
        topic_clean = re.sub(r"\s+", " ", profile.topic).strip()[:100] or "預設主題"
        profile = _profile_with_defaults(profile, topic_clean)

        try:
            skill, route = self.skill_generator.generate(topic_clean)
            plan = compile_learning_plan(skill, _profile_with_route(profile, route))
            validate_learning_plan(plan)
            log_event(
                "pelican_plan_generated",
                plan_source="skill",
                node_count=len(plan.nodes),
                skill_id=skill.skill_id,
                skill_version=skill.version,
                domain_category=skill.domain_category.value,
                skill_lifecycle=skill.lifecycle.value,
                route=route,
                skill_source=route,
            )
            return plan
        except (SkillGenerationError, SkillCompileError, ValueError, KeyError, TypeError) as exc:
            resolution = resolve_domain_category(topic_clean)
            log_event(
                "pelican_plan_fallback",
                plan_source="fallback",
                domain_category=resolution.category.value,
                route=resolution.route_slug,
                reason_code=type(exc).__name__,
                skill_source="fallback",
            )

        # Deterministic fallback
        # This path is intentionally reserved for unresolved/unknown domains or
        # catastrophic skill pipeline failures. Known domains should recover in
        # ``DomainSkillGenerator`` via generic skills so the engine remains
        # skill-backed and does not recreate a silent one-node legacy plan.
        plan_id = str(uuid.uuid4())
        nodes = (
            KnowledgeNode(node_id="f1", label=f"{topic_clean} 基礎", priority=2),
            KnowledgeNode(node_id="f2", label=f"{topic_clean} 進階", prerequisites=("f1",), priority=1),
        )
        diagnostics = (
            DiagnosticQuestion(node_id="f1", prompt=f"關於 {topic_clean} 基礎的測試題", expected_answer="基礎答案", source="rule"),
            DiagnosticQuestion(node_id="f2", prompt=f"關於 {topic_clean} 進階的測試題", expected_answer="進階答案", source="rule"),
        )
        task_steps = (
            {
                "step_id": "step1",
                "node_id": "f1",
                "label": "基礎學習",
                "prompt": f"請完成 {topic_clean} 的基礎步驟",
                "expected": "基礎答案"
            },
            {
                "step_id": "step2",
                "node_id": "f2",
                "label": "進階學習",
                "prompt": f"請完成 {topic_clean} 的進階步驟",
                "expected": "進階答案"
            }
        )

        fallback_plan = LearningPlanSnapshot(
            plan_id=plan_id,
            topic=topic_clean,
            goal_summary=f"學習 {topic_clean}",
            nodes=nodes,
            diagnostics=diagnostics,
            task_steps=task_steps
        )

        log_event(
            "pelican_plan_generated",
            plan_source="fallback",
            node_count=len(nodes),
            skill_source="fallback",
        )
        return fallback_plan


def _profile_with_defaults(profile: LearnerIntakeProfile, topic: str) -> LearnerIntakeProfile:
    if profile.topic == topic and profile.intent is not LearningIntent.UNKNOWN:
        return profile
    return LearnerIntakeProfile(
        topic=topic,
        goal_summary=profile.goal_summary or f"學習 {topic}",
        intent=profile.intent,
        level_hint=profile.level_hint,
        domain_category=profile.domain_category,
        skill_id=profile.skill_id,
        skill_version=profile.skill_version,
        skill_lifecycle=profile.skill_lifecycle,
        model_route=profile.model_route,
        intake_turns=profile.intake_turns,
    )


def _profile_with_route(profile: LearnerIntakeProfile, route: str) -> LearnerIntakeProfile:
    return LearnerIntakeProfile(
        topic=profile.topic,
        goal_summary=profile.goal_summary,
        intent=profile.intent,
        level_hint=profile.level_hint,
        domain_category=profile.domain_category,
        skill_id=profile.skill_id,
        skill_version=profile.skill_version,
        skill_lifecycle=profile.skill_lifecycle,
        model_route=route,
        intake_turns=profile.intake_turns,
    )
