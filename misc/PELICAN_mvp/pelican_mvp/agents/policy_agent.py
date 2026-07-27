"""Policy agent executor for EDF strategy recommendations."""

from __future__ import annotations

from ..edf_simulator import EdfSimulator
from ..models import AgentRole, MethodologyStage, ProposalValidationStatus, SessionState, TutorStrategyDecision
from .artifacts import safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


class PolicyAgent:
    """Propose EDF strategy metadata without directly mutating state."""

    role = AgentRole.POLICY_AGENT

    def __init__(self, edf: EdfSimulator | None = None) -> None:
        """Create a policy agent around the deterministic EDF evaluator."""
        self.edf = edf or EdfSimulator()

    def propose_strategy(
        self,
        state: SessionState,
        context: AgentExecutionContext | None = None,
    ) -> tuple[TutorStrategyDecision, AgentExecutionResult]:
        """Evaluate EDF and return the authoritative strategy decision.

        Args:
            state: Current session after GUM and knowledge-state updates.
            context: Optional safe execution correlation metadata.

        Returns:
            The bounded strategy decision plus an accepted policy proposal. The
            proposal metadata contains route, state, and strategy labels only;
            raw learner text and model output remain outside this boundary.
        """
        decision = self.edf.decide(state)
        result = AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.EDF_STRATEGY_SELECTION,
            artifact_type="strategy_decision",
            artifact_ref=safe_artifact_ref("strategy_decision", decision.reason_code, "current EDF policy"),
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=decision.reason_code,
            display_summary=(
                f"{decision.learner_state}:{decision.selected_strategy.value}:"
                f"{decision.route or 'fast'}"
            ),
            proposal_source="edf",
        )
        return decision, result
