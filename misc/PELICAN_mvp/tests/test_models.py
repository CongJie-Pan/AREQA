import pytest
from pelican_mvp.models import (
    ActivityEvent,
    AgentProposal,
    AgentRole,
    DiagnosticQuestion,
    KnowledgeNode,
    KnowledgeStatus,
    LearnerIntakeProfile,
    LearningIntent,
    LearningPlanSnapshot,
    MemoryEvidenceRecord,
    MethodologyEvent,
    MethodologyEventType,
    MethodologyRef,
    MethodologyStage,
    MethodologyStatus,
    PlanSource,
    ProposalValidationStatus,
    SessionState,
    TranscriptEntry,
    TurnRecord,
)

def test_session_state_from_dict_defaults() -> None:
    payload = {"learner_id": "tester"}
    state = SessionState.from_dict(payload)
    assert state.learner_id == "tester"
    assert state.mode == "rule"
    assert state.phase == "onboarding"
    assert state.plan_source is PlanSource.GENERATED
    assert state.curriculum_id is None
    assert state.completed is False
    assert state.nodes == {}
    assert state.history == []

def test_session_state_from_dict_with_partial_nodes() -> None:
    payload = {
        "learner_id": "tester",
        "nodes": {
            "n1": {
                # missing status and updated_at
                "evidence": [{"response": "a", "category": "correct", "direct": True, "timestamp": "t1"}]
            }
        }
    }
    state = SessionState.from_dict(payload)
    assert state.nodes["n1"].status == KnowledgeStatus.UNDIAGNOSED
    assert len(state.nodes["n1"].evidence) == 1
    assert state.nodes["n1"].updated_at is None

def test_knowledge_status_enum() -> None:
    assert KnowledgeStatus("mastered") == KnowledgeStatus.MASTERED
    with pytest.raises(ValueError):
        KnowledgeStatus("unknown")

def test_turn_record_serialization() -> None:
    record = TurnRecord(
        prompt="p", response="r", phase="ph", node_id="n",
        category="c", strategy="s", state_changes=["change1"]
    )
    assert "change1" in record.state_changes
    assert record.prompt == "p"


def test_session_state_round_trips_generated_plan_snapshot() -> None:
    plan = LearningPlanSnapshot(
        plan_id="binary-search-basics",
        topic="binary search",
        goal_summary="Understand binary search boundaries.",
        nodes=(
            KnowledgeNode("sorted-data", "Sorted data"),
            KnowledgeNode("boundaries", "Boundary updates", ("sorted-data",), 1),
        ),
        diagnostics=(
            DiagnosticQuestion("boundaries", "Why update a boundary?", "discard half"),
        ),
        task_steps=(
            {"step_id": "apply", "node_id": "boundaries", "prompt": "Trace one step", "expected": "move low"},
        ),
        skill_id="binary_search",
        skill_version="0.1.0",
        skill_lifecycle="validated_generated",
        domain_category="stem",
        model_route="catalog",
    )
    state = SessionState(
        learner_id="tester",
        learning_plan=plan,
        phase="diagnosis",
    )

    restored = SessionState.from_dict(state.to_dict())

    assert restored.learning_plan == plan
    assert restored.learning_plan.skill_id == "binary_search"
    assert restored.learning_plan.model_route == "catalog"
    assert restored.plan_source is PlanSource.GENERATED
    assert restored.edf_snapshot.reason_code == "not_evaluated"
    assert restored.memory_snapshot.evidence_count == 0


def test_session_state_treats_legacy_curriculum_as_fixture() -> None:
    state = SessionState.from_dict({"learner_id": "tester", "curriculum_id": "cnn"})

    assert state.plan_source is PlanSource.FIXTURE
    assert state.phase == "diagnosis"


