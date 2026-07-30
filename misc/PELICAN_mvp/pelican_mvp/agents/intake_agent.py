"""Intake agent executor for bounded goal-framing proposals."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..domain_catalog import DomainResolution, resolve_domain_category
from ..models import AgentRole, LearningIntent, MethodologyRef, MethodologyStage, ProposalValidationStatus
from .artifacts import bound_agent_text, safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


@dataclass(frozen=True)
class IntakeInterpretation:
    """Safe interpretation returned by ``IntakeAgent`` before engine mutation."""

    result: AgentExecutionResult
    topic: str = ""
    goal_summary: str = ""
    intent: LearningIntent = LearningIntent.UNKNOWN
    level_hint: str = "unknown"
    clarification_message: str = ""
    domain_resolution: DomainResolution | None = None


class IntakeAgent:
    """Own goal-framing proposals without mutating ``SessionState``.

    The agent receives raw learner text only as a method argument. It returns
    bounded metadata and normalized labels; ``PelicanEngine`` remains responsible
    for writing the intake profile after validation/adoption.
    """

    role = AgentRole.INTAKE_AGENT

    def __init__(self, *, artifact_root: Path | None = None) -> None:
        """Initialize intake routing with an optional runtime skill cache root.

        Args:
            artifact_root: Optional generated-skill artifact root. This keeps
                local tests isolated while allowing production intake to reuse
                the default runtime skill cache.
        """
        self.artifact_root = artifact_root

    def propose_topic(self, topic: str, context: AgentExecutionContext | None = None) -> IntakeInterpretation:
        """Propose a scoped topic and domain route for a learner utterance."""
        resolution = resolve_domain_category(topic, artifact_root=self.artifact_root)
        ref = safe_artifact_ref("learner_turn", (context.turn_id if context else None) or "turn", "topic answer")
        result = self._result(
            "topic_interpretation",
            ref,
            resolution.reason_code,
            display_summary=f"{resolution.category.value}:{resolution.route_slug}",
        )
        return IntakeInterpretation(result=result, topic=bound_agent_text(topic, 100), domain_resolution=resolution)

    def propose_goal(
        self,
        goal: str,
        intent: LearningIntent,
        context: AgentExecutionContext | None = None,
    ) -> IntakeInterpretation:
        """Propose a goal summary and learning intent label."""
        ref = safe_artifact_ref("learner_turn", (context.turn_id if context else None) or "turn", "goal answer")
        result = self._result(
            "goal_interpretation",
            ref,
            intent.value,
            display_summary=f"intent:{intent.value}",
        )
        return IntakeInterpretation(result=result, goal_summary=bound_agent_text(goal, 160), intent=intent)

    def propose_level(
        self,
        level_hint: str,
        context: AgentExecutionContext | None = None,
    ) -> IntakeInterpretation:
        """Propose a coarse level hint without asserting mastery evidence."""
        ref = safe_artifact_ref("learner_turn", (context.turn_id if context else None) or "turn", "level answer")
        result = self._result(
            "level_interpretation",
            ref,
            level_hint,
            display_summary=f"level:{level_hint}",
        )
        return IntakeInterpretation(result=result, level_hint=bound_agent_text(level_hint, 80) or "unknown")

    def propose_clarification(
        self,
        *,
        stage: str,
        message: str,
        reason_code: str,
        source: str,
        context: AgentExecutionContext | None = None,
    ) -> IntakeInterpretation:
        """Propose a bounded onboarding clarification without mutating state.

        Args:
            stage: Pending onboarding slot, such as ``goal`` or ``level``.
            message: Learner-facing clarification selected by the engine.
            reason_code: Safe semantic reason that triggered clarification.
            source: Safe message source label, such as ``llm`` or ``rule``.
            context: Optional turn context used only for safe artifact refs.

        Returns:
            A bounded clarification interpretation. ``PelicanEngine`` remains
            responsible for recording the proposal and preserving the current
            intake slot.
        """
        ref = safe_artifact_ref(
            "learner_turn",
            (context.turn_id if context else None) or "turn",
            f"{stage} clarification",
        )
        result = self._result(
            "intake_clarification",
            ref,
            reason_code,
            display_summary=f"{stage}:{source}",
        )
        return IntakeInterpretation(
            result=result,
            clarification_message=bound_agent_text(message, 500),
        )

    def _result(
        self,
        artifact_type: str,
        ref: MethodologyRef,
        reason_code: str,
        *,
        display_summary: str = "",
    ) -> AgentExecutionResult:
        """Build one accepted goal-framing proposal."""
        return AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.GOAL_FRAMING,
            artifact_type=artifact_type,
            artifact_ref=ref,
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=reason_code,
            display_summary=display_summary,
            proposal_source="rule",
        )
