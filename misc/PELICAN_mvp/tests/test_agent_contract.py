from pelican_mvp.agents import (
    AgentExecutionContext,
    AgentExecutionResult,
    CapabilityPolicy,
    LearningManagerAction,
    LearningManagerDecision,
    LearningManagerTurnContext,
    bound_agent_text,
    safe_artifact_ref,
)
from pelican_mvp.models import AgentRole, MethodologyStage, ProposalValidationStatus


def test_agent_execution_result_serializes_safe_bounded_metadata() -> None:
    long_preview = "safe preview " * 80
    result = AgentExecutionResult(
        role=AgentRole.SKILL_AGENT,
        stage=MethodologyStage.SKILL_CONSTRUCTION,
        artifact_type="skill_generation",
        artifact_ref=safe_artifact_ref("skill_route", "runtime_generated", "validated skill"),
        validation_status=ProposalValidationStatus.ACCEPTED,
        reason_code="validated",
        display_summary="Built a safe humanities skill summary.",
        final_message_preview=long_preview,
        proposal_source="runtime_generated",
    )

    metadata = result.to_safe_metadata()

    assert metadata["role"] == "skill_agent"
    assert metadata["proposal_source"] == "runtime_generated"
    assert len(metadata["final_message_preview"]) <= 220


def test_agent_context_log_fields_exclude_raw_payloads() -> None:
    context = AgentExecutionContext(
        learner_id="learner-123",
        turn_id="turn_1",
        cycle_id="cycle_1",
        phase="diagnosis",
        mode="llm",
        node_id="spring_autumn_order",
        skill_id="spring_autumn_history",
        edf_state="needs_support",
        edf_policy="simplify_or_decompose",
        recent_safe_signals=("unknown",),
    )

    fields = context.to_log_fields()

    assert fields["turn_id"] == "turn_1"
    assert fields["node_id"] == "spring_autumn_order"
    assert "learner-123" not in str(fields)
    assert "unknown" not in str(fields)


def test_safe_artifact_ref_and_bound_agent_text_normalize_display_fields() -> None:
    ref = safe_artifact_ref(" skill_route ", " runtime_generated ", " validated\nskill ")

    assert ref.ref_type == "skill_route"
    assert ref.ref_id == "runtime_generated"
    assert ref.label == "validated skill"
    assert bound_agent_text("a\n\nb", 10) == "a b"


def test_learning_manager_turn_context_keeps_raw_text_out_of_safe_decision_metadata() -> None:
    context = LearningManagerTurnContext(
        snapshot_id="snapshot_1",
        turn_id="turn_1",
        cycle_id="cycle_1",
        phase="tutoring",
        learner_text="private learner answer",
    )
    decision = LearningManagerDecision(
        action=LearningManagerAction.ANSWER_DIRECTLY,
        capability="",
        policy=CapabilityPolicy.NONE,
        target_phase=context.phase,
        confidence=0.8,
        reason_code="clarification",
        proposal_source="llm",
        snapshot_id=context.snapshot_id,
    )

    assert context.to_llm_payload()["learner_text"] == "private learner answer"
    assert "private learner answer" not in str(decision.to_safe_metadata())
