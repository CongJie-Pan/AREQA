"""EDF Simulator for pedagogical strategy generation."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import EdfSnapshot, KnowledgeStatus, ResponseCategory, SessionState
from .observability import log_event


class EdfSimulator:
    """Deterministic EDF-style evaluator for local teaching decisions."""

    def evaluate(self, state: SessionState) -> EdfSnapshot:
        """Evaluate learner state and determine a pedagogical policy."""
        total_evidence = sum(len(node.evidence) for node in state.nodes.values() if node.evidence)
        mastered_count = sum(1 for node in state.nodes.values() if node.status == KnowledgeStatus.MASTERED)
        total_nodes = len(state.nodes)

        # Analyze recent evidence
        recent_categories: list[str] = []
        for history_turn in reversed(state.history[-5:]):
            if history_turn.category:
                recent_categories.append(history_turn.category)

        # Default starting
        learner_state = "STARTING"
        policy = "probe_understanding"
        confidence = 0.5
        reason = "initial_state"

        if total_evidence > 0:
            confidence = min(0.9, 0.5 + (total_evidence * 0.05))

            recent_difficulties = recent_categories.count(ResponseCategory.DIFFICULTY.value) + \
                                  recent_categories.count(ResponseCategory.INABILITY.value)
            recent_incorrect = recent_categories.count(ResponseCategory.INCORRECT.value)
            recent_correct = recent_categories.count(ResponseCategory.CORRECT.value)

            if recent_difficulties >= 2:
                learner_state = "STRUGGLING"
                policy = "simplify_or_decompose"
                reason = "repeated_difficulty"
            elif recent_incorrect >= 2:
                learner_state = "TINKERING"
                policy = "correct_and_explain"
                reason = "frequent_errors"
            elif recent_correct >= 2:
                if mastered_count == total_nodes and total_nodes > 0:
                    learner_state = "MASTERY"
                    policy = "challenge_or_fade"
                    reason = "sustained_mastery"
                else:
                    learner_state = "PROGRESSING"
                    policy = "confirm_and_suggest_action"
                    reason = "demonstrated_progress"
            else:
                learner_state = "EXPLORING"
                policy = "probe_understanding"
                reason = "early_uncertain"

        snapshot = EdfSnapshot(
            learner_state=learner_state,
            pedagogical_strategy=policy,
            trigger_proactive=False,
            confidence=confidence,
            evidence_count=total_evidence,
            reason_code=reason,
            updated_at=datetime.now(timezone.utc).isoformat()
        )

        log_event(
            "pelican_edf_evaluated",
            learner_id=state.learner_id,
            learner_state=learner_state,
            strategy=policy,
            evidence_count=total_evidence,
            reason_code=reason,
        )

        return snapshot
