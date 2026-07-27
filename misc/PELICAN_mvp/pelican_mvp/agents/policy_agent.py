"""Policy agent executor for EDF strategy recommendations."""

from __future__ import annotations

from ..edf_simulator import EdfSimulator
from ..models import AgentRole, MethodologyStage, ProposalValidationStatus, SessionState
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
    ) -> tuple[object, AgentExecutionResult]:
        """Evaluate EDF and return the candidate snapshot plus safe proposal."""
        snapshot = self.edf.evaluate(state)
        result = AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.EDF_STRATEGY_SELECTION,
            artifact_type="strategy_recommendation",
            artifact_ref=safe_artifact_ref("edf_snapshot", snapshot.reason_code, "current EDF policy"),
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=snapshot.reason_code,
            display_summary=(
                f"{snapshot.learner_state}:{snapshot.pedagogical_strategy}:"
                f"{snapshot.route or 'fast'}"
            ),
            proposal_source="edf",
        )
        return snapshot, result
