"""Attachment turns must not spawn parser workers on the answer's critical path.

Production evidence (2026-11-14): three PDFs pushed a 512 MiB Render container to
its cgroup limit; the diagnostic-only inspection subprocess then stalled for its
10-second deadline and the whole answer was rejected as attachment_parse_timeout.
"""
import asyncio
import base64
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pymupdf
import pytest

from services.conversation.attachment_budget import AttachmentPart, attachment_transport_size
from services.conversation.history import prepare_history


def pdf_part(name: str, pages: int) -> dict:
    with pymupdf.open() as doc:
        for index in range(pages):
            doc.new_page().insert_text((40, 40), f'Motivation slide {index}')
        data = doc.tobytes()
    return {'type': 'file', 'file': {'filename': name, 'file_data':
            'data:application/pdf;base64,' + base64.b64encode(data).decode()}}


def test_transport_size_counts_parts_without_decoding():
    pdf = pdf_part('a.pdf', 2)
    image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AAAA'}}
    uploaded_text = AttachmentPart(type='text', text='extracted pdf text')
    messages = [
        {'role': 'system', 'content': 'not an attachment'},
        {'role': 'user', 'content': [{'type': 'text', 'text': 'question text'}, pdf, image, uploaded_text]},
    ]
    count, size = attachment_transport_size(messages)
    assert count == 3
    assert size == len(pdf['file']['file_data']) + len(image['image_url']['url']) + len(uploaded_text['text'])
    assert attachment_transport_size([{'role': 'user', 'content': 'plain'}]) == (0, 0)


@pytest.mark.asyncio
async def test_multiple_pdfs_reach_provider_without_parser_subprocess(monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    async def forbidden_subprocess(*args, **kwargs):
        raise AssertionError('attachment admission must not spawn a parser subprocess')

    monkeypatch.setattr(asyncio, 'create_subprocess_exec', forbidden_subprocess)
    parts = [pdf_part('ch08.pdf', 64), pdf_part('journal.pdf', 42), pdf_part('slides.pdf', 60)]
    messages = [
        {'role': 'system', 'content': 'Answer from the attachments.'},
        {'role': 'user', 'content': [{'type': 'text', 'text': 'Read these three PDFs.'}, *parts]},
    ]
    create = AsyncMock()
    result = await prepare_history(
        messages=messages, tools=[],
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
        user_id='test', conversation_id='three-pdfs', model='test', output_tokens=3200,
        context_tokens=32768,
    )
    assert result.messages[-1]['content'][1:] == parts
    create.assert_not_awaited()
    assert 'attachment.context_budget conversation_id=three-pdfs count=3' in caplog.text
    assert 'attachment.inspection' not in caplog.text
    assert parts[0]['file']['file_data'] not in caplog.text
