"""Adaptive tutoring and the bounded fast/slow strategy selector."""

from __future__ import annotations

from .curriculum import Curriculum
from .models import ResponseCategory, TutoringContext, TutoringStrategy


FAST_STRATEGIES = {
    ResponseCategory.CORRECT: TutoringStrategy.CONFIRMATION,
    ResponseCategory.PARTIAL_CORRECT: TutoringStrategy.CORRECTION,
    ResponseCategory.INCORRECT: TutoringStrategy.CORRECTION,
    ResponseCategory.INABILITY: TutoringStrategy.EXPLANATION,
    ResponseCategory.DIFFICULTY: TutoringStrategy.EXPLANATION,
    ResponseCategory.OTHER: TutoringStrategy.OPEN_QUESTION,
}


def select_strategy(
    context_or_category: TutoringContext | ResponseCategory,
    rounds: int | None = None,
    pedagogical_policy: str | None = None,
) -> tuple[TutoringStrategy, str]:
    """Select a fast or slow tutoring strategy constrained by current context.

    Args:
        context_or_category: Preferred ``TutoringContext`` carrying current EDF
            policy and safe GUM signal labels, or a legacy response category.
        rounds: Legacy round count when a category is passed.
        pedagogical_policy: Legacy EDF policy when a category is passed.

    Returns:
        Selected strategy and a safe reason string for user-visible/debug output.
    """
    if isinstance(context_or_category, TutoringContext):
        context = context_or_category
    else:
        context = TutoringContext(
            category=context_or_category,
            rounds=int(rounds or 0),
            pedagogical_policy=pedagogical_policy or "probe_understanding",
            learner_state="UNKNOWN",
            node_id=None,
            node_label="",
        )
    category = context.category
    rounds = context.rounds
    if rounds < 2:
        return FAST_STRATEGIES[category], "fast-thinking：依本回合回答類別選擇策略"
    candidates = _slow_candidates(category, context.pedagogical_policy)
    scored = [(strategy, _simulation_score(strategy, context)) for strategy in candidates]
    strategy, score = max(scored, key=lambda item: item[1])
    return strategy, f"slow-thinking：模擬 {len(candidates)} 條策略路徑後選擇最高分 {score:.2f}"


def select_strategy_for_category(
    category: ResponseCategory,
    rounds: int,
    pedagogical_policy: str | None = None,
) -> tuple[TutoringStrategy, str]:
    """Compatibility wrapper for older category-based strategy callers."""
    return select_strategy(category, rounds, pedagogical_policy)


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
    elif category in (ResponseCategory.INCORRECT, ResponseCategory.PARTIAL_CORRECT):
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


def _simulation_score(strategy: TutoringStrategy, context: TutoringContext, discount: float = 0.2) -> float:
    """A deterministic two-depth approximation of PELICAN's simulation tree."""
    category = context.category
    success_probability = {
        (ResponseCategory.INABILITY, TutoringStrategy.DECOMPOSITION): 0.85,
        (ResponseCategory.INABILITY, TutoringStrategy.SIMPLIFICATION): 0.75,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.DECOMPOSITION): 0.82,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.SIMPLIFICATION): 0.78,
        (ResponseCategory.PARTIAL_CORRECT, TutoringStrategy.CORRECTION): 0.84,
        (ResponseCategory.PARTIAL_CORRECT, TutoringStrategy.DECOMPOSITION): 0.74,
        (ResponseCategory.INCORRECT, TutoringStrategy.CORRECTION): 0.80,
        (ResponseCategory.INCORRECT, TutoringStrategy.DECOMPOSITION): 0.70,
    }.get((category, strategy), 0.60)
    recent = context.recent_signals[-3:]
    if strategy is TutoringStrategy.DECOMPOSITION and any(signal in {"unknown", ResponseCategory.INABILITY.value} for signal in recent):
        success_probability += 0.08
    if strategy is TutoringStrategy.SIMPLIFICATION and any(signal in {"too_detailed", "too_difficult", ResponseCategory.DIFFICULTY.value} for signal in recent):
        success_probability += 0.06
    if strategy is TutoringStrategy.CORRECTION and recent.count(ResponseCategory.INCORRECT.value) >= 2:
        success_probability += 0.06
    if strategy in (TutoringStrategy.CONFIRMATION, TutoringStrategy.OPEN_QUESTION) and recent.count(ResponseCategory.CORRECT.value) >= 2:
        success_probability += 0.05
    return success_probability + (1.0 - discount)


def rule_tutor_message(strategy: TutoringStrategy, node_id: str, prompt: str, curriculum: Curriculum) -> str:
    """Render a deterministic tutor message for rule mode."""
    label = curriculum.nodes[node_id].label
    hint_template = curriculum.tutor_hints.get(strategy, "請只聚焦「{label}」：{prompt}")
    return hint_template.format(label=label, prompt=prompt)
