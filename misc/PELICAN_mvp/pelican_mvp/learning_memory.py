"""Local learning memory simulator for recording direct learner evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import LearningMemorySnapshot, MemoryEvidenceRecord, ResponseCategory, SessionState
from .observability import log_event


class LearningMemorySimulator:
    def __init__(self, max_context_size: int = 10):
        self.max_context_size = max_context_size

    def record_direct_evidence(
        self,
        state: SessionState,
        answer: str,
        category: ResponseCategory,
        *,
        signal: str | None = None,
    ) -> None:
        """Store bounded direct learner evidence without promoting EDF inference."""
        state.direct_evidence.append(
            MemoryEvidenceRecord(
                source="user_message",
                kind="USER_EVIDENCE",
                text=answer,
                prompt_safe=True,
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
            updated_at=datetime.now(timezone.utc).isoformat()
        )

        log_event(
            "pelican_memory_updated",
            learner_id=state.learner_id,
            evidence_count=direct_evidence_count,
            working_context_count=working_context_count,
            category=category.value,
        )

    def get_working_context(self, state: SessionState) -> list[str]:
        """Return bounded prompt-safe direct evidence, never EDF/model inference."""
        return [
            f"{record.topic or 'topic'}:{record.node_id or '-'}:{record.signal or record.kind}:{record.text}"
            for record in state.direct_evidence[-self.max_context_size:]
            if record.prompt_safe and record.kind == "USER_EVIDENCE"
        ]
