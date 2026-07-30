"""Shared agent executor contracts for the PELICAN methodology pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import (
    AgentRole,
    MethodologyRef,
    MethodologyStage,
    ProposalValidationStatus,
)
from .artifacts import bound_agent_text


@dataclass(frozen=True)
class AgentExecutionContext:
    """Safe context passed from ``PelicanEngine`` to an agent executor.

    Args:
        learner_id: Local session identifier used only for correlation. Agents
            must not log it directly; structured logging hashes it at the
            observability boundary.
        turn_id: Current turn correlation id.
        cycle_id: Current methodology cycle correlation id.
        phase: Current learner-facing phase.
        mode: Current runtime mode, usually ``rule`` or ``llm``.
        node_id: Optional current focus node.
        skill_id: Optional active skill identifier.
        edf_state: Safe EDF learner-state label.
        edf_policy: Safe EDF policy label.
        recent_safe_signals: Bounded GUM signal labels.
        recent_messages: Bounded recent learner-visible transcript turns used
            only for response continuity.
        last_assistant_prompt: Latest learner-visible assistant prompt used to
            avoid repeating the same follow-up question.

    Compatibility:
        This context intentionally excludes hidden reasoning, model output,
        credentials, provider payloads, and non-visible prompts. Recent messages
        may contain learner-visible transcript text and must not be copied into
        structured logs or safe proposal metadata.
    """

    learner_id: str | None = None
    turn_id: str | None = None
    cycle_id: str | None = None
    phase: str = "unknown"
    mode: str = "rule"
    node_id: str | None = None
    skill_id: str | None = None
    edf_state: str = "unknown"
    edf_policy: str = "unknown"
    recent_safe_signals: tuple[str, ...] = ()
    recent_messages: tuple[dict[str, str], ...] = ()
    last_assistant_prompt: str = ""

    def to_log_fields(self) -> dict[str, str | int | None]:
        """Return allow-listed correlation fields for structured logs."""
        return {
            "turn_id": self.turn_id,
            "cycle_id": self.cycle_id,
            "phase": self.phase,
            "node_id": self.node_id,
            "skill_id": self.skill_id,
            "learner_state": self.edf_state,
            "strategy": self.edf_policy,
        }


@dataclass(frozen=True)
class AgentExecutionResult:
    """Safe result proposed by an agent before engine adoption.

    Args:
        role: Responsible methodology-layer agent role.
        stage: Six-stage methodology stage that will adopt or reject the result.
        artifact_type: Safe artifact type, such as ``skill_generation``.
        artifact_ref: Bounded reference to the proposed artifact.
        validation_status: Proposal status after local agent/validator checks.
        reason_code: Stable safe reason code.
        display_summary: Safe UI/export summary.
        pedagogical_move: Optional safe teaching-move label.
        final_message_preview: Optional bounded learner-facing preview after
            validation. This must be empty for non-tutor agents unless the
            artifact is explicitly learner-visible.
        proposal_source: Safe source, such as ``catalog``, ``runtime_generated``,
            ``rule``, ``llm``, or ``generic:humanities``.

    Ownership:
        Agents return proposals; ``PelicanEngine`` remains the only owner of
        session mutation. This separation keeps rejected/fallback proposals
        inspectable without letting agent output directly overwrite state.
    """

    role: AgentRole
    stage: MethodologyStage
    artifact_type: str
    artifact_ref: MethodologyRef
    validation_status: ProposalValidationStatus
    reason_code: str
    display_summary: str = ""
    pedagogical_move: str = ""
    final_message_preview: str = ""
    proposal_source: str = ""

    def to_safe_metadata(self) -> dict[str, str]:
        """Serialize bounded metadata for tests, UI, and export helpers."""
        return {
            "role": self.role.value,
            "stage": self.stage.value,
            "artifact_type": bound_agent_text(self.artifact_type, 80),
            "validation_status": self.validation_status.value,
            "reason_code": bound_agent_text(self.reason_code, 120),
            "display_summary": bound_agent_text(self.display_summary, 260),
            "pedagogical_move": bound_agent_text(self.pedagogical_move, 80),
            "final_message_preview": bound_agent_text(self.final_message_preview, 220),
            "proposal_source": bound_agent_text(self.proposal_source, 120),
        }


class BaseAgent(Protocol):
    """Protocol implemented by concrete PELICAN agent executors."""

    role: AgentRole

    def propose(self, context: AgentExecutionContext) -> AgentExecutionResult:
        """Return a bounded proposal without mutating session state.

        Args:
            context: Safe engine-owned execution context.

        Returns:
            An agent proposal ready for engine validation/adoption.
        """
        ...
