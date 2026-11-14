"""Token allowances must be converted to bytes before comparing with token_bound().

Production evidence (2026-11-14): a 108-message web-search conversation had
chat_budget=26330 bytes for a 32768-token setting, so the provider received only
instructions, the summary and the current question (selected_messages=3).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.conversation.history import _CACHE, prepare_history


def summary_client():
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content='Earlier turns compared neorealist theories.'),
        finish_reason='stop')], usage=None))
    return create, SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.asyncio
async def test_long_web_search_chat_keeps_previous_turn_verbatim():
    _CACHE.clear()
    instructions = {'role': 'system', 'content': '系統指令' * 1100}  # ~13 KB like production
    retrieval = '<context>\n[文獻1]\n' + '搜尋摘錄內容' * 450 + '\n</context>\n\n'  # ~8 KB
    history = []
    for turn in range(54):
        history.append({'role': 'user', 'content': f'第{turn}題：' + '請比較理論觀點。' * 20})
        history.append({'role': 'assistant', 'content': f'第{turn}答：' + '新古典現實主義的分析。' * 60})
    previous_answer = history[-1]
    current = {'role': 'user', 'content': retrieval + '請把上一段改寫成筆記。'}
    create, client = summary_client()
    result = await prepare_history(
        messages=[instructions, *history, current], tools=[], client=client,
        user_id='test', conversation_id='long-chat', model='test', output_tokens=3200,
        context_tokens=32768, retrieval_context=retrieval,
    )
    assert create.await_count == 1
    assert previous_answer in result.messages
    assert len(result.messages) > 3
    _CACHE.clear()


@pytest.mark.asyncio
async def test_current_turn_larger_than_converted_budget_is_rejected():
    from services.conversation.context_budget import ContextBudgetError
    with pytest.raises(ContextBudgetError, match='current_turn_too_large'):
        await prepare_history(
            messages=[{'role': 'user', 'content': 'x' * 400_000}], tools=[], client=None,
            user_id='test', conversation_id='test', model='test', output_tokens=3200,
            context_tokens=32768,
        )


@pytest.mark.asyncio
async def test_rejected_turn_reports_notice_as_final_answer():
    from services.conversation.stream import ConversationStreamService
    create = AsyncMock()
    service = ConversationStreamService(
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    chunks = [chunk async for chunk in service.stream(
        user_id='test', conversation_id='too-large', last_user_msg='x',
        messages=[{'role': 'user', 'content': 'x' * 400_000}],
        force_think=False, max_tokens=3200, temperature=0.1, top_p=0.9, repetition_penalty=1,
        request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
    )]
    create.assert_not_awaited()
    notice = next(c for c in chunks if '超過可處理容量' in c and c.startswith('data: '))
    final = next(c for c in chunks if c.startswith('event: accumulator\n'))
    assert '超過可處理容量' in notice
    assert '超過可處理容量' in final
