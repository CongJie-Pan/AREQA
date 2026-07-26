"""Fast tutor agent executor for bounded one-step tutor responses."""

from __future__ import annotations

from dataclasses import dataclass

from ..curriculum import Curriculum
from ..llm import LlmAdapter, LlmUnavailable
from ..models import (
    AgentRole,
    BoundedTutorProposal,
    MethodologyStage,
    ProposalValidationStatus,
    SessionState,
    TutoringStrategy,
)
from ..observability import log_event
from ..tutoring import rule_tutor_message
from .artifacts import safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


@dataclass(frozen=True)
class TutorAgentResponse:
    """Final bounded tutor proposal and safe executor result."""

    proposal: BoundedTutorProposal
    validation_status: ProposalValidationStatus
    reason_code: str
    result: AgentExecutionResult


class FastTutorAgent:
    """Produce concise grounded tutor responses with fail-closed validation."""

    role = AgentRole.FAST_TUTOR_AGENT

    def __init__(self, llm: LlmAdapter | None = None) -> None:
        """Create a fast tutor agent around an optional tutor LLM adapter."""
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
        """Propose a learner-facing response candidate for the current node."""
        proposal, status, reason = _candidate_or_fallback(
            role=self.role,
            llm=self.llm,
            state=state,
            curriculum=curriculum,
            strategy=strategy,
            node_id=node_id,
            base_prompt=base_prompt,
            evidence_signal=evidence_signal,
            recent_safe_signals=recent_safe_signals,
            base_message=base_message,
            slow_route=False,
        )
        return _response_from_proposal(self.role, proposal, status, reason)


def _candidate_or_fallback(
    *,
    role: AgentRole,
    llm: LlmAdapter,
    state: SessionState,
    curriculum: Curriculum,
    strategy: TutoringStrategy,
    node_id: str,
    base_prompt: str,
    evidence_signal: str,
    recent_safe_signals: tuple[str, ...],
    base_message: str | None,
    slow_route: bool,
) -> tuple[BoundedTutorProposal, ProposalValidationStatus, str]:
    """Return a validated LLM candidate or explicit deterministic fallback."""
    if state.mode == "llm":
        try:
            proposal = llm.tutor_proposal(
                strategy=strategy,
                node_id=node_id,
                node_label=curriculum.nodes[node_id].label,
                base_prompt=base_prompt,
                learner_state=state.edf_snapshot.learner_state,
                edf_policy=state.edf_snapshot.pedagogical_strategy,
                recent_signals=recent_safe_signals,
                evidence_signal=evidence_signal,
                domain_category=(
                    state.learning_plan.domain_category
                    if state.learning_plan and state.learning_plan.domain_category
                    else state.intake_profile.domain_category
                ),
                concept_description=_concept_description_from_state(state, node_id),
                expected_answer=state.current_expected_answer,
                remediation_template=_remediation_template_from_state(state, node_id),
                teaching_methodology=(
                    state.learning_plan.teaching_methodology
                    if state.learning_plan
                    else {}
                ),
            )
            log_event(
                "pelican_tutor_proposal_generated",
                learner_id=state.learner_id,
                phase=state.phase,
                node_id=node_id,
                strategy=strategy.value,
                agent_role=role.value,
                proposal_source="llm",
                reason_code="candidate",
            )
            domain_category = (
                state.learning_plan.domain_category
                if state.learning_plan and state.learning_plan.domain_category
                else state.intake_profile.domain_category
            )
            status, reason = validate_tutor_proposal(
                proposal,
                node_id,
                strategy,
                domain_category=domain_category,
            )
            if proposal and status is ProposalValidationStatus.ACCEPTED:
                return proposal, status, reason
            return (
                fallback_tutor_proposal(
                    strategy,
                    node_id,
                    evidence_signal,
                    curriculum,
                    base_prompt,
                    base_message=base_message,
                    reason_code=reason,
                    slow_route=slow_route,
                ),
                ProposalValidationStatus.FALLBACK_USED,
                reason,
            )
        except LlmUnavailable:
            reason_code = "llm_unavailable_fallback"
    else:
        reason_code = "rule_mode_baseline"
    return (
        fallback_tutor_proposal(
            strategy,
            node_id,
            evidence_signal,
            curriculum,
            base_prompt,
            base_message=base_message,
            reason_code=reason_code,
            slow_route=slow_route,
        ),
        ProposalValidationStatus.FALLBACK_USED,
        reason_code,
    )


