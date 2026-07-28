import logging
import pytest

from pelican_mvp.agents import (
    CapabilityPolicy,
    CapabilityRegistry,
    LearningManagerAction,
    LearningCapability,
    LearningManagerDecision,
    LearningManagerOrchestrator,
    LearningManagerTurnContext,
)
from pelican_mvp.llm import LlmUnavailable


class FakeLlm:
    def __init__(self, payload=None, exc: Exception | None = None) -> None:
        self.payload = payload or {}
        self.exc = exc
        self.seen_context = None

    def orchestrate_turn_decision(self, turn_context):
        self.seen_context = turn_context
        if self.exc:
            raise self.exc
        return self.payload


def make_context(**updates) -> LearningManagerTurnContext:
    values = {
        "snapshot_id": "snapshot_1",
        "turn_id": "turn_1",
        "cycle_id": "cycle_1",
        "phase": "tutoring",
        "current_node_id": "meiji_reform",
        "current_prompt_kind": "active_question",
        "expected_response_shape": "short_answer",
        "edf_state": "exploring",
        "edf_policy": "probe_understanding",
        "recent_safe_signals": ("active_prompt",),
        "learner_text": "secret learner text",
    }
    values.update(updates)
    return LearningManagerTurnContext(**values)


def valid_payload(**updates) -> dict:
    payload = {
        "snapshot_id": "snapshot_1",
        "action": "call_capability",
        "capability": "diagnose_answer",
        "policy": "write_proposed",
        "target_phase": "cognitive_diagnosis",
        "confidence": 0.91,
        "reason_code": "active_prompt_answer",
    }
    payload.update(updates)
    return payload


def test_interpret_turn_adopts_answer_diagnosis_capability() -> None:
    orchestrator = LearningManagerOrchestrator(FakeLlm(valid_payload()), capability_names=("diagnose_answer",))

    decision = orchestrator.interpret_turn(make_context())

    assert decision.action is LearningManagerAction.CALL_CAPABILITY
    assert decision.capability == "diagnose_answer"
    assert decision.policy is CapabilityPolicy.WRITE_PROPOSED
    assert decision.proposal_source == "llm"
    assert decision.reason_code == "active_prompt_answer"


def test_interpret_turn_allows_direct_no_write_clarification() -> None:
    payload = valid_payload(
        action="answer_directly",
        capability="diagnose_answer",
        policy="none",
        target_phase="tutor_response",
        reason_code="learner_clarification",
    )
    orchestrator = LearningManagerOrchestrator(FakeLlm(payload), capability_names=("diagnose_answer",))

    decision = orchestrator.interpret_turn(make_context(learner_text="what does turning point mean?"))

    assert decision.action is LearningManagerAction.ANSWER_DIRECTLY
    assert decision.capability == ""
    assert decision.policy is CapabilityPolicy.NONE
    assert decision.reason_code == "learner_clarification"


def test_interpret_turn_allows_delegated_specialist_capability() -> None:
    payload = valid_payload(
        action="delegate_capability",
        capability="slow_simulator",
        policy="specialist",
        target_phase="tutor_response",
        reason_code="complex_teaching_choice",
    )
    orchestrator = LearningManagerOrchestrator(FakeLlm(payload), capability_names=("slow_simulator",))

    decision = orchestrator.interpret_turn(make_context())

    assert decision.action is LearningManagerAction.DELEGATE_CAPABILITY
    assert decision.capability == "slow_simulator"
    assert decision.policy is CapabilityPolicy.SPECIALIST


@pytest.mark.parametrize(
    ("payload", "reason_code"),
    [
        (valid_payload(confidence=0.2), "low_confidence"),
        (valid_payload(action="not_allowed"), "invalid_enum"),
        (valid_payload(snapshot_id="stale"), "stale_snapshot"),
        (valid_payload(capability="unknown"), "unknown_capability"),
        (valid_payload(capability=""), "missing_capability"),
        (valid_payload(policy="none"), "policy_denied"),
        (valid_payload(action="continue_pipeline", policy="write_proposed"), "write_policy_without_capability"),
    ],
)
def test_interpret_turn_falls_back_for_unsafe_payloads(payload: dict, reason_code: str) -> None:
    orchestrator = LearningManagerOrchestrator(FakeLlm(payload), capability_names=("diagnose_answer",))

    decision = orchestrator.interpret_turn(make_context())

    assert decision.action is LearningManagerAction.FALLBACK_LEGACY_PIPELINE
    assert decision.policy is CapabilityPolicy.NONE
    assert decision.proposal_source == "fallback"
    assert decision.reason_code == reason_code


