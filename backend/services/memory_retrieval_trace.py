"""Privacy-safe sub-step tracing for long-term memory retrieval.

The trace records stable phase names, elapsed milliseconds, result-count
buckets, and safe outcomes only. It intentionally excludes raw queries, memory
contents, prompts, model output, credentials, and sensitive labels because
memory retrieval observability crosses a privacy boundary.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import time
from typing import Any, AsyncIterator


@dataclass(frozen=True, slots=True)
class MemoryRetrievalStep:
    """One safe memory retrieval sub-step duration."""

    name: str
    duration_ms: int
    outcome: str = "completed"


@dataclass(slots=True)
class MemoryRetrievalTrace:
    """Collect safe attribution for one memory retrieval attempt."""

    route_reason: str = "unknown"
    _started: float = field(default_factory=time.monotonic)
    _steps: list[MemoryRetrievalStep] = field(default_factory=list)
    _outcome: str = "unknown"
    _cache_status: str = "not_applicable"
    _result_count: int = 0
    _truncated: bool = False

    @asynccontextmanager
    async def measure(self, name: str) -> AsyncIterator[None]:
        """Measure one async sub-step with safe failure attribution."""

        safe_name = _safe_key(name)
        started = time.monotonic()
        try:
            yield
        except Exception:
            self.record_step(safe_name, _elapsed_ms(started), outcome="error")
            raise
        else:
            self.record_step(safe_name, _elapsed_ms(started), outcome="completed")

    def record_step(self, name: str, duration_ms: int, *, outcome: str = "completed") -> None:
        """Append one safe sub-step duration."""

        self._steps.append(
            MemoryRetrievalStep(
                name=_safe_key(name),
                duration_ms=max(0, int(duration_ms)),
                outcome=_safe_key(outcome),
            )
        )

    def has_step_outcome(self, name: str, outcomes: set[str]) -> bool:
        """Return whether a safe step ended with one of the expected outcomes.

        Args:
            name: Stable step name to inspect.
            outcomes: Stable outcome keys that should be treated as a match.

        Returns:
            True when the trace contains the step/outcome pair. This is used by
            orchestration code to choose safe prompt fallbacks without reading
            raw queries, prompts, model output, memory text, or credentials.
        """

        safe_name = _safe_key(name)
        safe_outcomes = {_safe_key(outcome) for outcome in outcomes}
        return any(
            step.name == safe_name and step.outcome in safe_outcomes
            for step in self._steps
        )

    def finish(
        self,
        *,
        outcome: str,
        cache_status: str = "not_applicable",
        result_count: int = 0,
        truncated: bool = False,
    ) -> None:
        """Record the final safe retrieval outcome."""

        self._outcome = _safe_key(outcome)
        self._cache_status = _safe_key(cache_status)
        self._result_count = max(0, int(result_count))
        self._truncated = bool(truncated)

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON/log-safe retrieval summary."""

        total_ms = int((time.monotonic() - self._started) * 1000)
        return {
            "route_reason": _safe_key(self.route_reason),
            "elapsed_ms": total_ms,
            "outcome": self._outcome,
            "cache_status": self._cache_status,
            "result_count_bucket": _count_bucket(self._result_count),
            "truncated": self._truncated,
            "steps": [
                {
                    "name": step.name,
                    "duration_ms": step.duration_ms,
                    "outcome": step.outcome,
                }
                for step in self._steps
            ],
            "top_steps": [
                {
                    "name": step.name,
                    "duration_ms": step.duration_ms,
                    "outcome": step.outcome,
                }
                for step in sorted(
                    self._steps,
                    key=lambda candidate: candidate.duration_ms,
                    reverse=True,
                )[:5]
            ],
        }


def _elapsed_ms(started: float) -> int:
    """Return elapsed milliseconds from a monotonic start time."""

    return int((time.monotonic() - started) * 1000)


def _safe_key(value: str) -> str:
    """Normalize a safe log key without preserving arbitrary content."""

    normalized = "".join(
        character if character.isalnum() or character in {"_", "-", ":"} else "_"
        for character in str(value or "unknown").strip().lower()
    )
    return normalized or "unknown"


def _count_bucket(count: int) -> str:
    """Bucket result counts to avoid leaking exact memory cardinality."""

    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 3:
        return "2-3"
    if count <= 5:
        return "4-5"
    return "6+"
