"""Adaptive tutoring and the bounded fast/slow strategy selector."""

from __future__ import annotations

from .curriculum import Curriculum
from .models import ResponseCategory, TutoringStrategy


FAST_STRATEGIES = {
    ResponseCategory.CORRECT: TutoringStrategy.CONFIRMATION,
    ResponseCategory.INCORRECT: TutoringStrategy.CORRECTION,
    ResponseCategory.INABILITY: TutoringStrategy.EXPLANATION,
    ResponseCategory.DIFFICULTY: TutoringStrategy.EXPLANATION,
    ResponseCategory.OTHER: TutoringStrategy.OPEN_QUESTION,
}


def select_strategy(category: ResponseCategory, rounds: int) -> tuple[TutoringStrategy, str]:
    if rounds < 2:
        return FAST_STRATEGIES[category], "fast-thinking：依本回合回答類別選擇策略"
    candidates = _slow_candidates(category)
    scored = [(strategy, _simulation_score(strategy, category)) for strategy in candidates]
    strategy, score = max(scored, key=lambda item: item[1])
    return strategy, f"slow-thinking：模擬 {len(candidates)} 條策略路徑後選擇最高分 {score:.2f}"


def _slow_candidates(category: ResponseCategory) -> tuple[TutoringStrategy, TutoringStrategy]:
    if category in (ResponseCategory.INABILITY, ResponseCategory.DIFFICULTY):
        return (TutoringStrategy.DECOMPOSITION, TutoringStrategy.SIMPLIFICATION)
    if category is ResponseCategory.INCORRECT:
        return (TutoringStrategy.CORRECTION, TutoringStrategy.DECOMPOSITION)
    return (TutoringStrategy.OPEN_QUESTION, TutoringStrategy.CONFIRMATION)


def _simulation_score(strategy: TutoringStrategy, category: ResponseCategory, discount: float = 0.2) -> float:
    """A deterministic two-depth approximation of PELICAN's simulation tree."""
    success_probability = {
        (ResponseCategory.INABILITY, TutoringStrategy.DECOMPOSITION): 0.85,
        (ResponseCategory.INABILITY, TutoringStrategy.SIMPLIFICATION): 0.75,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.DECOMPOSITION): 0.82,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.SIMPLIFICATION): 0.78,
        (ResponseCategory.INCORRECT, TutoringStrategy.CORRECTION): 0.80,
        (ResponseCategory.INCORRECT, TutoringStrategy.DECOMPOSITION): 0.70,
    }.get((category, strategy), 0.60)
    return success_probability + (1.0 - discount)


def rule_tutor_message(strategy: TutoringStrategy, node_id: str, prompt: str, curriculum: Curriculum) -> str:
    label = curriculum.nodes[node_id].label
    hint_template = curriculum.tutor_hints.get(strategy, "請只聚焦「{label}」：{prompt}")
    return hint_template.format(label=label, prompt=prompt)
