"""Collaborative cognitive diagnosis and rule-based answer evaluation."""

from __future__ import annotations

import re

from .curriculum import DIAGNOSTICS, NODES, successors
from .models import Evidence, KnowledgeStatus, ResponseCategory, SessionState


def next_diagnostic_node(state: SessionState) -> str | None:
    """Select an undiagnosed leaf first, as specified by PELICAN successor-first."""
    candidates = []
    for node in NODES.values():
        if state.nodes[node.node_id].status is not KnowledgeStatus.UNDIAGNOSED:
            continue
        if all(
            state.nodes[child].status is not KnowledgeStatus.UNDIAGNOSED
            for child in successors(node.node_id)
        ):
            candidates.append(node)
    if not candidates:
        return None
    return min(candidates, key=lambda node: node.priority).node_id


def normalize_answer(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("…", "...").lower()


def is_correct(answer: str, expected: str) -> bool:
    actual = normalize_answer(answer)
    target = normalize_answer(expected)
    if actual == target:
        return True
    aliases = {
        "{3,4}": {"3,4", "{4,3}"},
        "[-1,3]": {"-1≤x≤3", "-1<=x<=3", "x∈[-1,3]", "xintheinterval[-1,3]"},
        "{0,1,...,16}": {"{0,1,2,...,16}", "{0,1,2,3,...,16}", "{0,...,16}", "0≤x≤16", "0<=x<=16"},
        "{0,1,2,3}": {"0,1,2,3", "{3,2,1,0}", "{0,1,3,2}"},
    }
    return actual in {normalize_answer(item) for item in aliases.get(target, set())}


def classify_response(answer: str, expected: str) -> ResponseCategory:
    normalized = normalize_answer(answer)
    if not normalized:
        return ResponseCategory.OTHER
    if any(token in answer for token in ("不懂", "看不懂", "為什麼", "怎麼來的", "解釋")):
        return ResponseCategory.DIFFICULTY
    if any(token in answer for token in ("不會", "不知道", "無法", "想不出", "不確定")):
        return ResponseCategory.INABILITY
    if is_correct(answer, expected):
        return ResponseCategory.CORRECT
    return ResponseCategory.INCORRECT


def apply_diagnostic_result(
    state: SessionState, node_id: str, answer: str, category: ResponseCategory
) -> list[str]:
    status = KnowledgeStatus.MASTERED if category is ResponseCategory.CORRECT else KnowledgeStatus.NOT_MASTERED
    evidence = Evidence(response=answer, category=category.value, direct=True)
    state.nodes[node_id].update(status, evidence)
    changes = [f"{NODES[node_id].label}: {status.value}（直接證據）"]
    if status is KnowledgeStatus.MASTERED:
        changes.extend(_mark_prerequisites_mastered(state, node_id, answer, category))
    return changes


def _mark_prerequisites_mastered(
    state: SessionState, node_id: str, answer: str, category: ResponseCategory
) -> list[str]:
    changes: list[str] = []
    for prerequisite in NODES[node_id].prerequisites:
        parent = state.nodes[prerequisite]
        if parent.status is not KnowledgeStatus.MASTERED:
            parent.update(
                KnowledgeStatus.MASTERED,
                Evidence(response=answer, category=category.value, direct=False),
            )
            changes.append(f"{NODES[prerequisite].label}: mastered（由子節點推定）")
        changes.extend(_mark_prerequisites_mastered(state, prerequisite, answer, category))
    return changes


def diagnostic_for(node_id: str):
    return DIAGNOSTICS[node_id]

