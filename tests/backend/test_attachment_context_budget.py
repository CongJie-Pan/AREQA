"""Real attachment payloads must not consume the chat-history text allowance."""
import base64
from copy import deepcopy
import io
import random
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pymupdf
import pytest
from PIL import Image

from config import settings
from services.conversation.attachment_budget import AttachmentPart, attachment_cost
from services.conversation.context_budget import ContextBudgetError, token_bound
from services.conversation.history import prepare_history
from services.orchestration.visuals import OrchestrationVisualMixin


def attachment(kind):
    if kind == 'pdf':
        with pymupdf.open() as doc:
            doc.new_page().insert_text((40, 40), 'A small readable document.')
            doc.embfile_add('padding.bin', random.Random(0).randbytes(400000))
            data = doc.tobytes()
        return {'type': 'file', 'file': {'filename': 'fixture.pdf', 'file_data':
                'data:application/pdf;base64,' + base64.b64encode(data).decode()}}
    if kind == 'image':
        data = io.BytesIO()
        Image.frombytes('RGB', (300, 300), random.Random(0).randbytes(270000)).save(data, format='PNG')
        return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(data.getvalue()).decode()}}
    return {'type': 'text', 'text': ('# Markdown\n' if kind == 'markdown' else '') + 'source detail ' * 4000}


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['pdf', 'image', 'text', 'markdown'])
@pytest.mark.parametrize('prior', [False, True])
@pytest.mark.parametrize('search', [False, True])
async def test_attachments_preserved_with_independent_budget(kind, prior, search):
    prefix = '<context>\n[文獻1]\nURL: https://example.test/source\n' + 'evidence ' * 5000 + '\n</context>\n\n' if search else ''
    messages = [{'role': 'system', 'content': 'Answer based on sources.'}]
    if prior:
        messages += [{'role': 'user', 'content': 'Initial question'}, {'role': 'assistant', 'content': 'Initial answer'}]
    messages += [{'role': 'user', 'content': prefix + 'Explain the attachment.'}]
    part = attachment(kind)
    messages = OrchestrationVisualMixin._attach_to_latest_user_message(messages, [part])
    before = deepcopy(messages)
    create = AsyncMock()
    result = await prepare_history(messages=messages, tools=[], client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
                                   user_id='test', conversation_id='test', model='test', output_tokens=3200,
                                   context_tokens=32768, retrieval_context=prefix)
    assert result.messages[-1]['content'][-1] == part
    assert messages == before
    assert token_bound(result.messages) + 3200 + 1024 <= 32768
    create.assert_not_awaited()
    units, count = attachment_cost(messages)
    assert 0 < units < settings.conversation_attachment_tokens
    assert count == 1


@pytest.mark.asyncio
async def test_large_plain_question_is_still_rejected():
    with pytest.raises(ContextBudgetError, match='current_turn_too_large'):
        await prepare_history(messages=[{'role': 'user', 'content': 'x' * 100000}], tools=[], client=None,
                              user_id='test', conversation_id='test', model='test', output_tokens=3200, context_tokens=32768)


@pytest.mark.asyncio
async def test_attachment_above_legacy_allowance_is_preserved(monkeypatch):
    monkeypatch.setattr(settings, 'conversation_attachment_tokens', 1000)
    result = await prepare_history(messages=[{'role': 'user', 'content': [AttachmentPart(attachment('text'))]}], tools=[], client=None,
                              user_id='test', conversation_id='test', model='test', output_tokens=3200, context_tokens=32768)
    assert result.messages[-1]['content'][0]['text'] == attachment('text')['text']


@pytest.mark.asyncio
async def test_estimated_provider_capacity_does_not_reduce_chat_budget(monkeypatch):
    monkeypatch.setattr(settings, 'conversation_provider_context_tokens', 10000)
    result = await prepare_history(messages=[{'role': 'user', 'content': [AttachmentPart(attachment('text'))]}], tools=[], client=None,
                              user_id='test', conversation_id='test', model='test', output_tokens=3200, context_tokens=32768)
    assert result.messages[-1]['content'][0]['text'].endswith('source detail ')


def test_scan_pages_have_cost_without_text_and_no_raw_data_in_logs(caplog):
    with pymupdf.open() as doc:
        for _ in range(4):
            doc.new_page()
        part = {'type': 'file', 'file': {'file_data': 'data:application/pdf;base64,' + base64.b64encode(doc.tobytes()).decode()}}
    assert attachment_cost(part) == (4096, 1)
    assert part['file']['file_data'] not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['pdf', 'image', 'text', 'markdown'])
