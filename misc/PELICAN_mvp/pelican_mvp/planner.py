"""Dynamic learning plan generation and validation."""

from __future__ import annotations

import re
import uuid

from .llm import LlmAdapter, LlmUnavailable
from .models import DiagnosticQuestion, KnowledgeNode, LearningPlanSnapshot
from .observability import log_event


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
    def __init__(self, llm: LlmAdapter | None = None):
        self.llm = llm or LlmAdapter()

    def create_plan(self, topic: str) -> LearningPlanSnapshot:
        """Create a validated learning plan from a topic, falling back if necessary."""
        topic_clean = re.sub(r"\s+", " ", topic).strip()[:100] or "預設主題"

        if self.llm.available:
            try:
                plan = self.llm.generate_learning_plan(topic_clean)
                if plan:
                    validate_learning_plan(plan)
                    log_event(
                        "pelican_plan_generated",
                        plan_source="generated",
                        node_count=len(plan.nodes),
                    )
                    return plan
            except (LlmUnavailable, ValueError, KeyError, TypeError) as exc:
                log_event(
                    "pelican_plan_fallback",
                    plan_source="fallback",
                    reason_code=type(exc).__name__,
                )

        # Deterministic fallback
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
        )
        return fallback_plan
