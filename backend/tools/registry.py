from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from core.budgets import ToolBudgetTracker

ToolHandler = Callable[[Mapping[str, Any]], Awaitable["ToolResult"]]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result returned by a tool without exposing provider-private payloads."""

    tool_name: str
    status: str
    content: Any
    provenance: tuple[str, ...] = ()
    content_type: str = "application/json"
    truncated: bool = False
    latency_ms: int = 0
    cache_status: str = "not_applicable"
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    external: bool
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
        budget: ToolBudgetTracker,
    ) -> ToolResult:
        definition = self._tools.get(name)
        if definition is None:
            raise KeyError(f"unknown tool: {name}")
        budget.authorize(external=definition.external)
        started = time.monotonic()
        try:
            result = await definition.handler(arguments)
        except Exception:
            budget.record(
                external=definition.external,
                latency_ms=int((time.monotonic() - started) * 1000),
                succeeded=False,
            )
            raise
        budget.record(
            external=definition.external,
            latency_ms=result.latency_ms or int((time.monotonic() - started) * 1000),
            succeeded=result.status == "ok",
        )
        return result
