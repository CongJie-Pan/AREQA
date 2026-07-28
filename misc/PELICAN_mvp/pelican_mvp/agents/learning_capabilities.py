"""Engine-side capability registry for learning manager orchestration.

The registry exposes existing PELICAN specialist behavior as named capabilities
without giving the LLM direct execution authority. ``LearningManagerOrchestrator``
may propose a capability name and policy, but this module validates the request
before a callable runs, and ``PelicanEngine`` remains responsible for state
mutation and mastery-write adoption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Callable, Mapping

from ..observability import log_event
from .learning_manager_orchestrator import CapabilityPolicy


CapabilityHandler = Callable[["CapabilityRequest"], "CapabilityResult"]


@dataclass(frozen=True)
class LearningCapability:
    """Safe manifest entry for one orchestratable learning capability.

    Args:
        name: Stable lowercase capability label selected by the orchestrator.
        allowed_policies: Policies allowed to invoke this capability.
        can_write_mastery: Whether this capability may lead to mastery evidence
            writes after engine validation.
        emits_learner_text: Whether successful execution can produce
            learner-facing text.
        handler: Optional callable used by the engine dispatcher. Tests may
            leave this empty when only validating registry policy behavior.
        description: Safe human-readable summary for docs or debugging. It must
            not contain raw prompts, learner answers, or model output.
    """

    name: str
    allowed_policies: frozenset[CapabilityPolicy]
    can_write_mastery: bool = False
    emits_learner_text: bool = False
    handler: CapabilityHandler | None = None
    description: str = ""

    def allows(self, policy: CapabilityPolicy) -> bool:
        """Return whether the capability may be used with ``policy``."""
        return policy in self.allowed_policies


@dataclass(frozen=True)
class CapabilityRequest:
    """Engine-owned request to execute a validated learning capability.

    Args:
        name: Capability name selected after orchestration validation.
        policy: Requested capability policy.
        turn_id: Safe turn correlation id.
        cycle_id: Safe cycle correlation id.
        target_phase: Safe target pipeline phase.
        payload: Optional bounded engine-owned data. The registry does not log
            or inspect raw learner text; concrete handlers remain responsible
            for their own privacy boundaries.
    """

    name: str
    policy: CapabilityPolicy
    turn_id: str | None = None
    cycle_id: str | None = None
    target_phase: str = "unknown"
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityResult:
    """Safe capability execution result returned to the engine.

    Args:
        accepted: Whether the capability request passed registry policy checks.
        capability: Safe capability name.
        policy: Effective capability policy.
        reason_code: Stable safe reason code.
        can_write_mastery: Whether the capability may write mastery evidence
            after engine validation.
        emits_learner_text: Whether ``message`` can be shown to the learner.
        message: Optional learner-facing text or bounded summary. Raw model
            payloads and hidden reasoning must not be placed here.
        metadata: Additional safe bounded labels for tests or observability.
    """

    accepted: bool
    capability: str
    policy: CapabilityPolicy
    reason_code: str
    can_write_mastery: bool = False
    emits_learner_text: bool = False
    message: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)


class CapabilityRegistry:
    """Validate and execute named learning capabilities under explicit policy."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._capabilities: dict[str, LearningCapability] = {}

    def register(self, capability: LearningCapability) -> None:
        """Register or replace one capability manifest.

        Args:
            capability: Capability manifest and optional handler.

        Raises:
            ValueError: If the capability name is empty or no policies are
                allowed. Replacing a capability is allowed so tests and engine
                assembly can provide deterministic fakes.
        """
        name = _normalize_capability_name(capability.name)
        if not name:
            raise ValueError("capability name is required")
        if not capability.allowed_policies:
            raise ValueError("capability must allow at least one policy")
        self._capabilities[name] = LearningCapability(
            name=name,
            allowed_policies=frozenset(capability.allowed_policies),
            can_write_mastery=capability.can_write_mastery,
            emits_learner_text=capability.emits_learner_text,
            handler=capability.handler,
            description=capability.description,
        )

    def names(self) -> tuple[str, ...]:
        """Return sorted safe capability names available to the orchestrator."""
        return tuple(sorted(self._capabilities))

    def lookup(self, name: str) -> LearningCapability | None:
        """Return a capability by name, or ``None`` when absent."""
        return self._capabilities.get(_normalize_capability_name(name))

    def validate(self, request: CapabilityRequest) -> CapabilityResult:
        """Validate a request without executing the capability handler.

        Args:
            request: Engine-owned request.

        Returns:
            Accepted result metadata when the capability exists and allows the
            requested policy; otherwise a safe rejected result.
        """
        name = _normalize_capability_name(request.name)
        capability = self.lookup(name)
        if capability is None:
            return self.rejected(name, request.policy, "unknown_capability", request=request)
        if not capability.allows(request.policy):
            return self.rejected(name, request.policy, "policy_denied", request=request)
        log_event(
            "pelican_learning_capability_selected",
            level=logging.INFO,
            turn_id=request.turn_id,
            cycle_id=request.cycle_id,
            capability=name,
            policy=request.policy.value,
            target_phase=request.target_phase,
            reason_code="accepted",
        )
        return CapabilityResult(
            accepted=True,
            capability=name,
            policy=request.policy,
            reason_code="accepted",
            can_write_mastery=capability.can_write_mastery,
            emits_learner_text=capability.emits_learner_text,
        )

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """Validate and execute a registered handler when available.

        Args:
            request: Engine-owned capability request.

        Returns:
            Handler result after validation, a no-handler accepted result, or a
            safe rejected result. Unexpected handler exceptions are converted to
            deterministic safe failures so orchestration cannot crash the engine
            path.
        """
        validation = self.validate(request)
        if not validation.accepted:
            return validation
        capability = self.lookup(request.name)
        if capability is None or capability.handler is None:
            return validation
        try:
            result = capability.handler(request)
        except Exception:
            return self.rejected(request.name, request.policy, "capability_failed", request=request)
        completed = CapabilityResult(
            accepted=result.accepted,
            capability=_normalize_capability_name(result.capability) or capability.name,
            policy=result.policy,
            reason_code=result.reason_code,
            can_write_mastery=capability.can_write_mastery and result.can_write_mastery,
            emits_learner_text=capability.emits_learner_text and result.emits_learner_text,
            message=result.message,
            metadata=result.metadata,
        )
        log_event(
            "pelican_learning_capability_completed",
            level=logging.INFO,
            turn_id=request.turn_id,
            cycle_id=request.cycle_id,
            capability=completed.capability,
            policy=completed.policy.value,
            target_phase=request.target_phase,
            outcome="accepted" if completed.accepted else "rejected",
            reason_code=completed.reason_code,
        )
        return completed

    def rejected(
        self,
        name: str,
        policy: CapabilityPolicy,
        reason_code: str,
        *,
        request: CapabilityRequest | None = None,
    ) -> CapabilityResult:
        """Return a safe rejected result without invoking a capability."""
        result = CapabilityResult(
            accepted=False,
            capability=_normalize_capability_name(name),
            policy=policy,
            reason_code=_normalize_capability_name(reason_code) or "rejected",
        )
        log_event(
            "pelican_learning_capability_rejected",
            level=logging.INFO,
            turn_id=request.turn_id if request else None,
            cycle_id=request.cycle_id if request else None,
            capability=result.capability,
            policy=policy.value,
            target_phase=request.target_phase if request else "unknown",
            outcome="rejected",
            reason_code=result.reason_code,
        )
        return result


def _normalize_capability_name(value: str) -> str:
    """Normalize capability labels into bounded snake-case identifiers."""
    import re

    return re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_")[:80]