async def test_stream_sends_original_attachment_without_internal_metadata(kind):
    from services.conversation.stream import ConversationStreamService
    part = attachment(kind)
    messages = OrchestrationVisualMixin._attach_to_latest_user_message([
        {'role': 'user', 'content': 'First question'},
        {'role': 'assistant', 'content': 'First reply'},
        {'role': 'user', 'content': 'Explain this attachment'},
    ], [part])

    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Grounded answer', tool_calls=None))])
    create = AsyncMock(return_value=response())
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    output = ''.join([chunk async for chunk in service.stream(
        user_id='test', conversation_id='test', last_user_msg='Explain this attachment', messages=messages,
        force_think=False, max_tokens=3200, temperature=0.1, top_p=0.9, repetition_penalty=1,
        request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
    )])
    assert 'Grounded answer' in output
    assert create.await_count == 1
    import json
    sent = json.loads(json.dumps(create.call_args.kwargs['messages']))
    assert sent[-1]['content'][-1] == part


@pytest.mark.asyncio
async def test_stream_sends_attachment_above_legacy_allowance(monkeypatch):
    from services.conversation.stream import ConversationStreamService
    monkeypatch.setattr(settings, 'conversation_attachment_tokens', 1)
    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Grounded answer', tool_calls=None))])
    create = AsyncMock(return_value=response())
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    output = ''.join([chunk async for chunk in service.stream(
        user_id='test', conversation_id='test', last_user_msg='Explain',
        messages=[{'role': 'user', 'content': [AttachmentPart(attachment('text'))]}],
        force_think=False, max_tokens=3200, temperature=0.1, top_p=0.9, repetition_penalty=1,
        request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
    )])
    assert 'Grounded answer' in output
    assert create.await_count == 1
    assert create.call_args.kwargs['messages'][-1]['content'][0]['text'] == attachment('text')['text']


@pytest.mark.asyncio
@pytest.mark.parametrize('paper_source', ['dense', 'a_mem'])
async def test_paper_reaches_provider_without_payload_changes(paper_source, caplog, monkeypatch):
    # Match the Python 3.10 API surface used by the Render deployment.
    import asyncio
    caplog.set_level('INFO')
    from services.conversation.stream import ConversationStreamService
    monkeypatch.delattr(asyncio, 'timeout', raising=False)
    with pymupdf.open() as doc:
        for _ in range(30):
            page = doc.new_page()
            for line in range(46):
                page.insert_text((40, 40 + line * 16),
                                 'Research findings and methods are explained with supporting evidence here.')
        raw = doc.tobytes()
    if paper_source == 'a_mem':
        raw = (Path(__file__).resolve().parents[2] / 'docs/paper/memory_work/A-MEM_Agentic Memory for LLM Agents.pdf').read_bytes()
    part = {'type': 'file', 'file': {'filename': 'paper.pdf', 'file_data':
            'data:application/pdf;base64,' + base64.b64encode(raw).decode()}}
    if paper_source == 'dense':
        assert attachment_cost(part)[0] > 131072
    async def response():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Paper explained', tool_calls=None))])
    create = AsyncMock(return_value=response())
    service = ConversationStreamService(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), None)
    output = ''.join([chunk async for chunk in service.stream(
        user_id='test', conversation_id='dense-paper', last_user_msg='Explain',
        messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'Explain'}, part]}],
        force_think=False, max_tokens=3200, temperature=0.1, top_p=0.9, repetition_penalty=1,
        request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
    )])
    assert 'Paper explained' in output
    assert create.await_count == 1
    assert create.call_args.kwargs['messages'][-1]['content'][-1] == part

    assert 'attachment.context_budget conversation_id=dense-paper' in caplog.text
    assert 'excluded_from_chat_budget=True enforcement=provider' in caplog.text
    assert 'history.budget_evaluated conversation_id=dense-paper' in caplog.text
    assert 'compaction_required=False' in caplog.text
    assert 'orchestration.provider_request_started conversation_id=dense-paper' in caplog.text
    assert 'attachment_count=1' in caplog.text
    assert 'orchestration.provider_stream_received conversation_id=dense-paper' in caplog.text
    assert part['file']['file_data'] not in caplog.text
    assert 'Paper explained' not in caplog.text
    assert 'Research findings and methods' not in caplog.text
