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


def select_strategy(category: ResponseCategory, rounds: int, pedagogical_policy: str | None = None) -> tuple[TutoringStrategy, str]:
    """Select a fast or slow tutoring strategy constrained by EDF policy."""
    if rounds < 2:
        return FAST_STRATEGIES[category], "fast-thinking：依本回合回答類別選擇策略"
    candidates = _slow_candidates(category, pedagogical_policy)
    scored = [(strategy, _simulation_score(strategy, category)) for strategy in candidates]
    strategy, score = max(scored, key=lambda item: item[1])
    return strategy, f"slow-thinking：模擬 {len(candidates)} 條策略路徑後選擇最高分 {score:.2f}"


def strategy_for_remediation_signal(signal: str | None) -> TutoringStrategy | None:
    """Map domain-skill remediation signals to approved local tutoring moves."""
    if signal in {"too_detailed", "too_difficult", "unknown"}:
        return TutoringStrategy.DECOMPOSITION
    if signal == "too_easy":
        return TutoringStrategy.CONFIRMATION
    if signal in {"project_goal", "assessment_goal"}:
        return TutoringStrategy.OPEN_QUESTION
    return None


def _slow_candidates(category: ResponseCategory, pedagogical_policy: str | None = None) -> tuple[TutoringStrategy, ...]:
    """Return candidate strategies after repeated difficulty or failure."""
    candidates = []
    if category in (ResponseCategory.INABILITY, ResponseCategory.DIFFICULTY):
        candidates = [TutoringStrategy.DECOMPOSITION, TutoringStrategy.SIMPLIFICATION]
    elif category is ResponseCategory.INCORRECT:
        candidates = [TutoringStrategy.CORRECTION, TutoringStrategy.DECOMPOSITION]
    else:
        candidates = [TutoringStrategy.OPEN_QUESTION, TutoringStrategy.CONFIRMATION]

    if pedagogical_policy == "simplify_or_decompose":
        candidates = [c for c in candidates if c in (TutoringStrategy.SIMPLIFICATION, TutoringStrategy.DECOMPOSITION)]
    elif pedagogical_policy == "correct_and_explain":
        candidates = [c for c in candidates if c in (TutoringStrategy.CORRECTION, TutoringStrategy.EXPLANATION)]
    elif pedagogical_policy == "confirm_and_suggest_action":
        candidates = [c for c in candidates if c in (TutoringStrategy.CONFIRMATION, TutoringStrategy.CLOSED_QUESTION)]
    elif pedagogical_policy == "challenge_or_fade":
        candidates = [c for c in candidates if c in (TutoringStrategy.OPEN_QUESTION, TutoringStrategy.CONFIRMATION)]

    return tuple(candidates) if candidates else (TutoringStrategy.EXPLANATION,)


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
    """Render a deterministic tutor message for rule mode."""
    label = curriculum.nodes[node_id].label
    hint_template = curriculum.tutor_hints.get(strategy, "請只聚焦「{label}」：{prompt}")
    return hint_template.format(label=label, prompt=prompt)
