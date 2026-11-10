"""Boundary regressions discovered by the context-limit audit."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import settings
from services.attachments.parsing import _decode_text
from services.conversation.attachment_budget import AttachmentPart
from services.conversation.context_budget import ContextBudgetError, token_bound
from services.conversation.history import prepare_history


async def prepare(messages, **kwargs):
    return await prepare_history(messages=messages, tools=[], client=None, user_id='audit',
                                 conversation_id='audit', model='audit', context_tokens=32768,
                                 output_tokens=3200, **kwargs)


@pytest.mark.asyncio
async def test_optional_search_does_not_reject_valid_question():
    budget = 32768 - 3200 - token_bound([]) - 1024
    messages = [{'role': 'system', 'content': 'policy'}, {'role': 'user', 'content': ''}]
    question = 'q' * (budget - token_bound(messages) - 40)
    prefix = '<context>\n[文獻1]\nURL: https://example.test\n' + 'source ' * 1000 + '\n</context>\n\n'
    messages[-1]['content'] = prefix + question
    result = await prepare(messages, retrieval_context=prefix)
    assert result.messages[-1]['content'] == question
    assert result.notice
    assert messages[-1]['content'] == prefix + question


def test_text_attachment_keeps_tail_after_50000_characters():
    original = 'a' * 50000 + 'IMPORTANT_TAIL'
    assert original in _decode_text(original.encode(), 'audit.md')


@pytest.mark.asyncio
async def test_attachment_estimate_does_not_reduce_instruction_budget(monkeypatch):
    monkeypatch.setattr(settings, 'conversation_provider_context_tokens', 35000)
    result = await prepare([{'role': 'system', 'content': 's' * 15000},
                       {'role': 'user', 'content': [{'type': 'text', 'text': 'question'},
                         AttachmentPart(type='text', text='a' * 20000)]}])
    assert result.messages[0]['content'] == 's' * 15000
    assert result.messages[-1]['content'][-1]['text'] == 'a' * 20000


@pytest.mark.asyncio
async def test_native_parse_timeout_kills_and_reaps_child(monkeypatch):
    from services.conversation.attachment_budget import bounded_attachment_cost, AttachmentInspectionError
    process = SimpleNamespace(returncode=None, communicate=AsyncMock(side_effect=lambda *_: asyncio.sleep(10)),
                              kill=lambda: None, wait=AsyncMock())
    from unittest.mock import Mock
    process.kill = Mock(side_effect=lambda: setattr(process, 'returncode', -9))
    async def communicate(*args):
        if process.returncode is not None:
            return b'', b''
        await asyncio.sleep(10)
    process.communicate = communicate
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    with pytest.raises(AttachmentInspectionError, match='attachment_parse_timeout'):
        await bounded_attachment_cost({'type': 'file', 'file': {}}, timeout_seconds=.01)
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_parse_cancellation_kills_child(monkeypatch):
    from services.conversation.attachment_budget import bounded_attachment_cost
    from unittest.mock import Mock
    started = asyncio.Event()
    async def communicate(*args):
        if process.returncode is not None:
            return b'', b''
        started.set()
        await asyncio.sleep(10)
    process = SimpleNamespace(returncode=None, communicate=communicate, kill=Mock(), wait=AsyncMock())
    process.kill.side_effect = lambda: setattr(process, 'returncode', -9)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    task = asyncio.create_task(bounded_attachment_cost({'type': 'file', 'file': {}}, timeout_seconds=2))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


class ProviderError(Exception):
    def __init__(self, status=400, code='context_length_exceeded'):
        self.status_code = status
        self.body = {'error': {'code': code, 'message': 'PRIVATE PROVIDER TEXT'}}


async def chunks(text='answer', error=None):
    if text:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))])
    if error:
        raise error


async def stream(create, messages, retrieval_context=''):
    from services.conversation.stream import ConversationStreamService
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    return ''.join([item async for item in service.stream(
        user_id='audit', conversation_id='audit', last_user_msg='question', messages=messages,
        retrieval_context=retrieval_context, force_think=False, max_tokens=3200,
        temperature=.1, top_p=.9, repetition_penalty=1,
        request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)))])


def conversation():
    return [{'role': 'system', 'content': 'policy'}, {'role': 'user', 'content': 'old question'},
            {'role': 'assistant', 'content': 'old answer'}, {'role': 'user', 'content': 'current question'}]


@pytest.mark.asyncio
async def test_context_error_retries_once_without_changing_current_turn(caplog):
    create = AsyncMock(side_effect=[ProviderError(), chunks()])
    messages = conversation()
    result = await stream(create, messages)
    assert 'answer' in result
    assert create.await_count == 2
    assert create.call_args.kwargs['messages'] == [messages[0], messages[-1]]
    assert 'PRIVATE PROVIDER TEXT' not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(429, 'context_length_exceeded'), (400, 'invalid_request'), (500, 'server_error')])
async def test_other_errors_never_context_retry(status, code):
    create = AsyncMock(side_effect=ProviderError(status, code))
    await stream(create, conversation())
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_partial_answer_does_not_retry():
    create = AsyncMock(return_value=chunks('already started', ProviderError()))
    result = await stream(create, conversation())
    assert 'already started' in result
    assert create.await_count == 1


@pytest.mark.asyncio
async def test_second_context_failure_stops_with_specific_error():
    create = AsyncMock(side_effect=ProviderError())
    result = await stream(create, conversation())
    assert create.await_count == 2
    assert '模型仍無法容納' in result


@pytest.mark.asyncio
async def test_retry_removes_verified_sources_and_suppresses_split_citations():
    prefix = '<context>\n[文獻1]\nURL: https://example.test\nEvidence\n</context>\n\n'
    messages = conversation()
    messages[-1]['content'] = [{'type': 'text', 'text': prefix + 'question'}, AttachmentPart(type='text', text='complete attachment')]
    async def answer():
        async for part in chunks('answer【文'):
            yield part
        async for part in chunks('獻1】 finished'):
            yield part
    create = AsyncMock(side_effect=[ProviderError(), answer()])
    result = await stream(create, messages, prefix)
    sent = create.call_args.kwargs['messages'][-1]['content']
    assert sent[0]['text'] == 'question'
    assert sent[1] == messages[-1]['content'][1]
    assert '文獻1' not in result
    assert 'finished' in result


@pytest.mark.asyncio
async def test_timeout_terminates_real_worker(monkeypatch):
    import sys
    from services.conversation.attachment_budget import bounded_attachment_cost, AttachmentInspectionError
    spawn = asyncio.create_subprocess_exec
    processes = []
    async def sleeper(*args, **kwargs):
        process = await spawn(sys.executable, '-c', 'import time; time.sleep(30)', **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', sleeper)
    with pytest.raises(AttachmentInspectionError, match='attachment_parse_timeout'):
        await bounded_attachment_cost({'type': 'file', 'file': {}}, timeout_seconds=.2)
    assert len(processes) == 1
    assert processes[0].returncode is not None


@pytest.mark.asyncio
async def test_attachment_estimate_does_not_reduce_search_budget(monkeypatch):
    monkeypatch.setattr(settings, 'conversation_provider_context_tokens', 35000)
    prefix = '<context>\nEvidence\n</context>\n\n'
    result = await prepare([{'role': 'system', 'content': 's' * 15000},
                       {'role': 'user', 'content': [{'type': 'text', 'text': prefix + 'question'},
                         AttachmentPart(type='text', text='a' * 20000)]}], retrieval_context=prefix)
    assert result.messages[-1]['content'][0]['text'] == prefix + 'question'
    assert result.messages[-1]['content'][-1]['text'] == 'a' * 20000


@pytest.mark.asyncio
async def test_stream_error_before_any_answer_may_retry():
    create = AsyncMock(side_effect=[chunks('', ProviderError()), chunks('recovered')])
    result = await stream(create, conversation())
    assert 'recovered' in result
    assert create.await_count == 2


@pytest.mark.asyncio
async def test_mandatory_only_context_error_does_not_repeat_identical_request():
    create = AsyncMock(side_effect=ProviderError())
    result = await stream(create, [conversation()[0], conversation()[-1]])
    assert '模型仍無法容納' in result
    assert create.await_count == 1


def test_retry_preserves_user_authored_context_and_tool_group():
    from services.conversation.context_recovery import minimal_retry_context
    messages = conversation()
    messages[-1]['content'] = '<context>USER OWN TEXT</context> question'
    messages += [{'role': 'assistant', 'tool_calls': [{'id': 'call'}]},
                 {'role': 'tool', 'tool_call_id': 'call', 'content': 'tool result'}]
    result, removed = minimal_retry_context(messages, messages, '')
    assert result == [messages[0]] + messages[-3:]
    assert not removed


def test_no_evidence_filter_preserves_normal_brackets_and_tail():
    from services.conversation.context_recovery import UnavailableCitationFilter
    f = UnavailableCitationFilter()
    result = ''.join(f.feed(part) for part in ['normal [', 'text] result【文', '獻1】 end [tail']) + f.finish()
    assert result == 'normal [text] result end [tail'


@pytest.mark.asyncio
async def test_parse_worker_failure_is_not_assumed_to_fit(monkeypatch):
    from services.conversation.attachment_budget import bounded_attachment_cost, AttachmentInspectionError
    process = SimpleNamespace(returncode=1, communicate=AsyncMock(return_value=(b'', b'')))
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    with pytest.raises(AttachmentInspectionError, match='attachment_parse_failed'):
        await bounded_attachment_cost({'type': 'file', 'file': {}}, timeout_seconds=1)


@pytest.mark.asyncio
async def test_full_text_upload_reaches_capacity_check_without_losing_tail():
    import io
    from fastapi import UploadFile
    from starlette.datastructures import Headers
    from services.attachments.parsing import process_attachments
    from services.orchestration.visuals import OrchestrationVisualMixin
    original = 'x' * 140000 + 'TAIL_MUST_NOT_BE_DROPPED'
    uploads = await process_attachments([UploadFile(file=io.BytesIO(original.encode()), filename='source.md',
                                                    headers=Headers({'content-type': 'text/markdown'}))])
    assert original in uploads[0].content_part['text']
    assert uploads[0].plain_text == original
    messages = OrchestrationVisualMixin._attach_to_latest_user_message(
        [{'role': 'user', 'content': 'Read the final section'}], [uploads[0].content_part])
    result = await prepare(messages)
    assert original in result.messages[-1]['content'][-1]['text']


@pytest.mark.asyncio
async def test_provider_context_rejection_logs_safe_correlated_metadata(caplog):
    caplog.set_level('INFO')
    messages = [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'PRIVATE QUESTION'},
        AttachmentPart(type='text', text='PRIVATE ATTACHMENT'),
    ]}]
    create = AsyncMock(side_effect=ProviderError())
    result = await stream(create, messages)
    assert '模型仍無法容納本次附件' in result
    assert create.await_count == 1
    assert 'history.provider_context_rejected conversation_id=audit' in caplog.text
    assert 'attempt=1 attachment_count=1 answer_started=False' in caplog.text
    assert 'orchestration.stream_failed conversation_id=audit' in caplog.text
    assert 'error_function=stream error_line=' in caplog.text
    for secret in ('PRIVATE QUESTION', 'PRIVATE ATTACHMENT', 'PRIVATE PROVIDER TEXT'):
        assert secret not in caplog.text