def test_interpret_turn_falls_back_when_llm_unavailable() -> None:
    llm = FakeLlm(exc=LlmUnavailable("missing", reason_codes=("llm_missing_api_key",)))
    orchestrator = LearningManagerOrchestrator(llm, capability_names=("diagnose_answer",))

    decision = orchestrator.interpret_turn(make_context())

    assert decision.action is LearningManagerAction.FALLBACK_LEGACY_PIPELINE
    assert decision.reason_code == "llm_missing_api_key"


def test_safe_metadata_excludes_raw_learner_text_and_model_output() -> None:
    raw_text = "very distinctive private learner sentence"
    payload = valid_payload(reason_code="Active prompt answer with spaces")
    orchestrator = LearningManagerOrchestrator(FakeLlm(payload), capability_names=("diagnose_answer",))

    decision = orchestrator.interpret_turn(make_context(learner_text=raw_text))
    metadata = decision.to_safe_metadata()

    assert raw_text not in str(metadata)
    assert "model output" not in str(metadata).lower()
    assert metadata["reason_code"] == "active_prompt_answer_with_spaces"


def test_turn_context_payload_exposes_capability_manifest_to_llm() -> None:
    llm = FakeLlm(valid_payload())
    orchestrator = LearningManagerOrchestrator(llm, capability_names=("diagnose_answer", "slow_simulator"))

    orchestrator.interpret_turn(make_context())

    assert llm.seen_context["available_capabilities"] == ["diagnose_answer", "slow_simulator"]
    assert llm.seen_context["learner_text"] == "secret learner text"


def test_orchestrator_can_validate_against_registry_manifest() -> None:
    registry = CapabilityRegistry()
    registry.register(
        LearningCapability(
            name="diagnose_answer",
            allowed_policies=frozenset({CapabilityPolicy.WRITE_PROPOSED}),
            can_write_mastery=True,
        )
    )
    orchestrator = LearningManagerOrchestrator(
        FakeLlm(valid_payload()),
        capability_names=registry.names(),
    )

    decision = orchestrator.interpret_turn(make_context())

    assert decision.action is LearningManagerAction.CALL_CAPABILITY
    assert decision.capability == "diagnose_answer"


def test_learning_manager_decision_is_read_only_metadata() -> None:
    decision = LearningManagerDecision(
        action=LearningManagerAction.FALLBACK_LEGACY_PIPELINE,
        capability="",
        policy=CapabilityPolicy.NONE,
        target_phase="tutoring",
        confidence=0.0,
        reason_code="fallback",
        proposal_source="fallback",
        snapshot_id="snapshot_1",
    )

    assert decision.to_safe_metadata()["action"] == "fallback_legacy_pipeline"


def test_orchestrator_logs_decision_without_raw_learner_text(caplog: pytest.LogCaptureFixture) -> None:
    raw_text = "private learner text should not enter logs"
    orchestrator = LearningManagerOrchestrator(FakeLlm(valid_payload()), capability_names=("diagnose_answer",))

    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        orchestrator.interpret_turn(make_context(learner_text=raw_text))

    record = next(item for item in caplog.records if item.message == "pelican_learning_orchestrator_decided")
    assert record.action == "call_capability"
    assert record.capability == "diagnose_answer"
    assert record.policy == "write_proposed"
    assert record.confidence_bucket == "high"
    assert raw_text not in caplog.text


def test_orchestrator_logs_fallback_without_raw_learner_text(caplog: pytest.LogCaptureFixture) -> None:
    raw_text = "private fallback learner text"
    orchestrator = LearningManagerOrchestrator(
        FakeLlm(valid_payload(confidence=0.1)),
        capability_names=("diagnose_answer",),
    )

    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        orchestrator.interpret_turn(make_context(learner_text=raw_text))

    record = next(item for item in caplog.records if item.message == "pelican_learning_orchestrator_fallback")
    assert record.action == "fallback_legacy_pipeline"
    assert record.reason_code == "low_confidence"
    assert raw_text not in caplog.text
