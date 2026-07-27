"""Local learning memory simulator for recording direct learner evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import DialogueActSignal, LearningMemorySnapshot, MemoryEvidenceRecord, ResponseCategory, SessionState
from .observability import log_event


class LearningMemorySimulator:
    """Maintain bounded prompt-safe direct evidence for one local session."""

    def __init__(self, max_context_size: int = 10):
        """Configure the maximum direct-evidence context window."""
        self.max_context_size = max_context_size

    def record_direct_evidence(
        self,
        state: SessionState,
        answer: str,
        category: ResponseCategory,
        *,
        signal: str | None = None,
    ) -> None:
        """Store bounded direct learner evidence without promoting EDF inference.

        Raw learner text is retained only as local direct evidence. It is marked
        prompt-unsafe because bounded length alone does not make user text safe
        for LLM prompt construction; tutoring strategy selection should consume
        safe signal labels instead.
        """
        state.direct_evidence.append(
            MemoryEvidenceRecord(
                source="user_message",
                kind="USER_EVIDENCE",
                text=answer,
                prompt_safe=False,
                cold_export_eligible=False,
                confidence=1.0,
                topic=state.learning_plan.topic if state.learning_plan else state.intake_profile.topic,
                node_id=state.current_node_id,
                signal=signal or category.value,
            )
        )
        if len(state.direct_evidence) > self.max_context_size:
            state.direct_evidence = state.direct_evidence[-self.max_context_size:]

        direct_evidence_count = 0
        for node in state.nodes.values():
            direct_evidence_count += sum(1 for e in node.evidence if e.direct)
        direct_evidence_count = max(direct_evidence_count, len(state.direct_evidence))

        working_context_count = min(direct_evidence_count, self.max_context_size)

        state.memory_snapshot = LearningMemorySnapshot(
            evidence_count=direct_evidence_count,
            working_context_count=working_context_count,
            recent_dialogue_acts=tuple(state.memory_snapshot.recent_dialogue_acts),
            recent_tutor_moves=tuple(state.memory_snapshot.recent_tutor_moves),
            repeated_confusion_count=state.memory_snapshot.repeated_confusion_count,
            updated_at=datetime.now(timezone.utc).isoformat()
        )

        log_event(
            "pelican_memory_updated",
            learner_id=state.learner_id,
            evidence_count=direct_evidence_count,
            working_context_count=working_context_count,
            category=category.value,
        )

    def record_dialogue_act(
        self,
        state: SessionState,
        signal: DialogueActSignal,
        *,
        node_id: str | None,
        tutor_move: str,
    ) -> None:
        """Record bounded dialogue-control state without creating mastery evidence."""
        recent_acts = tuple(state.memory_snapshot.recent_dialogue_acts) + (signal.act.value,)
        recent_moves = tuple(state.memory_snapshot.recent_tutor_moves) + (tutor_move,)
        recent_acts = recent_acts[-self.max_context_size:]
        recent_moves = recent_moves[-self.max_context_size:]
        repeated_confusion_count = (
            state.memory_snapshot.repeated_confusion_count + 1
            if signal.act.value == "micro_check_confusion"
            else 0
        )
        state.memory_snapshot = LearningMemorySnapshot(
            evidence_count=state.memory_snapshot.evidence_count,
            working_context_count=state.memory_snapshot.working_context_count,
            recent_dialogue_acts=recent_acts,
            recent_tutor_moves=recent_moves,
            repeated_confusion_count=repeated_confusion_count,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        log_event(
            "pelican_memory_dialogue_act_recorded",
            learner_id=state.learner_id,
            node_id=node_id,
            dialogue_act=signal.act.value,
            tutor_move=tutor_move,
            repeated_confusion_count=repeated_confusion_count,
            reason_code=signal.reason_code,
        )

    def get_working_context(self, state: SessionState) -> list[str]:
        """Return bounded prompt-safe direct evidence, never EDF/model inference."""
        return [
            f"{record.topic or 'topic'}:{record.node_id or '-'}:{record.signal or record.kind}:untrusted_user_evidence"
            for record in state.direct_evidence[-self.max_context_size:]
            if record.prompt_safe and record.kind == "USER_EVIDENCE"
        ]

    def recent_safe_signals(self, state: SessionState, limit: int = 5) -> tuple[str, ...]:
        """Return bounded learner evidence signal labels for strategy context."""
        signals: list[str] = []
        for record in state.direct_evidence[-limit:]:
            if record.kind != "USER_EVIDENCE":
                continue
            signals.append((record.signal or "unknown")[:80])
        return tuple(signals)
