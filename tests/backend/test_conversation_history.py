"""Regression coverage for long-conversation context ownership and fallbacks."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.conversation.history import _CACHE, prepare_history, token_bound


def client(text='Goals: preserve the original constraint.'):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=text), finish_reason='stop')])
    ))))


def history(count=100):
    return [{'role': 'system', 'content': 'System policy'}] + [
        {'role': role, 'content': f'{i}: ' + ('history data ' * 80)}
        for i in range(count) for role in ('user', 'assistant')
    ] + [{'role': 'user', 'content': 'What was the original constraint?'}]


async def run(messages, model_client=None, **kwargs):
    return await prepare_history(
        messages=messages, tools=[], client=model_client or client(),
        user_id='alice', conversation_id='chat', model='test',
        output_tokens=500, context_tokens=8000, summary_tokens=256,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def clear_cache():
    _CACHE.clear()


@pytest.mark.asyncio
async def test_short_history_over_100_messages_is_not_a_model_limit():
    messages = [{'role': 'user', 'content': 'hi'}] * 101
    c = client()
    result = await run(messages, c)
    assert result.messages == messages
    c.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_summary_budget_and_unchanged_transcript():
    messages = history()
    before = [dict(m) for m in messages]
    result = await run(messages)
    assert messages == before
    assert result.messages[0] == messages[0]
    assert result.messages[-1] == messages[-1]
    assert token_bound(result.messages) + token_bound([]) <= (8000 - 500 - 1024) * 3
    assert any('Historical conversation summary' in m['content'] for m in result.messages)
    assert not result.notice


@pytest.mark.asyncio
async def test_cache_reuse_edits_and_user_isolation():
    c = client()
    messages = history(10)
    await run(messages, c)
    calls = c.chat.completions.create.await_count
    await run(messages, c)
    assert c.chat.completions.create.await_count == calls
    messages[1]['content'] = 'edited ' + messages[1]['content']
    await run(messages, c)
    assert c.chat.completions.create.await_count > calls
    calls = c.chat.completions.create.await_count
    await prepare_history(messages=messages, tools=[], client=c, user_id='bob',
                          conversation_id='chat', model='test', output_tokens=500,
                          context_tokens=8000, summary_tokens=256)
    assert c.chat.completions.create.await_count > calls


@pytest.mark.asyncio
async def test_failure_falls_back_and_logs_no_content(caplog):
    c = client()
    c.chat.completions.create.side_effect = RuntimeError('PRIVATE PROVIDER DATA')
    result = await run(history(), c)
    assert not result.notice
    assert result.messages[-1]['content'] == 'What was the original constraint?'
    assert 'history.summary_failed' in caplog.text
    assert 'PRIVATE PROVIDER DATA' not in caplog.text


@pytest.mark.asyncio
async def test_timeout_and_truncated_summary_are_not_cached():
    c = client()
    async def slow(**kwargs):
        await asyncio.sleep(10)
    c.chat.completions.create.side_effect = slow
    assert not (await run(history(), c, timeout_seconds=0.01)).notice
    assert not _CACHE
    c = client()
    c.chat.completions.create.return_value.choices[0].finish_reason = 'length'
    assert not (await run(history(), c)).notice
    assert not _CACHE


@pytest.mark.asyncio
async def test_current_input_is_never_silently_truncated():
    with pytest.raises(ValueError, match='current_turn_too_large'):
        await run([{'role': 'user', 'content': '中' * 10_000}])


@pytest.mark.asyncio
async def test_disabled_feature_rejects_instead_of_unbounded_call():
    with pytest.raises(ValueError, match='compaction_disabled'):
        await run(history(), enabled=False)


@pytest.mark.asyncio
async def test_recall_returns_early_original_including_chinese():
    messages = history(20)
    messages[1]['content'] = '原先約定：所有程式範例都必須使用 Python。'
    messages[-1]['content'] = '原先約定的程式範例語言是什麼？'
    result = await run(messages)
    assert any('Historical source message' in m['content'] and 'Python' in m['content'] for m in result.messages)


@pytest.mark.asyncio
async def test_incremental_summary_reuses_covered_prefix():
    c = client()
    messages = history(12)
    await run(messages, c)
    c.chat.completions.create.reset_mock()
    messages.extend([{'role': 'assistant', 'content': 'answered ' * 120},
                     {'role': 'user', 'content': 'new question ' * 100}])
    await run(messages, c)
    # Updated summaries carry the previous summary and only newly aged messages.
    calls = c.chat.completions.create.call_args_list
    assert calls
    import json
    payload = json.loads(calls[0].kwargs['messages'][1]['content'])
    assert payload['previous_summary']
    assert payload['messages'][0]['turn'] > 1


@pytest.mark.asyncio
async def test_keeps_tool_calls_and_results_in_the_same_recent_turn():
    messages = history(10)
    messages.extend([
        {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call1', 'type': 'function', 'function': {'name': 'lookup', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': 'call1', 'content': 'result'},
        {'role': 'assistant', 'content': 'done'},
    ])
    result = await run(messages)
    assert result.messages[-4:] == messages[-4:]


@pytest.mark.asyncio
async def test_summary_debug_logs_use_safe_metadata(caplog):
    import logging
    caplog.set_level(logging.INFO, logger='services.conversation.history')
    c = client('PRIVATE SUMMARY TEXT')
    c.chat.completions.create.return_value.usage = SimpleNamespace(prompt_tokens=123, completion_tokens=20)
    await run(history(10), c)
    assert 'history.summary_started model=test' in caplog.text
    assert 'history.summary_completed model=test elapsed_ms=' in caplog.text
    assert 'input_tokens=123 output_tokens=20 finish_reason=stop' in caplog.text
    assert 'PRIVATE SUMMARY TEXT' not in caplog.text
    caplog.clear()
    await run(history(10), c)
    assert 'cache_hit=True' in caplog.text
    assert 'history.summary_started' not in caplog.text


@pytest.mark.asyncio
async def test_cold_start_110_messages_uses_one_summary_request():
    import json
    c = client()
    messages = history(55)
    result = await run(messages, c)
    assert c.chat.completions.create.await_count == 1
    payload = json.loads(c.chat.completions.create.call_args.kwargs['messages'][1]['content'])
    assert payload['messages'][0]['turn'] == 1
    sources = [{key: value for key, value in record.items() if key != 'turn'}
               for record in payload['messages']]
    recent = [m for m in result.messages[1:] if not m['content'].startswith('Historical ')]
    assert sources + recent == messages[1:]
    assert not result.notice


@pytest.mark.asyncio
async def test_timeout_never_prepends_history_warning(caplog):
    async def slow(**kwargs):
        await asyncio.sleep(10)
    c = client()
    c.chat.completions.create.side_effect = slow
    result = await run(history(55), c, timeout_seconds=0.01)
    assert result.notice == ''
    assert result.messages[-1] == history(55)[-1]
    assert 'history.summary_failed' in caplog.text


@pytest.mark.asyncio
async def test_independent_summary_budget_batches_complete_sources():
    import json
    c = client()
    messages = history(37)
    await run(messages, c, summary_context_tokens=16000)
    calls = c.chat.completions.create.call_args_list
    assert 1 < len(calls) < 30
    turns = []
    for call in calls:
        assert token_bound(call.kwargs['messages']) + 256 + 1024 <= 16000
        payload = json.loads(call.kwargs['messages'][1]['content'])
        turns.extend(m['turn'] for m in payload['messages'])
    assert turns == list(range(1, turns[-1] + 1))
    assert turns[-1] >= 58


@pytest.mark.asyncio
async def test_prompt_and_model_changes_invalidate_checkpoints(monkeypatch):
    import services.conversation.history as module
    c = client()
    messages = history(10)
    await run(messages, c)
    monkeypatch.setattr(module, '_INSTRUCTION', module._INSTRUCTION + ' Revised instruction.')
    await run(messages, c)
    assert c.chat.completions.create.await_count == 2
    await prepare_history(messages=messages, tools=[], client=c, user_id='alice',
                          conversation_id='chat', model='different', output_tokens=500,
                          context_tokens=8000, summary_tokens=256)
    assert c.chat.completions.create.await_count == 3


@pytest.mark.asyncio
async def test_partial_timeout_checkpoint_is_reused_by_next_request(caplog):
    import json
    c = client()
    valid = c.chat.completions.create.return_value
    attempts = 0

    async def provider(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts > 1:
            await asyncio.sleep(10)
        return valid

    c.chat.completions.create.side_effect = provider
    first = await run(history(15), c, summary_context_tokens=12000, timeout_seconds=0.01)
    assert not first.notice
    assert 'covered=0' not in caplog.text
    c.chat.completions.create.reset_mock(side_effect=True)
    await run(history(15), c, summary_context_tokens=12000)
    payload = json.loads(c.chat.completions.create.call_args_list[0].kwargs['messages'][1]['content'])
    assert payload['previous_summary']
    assert payload['messages'][0]['turn'] > 1
