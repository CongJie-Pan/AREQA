"""Slow simulator agent executor for deeper tutor-response proposals."""

from __future__ import annotations

from dataclasses import replace

from ..curriculum import Curriculum
from ..llm import LlmAdapter
from ..models import (
    AgentRole,
    ResponseCategory,
    SessionState,
    TutoringContext,
    TutoringStrategy,
)
from ..tutoring import StrategySimulationCandidate, simulate_strategy_candidates
from .artifacts import bound_agent_text
from .base import AgentExecutionContext
from .fast_tutor_agent import TutorAgentResponse, _candidate_or_fallback, _response_from_proposal


class SlowSimulatorAgent:
    """Produce slow-route tutor proposals after candidate path simulation."""

    role = AgentRole.SLOW_SIMULATOR_AGENT

    def __init__(self, llm: LlmAdapter | None = None) -> None:
        """Create a slow simulator agent around an optional tutor LLM adapter."""
        self.llm = llm or LlmAdapter()

    def propose_response(
        self,
        *,
        state: SessionState,
        curriculum: Curriculum,
        strategy: TutoringStrategy,
        node_id: str,
        base_prompt: str,
        evidence_signal: str,
        recent_safe_signals: tuple[str, ...] = (),
        base_message: str | None = None,
        context: AgentExecutionContext | None = None,
    ) -> TutorAgentResponse:
        """Propose a response after simulating multiple tutoring paths.

        Args:
            state: Engine-owned session state. Only bounded state labels are
                used for simulation; raw learner text is not inspected.
            curriculum: Current knowledge tree.
            strategy: Strategy selected by the deterministic policy. The slow
                simulator recomputes the same candidate family to produce a
                traceable comparison and selected path.
            node_id: Current concept node.
            base_prompt: Current prompt for fallback response generation.
            evidence_signal: Current bounded evidence signal.
            recent_safe_signals: Recent bounded GUM signal labels.
            base_message: Optional engine-provided fallback response.
            context: Safe execution correlation metadata.

        Returns:
            A bounded tutor response whose display summary includes the
            simulated candidate count, selected strategy, expected gain, risk,
            and compact candidate comparison.

        Side Effects:
            None. The engine remains responsible for persistence and structured
            log emission after adopting the proposal.
        """
        simulation_context = _simulation_context(
            state=state,
            curriculum=curriculum,
            node_id=node_id,
            evidence_signal=evidence_signal,
            recent_safe_signals=recent_safe_signals,
        )
        candidates = simulate_strategy_candidates(simulation_context)
        selected = max(candidates, key=lambda item: item.score)
        proposal, status, reason = _candidate_or_fallback(
            role=self.role,
            llm=self.llm,
            state=state,
            curriculum=curriculum,
            strategy=selected.strategy,
            node_id=node_id,
            base_prompt=base_prompt,
            evidence_signal=evidence_signal,
            recent_safe_signals=recent_safe_signals,
            base_message=base_message,
            slow_route=True,
        )
        proposal = replace(
            proposal,
            summary=_simulation_summary(
                candidates=candidates,
                selected=selected,
                fallback_reason=reason,
            ),
            pedagogical_move=_slow_pedagogical_move(proposal.pedagogical_move),
            strategy=selected.strategy.value,
        )
        return _response_from_proposal(self.role, proposal, status, reason)


def _simulation_context(
    *,
    state: SessionState,
    curriculum: Curriculum,
    node_id: str,
    evidence_signal: str,
    recent_safe_signals: tuple[str, ...],
) -> TutoringContext:
    """Build a bounded context for slow candidate simulation."""
    category = _category_from_signal(evidence_signal)
    step_id = state.current_step_id or ""
    rounds = max(2, int(state.step_rounds.get(step_id, 2)))
    node_label = curriculum.nodes[node_id].label if node_id in curriculum.nodes else ""
    return TutoringContext(
        category=category,
        rounds=rounds,
        pedagogical_policy=state.edf_snapshot.pedagogical_strategy,
        learner_state=state.edf_snapshot.learner_state,
        node_id=node_id,
        node_label=node_label,
        recent_signals=recent_safe_signals,
        plan_source=state.plan_source,
        skill_id=state.learning_plan.skill_id if state.learning_plan else None,
    )


def _category_from_signal(signal: str) -> ResponseCategory:
    """Convert a bounded signal label into a response category."""
    try:
        return ResponseCategory(signal)
    except ValueError:
        if signal == "unknown":
            return ResponseCategory.INABILITY
        return ResponseCategory.OTHER


def _simulation_summary(
    *,
    candidates: tuple[StrategySimulationCandidate, ...],
    selected: StrategySimulationCandidate,
    fallback_reason: str,
) -> str:
    """Render a bounded candidate comparison for trace display."""
    comparison = "; ".join(
        f"{candidate.strategy.value}=score:{candidate.score:.2f}/"
        f"gain:{candidate.expected_gain:.2f}/risk:{candidate.risk:.2f}"
        for candidate in candidates
    )
    return bound_agent_text(
        "slow_simulation "
        f"candidates={len(candidates)} selected={selected.strategy.value} "
        f"gain={selected.expected_gain:.2f} risk={selected.risk:.2f} "
        f"reason={fallback_reason}; {comparison}",
        260,
    )


def _slow_pedagogical_move(move: str) -> str:
    """Ensure slow-route proposals remain visibly attributable in traces."""
    normalized = move or "simulation"
    return normalized if normalized.startswith("slow_") else f"slow_{normalized}"