def test_session_state_round_trips_intake_profile_and_direct_evidence() -> None:
    state = SessionState(
        learner_id="tester",
        intake_profile=LearnerIntakeProfile(
            topic="深度學習",
            goal_summary="想先理解概念",
            intent=LearningIntent.CONCEPTUAL,
            level_hint="beginner",
            domain_category="stem",
            skill_id="deep_learning",
            skill_version="0.1.0",
            skill_lifecycle="validated_generated",
            model_route="openrouter_gpt_5_5",
            intake_turns=1,
        ),
        direct_evidence=[
            MemoryEvidenceRecord(
                source="user_message",
                kind="USER_EVIDENCE",
                text="使用者表示題目太細且不知道答案",
                topic="深度學習",
                node_id="mlp_implementation",
                signal="too_detailed",
            )
        ],
    )

    restored = SessionState.from_dict(state.to_dict())

    assert restored.intake_profile.intent is LearningIntent.CONCEPTUAL
    assert restored.intake_profile.skill_id == "deep_learning"
    assert restored.direct_evidence[0].kind == "USER_EVIDENCE"
    assert restored.direct_evidence[0].cold_export_eligible is False
    assert restored.direct_evidence[0].signal == "too_detailed"


def test_session_state_round_trips_activity_log() -> None:
    state = SessionState(
        learner_id="tester",
        activity_log=[
            ActivityEvent(
                code="skill_loaded",
                label="載入領域 Skill",
                status="done",
                detail="deep_learning",
            )
        ],
    )

    restored = SessionState.from_dict(state.to_dict())

    assert restored.activity_log[0].code == "skill_loaded"
    assert restored.activity_log[0].label == "載入領域 Skill"
    assert restored.activity_log[0].detail == "deep_learning"


def test_session_state_round_trips_transcript() -> None:
    state = SessionState(
        learner_id="tester",
        transcript=[
            TranscriptEntry(
                role="user",
                text="中國歷史",
                phase="onboarding",
            )
        ],
    )

    restored = SessionState.from_dict(state.to_dict())

    assert restored.transcript[0].role == "user"
    assert restored.transcript[0].text == "中國歷史"
    assert restored.transcript[0].phase == "onboarding"


def test_session_state_legacy_payload_defaults_new_skill_fields() -> None:
    state = SessionState.from_dict({"learner_id": "tester", "schema_version": 2})

    assert state.intake_profile.intent is LearningIntent.UNKNOWN
    assert state.intake_profile.domain_category == "unknown"
    assert state.direct_evidence == []
    assert state.activity_log == []


def test_session_state_schema_two_defaults_methodology_contract() -> None:
    state = SessionState.from_dict({"learner_id": "tester", "schema_version": 2})

    assert state.schema_version == 2
    assert state.turn_id is None
    assert state.cycle_id is None
    assert state.methodology_sequence == 0
    assert state.methodology_events == []
    assert state.agent_proposals == []
    assert state.learner_progress.nodes == ()
    assert state.to_dict()["schema_version"] == 2


def test_session_state_round_trips_methodology_records() -> None:
    event = MethodologyEvent(
        event_id="event_1",
        turn_id="turn_1",
        cycle_id="cycle_1",
        sequence=1,
        event_type=MethodologyEventType.PIPELINE_STAGE,
        stage=MethodologyStage.GOAL_FRAMING,
        status=MethodologyStatus.COMPLETED,
        source="engine",
        input_ref=MethodologyRef("learner_message", "turn_1", "topic"),
        output_ref=MethodologyRef("intake_profile", "profile", "goal"),
        reason_code="topic_received",
    )
    proposal = AgentProposal(
        proposal_id="proposal_1",
        turn_id="turn_1",
        cycle_id="cycle_1",
        sequence=2,
        role=AgentRole.INTAKE_AGENT,
        stage=MethodologyStage.GOAL_FRAMING,
        artifact_type="goal_interpretation",
        payload_ref=MethodologyRef("intake_profile", "profile", "goal"),
        validation_status=ProposalValidationStatus.ACCEPTED,
        reason_code="accepted",
    )
    state = SessionState(
        learner_id="tester",
        turn_id="turn_1",
        cycle_id="cycle_1",
        methodology_sequence=2,
        methodology_events=[event],
        agent_proposals=[proposal],
    )

    restored = SessionState.from_dict(state.to_dict())

    assert restored.methodology_sequence == 2
    assert restored.methodology_events[0].stage is MethodologyStage.GOAL_FRAMING
    assert restored.agent_proposals[0].role is AgentRole.INTAKE_AGENT


def test_session_state_drops_malformed_methodology_records() -> None:
    state = SessionState.from_dict(
        {
            "learner_id": "tester",
            "methodology_events": [{"event_type": "bad", "status": "completed"}],
            "agent_proposals": [{"role": "bad", "stage": "goal_framing"}],
        }
    )

    assert state.methodology_events == []
    assert state.agent_proposals == []
