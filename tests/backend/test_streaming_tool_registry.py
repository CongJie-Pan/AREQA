"""Shared tool execution and independent capability budget contracts."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from core import ToolBudget, ToolBudgetTracker
from tools import ToolDefinition, ToolRegistry, ToolResult


@pytest.mark.asyncio
async def test_legacy_execute_contract_unchanged():
    handler = AsyncMock(return_value=ToolResult('search', 'ok', {'facts': []}))
    registry = ToolRegistry()
    registry.register(ToolDefinition('search', True, handler))
    budget = ToolBudgetTracker(ToolBudget())
    assert (await registry.execute('search', {}, budget)).status == 'ok'
    assert budget.external_calls == 1


@pytest.mark.asyncio
async def test_scoped_generation_runs_after_retrieval_but_cannot_repeat():
    async def handler(arguments):
        yield {'state': 'accepted'}
        yield {'state': 'completed', 'block': {'imageUrl': 'image'}}
    registry = ToolRegistry()
    registry.register(ToolDefinition('image', True, stream_handler=handler,
        budget_scope='image', budget_limits=ToolBudget(max_tool_calls_per_run=1)))
    budget = ToolBudgetTracker(ToolBudget())
    budget.record(external=True, latency_ms=9000, succeeded=True)
    assert (await registry.execute('image', {}, budget)).status == 'ok'
    assert (await registry.execute('image', {}, budget)).status == 'error'
    assert budget.scopes['image'].tool_calls == 1
    assert budget.total_tool_latency_ms == 9000


@pytest.mark.asyncio
async def test_deadline_cancels_generator_and_emits_one_failure():
    cleaned = asyncio.Event()
    async def handler(arguments):
        try:
            yield {'state': 'accepted'}
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    registry = ToolRegistry()
    registry.register(ToolDefinition('slow', True, stream_handler=handler, timeout_seconds=0.02))
    budget = ToolBudgetTracker(ToolBudget())
    events = [event async for event in registry.stream('slow', {}, budget)]
    assert events[-1] == {'state': 'failed', 'reason': 'TimeoutError'}
    assert cleaned.is_set()
    assert budget.consecutive_failures == 1


@pytest.mark.asyncio
async def test_closing_consumer_cleans_up_in_flight_tool():
    cleaned = asyncio.Event()
    async def handler(arguments):
        try:
            yield {'state': 'accepted'}
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    registry = ToolRegistry()
    registry.register(ToolDefinition('cancel', True, stream_handler=handler))
    iterator = registry.stream('cancel', {}, ToolBudgetTracker(ToolBudget()))
    await anext(iterator)
    await iterator.aclose()
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_terminal_event_stops_handler_and_does_not_emit_late_result():
    async def handler(arguments):
        yield {'state': 'failed'}
        yield {'state': 'completed'}
    registry = ToolRegistry()
    registry.register(ToolDefinition('terminal', True, stream_handler=handler))
    assert [event async for event in registry.stream('terminal', {}, ToolBudgetTracker(ToolBudget()))] == [{'state': 'failed'}]


@pytest.mark.asyncio
async def test_asgi_style_cancel_scope_drains_running_generator_before_close():
    import anyio
    started, cleaned = asyncio.Event(), asyncio.Event()
    async def handler(arguments):
        try:
            yield {'state': 'accepted'}
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()
    registry = ToolRegistry()
    registry.register(ToolDefinition('asgi', True, stream_handler=handler, timeout_seconds=10))
    async def consume():
        async for _ in registry.stream('asgi', {}, ToolBudgetTracker(ToolBudget())):
            pass
    async with anyio.create_task_group() as group:
        group.start_soon(consume)
        await started.wait()
        group.cancel_scope.cancel()
    assert cleaned.is_set()
