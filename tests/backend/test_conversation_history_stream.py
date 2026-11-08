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

    monkeypatch.setattr(module.settings, 'model_conversation_summary', 'google/gemini-2.5-flash-lite')
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
    assert selector.call_args.kwargs['model'] == 'google/gemini-2.5-flash-lite'
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
