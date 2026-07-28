from pelican_mvp.agents import (
    CapabilityPolicy,
    CapabilityRegistry,
    CapabilityRequest,
    CapabilityResult,
    LearningCapability,
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
