"""Diagnosis agent executor for bounded diagnostic-task proposals."""

from __future__ import annotations

from dataclasses import dataclass

from ..curriculum import Curriculum
from ..diagnosis import diagnostic_for, next_diagnostic_node
from ..llm import LlmAdapter, LlmUnavailable
from ..models import (
    AgentRole,
    DiagnosticQuestion,
    MethodologyStage,
    ProposalValidationStatus,
    SessionState,
)
from .artifacts import safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


@dataclass(frozen=True)
class DiagnosticAgentProposal:
    """Safe diagnostic-task proposal plus the adopted question candidate."""

    result: AgentExecutionResult
    node_id: str | None
    question: DiagnosticQuestion | None
    reason_code: str


class DiagnosisAgent:
    """Select the next diagnostic task without mutating session state."""

    role = AgentRole.DIAGNOSIS_AGENT

    def __init__(self, llm: LlmAdapter | None = None) -> None:
        """Create a diagnosis agent with optional verified-question provider."""
        self.llm = llm or LlmAdapter()

    def propose_next_diagnostic(
        self,
        state: SessionState,
        curriculum: Curriculum,
        *,
        context: AgentExecutionContext | None = None,
    ) -> DiagnosticAgentProposal:
        """Propose the next diagnostic node and bounded question source."""
        node_id = next_diagnostic_node(state, curriculum)
        if node_id is None:
            return DiagnosticAgentProposal(
                result=AgentExecutionResult(
                    role=self.role,
                    stage=MethodologyStage.COGNITIVE_DIAGNOSIS,
                    artifact_type="diagnostic_completion",
                    artifact_ref=safe_artifact_ref("diagnostic_node", "complete", "diagnosis complete"),
                    validation_status=ProposalValidationStatus.ACCEPTED,
                    reason_code="diagnosis_complete",
                    display_summary="diagnosis complete",
                    proposal_source="rule",
                ),
                node_id=None,
                question=None,
                reason_code="diagnosis_complete",
            )

        question = diagnostic_for(node_id, curriculum)
        reason_code = "successor_first"
        source = question.source
        skill_question_locked = bool(state.learning_plan and state.learning_plan.skill_id and question.source == "skill")
        if state.mode == "llm" and not skill_question_locked:
            try:
                generated = self.llm.verified_diagnostic(curriculum.nodes[node_id].label)
                if generated:
                    question = DiagnosticQuestion(node_id, generated.prompt, generated.expected_answer, generated.source)
                    source = generated.source
                    reason_code = "llm_verified"
            except LlmUnavailable:
                reason_code = "llm_unavailable_fallback"

        result = AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.COGNITIVE_DIAGNOSIS,
            artifact_type="diagnostic_selection",
            artifact_ref=safe_artifact_ref("diagnostic_node", node_id, "next diagnostic node"),
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=reason_code,
            display_summary=f"{source}:{node_id}",
            proposal_source=source,
        )
        return DiagnosticAgentProposal(result=result, node_id=node_id, question=question, reason_code=reason_code)
