"""EDF Simulator for pedagogical strategy generation."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    EdfSnapshot,
    KnowledgeStatus,
    ResponseCategory,
    SessionState,
    StrategyCandidate,
    TutorStrategyDecision,
    TutoringStrategy,
)
from .observability import log_event


class EdfSimulator:
    """Deterministic EDF-style evaluator for local teaching decisions."""

    def evaluate(self, state: SessionState) -> EdfSnapshot:
        """Evaluate learner state and return the legacy EDF snapshot.

        Compatibility:
            ``EdfSnapshot`` remains the persisted public summary for older API
            consumers. New policy arbitration should use ``decide`` so the
            engine has a single authoritative strategy decision object.
        """
        decision = self.decide(state)
        snapshot = self.snapshot_from_decision(state, decision)
        log_event(
            "pelican_edf_evaluated",
            learner_id=state.learner_id,
            learner_state=snapshot.learner_state,
            strategy=snapshot.pedagogical_strategy,
            route=snapshot.route,
            dialogue_act=snapshot.dialogue_act,
            evidence_count=snapshot.evidence_count,
            reason_code=snapshot.reason_code,
        )
        return snapshot

    def snapshot_from_decision(
        self,
        state: SessionState,
        decision: TutorStrategyDecision,
    ) -> EdfSnapshot:
        """Build a legacy EDF snapshot from an authoritative decision.

        Args:
            state: Current session used only for legacy evidence counts.
            decision: Strategy decision returned by ``decide``.

        Returns:
            Public compatibility snapshot for persisted state and existing API
            consumers. This method does not log; callers log the policy event
            exactly once after adopting the decision.
        """
        total_evidence = _total_evidence(state)
        return EdfSnapshot(
            learner_state=decision.learner_state,
            pedagogical_strategy=_policy_from_decision(decision),
            trigger_proactive=False,
            confidence=max(0.5, min(0.95, 0.5 + decision.intervention_strength * 0.4)),
            evidence_count=total_evidence,
            reason_code=decision.reason_code,
            route=decision.route,
            selected_strategy=decision.selected_strategy.value,
            dialogue_act=decision.dialogue_act,
            updated_at=decision.updated_at,
        )

    def decide(self, state: SessionState) -> TutorStrategyDecision:
        """Return the authoritative EDF strategy decision for one turn.

        Args:
            state: Current session state after GUM/memory updates.

        Returns:
            A bounded strategy decision consumed by ``PolicyAgent`` and the
            engine. The decision uses only safe labels from evidence history,
            node states, and memory snapshots; it never inspects raw learner
            answers.
        """
        total_evidence = sum(len(node.evidence) for node in state.nodes.values() if node.evidence)
        mastered_count = sum(1 for node in state.nodes.values() if node.status == KnowledgeStatus.MASTERED)
        total_nodes = len(state.nodes)
        recent_dialogue_acts = tuple(state.memory_snapshot.recent_dialogue_acts)
        last_dialogue_act = recent_dialogue_acts[-1] if recent_dialogue_acts else ""

        # Analyze recent evidence
        recent_categories: list[str] = []
        for history_turn in reversed(state.history[-5:]):
            if history_turn.category:
                recent_categories.append(history_turn.category)

        learner_state = "STARTING"
        reason = "initial_state"
        route = "fast"
        selected_strategy = TutoringStrategy.OPEN_QUESTION
        intervention_strength = 0.2
        should_advance = False
        should_recheck = True

        if last_dialogue_act in {"term_definition_request", "clarification_question"}:
            learner_state = "CLARIFYING"
            reason = "dialogue_clarification"
            route = "dialogue"
            selected_strategy = TutoringStrategy.CLARIFY_TERM
            intervention_strength = 0.4
        elif last_dialogue_act == "micro_check_confusion":
            learner_state = "CLARIFYING"
            reason = (
                "repeated_micro_check_confusion"
                if state.memory_snapshot.repeated_confusion_count >= 2
                else "micro_check_confusion"
            )
            route = "slow" if state.memory_snapshot.repeated_confusion_count >= 2 else "dialogue"
            selected_strategy = TutoringStrategy.GIVE_CHOICES
            intervention_strength = 0.65 if route == "slow" else 0.45

        if reason == "initial_state" and total_evidence > 0:
            recent_difficulties = recent_categories.count(ResponseCategory.DIFFICULTY.value) + \
                                  recent_categories.count(ResponseCategory.INABILITY.value)
            recent_incorrect = recent_categories.count(ResponseCategory.INCORRECT.value)
            recent_correct = recent_categories.count(ResponseCategory.CORRECT.value)

            if recent_difficulties >= 2:
                learner_state = "STRUGGLING"
                reason = "repeated_difficulty"
                route = "slow"
                selected_strategy = TutoringStrategy.DECOMPOSITION
                intervention_strength = 0.8
            elif recent_incorrect >= 2:
                learner_state = "TINKERING"
                reason = "frequent_errors"
                route = "slow"
                selected_strategy = TutoringStrategy.CORRECTION
                intervention_strength = 0.7
            elif recent_correct >= 2:
                if mastered_count == total_nodes and total_nodes > 0:
                    learner_state = "MASTERY"
                    reason = "sustained_mastery"
                    route = "slow"
                    selected_strategy = TutoringStrategy.OPEN_QUESTION
                    intervention_strength = 0.25
                    should_advance = False
                    should_recheck = False
                else:
                    learner_state = "PROGRESSING"
                    reason = "demonstrated_progress"
                    selected_strategy = TutoringStrategy.CONFIRMATION
                    intervention_strength = 0.2
                    should_advance = True
                    should_recheck = False
            else:
                learner_state = "EXPLORING"
                reason = "early_uncertain"
                selected_strategy = TutoringStrategy.OPEN_QUESTION
                intervention_strength = 0.3

        candidate = StrategyCandidate(
            strategy=selected_strategy,
            route=route,
            score=1.0 + intervention_strength,
            expected_gain=max(0.0, min(1.0, 0.55 + intervention_strength / 3.0)),
            risk=max(0.0, min(1.0, 0.55 - intervention_strength / 4.0)),
            cognitive_load=max(0.0, min(1.0, intervention_strength)),
            learner_fit=max(0.0, min(1.0, 0.65 + intervention_strength / 5.0)),
            rationale=f"{reason}: {selected_strategy.value} via {route}",
        )
        decision = TutorStrategyDecision(
            learner_state=learner_state,
            route=route,
            selected_strategy=selected_strategy,
            intervention_strength=intervention_strength,
            should_advance=should_advance,
            should_recheck=should_recheck,
            reason_code=reason,
            candidates=(candidate,),
            dialogue_act=last_dialogue_act,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        log_event(
            "pelican_edf_strategy_decided",
            learner_id=state.learner_id,
            learner_state=learner_state,
            strategy=selected_strategy.value,
            route=route,
            dialogue_act=last_dialogue_act,
            evidence_count=total_evidence,
            reason_code=reason,
        )
        return decision


def _total_evidence(state: SessionState) -> int:
    """Return the legacy evidence count used by public EDF snapshots."""
    return sum(len(node.evidence) for node in state.nodes.values() if node.evidence)


def _policy_from_decision(decision: TutorStrategyDecision) -> str:
    """Map an authoritative tutor strategy back to the legacy EDF policy label."""
    if decision.reason_code in {"initial_state", "early_uncertain"}:
        return "probe_understanding"
    strategy = decision.selected_strategy
    if strategy is TutoringStrategy.CLARIFY_TERM:
        return "clarify_term"
    if strategy is TutoringStrategy.GIVE_CHOICES:
        return "give_choices"
    if strategy is TutoringStrategy.DECOMPOSITION:
        return "simplify_or_decompose"
    if strategy is TutoringStrategy.CORRECTION:
        return "correct_and_explain"
    if strategy is TutoringStrategy.CONFIRMATION:
        return "confirm_and_suggest_action"
    if strategy is TutoringStrategy.OPEN_QUESTION:
        return "challenge_or_fade"
    return strategy.value
