"""Skill Agent executor for the Agentic PELICAN skill-construction stage."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain_skill import DomainSkill
from ..models import AgentRole, LearnerIntakeProfile, MethodologyStage, ProposalValidationStatus
from ..observability import log_event
from ..skill_generator import DomainSkillGenerator, SkillGenerationResult
from .artifacts import safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


@dataclass(frozen=True)
class SkillAgentInput:
    """Input owned by ``SkillAgent`` when proposing a skill artifact.

    Args:
        profile: Calibrated learner intake profile. The profile carries only the
            scoped topic, goal summary, intent, level hint, and safe route
            metadata needed for skill construction.
        force_regenerate: Whether to bypass catalog/cache and exercise runtime
            generation. Tests use this to verify repair and fallback behavior.

    Privacy:
        The profile topic and goal are learner-provided content. This input may
        be sent to the skill-generation model, but ``SkillAgent`` returns only
        bounded proposal metadata and never logs raw profile text.
    """

    profile: LearnerIntakeProfile
    force_regenerate: bool = False


@dataclass(frozen=True)
class SkillAgentProposal:
    """Validated Skill Agent proposal adopted later by ``PelicanEngine``.

    Args:
        skill: Validated catalog/runtime/generic skill selected by the agent.
        route: Safe route/source string, such as ``catalog`` or
            ``generic:humanities``.
        attempts: Safe attempt-level proposal records for UI/export trace.
        used_fallback: Whether the final skill is an explicit fallback route.
        final_reason_code: Stable safe reason code for the final route.

    Ownership:
        This object is a proposal. It does not compile a learning plan or mutate
        session state. The engine validates/adopts the skill by compiling it into
        a session-owned ``LearningPlanSnapshot``.
    """

    skill: DomainSkill
    route: str
    attempts: tuple[AgentExecutionResult, ...]
    used_fallback: bool
    final_reason_code: str

    @classmethod
    def from_generation_result(cls, result: SkillGenerationResult) -> "SkillAgentProposal":
        """Convert a generator result into Skill Agent proposal metadata."""
        attempts = tuple(
            AgentExecutionResult(
                role=AgentRole.SKILL_AGENT,
                stage=MethodologyStage.SKILL_CONSTRUCTION,
                artifact_type="skill_generation",
                artifact_ref=safe_artifact_ref("skill_route", attempt.route, "skill proposal attempt"),
                validation_status=attempt.validation_status,
                reason_code=attempt.reason_code,
                display_summary=(
                    f"{attempt.route}: {attempt.validation_status.value} ({attempt.reason_code})"
                ),
                proposal_source=attempt.route,
            )
            for attempt in result.attempts
        )
        return cls(
            skill=result.skill,
            route=result.route,
            attempts=attempts,
            used_fallback=result.used_fallback,
            final_reason_code=result.final_reason_code,
        )


class SkillAgent:
    """Generate, validate, and propose one domain skill for Skill Construction."""

    role = AgentRole.SKILL_AGENT

    def __init__(self, generator: DomainSkillGenerator) -> None:
        """Create a Skill Agent around the existing safe generation service.

        Args:
            generator: Low-level service that owns catalog/cache/runtime
                generation, validation, repair retries, and generic fallback.
        """
        self.generator = generator

    def propose_skill(
        self,
        agent_input: SkillAgentInput,
        *,
        context: AgentExecutionContext | None = None,
    ) -> SkillAgentProposal:
        """Return a validated skill proposal without mutating session state.

        Args:
            agent_input: Scoped intake profile and optional regeneration flag.
            context: Optional safe execution context for structured logs.

        Returns:
            Skill proposal containing a validated skill plus bounded attempt
            metadata.

        Raises:
            SkillGenerationError: Propagated when no safe skill route can be
                selected, such as an unknown domain requiring clarification.

        Side Effects:
            Emits safe structured events:
            ``pelican_skill_agent_started`` and
            ``pelican_skill_agent_proposal_validated``. The metadata is limited
            to phase/turn/cycle/route/status/reason/skill identifiers.
        """
        log_fields = context.to_log_fields() if context else {}
        proposal_log_fields = dict(log_fields)
        # The proposal owns final skill identifiers; context may only know the
        # previously active skill and must not override the accepted proposal.
        proposal_log_fields.pop("skill_id", None)
        log_event(
            "pelican_skill_agent_started",
            learner_id=context.learner_id if context else None,
            agent_role=self.role.value,
            agent_stage=MethodologyStage.SKILL_CONSTRUCTION.value,
            artifact_type="skill_generation",
            **log_fields,
        )
        result = self.generator.generate_with_result(
            agent_input.profile.topic,
            force_regenerate=agent_input.force_regenerate,
            goal_context=agent_input.profile.goal_summary,
        )
        proposal = SkillAgentProposal.from_generation_result(result)
        log_event(
            "pelican_skill_agent_proposal_validated",
            learner_id=context.learner_id if context else None,
            agent_role=self.role.value,
            agent_stage=MethodologyStage.SKILL_CONSTRUCTION.value,
            artifact_type="skill_generation",
            skill_id=proposal.skill.skill_id,
            skill_version=proposal.skill.version,
            domain_category=proposal.skill.domain_category.value,
            route=proposal.route,
            proposal_source=proposal.route,
            validation_status=(
                ProposalValidationStatus.FALLBACK_USED.value
                if proposal.used_fallback
                else ProposalValidationStatus.ACCEPTED.value
            ),
            reason_code=proposal.final_reason_code,
            **proposal_log_fields,
        )
        return proposal
