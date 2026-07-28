"""Turn-level orchestration contract for the PELICAN learning engine.

The learning manager orchestrator is intentionally read-only. It interprets the
current learner turn and proposes one bounded action, while ``PelicanEngine``
remains the only owner of session mutation, persistence, methodology events, and
mastery writes. This mirrors the orchestration MVP design where a top-level
agent can answer directly, call a capability, delegate work, continue the
pipeline, or fall back without exposing unrestricted tools to every child path.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from ..llm import LlmAdapter, LlmUnavailable
from ..observability import log_event


DEFAULT_CONFIDENCE_THRESHOLD = 0.62
SAFE_REASON_MAX_LENGTH = 80


class LearningManagerAction(str, Enum):
    """Bounded actions the learning manager may propose for one learner turn."""

    ANSWER_DIRECTLY = "answer_directly"
    CALL_CAPABILITY = "call_capability"
    DELEGATE_CAPABILITY = "delegate_capability"
    RESUME_PIPELINE = "resume_pipeline"
    CONTINUE_PIPELINE = "continue_pipeline"
    FALLBACK_LEGACY_PIPELINE = "fallback_legacy_pipeline"
    REJECT_ILLEGAL_ACTION = "reject_illegal_action"


class CapabilityPolicy(str, Enum):
    """Capability visibility and write-intent policy for orchestrated actions.

    ``WRITE_PROPOSED`` is not write permission. It marks that the orchestrator
    believes a state-writing specialist may be needed; ``PelicanEngine`` must
    still validate phase legality, snapshot identity, idempotency, and capability
    metadata before any state mutation occurs.
    """

    NONE = "none"
    READ = "read"
    SPECIALIST = "specialist"
    WRITE_PROPOSED = "write_proposed"


@dataclass(frozen=True)
class LearningManagerTurnContext:
    """Immutable snapshot used to interpret one learner turn.

    Args:
        snapshot_id: Stable id tying the model proposal to this exact turn
            snapshot. A stale decision with a different id must be rejected.
        turn_id: Engine-owned turn correlation id.
        cycle_id: Engine-owned methodology cycle correlation id.
        phase: Current PELICAN pipeline phase.
        current_node_id: Optional active knowledge node.
        current_prompt_kind: Safe label for the expected response shape.
        expected_response_shape: Safe expected answer/control label.
        edf_state: Safe EDF learner-state label.
        edf_policy: Safe EDF policy label.
        recent_safe_signals: Recent bounded memory/dialogue signals.
        learner_text: Raw current learner turn used only for interpretation.
            It must never be copied into safe metadata or structured logs.
    """

    snapshot_id: str
    turn_id: str | None
    cycle_id: str | None
    phase: str
    current_node_id: str | None = None
    current_prompt_kind: str = "unknown"
    expected_response_shape: str = "unknown"
    edf_state: str = "unknown"
    edf_policy: str = "unknown"
    recent_safe_signals: tuple[str, ...] = ()
    learner_text: str = ""

    def to_llm_payload(self, capability_names: Iterable[str] = ()) -> dict[str, Any]:
        """Serialize the snapshot for the orchestration model.

        Args:
            capability_names: Safe registry manifest names the orchestrator may
                select. Raw implementation details and stateful callables are not
                exposed.

        Returns:
            JSON-safe payload. It includes raw ``learner_text`` because the
            model needs the current turn for interpretation; callers must not
            log or export this payload.
        """
        return {
            "snapshot_id": self.snapshot_id,
            "turn_id": self.turn_id,
            "cycle_id": self.cycle_id,
            "phase": self.phase,
            "current_node_id": self.current_node_id,
            "current_prompt_kind": self.current_prompt_kind,
            "expected_response_shape": self.expected_response_shape,
            "edf_state": self.edf_state,
            "edf_policy": self.edf_policy,
            "recent_safe_signals": list(self.recent_safe_signals),
            "learner_text": self.learner_text,
            "available_capabilities": sorted(set(capability_names)),
        }


@dataclass(frozen=True)
class LearningManagerDecision:
    """Validated read-only proposal for one learner turn.

    Args:
        action: Bounded orchestration action.
        capability: Optional safe capability name selected by the action.
        policy: Capability policy requested by the orchestrator.
        target_phase: Safe target pipeline phase label.
        confidence: Clamped model confidence from 0.0 to 1.0.
        reason_code: Stable safe reason code for debugging.
        proposal_source: ``llm`` for adopted model decisions, or ``fallback``
            for deterministic local fallback.
        snapshot_id: Snapshot id the decision applies to.

    Ownership:
        The decision is never self-executing. ``PelicanEngine`` owns adoption,
        state writes, idempotency, and final learner-facing output.
    """

    action: LearningManagerAction
    capability: str
    policy: CapabilityPolicy
    target_phase: str
    confidence: float
    reason_code: str
    proposal_source: str
    snapshot_id: str

    def to_safe_metadata(self) -> dict[str, str | float]:
        """Return bounded metadata safe for logs, tests, and exports."""
        return {
            "action": self.action.value,
            "capability": self.capability,
            "policy": self.policy.value,
            "target_phase": self.target_phase,
            "confidence": round(self.confidence, 3),
            "reason_code": self.reason_code,
            "proposal_source": self.proposal_source,
            "snapshot_id": self.snapshot_id,
        }


class LearningManagerOrchestrator:
    """Read-only turn-level conductor for learning capability selection."""

    def __init__(
        self,
        llm: LlmAdapter,
        *,
        capability_names: Iterable[str] = (),
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        """Create an orchestrator around the optional LLM adapter.

        Args:
            llm: Optional OpenAI-compatible adapter used for decision proposals.
            capability_names: Safe capability manifest names available to the
                engine dispatcher.
            confidence_threshold: Minimum confidence required before a model
                decision can be adopted.
        """
        self.llm = llm
        self.capability_names = frozenset(_slug_label(item) for item in capability_names if item)
        self.confidence_threshold = max(0.0, min(1.0, confidence_threshold))

    def interpret_turn(self, context: LearningManagerTurnContext) -> LearningManagerDecision:
        """Interpret the learner turn and return a bounded proposal.

        Args:
            context: Immutable engine-owned turn snapshot.

        Returns:
            A validated ``LearningManagerDecision``. Invalid, unavailable,
            low-confidence, stale, or policy-incompatible model proposals become
            deterministic fallback decisions.

        Side Effects:
            None. The method does not mutate session state and does not emit
            logs in this phase; same-turn observability is added after engine
            dispatch exists.
        """
        try:
            payload = self.llm.orchestrate_turn_decision(
                context.to_llm_payload(self.capability_names),
            )
        except LlmUnavailable as exc:
            reason = _first_safe_reason(exc.reason_codes, "llm_unavailable")
            return self._fallback(context, reason)
        except Exception:
            return self._fallback(context, "orchestrator_unexpected_failure")
        return self._decision_from_payload(payload, context)

    def _decision_from_payload(
        self,
        payload: dict[str, Any],
        context: LearningManagerTurnContext,
    ) -> LearningManagerDecision:
        """Validate raw model payload and reduce unsafe output to fallback."""
        if not isinstance(payload, dict):
            return self._fallback(context, "invalid_payload")
        if str(payload.get("snapshot_id", "")) != context.snapshot_id:
            return self._fallback(context, "stale_snapshot")
        try:
            action = LearningManagerAction(str(payload.get("action", "")))
            policy = CapabilityPolicy(str(payload.get("policy", "")))
        except ValueError:
            return self._fallback(context, "invalid_enum")
        confidence = _bounded_confidence(payload.get("confidence"))
        if confidence < self.confidence_threshold:
            return self._fallback(context, "low_confidence")
        capability = _slug_label(str(payload.get("capability", "")))
        if action in {LearningManagerAction.CALL_CAPABILITY, LearningManagerAction.DELEGATE_CAPABILITY}:
            if not capability:
                return self._fallback(context, "missing_capability")
            if self.capability_names and capability not in self.capability_names:
                return self._fallback(context, "unknown_capability")
            if policy is CapabilityPolicy.NONE:
                return self._fallback(context, "policy_denied")
        else:
            # Non-capability actions should not smuggle a write-capable target.
            capability = ""
            if policy is CapabilityPolicy.WRITE_PROPOSED:
                return self._fallback(context, "write_policy_without_capability")
        decision = LearningManagerDecision(
            action=action,
            capability=capability,
            policy=policy,
            target_phase=_slug_label(str(payload.get("target_phase", context.phase))) or context.phase,
            confidence=confidence,
            reason_code=_slug_reason(str(payload.get("reason_code", action.value))),
            proposal_source="llm",
            snapshot_id=context.snapshot_id,
        )
        log_event(
            "pelican_learning_orchestrator_decided",
            level=logging.INFO,
            turn_id=context.turn_id,
            cycle_id=context.cycle_id,
            phase=context.phase,
            node_id=context.current_node_id,
            action=decision.action.value,
            capability=decision.capability,
            policy=decision.policy.value,
            target_phase=decision.target_phase,
            confidence_bucket=_confidence_bucket(decision.confidence),
            proposal_source=decision.proposal_source,
            reason_code=decision.reason_code,
        )
        return decision

    def _fallback(self, context: LearningManagerTurnContext, reason_code: str) -> LearningManagerDecision:
        """Build a deterministic no-write legacy fallback decision."""
        decision = LearningManagerDecision(
            action=LearningManagerAction.FALLBACK_LEGACY_PIPELINE,
            capability="",
            policy=CapabilityPolicy.NONE,
            target_phase=context.phase,
            confidence=0.0,
            reason_code=_slug_reason(reason_code),
            proposal_source="fallback",
            snapshot_id=context.snapshot_id,
        )
        log_event(
            "pelican_learning_orchestrator_fallback",
            level=logging.INFO,
            turn_id=context.turn_id,
            cycle_id=context.cycle_id,
            phase=context.phase,
            node_id=context.current_node_id,
            action=decision.action.value,
            policy=decision.policy.value,
            target_phase=decision.target_phase,
            confidence_bucket=_confidence_bucket(decision.confidence),
            proposal_source=decision.proposal_source,
            reason_code=decision.reason_code,
        )
        return decision


def _bounded_confidence(value: Any) -> float:
    """Clamp model confidence to the inclusive 0.0 to 1.0 range."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _first_safe_reason(reason_codes: tuple[str, ...], default: str) -> str:
    """Return the first safe reason code emitted by a provider failure."""
    for reason in reason_codes:
        safe = _slug_reason(reason)
        if safe:
            return safe
    return default


def _confidence_bucket(value: float) -> str:
    """Return a coarse confidence label that avoids overprecise model scoring."""
    if value >= 0.8:
        return "high"
    if value >= 0.62:
        return "medium"
    if value > 0:
        return "low"
    return "none"


def _slug_label(value: str) -> str:
    """Normalize a model-selected action target into a bounded safe label."""
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")[:SAFE_REASON_MAX_LENGTH]


def _slug_reason(value: str) -> str:
    """Normalize free-form model/provider text into a safe reason code."""
    return _slug_label(value) or "unknown"
