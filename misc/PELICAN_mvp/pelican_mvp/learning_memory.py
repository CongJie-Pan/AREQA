"""Local learning memory simulator for recording direct learner evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import DialogueActSignal, LearnerDialogueAct, LearningMemorySnapshot, MemoryEvidenceRecord, ResponseCategory, SessionState
from .observability import log_event


@dataclass(frozen=True)
class LearningMemoryGateDecision:
    """Bounded local memory-gate decision for one learner turn.

    Args:
        memory_kind: Safe event class used by GUM/EDF context.
        evidence_kind: Direct-evidence record kind when a local record is kept.
        should_record_direct_evidence: Whether raw learner text should be kept
            in session-local direct evidence.
        should_update_dialogue_context: Whether bounded dialogue history should
            be updated.
        counts_as_mastery_evidence: Whether the event contributes to mastery
            evidence counters. Control signals and clarification questions must
            keep this false.
        signal: Safe signal label for strategy context.
        reason_code: Stable reason code for logs and methodology traces.

    Privacy:
        The decision contains no raw learner text. Raw text, when retained, is
        stored only in prompt-unsafe ``MemoryEvidenceRecord`` entries.
    """

    memory_kind: str
    evidence_kind: str
    should_record_direct_evidence: bool
    should_update_dialogue_context: bool
    counts_as_mastery_evidence: bool
    signal: str
    reason_code: str


CONTROL_SIGNALS = frozenset({"unknown", "too_detailed", "too_difficult", "too_easy"})


def classify_turn_memory(
    category: ResponseCategory | None,
    *,
    signal: str | None = None,
    dialogue_signal: DialogueActSignal | None = None,
) -> LearningMemoryGateDecision:
    """Classify one learner turn before writing local GUM state.

    Args:
        category: Cognitive diagnosis category when the turn is an answer.
        signal: Optional bounded remediation/control signal.
        dialogue_signal: Optional pre-diagnosis dialogue act.

    Returns:
        A deterministic memory-gate decision aligned with the main backend's
        conservative rule: questions and control turns can update working
        context, but they must not become mastery evidence.
    """
    if dialogue_signal is not None and dialogue_signal.act is not LearnerDialogueAct.ANSWER_ATTEMPT:
        return LearningMemoryGateDecision(
            memory_kind="dialogue_control",
            evidence_kind="DIALOGUE_CONTROL",
            should_record_direct_evidence=False,
            should_update_dialogue_context=True,
            counts_as_mastery_evidence=False,
            signal=dialogue_signal.act.value,
            reason_code=dialogue_signal.reason_code,
        )
    safe_signal = (signal or (category.value if category else "unknown"))[:80]
    if safe_signal in CONTROL_SIGNALS:
        return LearningMemoryGateDecision(
            memory_kind="control_signal",
            evidence_kind="CONTROL_EVIDENCE",
            should_record_direct_evidence=True,
            should_update_dialogue_context=False,
            counts_as_mastery_evidence=False,
            signal=safe_signal,
            reason_code=safe_signal,
        )
    return LearningMemoryGateDecision(
        memory_kind="answer_evidence",
        evidence_kind="USER_EVIDENCE",
        should_record_direct_evidence=True,
        should_update_dialogue_context=False,
        counts_as_mastery_evidence=True,
        signal=safe_signal,
        reason_code=safe_signal,
    )


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
        decision = classify_turn_memory(category, signal=signal)
        if decision.should_record_direct_evidence:
            state.direct_evidence.append(
                MemoryEvidenceRecord(
                    source="user_message",
                    kind=decision.evidence_kind,
                    text=answer,
                    prompt_safe=False,
                    cold_export_eligible=False,
                    confidence=1.0,
                    topic=state.learning_plan.topic if state.learning_plan else state.intake_profile.topic,
                    node_id=state.current_node_id,
                    signal=decision.signal,
                )
            )
        if len(state.direct_evidence) > self.max_context_size:
            state.direct_evidence = state.direct_evidence[-self.max_context_size:]

        direct_evidence_count = 0
        for node in state.nodes.values():
            direct_evidence_count += sum(1 for e in node.evidence if e.direct)
        user_evidence_count = sum(1 for record in state.direct_evidence if record.kind == "USER_EVIDENCE")
        direct_evidence_count = max(direct_evidence_count, user_evidence_count)

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
            memory_kind=decision.memory_kind,
            reason_code=decision.reason_code,
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
        decision = classify_turn_memory(None, dialogue_signal=signal)
        if not decision.should_update_dialogue_context:
            return
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
            memory_kind=decision.memory_kind,
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
            if record.kind not in {"USER_EVIDENCE", "CONTROL_EVIDENCE"}:
                continue
            signals.append((record.signal or "unknown")[:80])
        return tuple(signals)
