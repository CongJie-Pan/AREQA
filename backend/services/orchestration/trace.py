"""Track privacy-safe foreground latency and model/tool counters.

The trace is run-local observability for chat orchestration. It records stable
phase names, elapsed milliseconds, and aggregate counters without retaining raw
user text, prompts, memory contents, model output, credentials, or provider
payloads.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import time
from typing import AsyncIterator


@dataclass(frozen=True, slots=True)
class PhaseTiming:
    """A single safe phase milestone measured from the trace start."""

    name: str
    elapsed_ms: int
    occurrence: int = 1


@dataclass(slots=True)
class ModelCallCounter:
    """Aggregate counters for foreground provider and tool usage."""

    model_calls: dict[str, int] = field(default_factory=dict)
    tool_calls: dict[str, int] = field(default_factory=dict)
    cache_statuses: dict[str, int] = field(default_factory=dict)

    def increment_model_call(self, kind: str) -> None:
        """Increment one safe model-call category."""

        safe_kind = _safe_key(kind)
        self.model_calls[safe_kind] = self.model_calls.get(safe_kind, 0) + 1

    def increment_tool_call(self, kind: str, cache_status: str = "not_applicable") -> None:
        """Increment one safe tool-call category and optional cache status."""

        safe_kind = _safe_key(kind)
        safe_cache_status = _safe_key(cache_status)
        self.tool_calls[safe_kind] = self.tool_calls.get(safe_kind, 0) + 1
        cache_key = f"{safe_kind}:{safe_cache_status}"
        self.cache_statuses[cache_key] = self.cache_statuses.get(cache_key, 0) + 1


class TurnLatencyTrace:
    """Collect one chat turn's safe latency milestones and counters."""

    def __init__(self, *, run_id: str, conversation_id: str) -> None:
        """Create a trace scoped to one runtime session.

        Args:
            run_id: Safe run correlation identifier.
            conversation_id: Safe conversation correlation identifier.
        """

        self.run_id = run_id
        self.conversation_id = conversation_id
        self._started = time.monotonic()
        self._phases: list[PhaseTiming] = []
        self._phase_counts: dict[str, int] = {}
        self.counters = ModelCallCounter()

    def mark(self, name: str) -> None:
        """Record a safe phase milestone using elapsed monotonic time."""

        safe_name = _safe_key(name)
        occurrence = self._phase_counts.get(safe_name, 0) + 1
        self._phase_counts[safe_name] = occurrence
        self._phases.append(
            PhaseTiming(
                name=safe_name,
                elapsed_ms=self.elapsed_ms(),
                occurrence=occurrence,
            )
        )

    def mark_once(self, name: str) -> None:
        """Record a milestone only for its first occurrence."""

        safe_name = _safe_key(name)
        if self._phase_counts.get(safe_name, 0):
            return
        self.mark(safe_name)

    @asynccontextmanager
    async def measure(self, name: str) -> AsyncIterator[None]:
        """Mark start and finish milestones around an async phase."""

        safe_name = _safe_key(name)
        self.mark(f"{safe_name}_started")
        try:
            yield
        except Exception:
            self.mark(f"{safe_name}_failed")
            raise
        else:
            self.mark(f"{safe_name}_finished")

    def increment_model_call(self, kind: str) -> None:
        """Increment one foreground model-call counter."""

        self.counters.increment_model_call(kind)

    def increment_tool_call(
        self,
        kind: str,
        cache_status: str = "not_applicable",
    ) -> None:
        """Increment one foreground tool-call counter."""

        self.counters.increment_tool_call(kind, cache_status)

    def elapsed_ms(self) -> int:
        """Return elapsed milliseconds since this trace was created."""

        return int((time.monotonic() - self._started) * 1000)

    def snapshot(self) -> dict[str, object]:
        """Return a JSON/log-safe snapshot of phases and aggregate counters."""

        return {
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "elapsed_ms": self.elapsed_ms(),
            "phases": [
                {
                    "name": phase.name,
                    "elapsed_ms": phase.elapsed_ms,
                    "occurrence": phase.occurrence,
                }
                for phase in self._phases
            ],
            "model_calls": dict(sorted(self.counters.model_calls.items())),
            "tool_calls": dict(sorted(self.counters.tool_calls.items())),
            "cache_statuses": dict(sorted(self.counters.cache_statuses.items())),
        }

    def phase_durations_ms(self) -> dict[str, int]:
        """Return safe durations for completed phase start/end pairs."""

        started_by_phase: dict[str, int] = {}
        durations: dict[str, int] = {}
        terminal_suffixes = ("_finished", "_failed", "_timeout")
        for phase in self._phases:
            if phase.name.endswith("_started"):
                started_by_phase[phase.name.removesuffix("_started")] = phase.elapsed_ms
                continue

            for suffix in terminal_suffixes:
                if not phase.name.endswith(suffix):
                    continue
                base_name = phase.name.removesuffix(suffix)
                started_at = started_by_phase.get(base_name)
                if started_at is None:
                    break
                durations[base_name] = max(0, phase.elapsed_ms - started_at)
                break

        return dict(sorted(durations.items()))

    def milestone_elapsed_ms(self, name: str) -> int | None:
        """Return the first elapsed time for one safe milestone."""

        safe_name = _safe_key(name)
        for phase in self._phases:
            if phase.name == safe_name:
                return phase.elapsed_ms
        return None

    def diagnostic_summary(
        self,
        *,
        slow_total_threshold_ms: int,
        slow_first_token_threshold_ms: int,
        top_phase_count: int = 5,
    ) -> dict[str, object]:
        """Return a compact production-friendly latency summary."""

        phase_durations = self.phase_durations_ms()
        top_phase_durations = [
            {"name": name, "duration_ms": duration_ms}
            for name, duration_ms in sorted(
                phase_durations.items(),
                key=lambda item: item[1],
                reverse=True,
            )[: max(1, top_phase_count)]
        ]
        first_answer_delta_ms = self.milestone_elapsed_ms("first_answer_delta")
        main_model_started_ms = self.milestone_elapsed_ms("main_model_started")
        terminal_sent_ms = self.milestone_elapsed_ms("terminal_sent")
        elapsed_ms = terminal_sent_ms if terminal_sent_ms is not None else self.elapsed_ms()

        provider_first_token_ms = None
        if first_answer_delta_ms is not None and main_model_started_ms is not None:
            provider_first_token_ms = max(0, first_answer_delta_ms - main_model_started_ms)

        slow_reasons: list[str] = []
        if elapsed_ms >= slow_total_threshold_ms:
            slow_reasons.append("total_elapsed")
        if (
            first_answer_delta_ms is not None
            and first_answer_delta_ms >= slow_first_token_threshold_ms
        ):
            slow_reasons.append("time_to_first_answer")
        if (
            provider_first_token_ms is not None
            and provider_first_token_ms >= slow_first_token_threshold_ms
        ):
            slow_reasons.append("provider_first_token")
        is_slow = bool(slow_reasons)
        if is_slow and top_phase_durations:
            slow_reasons.append(f"top_phase:{top_phase_durations[0]['name']}")

        return {
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "elapsed_ms": elapsed_ms,
            "terminal_sent_ms": terminal_sent_ms,
            "time_to_first_answer_ms": first_answer_delta_ms,
            "main_model_started_ms": main_model_started_ms,
            "provider_first_token_ms": provider_first_token_ms,
            "phase_durations_ms": phase_durations,
            "top_phase_durations": top_phase_durations,
            "model_calls": dict(sorted(self.counters.model_calls.items())),
            "tool_calls": dict(sorted(self.counters.tool_calls.items())),
            "cache_statuses": dict(sorted(self.counters.cache_statuses.items())),
            "is_slow": is_slow,
            "slow_reasons": slow_reasons,
        }


def _safe_key(value: str) -> str:
    """Normalize a log key without preserving arbitrary raw content."""

    normalized = "".join(
        character if character.isalnum() or character in {"_", "-", ":"} else "_"
        for character in str(value or "unknown").strip().lower()
    )
    return normalized or "unknown"
