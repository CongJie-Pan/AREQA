import logging

from pelican_mvp.agents import (
    CapabilityPolicy,
    CapabilityRegistry,
    CapabilityRequest,
    CapabilityResult,
    LearningCapability,
    repair_capability_policy,
)


def test_capability_registry_registers_and_validates_known_capability() -> None:
    registry = CapabilityRegistry()
    registry.register(
        LearningCapability(
            name="diagnose_answer",
            allowed_policies=frozenset({CapabilityPolicy.WRITE_PROPOSED}),
            can_write_mastery=True,
            emits_learner_text=False,
        )
    )

    result = registry.validate(
        CapabilityRequest(
            name="diagnose_answer",
            policy=CapabilityPolicy.WRITE_PROPOSED,
            turn_id="turn_1",
            cycle_id="cycle_1",
            target_phase="cognitive_diagnosis",
        )
    )

    assert registry.names() == ("diagnose_answer",)
    assert result.accepted is True
    assert result.can_write_mastery is True
    assert result.emits_learner_text is False


def test_capability_registry_rejects_unknown_capability() -> None:
    registry = CapabilityRegistry()

    result = registry.validate(CapabilityRequest(name="missing", policy=CapabilityPolicy.SPECIALIST))

    assert result.accepted is False
    assert result.reason_code == "unknown_capability"


def test_capability_registry_rejects_policy_denied_before_handler_runs() -> None:
    called = False

    def handler(request: CapabilityRequest) -> CapabilityResult:
        nonlocal called
        called = True
        return CapabilityResult(True, request.name, request.policy, "ok")

    registry = CapabilityRegistry()
    registry.register(
        LearningCapability(
            name="clarify",
            allowed_policies=frozenset({CapabilityPolicy.NONE}),
            handler=handler,
            emits_learner_text=True,
        )
    )

    result = registry.execute(CapabilityRequest(name="clarify", policy=CapabilityPolicy.WRITE_PROPOSED))

    assert result.accepted is False
    assert result.reason_code == "policy_denied"
    assert called is False


def test_manifest_policy_repair_corrects_single_policy_capability() -> None:
    manifest = {
        "tutor_response": ("specialist",),
        "conversation_control": ("none",),
        "diagnose_answer": ("write_proposed",),
    }

    tutor = repair_capability_policy("tutor_response", CapabilityPolicy.WRITE_PROPOSED, manifest)
    control = repair_capability_policy("conversation_control", CapabilityPolicy.WRITE_PROPOSED, manifest)
    diagnosis = repair_capability_policy("diagnose_answer", CapabilityPolicy.NONE, manifest)

    assert tutor.accepted is True
    assert tutor.repaired is True
    assert tutor.effective_policy is CapabilityPolicy.SPECIALIST
    assert control.effective_policy is CapabilityPolicy.NONE
    assert diagnosis.effective_policy is CapabilityPolicy.WRITE_PROPOSED


def test_manifest_policy_repair_rejects_ambiguous_policy_choice() -> None:
    manifest = {"clarify_current_prompt": ("none", "specialist")}

    result = repair_capability_policy(
        "clarify_current_prompt",
        CapabilityPolicy.WRITE_PROPOSED,
        manifest,
    )

    assert result.accepted is False
    assert result.repaired is False
    assert result.reason_code == "ambiguous_policy_repair"


def test_manifest_policy_repair_accepts_valid_pair_without_repair() -> None:
    result = repair_capability_policy(
        "resume_pipeline",
        CapabilityPolicy.READ,
        {"resume_pipeline": ("read", "specialist")},
    )

    assert result.accepted is True
    assert result.repaired is False
    assert result.effective_policy is CapabilityPolicy.READ


def test_capability_registry_executes_handler_after_policy_validation() -> None:
    def handler(request: CapabilityRequest) -> CapabilityResult:
        return CapabilityResult(
            accepted=True,
            capability=request.name,
            policy=request.policy,
            reason_code="handled",
            can_write_mastery=False,
            emits_learner_text=True,
            message="bounded response",
            metadata={"kind": "clarification"},
        )

    registry = CapabilityRegistry()
    registry.register(
        LearningCapability(
            name="clarify",
            allowed_policies=frozenset({CapabilityPolicy.NONE}),
            handler=handler,
            can_write_mastery=False,
            emits_learner_text=True,
        )
    )

    result = registry.execute(CapabilityRequest(name="clarify", policy=CapabilityPolicy.NONE))

    assert result.accepted is True
    assert result.reason_code == "handled"
    assert result.can_write_mastery is False
    assert result.emits_learner_text is True
    assert result.message == "bounded response"


def test_capability_registry_converts_handler_failure_to_safe_result() -> None:
    def handler(request: CapabilityRequest) -> CapabilityResult:
        raise RuntimeError("raw failure details")

    registry = CapabilityRegistry()
    registry.register(
        LearningCapability(
            name="slow_simulator",
            allowed_policies=frozenset({CapabilityPolicy.SPECIALIST}),
            handler=handler,
        )
    )

    result = registry.execute(CapabilityRequest(name="slow_simulator", policy=CapabilityPolicy.SPECIALIST))

    assert result.accepted is False
    assert result.reason_code == "capability_failed"
    assert "raw failure details" not in str(result)


def test_capability_registry_logs_safe_selection_and_completion(caplog) -> None:
    def handler(request: CapabilityRequest) -> CapabilityResult:
        return CapabilityResult(True, request.name, request.policy, "handled", emits_learner_text=True)

    registry = CapabilityRegistry()
    registry.register(
        LearningCapability(
            name="clarify",
            allowed_policies=frozenset({CapabilityPolicy.NONE}),
            handler=handler,
            emits_learner_text=True,
        )
    )
    logging.getLogger("pelican_mvp").propagate = True

    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        registry.execute(CapabilityRequest(name="clarify", policy=CapabilityPolicy.NONE, turn_id="turn_1"))

    selected = next(record for record in caplog.records if record.message == "pelican_learning_capability_selected")
    completed = next(record for record in caplog.records if record.message == "pelican_learning_capability_completed")
    assert selected.capability == "clarify"
    assert completed.reason_code == "handled"


def test_capability_registry_logs_safe_rejection(caplog) -> None:
    registry = CapabilityRegistry()
    logging.getLogger("pelican_mvp").propagate = True

    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        registry.validate(CapabilityRequest(name="missing raw secret", policy=CapabilityPolicy.NONE))

    record = next(item for item in caplog.records if item.message == "pelican_learning_capability_rejected")
    assert record.capability == "missing_raw_secret"
    assert record.reason_code == "unknown_capability"
