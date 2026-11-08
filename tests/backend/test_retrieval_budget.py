"""Regression for the five-message web-search rejection seen in production logs."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.conversation.history import prepare_history, token_bound


def sources(count=12, size=500):
    return '<context>\n' + '\n\n'.join(
        f'[文獻{i}] Source {i}\nURL: https://example.com/{i}\n內容段落: ' + '資料' * size
        for i in range(1, count + 1)
    ) + '\n</context>\n\n'


def prompt(prefix, count=5):
    return [{'role': 'system', 'content': 'Answer using the supplied sources.'}] + [
        {'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'prior turn'}
        for i in range(count - 1)
    ] + [{'role': 'user', 'content': prefix + 'short question'}]


@pytest.mark.asyncio
async def test_regression_five_messages_with_twelve_large_sources_fit_without_summary(caplog):
    prefix = sources()
    messages = prompt(prefix)
    before = deepcopy(messages)
    create = AsyncMock(side_effect=AssertionError('No summary needed for five short turns'))
    result = await prepare_history(
        messages=messages, tools=[], client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        user_id='test', conversation_id='test', model='test', output_tokens=2048,
        context_tokens=32768, retrieval_context=prefix,
    )
    assert result.messages[-1]['content'].endswith('short question')
    assert token_bound(result.messages) <= 32768 - 2048 - token_bound([]) - 1024
    assert messages == before
    create.assert_not_called()
    assert 'mandatory_context_too_large' not in caplog.text


@pytest.mark.parametrize('multimodal', [False, True])
def test_budget_preserves_question_attachments_citations_and_input(multimodal, caplog):
    import logging
    from services.conversation.context_budget import budget_retrieval
    caplog.set_level(logging.INFO)
    prefix = sources()
    messages = prompt(prefix)
    attachment = {'type': 'image_url', 'image_url': {'url': 'https://example.com/image.png'}}
    if multimodal:
        messages[-1]['content'] = [{'type': 'text', 'text': messages[-1]['content']}, attachment]
    before = deepcopy(messages)
    bounded, omitted = budget_retrieval(messages, retrieval_context=prefix, budget=12000, conversation_id='trace-safe')
    text = bounded[-1]['content'][0]['text'] if multimodal else bounded[-1]['content']
    assert text.endswith('short question')
    for i in range(1, 13):
        assert f'[文獻{i}] Source {i}\nURL: https://example.com/{i}' in text
    if multimodal:
        assert bounded[-1]['content'][1] == attachment
    assert token_bound(bounded) < 12000
    assert not omitted
    assert messages == before
    assert 'retrieval.context_budgeted conversation_id=trace-safe' in caplog.text
    assert 'trimmed=True' in caplog.text
    assert 'short question' not in caplog.text
    assert 'example.com' not in caplog.text


def test_small_retrieval_is_byte_for_byte_unchanged():
    from services.conversation.context_budget import budget_retrieval
    prefix = sources(count=2, size=1)
    messages = prompt(prefix)
    bounded, omitted = budget_retrieval(messages, retrieval_context=prefix, budget=32768)
    assert bounded == messages
    assert not omitted


def test_omitted_source_does_not_renumber_remaining_sources():
    from services.conversation.context_budget import budget_retrieval
    prefix = '<context>\n[文獻1] Huge header\nURL: https://example.com/' + 'x' * 5000 + '\nbody\n\n[文獻2] Normal\nURL: https://example.com/2\n' + '資料' * 500 + '\n</context>\n\n'
    bounded, omitted = budget_retrieval(prompt(prefix), retrieval_context=prefix, budget=3000)
    text = bounded[-1]['content']
    assert '[文獻1]' not in text
    assert '[文獻2] Normal' in text
    assert not omitted


def test_unstructured_retrieval_summary_also_fits():
    from services.conversation.context_budget import budget_retrieval
    prefix = '<context>\n[網路搜尋摘要]\n' + '摘要' * 6000 + '\n</context>\n\n'
    bounded, _ = budget_retrieval(prompt(prefix), retrieval_context=prefix, budget=12000)
    assert token_bound(bounded) < 12000
    assert bounded[-1]['content'].endswith('short question')


def test_no_readable_source_gets_explicit_evidence_marker():
    from services.conversation.context_budget import budget_retrieval
    prefix = '<context>\n[文獻1] ' + 'long-header' * 1000 + '\nbody\n</context>\n\n'
    bounded, omitted = budget_retrieval(prompt(prefix), retrieval_context=prefix, budget=2000)
    assert omitted
    assert 'Do not cite unavailable evidence.' in bounded[-1]['content']
    assert bounded[-1]['content'].endswith('short question')


def test_mismatched_server_prefix_never_cuts_user_text():
    from services.conversation.context_budget import budget_retrieval
    original = prompt('user-authored <context>data</context>')
    before = deepcopy(original)
    with pytest.raises(ValueError, match='retrieval_prefix_mismatch'):
        budget_retrieval(original, retrieval_context=sources(), budget=12000)
    assert original == before


@pytest.mark.asyncio
async def test_user_authored_context_tags_are_not_treated_as_optional_retrieval():
    with pytest.raises(ValueError, match='current_turn_too_large'):
        await prepare_history(messages=prompt(sources()), tools=[], client=None,
                              user_id='test', conversation_id='test', model='test',
                              output_tokens=2048, context_tokens=32768)


@pytest.mark.asyncio
async def test_large_original_question_is_still_rejected_with_separate_sizes():
    from services.conversation.context_budget import ContextBudgetError
    prefix = sources()
    messages = prompt(prefix)
    messages[-1]['content'] += '原文' * 10000
    with pytest.raises(ContextBudgetError) as error:
        await prepare_history(messages=messages, tools=[], client=None,
                              user_id='test', conversation_id='test', model='test',
                              output_tokens=2048, context_tokens=32768, retrieval_context=prefix)
    assert error.value.reason == 'current_turn_too_large'
    assert error.value.sizes['current_turn_bytes'] > error.value.sizes['budget']
    assert error.value.sizes['retrieval_bytes'] > 0


@pytest.mark.asyncio
async def test_retrieval_budget_and_long_history_compaction_work_together():
    prefix = sources()
    messages = prompt(prefix, count=101)
    for message in messages[1:-1]:
        message['content'] = 'previous state ' * 60
    before = deepcopy(messages)
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content='Earlier decisions and open questions.'), finish_reason='stop')]))
    result = await prepare_history(messages=messages, tools=[],
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        user_id='regression', conversation_id='long-history', model='test',
        output_tokens=2048, context_tokens=32768, retrieval_context=prefix)
    assert create.await_count > 0
    assert any('Historical conversation summary' in m['content'] for m in result.messages)
    assert result.messages[-1]['content'].endswith('short question')
    assert '[文獻1]' in result.messages[-1]['content']
    assert token_bound(result.messages) <= 32768 - 2048 - token_bound([]) - 1024
    assert messages == before


@pytest.mark.asyncio
@pytest.mark.parametrize('retrieval_kind', ['web', 'rag'])
@pytest.mark.parametrize('with_attachment', [False, True])
async def test_integration_sources_context_mixin_budget_and_provider_stream(
    monkeypatch, caplog, retrieval_kind, with_attachment,
):
    """Exercise real source formatting, prompt assembly and stream boundary with a fake provider."""
    import json
    import logging
    import sys
    from types import ModuleType
    from app import prompts as real_prompts
    from services.conversation.context import ConversationContextService
    from services.conversation.stream import ConversationStreamService
    from services.orchestration.streaming import OrchestrationStreamingMixin
    from services.orchestration.visuals import OrchestrationVisualMixin
    from services.orchestration.utils import _build_valid_web_sources
    import config

    # Isolate legacy main-module bootstrap; prompt constants remain the real ones.
    main = ModuleType('main')
    for name in ('EVIDENCE_MODE_OVERLAYS', 'LEARNING_TECHNIQUE_OVERLAYS', 'RESPONSE_POLICY_OVERLAYS',
                 'SYSTEM_PROMPT_FORCE_THINK', 'SYSTEM_PROMPT_NORMAL',
                 'SYSTEM_PROMPT_WITH_RAG', 'SYSTEM_PROMPT_WITH_RAG_THINK'):
        setattr(main, name, getattr(real_prompts, name))
    monkeypatch.setitem(sys.modules, 'main', main)
    monkeypatch.setattr(config.settings, 'conversation_context_tokens', 32768)
    monkeypatch.setattr(config.settings, 'enable_conversation_compaction', True)
    caplog.set_level(logging.INFO)
    results = [{'title': f'Source {i}', 'url': f'https://example.com/{i}',
                'snippet': '資料' * 500} for i in range(1, 13)]
    source_texts, source_payload = _build_valid_web_sources(results)
    prefix = '<context>\n' + '\n\n'.join(source_texts) + '\n</context>\n\n'
    original = prompt('')[1:]
    original_before = deepcopy(original)
    policy = SimpleNamespace(evaluate=lambda _: SimpleNamespace(allow_long_term_query=False))
    context = await ConversationContextService(policy, AsyncMock()).build_conversation_context(
        user_id='test', conversation_id='five-message-regression', messages=original,
        use_rag=retrieval_kind == 'rag', use_web_search=retrieval_kind == 'web',
        force_think=False, context_results_obj={'source': retrieval_kind},
        last_user_msg='short question', context_prompt=prefix, client=None,
        snapshot_loader=AsyncMock(return_value=''), store=None, chat_avatar_key='test',
    )
    attachment = {'type': 'file', 'file': {'filename': 'test.pdf', 'file_data': 'data:application/pdf;base64,AA=='}}
    if with_attachment:
        context.messages[:] = OrchestrationVisualMixin._attach_to_latest_user_message(context.messages, [attachment])
    assembled_before = deepcopy(context.messages)

    async def answer_chunks():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Answer【文獻1】', tool_calls=None))])
    create = AsyncMock(return_value=answer_chunks())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    mixin = OrchestrationStreamingMixin()
    mixin.stream_service = ConversationStreamService(client, None)
    chunks = [chunk async for chunk in mixin._node_llm_stream(
        'test', 'five-message-regression', 'short question', context.messages,
        False, 2048, 0.1, 0.9, 1.0,
        SimpleNamespace(is_disconnected=AsyncMock(return_value=False)), retrieval_context=prefix,
    )]
    create.assert_awaited_once()
    kwargs = create.call_args.kwargs
    sent = kwargs['messages']
    text = sent[-1]['content'][0]['text'] if with_attachment else sent[-1]['content']
    assert text.endswith('short question')
    assert '[文獻1] Source 1\nURL: https://example.com/1' in text
    assert len(source_payload) == 12 and source_payload[-1]['url'] == 'https://example.com/12'
    assert token_bound(sent) <= 32768 - 2048 - token_bound(kwargs['tools']) - 1024
    if with_attachment:
        assert sent[-1]['content'][1] == attachment
    answer = ''.join(json.loads(chunk[6:])['choices'][0]['delta'].get('content', '')
                     for chunk in chunks if isinstance(chunk, str) and chunk.startswith('data: {'))
    assert 'Answer【文獻1】' in answer
    assert '超過可處理容量' not in answer
    assert 'retrieval.context_budgeted' in caplog.text
    assert 'history.rejected' not in caplog.text
    assert original == original_before
    assert context.messages == assembled_before


@pytest.mark.asyncio
async def test_regression_execute_carries_request_scoped_retrieval_to_real_stream(monkeypatch):
    """Protect the execution-to-stream handoff that isolated history tests cannot cover."""
    import sys
    from types import ModuleType
    from unittest.mock import MagicMock
    from app import prompts as real_prompts
    import config
    import services.orchestration.execution as execution
    from services.orchestration.service import OrchestrationService
    from services.query_policy.classifier import default_response_policy

    main = ModuleType('main')
    for name in ('EVIDENCE_MODE_OVERLAYS', 'LEARNING_TECHNIQUE_OVERLAYS', 'RESPONSE_POLICY_OVERLAYS',
                 'SYSTEM_PROMPT_FORCE_THINK', 'SYSTEM_PROMPT_NORMAL',
                 'SYSTEM_PROMPT_WITH_RAG', 'SYSTEM_PROMPT_WITH_RAG_THINK'):
        setattr(main, name, getattr(real_prompts, name))
    monkeypatch.setitem(sys.modules, 'main', main)
    monkeypatch.setattr(config.settings, 'enable_turn_plan_runtime', False)
    monkeypatch.setattr(config.settings, 'enable_parts_prompt_context', False)
    monkeypatch.setattr(config.settings, 'enable_visual_preflight', False)
    monkeypatch.setattr(config.settings, 'conversation_context_tokens', 32768)
    monkeypatch.setattr(config.settings, 'enable_conversation_compaction', True)
    monkeypatch.setattr(execution, 'record_interaction_timestamp', AsyncMock(return_value=True))
    monkeypatch.setattr('services.memory.store.service.get_global_store', lambda: None)
    prefix = sources()

    async def answer():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Grounded answer【文獻1】', tool_calls=None))])
    create = AsyncMock(return_value=answer())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    service = OrchestrationService(MagicMock(), None, None, client)
    service.snapshot_loader = AsyncMock(return_value='')
    service.context_service.memory_policy = SimpleNamespace(evaluate=lambda _: SimpleNamespace(allow_long_term_query=False))
    service.turn_intake_service.process = AsyncMock()
    service.classify_dialogue_policy = AsyncMock(return_value=default_response_policy())

    async def search(_query, _conversation_id, messages, run_state, **kwargs):
        run_state.context_prompt = prefix
        run_state.context_results = {'source': 'web_search'}
        yield 'event: sources\ndata: []\n\n'
        yield 'event: results_obj\n\n'
    service._node_perplexity_search = search

    async def finish(*args, **kwargs):
        yield 'data: [DONE]\n\n'
    monkeypatch.setattr(execution, 'complete_answer', finish)
    request = SimpleNamespace(headers={}, is_disconnected=AsyncMock(return_value=False))
    chunks = [event async for event in service.execute(
        prompt('')[1:], 'execution-regression', False, True, False,
        2048, 0.1, 0.9, 1.0, request, 'test', search_mode='always',
    )]
    create.assert_awaited_once()
    kwargs = create.call_args.kwargs
    sent = kwargs['messages']
    assert token_bound(sent) <= config.settings.conversation_context_tokens - kwargs['max_tokens'] - token_bound(kwargs['tools']) - 1024
    assert '[文獻1]' in sent[-1]['content']
    assert sent[-1]['content'].endswith('short question')
    assert 'Grounded answer' in ''.join(chunks)
    assert '超過可處理容量' not in ''.join(chunks)
    assert any('[DONE]' in chunk for chunk in chunks)


def test_rag_citation_headers_without_url_survive_shortening():
    from services.conversation.context_budget import budget_retrieval
    prefix = '<context>\n' + '\n\n'.join(f'[文獻{i}] Local book\n' + '古籍資料' * 500 for i in range(1, 8)) + '\n</context>\n\n'
    bounded, omitted = budget_retrieval(prompt(prefix), retrieval_context=prefix, budget=9000)
    assert not omitted
    assert token_bound(bounded) < 9000
    for i in range(1, 8):
        assert f'[文獻{i}] Local book' in bounded[-1]['content']


@pytest.mark.asyncio
async def test_no_source_excerpt_notice_is_propagated_to_stream_context():
    prefix = '<context>\n[文獻1] ' + 'long-header' * 1000 + '\nbody\n</context>\n\n'
    result = await prepare_history(messages=prompt(prefix), tools=[], client=None,
                                  user_id='test', conversation_id='test', model='test',
                                  output_tokens=500, context_tokens=3500, retrieval_context=prefix)
    assert '沒有可納入的搜尋摘錄' in result.notice
    assert result.messages[-1]['content'].endswith('short question')