def validate_tutor_proposal(
    proposal: BoundedTutorProposal | None,
    node_id: str,
    strategy: TutoringStrategy,
    *,
    domain_category: str | None = None,
) -> tuple[ProposalValidationStatus, str]:
    """Validate a bounded tutor proposal before learner display."""
    if proposal is None:
        return ProposalValidationStatus.REJECTED, "empty_tutor_proposal"
    if proposal.node_id != node_id:
        return ProposalValidationStatus.REJECTED, "off_node_tutor_proposal"
    if proposal.strategy != strategy.value:
        return ProposalValidationStatus.REJECTED, "strategy_mismatch"
    if proposal.evidence_signal in {"unknown", "inability_to_respond"} and _is_question_only_inability_response(
        proposal.response
    ):
        return ProposalValidationStatus.REJECTED, "question_only_inability_response"
    if domain_category == "humanities" and proposal.evidence_signal in {
        "unknown",
        "inability_to_respond",
        "incorrect",
        "partial_correct",
        "difficulty_in_understanding",
    } and _lacks_humanities_explanation_cycle(proposal.response):
        return ProposalValidationStatus.REJECTED, "thin_humanities_remediation"
    if len(proposal.response) > 900:
        return ProposalValidationStatus.REJECTED, "tutor_response_too_long"
    if len(proposal.response.strip()) < 8:
        return ProposalValidationStatus.REJECTED, "tutor_response_too_short"
    return ProposalValidationStatus.ACCEPTED, "accepted"


def _is_question_only_inability_response(response: str) -> bool:
    """Return whether an inability response keeps probing without teaching.

    Args:
        response: Candidate learner-facing tutor response.

    Returns:
        ``True`` when the response appears to be primarily another diagnostic
        question. This is intentionally conservative: direct teaching may end
        with one low-load check, but it must include explicit explanation
        markers before the question.
    """
    text = response.strip()
    if not any(mark in text for mark in ("?", "？", "你認為", "如何", "什麼")):
        return False
    teaching_markers = (
        "重點",
        "答案",
        "先直接",
        "先講",
        "原因",
        "因為",
        "例如",
        "也就是",
        "這表示",
        "所以",
        "說明",
    )
    return not any(marker in text for marker in teaching_markers)


def _lacks_humanities_explanation_cycle(response: str) -> bool:
    """Return whether humanities remediation skips teaching before rechecking.

    Humanities learners often need an explanatory narrative before a mastery
    check. This validator blocks LLM proposals that continue probing or offer a
    thin hint without asking the learner to restate the concept in their own
    words.
    """
    text = response.strip()
    explanation_markers = (
        "背景",
        "脈絡",
        "原因",
        "關鍵",
        "因為",
        "所以",
        "先理解",
        "先抓",
        "這表示",
        "這代表",
    )


def _concept_description_from_state(state: SessionState, node_id: str) -> str:
    """Return the generated skill description for the active node."""
    if not state.learning_plan:
        return ""
    for node in state.learning_plan.nodes:
        if node.node_id == node_id:
            return node.label
    return ""


def _remediation_template_from_state(state: SessionState, node_id: str) -> str:
    """Return skill-authored remediation guidance for the active node."""
    if not state.learning_plan:
        return ""
    return state.learning_plan.remediation_templates.get(node_id, "")
    restatement_markers = (
        "用自己的話",
        "再說一次",
        "重新說",
        "解釋給我聽",
        "說給我聽",
        "複述",
    )
    return not (
        any(marker in text for marker in explanation_markers)
        and any(marker in text for marker in restatement_markers)
    )


def fallback_tutor_proposal(
    strategy: TutoringStrategy,
    node_id: str,
    evidence_signal: str,
    curriculum: Curriculum,
    base_prompt: str,
    *,
    base_message: str | None,
    reason_code: str,
    slow_route: bool,
) -> BoundedTutorProposal:
    """Build deterministic fallback content with explicit route metadata."""
    message = base_message or rule_tutor_message(strategy, node_id, base_prompt, curriculum)
    label = curriculum.nodes[node_id].label
    move = {
        "unknown": "scaffold",
        "too_detailed": "scope_recalibration",
        "too_difficult": "scope_recalibration",
    }.get(evidence_signal, strategy.value)
    if slow_route and not move.startswith("slow_"):
        move = f"slow_{move}"
    return BoundedTutorProposal(
        response=message,
        pedagogical_move=move,
        summary=f"{reason_code}: {strategy.value} grounded on {label}",
        node_id=node_id,
        strategy=strategy.value,
        evidence_signal=evidence_signal,
        source="rule",
    )


def _response_from_proposal(
    role: AgentRole,
    proposal: BoundedTutorProposal,
    status: ProposalValidationStatus,
    reason_code: str,
) -> TutorAgentResponse:
    """Create a safe executor result from a validated/fallback tutor proposal."""
    result = AgentExecutionResult(
        role=role,
        stage=MethodologyStage.TUTOR_RESPONSE,
        artifact_type="tutor_proposal",
        artifact_ref=safe_artifact_ref("tutor_message", proposal.source, "tutor response"),
        validation_status=status,
        reason_code=reason_code,
        display_summary=proposal.summary,
        pedagogical_move=proposal.pedagogical_move,
        final_message_preview=proposal.response,
        proposal_source=proposal.source,
    )
    return TutorAgentResponse(proposal=proposal, validation_status=status, reason_code=reason_code, result=result)
