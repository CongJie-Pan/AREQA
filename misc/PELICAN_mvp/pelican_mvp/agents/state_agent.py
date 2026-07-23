"""State agent executor for bounded knowledge-state update proposals."""

from __future__ import annotations

from ..models import AgentRole, MethodologyStage, ProposalValidationStatus, ResponseCategory
from .artifacts import safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


class StateAgent:
    """Propose state-delta metadata while the engine owns mutation."""

    role = AgentRole.STATE_AGENT

    def propose_diagnostic_update(
        self,
        node_id: str,
        category: ResponseCategory,
        context: AgentExecutionContext | None = None,
    ) -> AgentExecutionResult:
        """Return a safe proposal to update the active diagnostic node."""
        return AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.KNOWLEDGE_STATE_UPDATE,
            artifact_type="diagnostic_state_update",
            artifact_ref=safe_artifact_ref("diagnostic_evidence", node_id, "classified diagnostic evidence"),
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=category.value,
            display_summary=f"{node_id}:{category.value}",
            proposal_source="rule",
        )

    def propose_practice_update(
        self,
        node_id: str,
        category: ResponseCategory,
        context: AgentExecutionContext | None = None,
    ) -> AgentExecutionResult:
        """Return a safe proposal to update a tutoring practice step."""
        return AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.KNOWLEDGE_STATE_UPDATE,
            artifact_type="practice_state_update",
            artifact_ref=safe_artifact_ref("practice_evidence", node_id, "classified practice evidence"),
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=category.value,
            display_summary=f"{node_id}:{category.value}",
            proposal_source="rule",
        )
