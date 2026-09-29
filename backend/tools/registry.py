from __future__ import annotations

import asyncio
import anyio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping

from core.budgets import ToolBudget, ToolBudgetTracker

ToolHandler = Callable[[Mapping[str, Any]], Awaitable["ToolResult"]]
ToolStreamHandler = Callable[[Mapping[str, Any]], AsyncIterator[dict[str, Any]]]
logger = logging.getLogger(__name__)


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
    handler: ToolHandler | None = None
    stream_handler: ToolStreamHandler | None = None
    timeout_seconds: float | None = None
    budget_scope: str | None = None
    budget_limits: ToolBudget | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def has(self, name: str) -> bool:
        """Return whether a capability is registered without exposing handler internals."""
        return name in self._tools

    async def stream(self, name: str, arguments: Mapping[str, Any], budget: ToolBudgetTracker) -> AsyncIterator[dict[str, Any]]:
        """Execute a streaming tool with scoped budgets, a total deadline and cleanup.

        Args:
            name: Registered capability, never an arbitrary executable.
            arguments: Caller-owned authorization context and validated tool inputs.
            budget: Per-run tracker; named capability scopes survive repeated calls.

        Yields:
            State events and one terminal result. Heartbeats do not change state.
            Failures expose exception classes only, never provider payloads.

        Side Effects:
            Calls the handler, records budget usage and cancels work on disconnect.
        """
        definition = self._tools.get(name)
        if definition is None or definition.stream_handler is None:
            raise KeyError(f"unknown streaming tool: {name}")
        tracker = budget.scoped(definition.budget_scope, definition.budget_limits) if definition.budget_scope and definition.budget_limits else budget
        started = time.monotonic()
        iterator = None
        next_event = None
        succeeded = False
        authorized = False
        try:
            if tracker is not budget and budget.tool_calls + sum(scope.tool_calls for scope in budget.scopes.values()) >= budget.limits.max_tool_calls_per_run:
                from core.budgets import ToolBudgetExceeded
                raise ToolBudgetExceeded("tool call budget exhausted")
            tracker.authorize(external=definition.external)
            authorized = True
            iterator = definition.stream_handler(arguments).__aiter__()
            while True:
                next_event = asyncio.create_task(iterator.__anext__())
                if definition.timeout_seconds is None:
                    event = await next_event
                else:
                    remaining = definition.timeout_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        raise asyncio.TimeoutError()
                    done, _ = await asyncio.wait([next_event], timeout=remaining)
                    if not done:
                        raise asyncio.TimeoutError()
                    event = next_event.result()
                state = event.get("state")
                if state:
                    logger.info("tool.state_changed tool=%s state=%s", name, state)
                if state in {"completed", "failed", "cancelled"}:
                    succeeded = state == "completed"
                    yield event
                    break
                yield event
        except StopAsyncIteration:
            yield {"state": "cancelled"}
        except asyncio.CancelledError:
            logger.info("tool.cancelled tool=%s", name)
            raise
        except Exception as exc:
            logger.warning("tool.failed tool=%s reason=%s", name, type(exc).__name__)
            yield {"state": "failed", "reason": type(exc).__name__}
        finally:
            try:
                # ASGI disconnects repeatedly cancel within an AnyIO scope. Drain
                # the in-flight __anext__ before closing its generator, under a shield.
                with anyio.CancelScope(shield=True):
                    if next_event is not None:
                        if not next_event.done():
                            next_event.cancel()
                        await asyncio.gather(next_event, return_exceptions=True)
                    closer = getattr(iterator, "aclose", None)
                    if closer is not None:
                        await closer()
            finally:
                if authorized:
                    tracker.record(external=definition.external, latency_ms=int((time.monotonic() - started) * 1000), succeeded=succeeded)

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
        budget: ToolBudgetTracker,
    ) -> ToolResult:
        definition = self._tools.get(name)
        if definition is None:
            raise KeyError(f"unknown tool: {name}")
        if definition.stream_handler is not None:
            terminal = {}
            async for event in self.stream(name, arguments, budget):
                terminal = event
            return ToolResult(name, "ok" if terminal.get("state") == "completed" else "error", terminal)
        if definition.handler is None:
            raise ValueError(f"tool has no handler: {name}")
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
