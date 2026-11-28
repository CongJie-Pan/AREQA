"""Summaries computed ahead of need replace the answer-path summary call."""
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.conversation import summary_precompute
from services.conversation.history import _CACHE, prepare_history
from services.conversation.summary_precompute import PrecomputeSettings


def _response(text='Learning state: goal kept.'):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason='stop')])


def client():
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=_response()))))


def history(count):
    return [{'role': 'system', 'content': 'System policy'}] + [
        {'role': role, 'content': f'{i}: ' + ('history data ' * 80)}
        for i in range(count) for role in ('user', 'assistant')
    ] + [{'role': 'user', 'content': 'What was the original constraint?'}]


SETTINGS = PrecomputeSettings(ratio=0.75, tail_share=0.5, wait_seconds=1.0, timeout_seconds=5.0)


async def run(messages, model_client, precompute=SETTINGS):
    return await prepare_history(
        messages=messages, tools=[], client=model_client, user_id='alice', conversation_id='chat',
        model='test', output_tokens=500, context_tokens=8000, summary_tokens=256, precompute=precompute)


async def settle():
    # Let scheduled background jobs run to completion.
    for _ in range(20):
        await asyncio.sleep(0)
    running = list(summary_precompute._inflight.values())
    if running:
        await asyncio.wait([task for _, task in running], timeout=2)


@pytest.fixture(autouse=True)
def clean_state():
    _CACHE.clear()
    summary_precompute.reset()
    yield
    summary_precompute.reset()


@pytest.mark.asyncio
async def test_near_budget_turn_precomputes_and_next_turn_skips_summary_call(caplog):
    caplog.set_level(logging.INFO)
    c = client()
    near = history(8)
    first = await run(near, c)
    # Under budget: the answer context is unchanged; the summary runs in the background.
    assert first.messages == near
    await settle()
    assert c.chat.completions.create.await_count == 1
    assert 'history.precompute_completed' in caplog.text

    result = await run(history(12), c)
    assert c.chat.completions.create.await_count == 1
    assert any('Historical conversation summary' in str(m['content']) for m in result.messages)
    assert result.messages[-1]['content'] == 'What was the original constraint?'
    assert 'sync_summary=False' in caplog.text


@pytest.mark.asyncio
async def test_edited_history_misses_checkpoint_and_summarizes_on_answer_path(caplog):
    caplog.set_level(logging.INFO)
    c = client()
    await run(history(8), c)
    await settle()
    edited = history(12)
    edited[1] = {'role': 'user', 'content': '0: edited ' + ('history data ' * 80)}
    calls = c.chat.completions.create.await_count
    result = await run(edited, c)
    assert c.chat.completions.create.await_count > calls
    assert 'sync_summary=True' in caplog.text
    assert result.messages[-1] == edited[-1]


@pytest.mark.asyncio
async def test_answer_path_waits_for_running_summary():
    c = client()
    release = asyncio.Event()

    async def slow(**_):
        await release.wait()
        return _response()

    c.chat.completions.create.side_effect = slow
    await run(history(8), c)
    await asyncio.sleep(0)
    assert summary_precompute._inflight
    asyncio.get_running_loop().call_later(0.05, release.set)
    result = await run(history(12), c)
    # The waited-for background summary served this turn; no second summary call.
    assert c.chat.completions.create.await_count == 1
    assert any('Historical conversation summary' in str(m['content']) for m in result.messages)


@pytest.mark.asyncio
async def test_repeated_failures_stop_scheduling(caplog):
    caplog.set_level(logging.INFO)
    c = client()
    c.chat.completions.create.side_effect = RuntimeError('provider down')
    for _ in range(3):
        await run(history(8), c)
        await settle()
    assert c.chat.completions.create.await_count == summary_precompute.MAX_FAILURES
    assert 'reason=failure_limit' in caplog.text
    assert 'provider down' not in caplog.text


@pytest.mark.asyncio
async def test_disabled_precompute_keeps_synchronous_behavior():
    c = client()
    await run(history(8), c, precompute=None)
    await settle()
    c.chat.completions.create.assert_not_called()
    assert not summary_precompute._inflight


@pytest.mark.asyncio
async def test_compaction_disabled_never_precomputes():
    c = client()
    await prepare_history(
        messages=history(8), tools=[], client=c, user_id='alice', conversation_id='chat', model='test',
        output_tokens=500, context_tokens=8000, summary_tokens=256, enabled=False, precompute=SETTINGS)
    await settle()
    c.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_covered_target_is_not_summarized_again(caplog):
    caplog.set_level(logging.INFO)
    c = client()
    await run(history(8), c)
    await settle()
    await run(history(8), c)
    await settle()
    assert c.chat.completions.create.await_count == 1
    assert 'reason=already_covered' in caplog.text
