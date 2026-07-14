"""The reviewed knowledge tree and task plan for the paper's set example."""

from __future__ import annotations

from .models import DiagnosticQuestion, KnowledgeNode


NODES: dict[str, KnowledgeNode] = {
    "set_basics": KnowledgeNode("set_basics", "集合與元素範圍", priority=99),
    "set_intersection": KnowledgeNode(
        "set_intersection", "集合交集", prerequisites=("set_basics",), priority=1
    ),
    "absolute_value": KnowledgeNode(
        "absolute_value", "絕對值不等式", prerequisites=("set_basics",), priority=2
    ),
    "sqrt_integer": KnowledgeNode(
        "sqrt_integer", "根號條件與整數範圍", prerequisites=("set_basics",), priority=3
    ),
}

DIAGNOSTICS: dict[str, DiagnosticQuestion] = {
    "set_intersection": DiagnosticQuestion(
        "set_intersection",
        "診斷題：已知 A = {1, 2, 3, 4}、B = {3, 4, 5, 6}，A ∩ B 是什麼？",
        "{3,4}",
    ),
    "absolute_value": DiagnosticQuestion(
        "absolute_value",
        "診斷題：解不等式 |x - 1| ≤ 2，x 的範圍是什麼？",
        "[-1,3]",
    ),
    "sqrt_integer": DiagnosticQuestion(
        "sqrt_integer",
        "診斷題：x 為整數且 √x ≤ 4，x 可能的值組成的集合是什麼？",
        "{0,1,...,16}",
    ),
}

TASK_STEPS = (
    {
        "step_id": "solve_a",
        "node_id": "absolute_value",
        "label": "求集合 A",
        "prompt": "原題第一步：由 |x - 1| ≤ 2 求出集合 A。請寫出 x 的範圍。",
        "expected": "[-1,3]",
    },
    {
        "step_id": "solve_b",
        "node_id": "sqrt_integer",
        "label": "求集合 B",
        "prompt": "原題第二步：x 為整數且 √x ≤ 4。請寫出集合 B。",
        "expected": "{0,1,...,16}",
    },
    {
        "step_id": "intersect",
        "node_id": "set_intersection",
        "label": "求 A ∩ B",
        "prompt": "原題最後一步：A = [-1, 3]，B = {0, 1, ..., 16}。A ∩ B 是什麼？",
        "expected": "{0,1,2,3}",
    },
)


def successors(node_id: str) -> tuple[str, ...]:
    return tuple(node.node_id for node in NODES.values() if node_id in node.prerequisites)


def first_task_step() -> dict[str, str]:
    return TASK_STEPS[0]


def next_task_step(step_id: str) -> dict[str, str] | None:
    for index, step in enumerate(TASK_STEPS):
        if step["step_id"] == step_id:
            return TASK_STEPS[index + 1] if index + 1 < len(TASK_STEPS) else None
    raise ValueError(f"Unknown task step: {step_id}")

