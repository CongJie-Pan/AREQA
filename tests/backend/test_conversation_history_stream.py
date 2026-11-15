"""Prove context selection is wired into the final streaming provider request."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.conversation.stream import ConversationStreamService


@pytest.mark.asyncio
async def test_stream_forwards_bounded_history_and_announces_degradation(monkeypatch):
    import services.conversation.stream as module
    from services.conversation.history import HistoryContext

    monkeypatch.setattr(module.settings, 'model_conversation_summary', 'google/gemini-3.1-flash-lite')
    original = [{'role': 'user', 'content': 'old'}] * 101
    selected = [{'role': 'user', 'content': 'current'}]
    selector = AsyncMock(return_value=HistoryContext(selected, 'context limited'))
    monkeypatch.setattr(module, 'prepare_history', selector)

    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='answer', tool_calls=None))])
    create = AsyncMock(return_value=response())
    c = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    service = ConversationStreamService(c, None)
    request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
    chunks = [chunk async for chunk in service.stream(
        user_id='alice', conversation_id='chat', last_user_msg='current', messages=original,
        force_think=False, max_tokens=500, temperature=0.1, top_p=0.9,
        repetition_penalty=1, request=request,
    )]
    assert create.call_args.kwargs['messages'] == selected
    assert selector.call_args.kwargs['model'] == 'google/gemini-3.1-flash-lite'
    assert create.call_args.kwargs['model'] == module.settings.model_main_instruct
    assert selector.call_args.kwargs['user_id'] == 'alice'
    assert selector.call_args.kwargs['tools'] == create.call_args.kwargs['tools']
    assert 'context limited' in chunks[0]
    assert 'answer' in ''.join(str(c) for c in chunks)
    assert len(original) == 101


@pytest.mark.asyncio
async def test_oversized_current_turn_does_not_call_provider(monkeypatch):
    import services.conversation.stream as module
    monkeypatch.setattr(module, 'prepare_history', AsyncMock(side_effect=ValueError('current_turn_too_large')))
    create = AsyncMock()
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    chunks = [chunk async for chunk in service.stream(
        user_id='alice', conversation_id='chat', last_user_msg='large', messages=[],
        force_think=False, max_tokens=500, temperature=0.1, top_p=0.9,
        repetition_penalty=1, request=SimpleNamespace(),
    )]
    create.assert_not_called()
    assert '超過可處理容量' in json.loads(chunks[0][6:])['choices'][0]['delta']['content']


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['instructions_too_large', 'current_turn_too_large', 'output_budget', 'retrieval_prefix_mismatch'])
async def test_budget_rejection_logs_exact_safe_reason_and_sizes(monkeypatch, caplog, reason):
    import logging
    import services.conversation.stream as module
    from services.conversation.context_budget import ContextBudgetError
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(module, 'prepare_history', AsyncMock(side_effect=ContextBudgetError(
        reason, budget=1000, instructions_bytes=800, current_turn_bytes=300, retrieval_bytes=2000)))
    create = AsyncMock()
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    _ = [chunk async for chunk in service.stream(
        user_id='test', conversation_id='safe-trace', last_user_msg='PRIVATE USER TEXT', messages=[],
        force_think=False, max_tokens=500, temperature=0.1, top_p=0.9,
        repetition_penalty=1, request=SimpleNamespace(),
    )]
    create.assert_not_called()
    assert f'reason={reason}' in caplog.text
    assert 'conversation_id=safe-trace' in caplog.text
    assert 'budget=1000 instructions_bytes=800 current_turn_bytes=300 retrieval_bytes=2000' in caplog.text
    assert 'PRIVATE USER TEXT' not in caplog.text


@pytest.mark.asyncio
async def test_real_history_timeout_still_streams_answer_without_warning(monkeypatch, caplog):
    import asyncio
    import services.conversation.stream as module
    from services.conversation.history import _CACHE
    _CACHE.clear()
    monkeypatch.setattr(module.settings, 'conversation_context_tokens', 8000)
    monkeypatch.setattr(module.settings, 'conversation_summary_cold_timeout_seconds', 0.01)

    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Normal answer', tool_calls=None))])

    async def provider(**kwargs):
        if not kwargs.get('stream'):
            await asyncio.sleep(10)
        return response()

    create = AsyncMock(side_effect=provider)
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    messages = [{'role': role, 'content': 'Earlier discussion ' * 100}
                for _ in range(55) for role in ('user', 'assistant')]
    messages.append({'role': 'user', 'content': 'Continue with web search.'})
    chunks = [chunk async for chunk in service.stream(
        user_id='alice', conversation_id='chat-timeout', last_user_msg=messages[-1]['content'], messages=messages,
        force_think=False, max_tokens=500, temperature=0.1, top_p=0.9,
        repetition_penalty=1, request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
    )]
    output = ''.join(chunks)
    assert 'Normal answer' in output
    assert '部分較早對話' not in output
    assert 'history.summary_failed reason=TimeoutError' in caplog.text
    assert create.call_args.kwargs['messages'][-1] == messages[-1]
    _CACHE.clear()


@pytest.mark.asyncio
async def test_wait_status_is_separate_from_answer_and_cancels_on_disconnect(monkeypatch):
    import asyncio
    import services.conversation.stream as module
    cancelled = asyncio.Event()

    async def preparation(**kwargs):
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.set()

    monkeypatch.setattr(module, 'prepare_history', preparation)
    create = AsyncMock()
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    chunks = [chunk async for chunk in service.stream(
        user_id='alice', conversation_id='disconnect', last_user_msg='Continue', messages=[],
        force_think=False, max_tokens=500, temperature=0.1, top_p=0.9,
        repetition_penalty=1, request=SimpleNamespace(is_disconnected=AsyncMock(return_value=True)),
    )]
    assert chunks[0].startswith('event: status\n')
    assert '正在整理較早對話' in chunks[0]
    assert 'choices' not in chunks[0]
    assert cancelled.is_set()
    create.assert_not_called()


@pytest.mark.asyncio
async def test_length_finish_adds_visible_notice_and_logs_usage(monkeypatch, caplog):
    """Production answers stopped mid-sentence without any explanation (2026-11-15)."""
    import logging
    import services.conversation.stream as module
    from services.conversation.history import HistoryContext

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(module, 'prepare_history', AsyncMock(return_value=HistoryContext(
        [{'role': 'user', 'content': 'explain'}], '')))

    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content='The LSTM paper shows', tool_calls=None), finish_reason=None)])
        yield SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content='', tool_calls=None), finish_reason='length')])
        yield SimpleNamespace(choices=[], usage=SimpleNamespace(
            prompt_tokens=50_000, completion_tokens=3_200,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=1_900),
            prompt_tokens_details=SimpleNamespace(cached_tokens=40_000)))

    create = AsyncMock(return_value=response())
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    chunks = [chunk async for chunk in service.stream(
        user_id='alice', conversation_id='chat', last_user_msg='explain', messages=[],
        force_think=False, max_tokens=3200, temperature=0.1, top_p=0.9,
        repetition_penalty=1, request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
    )]
    joined = ''.join(chunks)
    assert '回答已達單次長度上限' in joined
    final = next(c for c in chunks if c.startswith('event: accumulator'))
    assert '回答已達單次長度上限' in final
    assert create.call_args.kwargs['extra_body']['usage'] == {'include': True}
    assert ('orchestration.provider_finish conversation_id=chat finish_reason=length prompt_tokens=50000 '
            'completion_tokens=3200 reasoning_tokens=1900 cached_tokens=40000') in caplog.text
    assert 'The LSTM paper shows' not in caplog.text


@pytest.mark.asyncio
async def test_normal_finish_has_no_truncation_notice(monkeypatch, caplog):
    import logging
    import services.conversation.stream as module
    from services.conversation.history import HistoryContext

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(module, 'prepare_history', AsyncMock(return_value=HistoryContext(
        [{'role': 'user', 'content': 'hi'}], '')))

    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content='Hello', tool_calls=None), finish_reason='stop')])

    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=AsyncMock(return_value=response())))), None)
    chunks = [chunk async for chunk in service.stream(
        user_id='alice', conversation_id='chat', last_user_msg='hi', messages=[],
        force_think=False, max_tokens=500, temperature=0.1, top_p=0.9,
        repetition_penalty=1, request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
    )]
    assert '長度上限' not in ''.join(chunks)
    assert 'finish_reason=stop' in caplog.text
    assert 'reasoning_tokens=None' in caplog.text
