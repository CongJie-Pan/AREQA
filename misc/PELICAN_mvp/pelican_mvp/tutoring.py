"""Adaptive tutoring and the bounded fast/slow strategy selector."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True)
class StrategySimulationCandidate:
    """Safe summary of one simulated tutoring strategy path.

    Args:
        strategy: Candidate tutoring strategy.
        score: Deterministic expected utility score used for selection.
        expected_gain: Bounded proxy for learning progress if the candidate is
            chosen. This is derived metadata, not a learner memory fact.
        risk: Bounded proxy for confusion or overload risk.
        rationale: Safe explanation suitable for trace display.
    """

    strategy: TutoringStrategy
    score: float
    expected_gain: float
    risk: float
    rationale: str


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
    candidates = simulate_strategy_candidates(context)
    selected = max(candidates, key=lambda item: item.score)
    return selected.strategy, f"slow-thinking：模擬 {len(candidates)} 條策略路徑後選擇最高分 {selected.score:.2f}"


def simulate_strategy_candidates(context: TutoringContext) -> tuple[StrategySimulationCandidate, ...]:
    """Simulate candidate tutoring paths for repeated or fragile attempts.

    Args:
        context: Current tutoring context after state, GUM, and EDF updates.

    Returns:
        Candidate strategy summaries sorted in the same order as the policy
        candidates. The caller selects the highest score.

    Compatibility:
        This is a deterministic local approximation of the paper's slow
        simulator. It never uses raw learner text and only emits bounded labels
        so the results can be shown in traces.
    """
    candidates = _slow_candidates(context.category, context.pedagogical_policy)
    return tuple(_simulate_strategy(strategy, context) for strategy in candidates)


def select_strategy_for_category(
    category: ResponseCategory,
    rounds: int,
    pedagogical_policy: str | None = None,
) -> tuple[TutoringStrategy, str]:
    """Compatibility wrapper for older category-based strategy callers."""
    return select_strategy(category, rounds, pedagogical_policy)


def strategy_for_remediation_signal(signal: str | None) -> TutoringStrategy | None:
    """Map domain-skill remediation signals to approved local tutoring moves."""
    if signal == "unknown":
        return TutoringStrategy.EXPLANATION
    if signal in {"too_detailed", "too_difficult"}:
        return TutoringStrategy.DECOMPOSITION
    if signal == "too_easy":
        return TutoringStrategy.CONFIRMATION
    if signal in {"project_goal", "assessment_goal"}:
        return TutoringStrategy.OPEN_QUESTION
    return None


def _slow_candidates(
    category: ResponseCategory,
    pedagogical_policy: str | None = None,
) -> tuple[TutoringStrategy, ...]:
    """Return candidate strategies after repeated difficulty or failure."""
    candidates = []
    if category in (ResponseCategory.INABILITY, ResponseCategory.DIFFICULTY):
        candidates = [TutoringStrategy.EXPLANATION, TutoringStrategy.SIMPLIFICATION]
    elif category in (ResponseCategory.INCORRECT, ResponseCategory.PARTIAL_CORRECT):
        candidates = [TutoringStrategy.CORRECTION, TutoringStrategy.DECOMPOSITION]
    else:
        candidates = [TutoringStrategy.OPEN_QUESTION, TutoringStrategy.CONFIRMATION]

    if pedagogical_policy == "simplify_or_decompose":
        allowed = (
            TutoringStrategy.EXPLANATION,
            TutoringStrategy.SIMPLIFICATION,
            TutoringStrategy.DECOMPOSITION,
        )
        candidates = [c for c in candidates if c in allowed]
    elif pedagogical_policy == "correct_and_explain":
        candidates = [
            c
            for c in candidates
            if c in (TutoringStrategy.CORRECTION, TutoringStrategy.EXPLANATION)
        ]
    elif pedagogical_policy == "confirm_and_suggest_action":
        candidates = [
            c
            for c in candidates
            if c in (TutoringStrategy.CONFIRMATION, TutoringStrategy.CLOSED_QUESTION)
        ]
    elif pedagogical_policy == "challenge_or_fade":
        candidates = [c for c in candidates if c in (TutoringStrategy.OPEN_QUESTION, TutoringStrategy.CONFIRMATION)]

    return tuple(candidates) if candidates else (TutoringStrategy.EXPLANATION,)


def _simulation_score(strategy: TutoringStrategy, context: TutoringContext, discount: float = 0.2) -> float:
    """A deterministic two-depth approximation of PELICAN's simulation tree."""
    return _simulate_strategy(strategy, context, discount=discount).score


