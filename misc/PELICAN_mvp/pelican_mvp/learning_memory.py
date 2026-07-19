"""Local learning memory simulator for recording direct learner evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import LearningMemorySnapshot, ResponseCategory, SessionState
from .observability import log_event


class LearningMemorySimulator:
    def __init__(self, max_context_size: int = 10):
        self.max_context_size = max_context_size

    def record_direct_evidence(self, state: SessionState, answer: str, category: ResponseCategory) -> None:
        """Update memory counters. Actual evidence is stored in node evidence and history."""
        # Evidence is actually appended in engine, we just update memory metadata here
        # to simulate GUM's direct evidence boundary.

        # Calculate working context based on direct evidence only
        direct_evidence_count = 0
        for node in state.nodes.values():
            direct_evidence_count += sum(1 for e in node.evidence if e.direct)

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
        """Return the most recent bounded direct evidence as working context."""
        direct_evidence = []
        for record in reversed(state.history):
            if len(direct_evidence) >= self.max_context_size:
                break
            if record.category:
                # In this MVP, user answers in history with a category are direct evidence
                direct_evidence.append(f"Q: {record.prompt} | A: {record.response}")
        return direct_evidence[::-1]
