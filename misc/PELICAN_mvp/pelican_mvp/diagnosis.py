"""Collaborative cognitive diagnosis and rule-based answer evaluation."""

from __future__ import annotations

import re

from .curriculum import Curriculum
from .models import Evidence, KnowledgeStatus, ResponseCategory, SessionState


def next_diagnostic_node(state: SessionState, curriculum: Curriculum) -> str | None:
    """Select an undiagnosed leaf first, as specified by PELICAN successor-first."""
    candidates = []
    for node in curriculum.nodes.values():
        if state.nodes[node.node_id].status is not KnowledgeStatus.UNDIAGNOSED:
            continue
        if all(
            state.nodes[child].status is not KnowledgeStatus.UNDIAGNOSED
            for child in curriculum.successors(node.node_id)
        ):
            candidates.append(node)
    if not candidates:
        return None
    return min(candidates, key=lambda node: node.priority).node_id


def normalize_answer(text: str) -> str:
    """Normalize short rule-mode answers for deterministic comparison."""
    return re.sub(r"\s+", "", text).replace("…", "...").lower()


def is_correct(answer: str, expected: str, curriculum: Curriculum) -> bool:
    """Evaluate rule-mode correctness using exact matches and aliases."""
    actual = normalize_answer(answer)
    target = normalize_answer(expected)
    if actual == target:
        return True
    return actual in {normalize_answer(item) for item in curriculum.answer_aliases.get(target, set())}


def classify_response(
    answer: str,
    expected: str,
    curriculum: Curriculum,
    *,
    prompt: str = "",
) -> ResponseCategory:
    """Classify a learner response while keeping fixture behavior stable.

    Args:
        answer: Learner answer from the current diagnostic turn.
        expected: Teacher-side expected answer. It may be English for generated
            skills, so partial-understanding checks cannot rely on exact string
            overlap only.
        curriculum: Active curriculum used for exact-answer aliases.
        prompt: Optional current diagnostic prompt. Generated humanities skills
            use this to detect safe partial evidence when the expected answer is
            in another language.

    Returns:
        A bounded response category. ``PARTIAL_CORRECT`` is used only when the
        answer carries a recognizable clue but does not satisfy the expected
        answer. It lets the tutor acknowledge partial understanding without
        advancing mastery.
    """
    normalized = normalize_answer(answer)
    if not normalized:
        return ResponseCategory.OTHER
    if any(token in answer for token in ("不懂", "看不懂", "為什麼", "怎麼來的", "解釋")):
        return ResponseCategory.DIFFICULTY
    if any(token in answer for token in ("不會", "不知道", "無法", "想不出", "不確定")):
        return ResponseCategory.INABILITY
    if is_correct(answer, expected, curriculum):
        return ResponseCategory.CORRECT
    if _has_partial_understanding(answer, expected, prompt):
        return ResponseCategory.PARTIAL_CORRECT
    return ResponseCategory.INCORRECT


def remediation_signal(answer: str) -> str | None:
    """Detect skill-remediation signals without changing fixture classifications."""
    if any(token in answer for token in ("太細", "太深入", "太進階")):
        return "too_detailed"
    if any(token in answer for token in ("太難", "看不懂")):
        return "too_difficult"
    if any(token in answer for token in ("太簡單", "太容易")):
        return "too_easy"
    if any(token in answer for token in ("專案", "project")):
        return "project_goal"
    if any(token in answer for token in ("考試", "面試", "測驗")):
        return "assessment_goal"
    return None


def apply_diagnostic_result(
    state: SessionState, node_id: str, answer: str, category: ResponseCategory, curriculum: Curriculum
) -> list[str]:
    """Apply diagnostic evidence and infer prerequisite state from correct answers."""
    if category is ResponseCategory.CORRECT:
        status = KnowledgeStatus.MASTERED
    elif category is ResponseCategory.PARTIAL_CORRECT:
        status = KnowledgeStatus.PARTIALLY_MASTERED
    else:
        status = KnowledgeStatus.NOT_MASTERED
    evidence = Evidence(response=answer, category=category.value, direct=True)
    state.nodes[node_id].update(status, evidence)
    changes = [f"{curriculum.nodes[node_id].label}: {status.value}（直接證據）"]
    if status is KnowledgeStatus.MASTERED:
        changes.extend(_mark_prerequisites_mastered(state, node_id, answer, category, curriculum))
    return changes


def _mark_prerequisites_mastered(
    state: SessionState, node_id: str, answer: str, category: ResponseCategory, curriculum: Curriculum
) -> list[str]:
    """Recursively mark prerequisite mastery inferred from a mastered child."""
    changes: list[str] = []
    for prerequisite in curriculum.nodes[node_id].prerequisites:
        parent = state.nodes[prerequisite]
        if parent.status not in (KnowledgeStatus.MASTERED, KnowledgeStatus.INFERRED_MASTERED):
            parent.update(
                KnowledgeStatus.INFERRED_MASTERED,
                Evidence(response=answer, category=category.value, direct=False),
            )
            changes.append(f"{curriculum.nodes[prerequisite].label}: inferred_mastered（由子節點推定）")
        changes.extend(_mark_prerequisites_mastered(state, prerequisite, answer, category, curriculum))
    return changes


def diagnostic_for(node_id: str, curriculum: Curriculum):
    """Return the diagnostic question for a known curriculum node."""
    return curriculum.diagnostics[node_id]


def _has_partial_understanding(answer: str, expected: str, prompt: str) -> bool:
    """Return whether an incomplete answer contains safe domain clues.

    The check is intentionally conservative. It does not mark arbitrary keyword
    overlap as correct; it only emits a partial category so the tutor can
    acknowledge a useful clue while continuing remediation.
    """
    normalized_answer = normalize_answer(answer)
    normalized_expected = normalize_answer(expected)
    if len(normalized_answer) < 2:
        return False
    if len(normalized_expected) >= 6:
        expected_chunks = {
            normalized_expected[index : index + 4]
            for index in range(0, max(0, len(normalized_expected) - 3))
        }
        if any(chunk and chunk in normalized_answer for chunk in expected_chunks):
            return True

    source_tokens = _significant_cjk_tokens(f"{expected} {prompt}")
    if source_tokens:
        return sum(1 for token in source_tokens if token in answer) >= 2
    return False


def _significant_cjk_tokens(text: str) -> set[str]:
    """Extract bounded CJK clue tokens from the active rubric and prompt.

    Returns:
        Domain-neutral tokens that can support a partial-understanding signal
        without embedding topic-specific facts in the classifier.
    """
    stop_tokens = {
        "請回答",
        "請簡述",
        "為什麼",
        "如何",
        "哪一位",
        "什麼",
        "是否",
        "可以",
        "需要",
        "概念",
        "學習",
        "診斷題",
    }
    tokens: set[str] = set()
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if phrase in stop_tokens:
            continue
        if len(phrase) <= 8:
            tokens.add(phrase)
            continue
        for index in range(0, len(phrase) - 1, 2):
            chunk = phrase[index : index + 4]
            if len(chunk) >= 2 and chunk not in stop_tokens:
                tokens.add(chunk)
    return {token for token in tokens if token not in stop_tokens}