def _simulate_strategy(
    strategy: TutoringStrategy,
    context: TutoringContext,
    discount: float = 0.2,
) -> StrategySimulationCandidate:
    """Return one deterministic slow-simulation candidate."""
    category = context.category
    success_probability = {
        (ResponseCategory.INABILITY, TutoringStrategy.DECOMPOSITION): 0.85,
        (ResponseCategory.INABILITY, TutoringStrategy.EXPLANATION): 0.92,
        (ResponseCategory.INABILITY, TutoringStrategy.SIMPLIFICATION): 0.78,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.DECOMPOSITION): 0.82,
        (ResponseCategory.DIFFICULTY, TutoringStrategy.SIMPLIFICATION): 0.78,
        (ResponseCategory.PARTIAL_CORRECT, TutoringStrategy.CORRECTION): 0.84,
        (ResponseCategory.PARTIAL_CORRECT, TutoringStrategy.DECOMPOSITION): 0.74,
        (ResponseCategory.INCORRECT, TutoringStrategy.CORRECTION): 0.80,
        (ResponseCategory.INCORRECT, TutoringStrategy.DECOMPOSITION): 0.70,
    }.get((category, strategy), 0.60)
    recent = context.recent_signals[-3:]
    if strategy is TutoringStrategy.EXPLANATION and any(
        signal in {"unknown", ResponseCategory.INABILITY.value} for signal in recent
    ):
        success_probability += 0.08
    if strategy is TutoringStrategy.SIMPLIFICATION and any(
        signal in {"too_detailed", "too_difficult", ResponseCategory.DIFFICULTY.value}
        for signal in recent
    ):
        success_probability += 0.06
    if strategy is TutoringStrategy.CORRECTION and recent.count(ResponseCategory.INCORRECT.value) >= 2:
        success_probability += 0.06
    if (
        strategy in (TutoringStrategy.CONFIRMATION, TutoringStrategy.OPEN_QUESTION)
        and recent.count(ResponseCategory.CORRECT.value) >= 2
    ):
        success_probability += 0.05
    expected_gain = max(0.0, min(1.0, success_probability))
    risk = max(0.0, min(1.0, 1.0 - expected_gain + (discount / 2.0)))
    score = expected_gain + (1.0 - discount)
    rationale = _candidate_rationale(strategy, context, expected_gain, risk)
    return StrategySimulationCandidate(
        strategy=strategy,
        score=score,
        expected_gain=expected_gain,
        risk=risk,
        rationale=rationale,
    )


def _candidate_rationale(
    strategy: TutoringStrategy,
    context: TutoringContext,
    expected_gain: float,
    risk: float,
) -> str:
    """Build a safe rationale for simulation trace output."""
    if strategy is TutoringStrategy.EXPLANATION:
        base = "teach missing concept before rechecking"
    elif strategy is TutoringStrategy.SIMPLIFICATION:
        base = "lower abstraction to reduce load"
    elif strategy is TutoringStrategy.DECOMPOSITION:
        base = "split the current task into smaller checks"
    elif strategy is TutoringStrategy.CORRECTION:
        base = "address current misconception directly"
    else:
        base = "continue with a bounded follow-up"
    return (
        f"{strategy.value}: {base}; category={context.category.value}; "
        f"gain={expected_gain:.2f}; risk={risk:.2f}"
    )


def rule_tutor_message(strategy: TutoringStrategy, node_id: str, prompt: str, curriculum: Curriculum) -> str:
    """Render a deterministic tutor message for rule mode."""
    label = curriculum.nodes[node_id].label
    hint_template = curriculum.tutor_hints.get(strategy, "請只聚焦「{label}」：{prompt}")
    return hint_template.format(label=label, prompt=prompt)
