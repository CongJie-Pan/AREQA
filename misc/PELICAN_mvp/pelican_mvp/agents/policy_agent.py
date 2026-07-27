"""Policy agent executor for EDF strategy recommendations."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..edf_simulator import EdfSimulator
from ..models import (
    AgentRole,
    KnowledgeStatus,
    MethodologyStage,
    ProposalValidationStatus,
    SessionState,
    StrategyCandidate,
    TutorStrategyDecision,
    TutoringStrategy,
)
from ..observability import log_event
from .artifacts import safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


class PolicyAgent:
    """Propose EDF strategy metadata without directly mutating state."""

    role = AgentRole.POLICY_AGENT

    def __init__(self, edf: EdfSimulator | None = None, llm: Any | None = None) -> None:
        """Create a policy agent around the deterministic EDF evaluator."""
        self.edf = edf or EdfSimulator()
        self.llm = llm

    def propose_strategy(
        self,
        state: SessionState,
        context: AgentExecutionContext | None = None,
    ) -> tuple[TutorStrategyDecision, AgentExecutionResult]:
        """Evaluate EDF and return the authoritative strategy decision.

        Args:
            state: Current session after GUM and knowledge-state updates.
            context: Optional safe execution correlation metadata.

        Returns:
            The bounded strategy decision plus an accepted policy proposal. The
            proposal metadata contains route, state, and strategy labels only;
            raw learner text and model output remain outside this boundary.
        """
        fallback = self.edf.decide(state)
        decision = self._llm_decision(state, fallback) or fallback
        proposal_source = "llm" if decision is not fallback else "edf"
        log_event(
            "pelican_edf_policy_agent_decided",
            learner_id=state.learner_id,
            phase=state.phase,
            node_id=state.current_node_id,
            learner_state=decision.learner_state,
            route=decision.route,
            strategy=decision.selected_strategy.value,
            selected_strategy=decision.selected_strategy.value,
            fallback_strategy=fallback.selected_strategy.value,
            proposal_source=proposal_source,
            llm_decision_status="adopted" if proposal_source == "llm" else "fallback",
            reason_code=decision.reason_code,
            candidate_count=len(decision.candidates),
        )
        result = AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.EDF_STRATEGY_SELECTION,
            artifact_type="strategy_decision",
            artifact_ref=safe_artifact_ref("strategy_decision", decision.reason_code, "current EDF policy"),
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=decision.reason_code,
            display_summary=(
                f"{decision.learner_state}:{decision.selected_strategy.value}:"
                f"{decision.route or 'fast'}"
            ),
            proposal_source=proposal_source,
        )
        return decision, result

    def _llm_decision(
        self,
        state: SessionState,
        fallback: TutorStrategyDecision,
    ) -> TutorStrategyDecision | None:
        """Return a validated prompt-driven EDF decision when LLM mode is active."""
        llm = self.llm
        if state.mode != "llm" or llm is None or not getattr(llm, "available", False):
            log_event(
                "pelican_edf_policy_llm_skipped",
                learner_id=state.learner_id,
                phase=state.phase,
                node_id=state.current_node_id,
                route=fallback.route,
                strategy=fallback.selected_strategy.value,
                llm_decision_status="skipped",
                reason_code="llm_policy_not_available" if state.mode == "llm" else "rule_mode",
            )
            return None
        try:
            payload = llm.edf_policy_decision(
                current_learner_state=fallback.learner_state,
                current_policy=state.edf_snapshot.pedagogical_strategy,
                current_route=fallback.route,
                current_strategy=fallback.selected_strategy.value,
                current_node_id=state.current_node_id or "",
                current_node_label=_current_node_label(state),
                recent_safe_signals=_recent_safe_signals(state),
                recent_dialogue_acts=tuple(state.memory_snapshot.recent_dialogue_acts),
                mastery_summary=_mastery_summary(state),
            )
        except Exception:
            log_event(
                "pelican_edf_policy_llm_rejected",
                learner_id=state.learner_id,
                phase=state.phase,
                node_id=state.current_node_id,
                route=fallback.route,
                strategy=fallback.selected_strategy.value,
                llm_decision_status="exception",
                reason_code="llm_policy_exception",
            )
            return None
        decision, rejection_reason = _validated_llm_decision(payload, fallback)
        if decision is None:
            log_event(
                "pelican_edf_policy_llm_rejected",
                learner_id=state.learner_id,
                phase=state.phase,
                node_id=state.current_node_id,
                route=fallback.route,
                strategy=fallback.selected_strategy.value,
                llm_decision_status="rejected",
                reason_code=rejection_reason,
            )
            return None
        log_event(
            "pelican_edf_policy_llm_adopted",
            learner_id=state.learner_id,
            phase=state.phase,
            node_id=state.current_node_id,
            learner_state=decision.learner_state,
            route=decision.route,
            strategy=decision.selected_strategy.value,
            selected_strategy=decision.selected_strategy.value,
            fallback_strategy=fallback.selected_strategy.value,
            llm_decision_status="adopted",
            reason_code=decision.reason_code,
        )
        return decision


def _validated_llm_decision(
    payload: dict[str, Any] | None,
    fallback: TutorStrategyDecision,
) -> tuple[TutorStrategyDecision | None, str]:
    """Convert a raw model payload into an EDF decision or reject it."""
    if not isinstance(payload, dict):
        return None, "llm_policy_empty_payload"
    try:
        strategy = TutoringStrategy(str(payload.get("selected_strategy", "")))
    except ValueError:
        return None, "llm_policy_invalid_strategy"
    route = str(payload.get("route", "")).strip().lower()
    if route not in {"fast", "slow", "dialogue"}:
        return None, "llm_policy_invalid_route"
    reason_code = _slug_reason(str(payload.get("reason_code", "llm_edf_policy")))
    candidate = StrategyCandidate(
        strategy=strategy,
        route=route,
        score=1.0,
        expected_gain=0.6,
        risk=0.4,
        cognitive_load=_bounded_float(payload.get("intervention_strength", fallback.intervention_strength)),
        learner_fit=0.65,
        rationale=f"{reason_code}: {strategy.value} via {route}",
    )
    return TutorStrategyDecision(
        learner_state=str(payload.get("learner_state", fallback.learner_state)).strip()[:80]
        or fallback.learner_state,
        route=route,
        selected_strategy=strategy,
        intervention_strength=_bounded_float(
            payload.get("intervention_strength", fallback.intervention_strength)
        ),
        should_advance=bool(payload.get("should_advance", fallback.should_advance)),
        should_recheck=bool(payload.get("should_recheck", fallback.should_recheck)),
        reason_code=reason_code,
        candidates=(candidate,),
        dialogue_act=str(payload.get("dialogue_act", fallback.dialogue_act)).strip()[:80],
        updated_at=datetime.now(timezone.utc).isoformat(),
    ), "accepted"


def _current_node_label(state: SessionState) -> str:
    """Return the safe label for the current node from the active plan."""
    if state.learning_plan is None or state.current_node_id is None:
        return ""
    for node in state.learning_plan.nodes:
        if node.node_id == state.current_node_id:
            return node.label[:160]
    return ""


def _mastery_summary(state: SessionState) -> str:
    """Summarize knowledge status counts without raw learner text."""
    counts = {status.value: 0 for status in KnowledgeStatus}
    for node_state in state.nodes.values():
        counts[node_state.status.value] = counts.get(node_state.status.value, 0) + 1
    return ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _recent_safe_signals(state: SessionState) -> tuple[str, ...]:
    """Return recent bounded response labels from turn history."""
    return tuple(item.category for item in state.history[-8:] if item.category)


def _bounded_float(value: Any) -> float:
    """Return a 0.0 to 1.0 float for model-provided policy strength."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _slug_reason(value: str) -> str:
    """Normalize model reason text into a stable safe reason code."""
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")[:60] or "llm_edf_policy"
