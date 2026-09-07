from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class ToolBudget:
    max_tool_calls_per_run: int = 3
    max_external_calls: int = 1
    max_consecutive_failures: int = 2
    max_tool_result_tokens: int = 4000
    max_total_tool_latency_ms: int = 8000

    def __post_init__(self) -> None:
        for field in fields(self):
            name = field.name
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must not be negative")


@dataclass(slots=True)
class ToolBudgetTracker:
    limits: ToolBudget
    tool_calls: int = 0
    external_calls: int = 0
    consecutive_failures: int = 0
    total_tool_latency_ms: int = 0

    def authorize(self, *, external: bool) -> None:
        if self.total_tool_latency_ms > self.limits.max_total_tool_latency_ms:
            raise ToolBudgetExceeded("total tool latency budget exhausted")
        if self.tool_calls >= self.limits.max_tool_calls_per_run:
            raise ToolBudgetExceeded("tool call budget exhausted")
        if external and self.external_calls >= self.limits.max_external_calls:
            raise ToolBudgetExceeded("external call budget exhausted")
        if self.consecutive_failures >= self.limits.max_consecutive_failures:
            raise ToolBudgetExceeded("consecutive failure budget exhausted")

    def record(self, *, external: bool, latency_ms: int, succeeded: bool) -> None:
        self.tool_calls += 1
        self.external_calls += int(external)
        self.total_tool_latency_ms += max(latency_ms, 0)
        self.consecutive_failures = 0 if succeeded else self.consecutive_failures + 1


class ToolBudgetExceeded(RuntimeError):
    pass
