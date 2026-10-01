"""Regressions for generation as a chat tool rather than a mandatory router."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.conversation.stream import ConversationStreamService
from services.conversation import image_generation as image_tool
from services.generated_image_service import GeneratedImage
from tools import ToolRegistry


@pytest.fixture
def chat_request():
    return SimpleNamespace(is_disconnected=AsyncMock(return_value=False))


@pytest.fixture
def provider(monkeypatch):
    quota = AsyncMock(return_value=True)
    generate = AsyncMock(return_value=GeneratedImage('https://example.com/private.png', 'flare', '教學圖', None, False))
    reference = AsyncMock(return_value='bounded attachment facts')
    monkeypatch.setattr(image_tool, 'consume_image_quota', quota)
    monkeypatch.setattr(image_tool, 'generate_teaching_image', generate)
    monkeypatch.setattr(image_tool, 'prepare_image_reference', reference)
    return SimpleNamespace(quota=quota, generate=generate, reference=reference)


async def collect(chat_request, **kwargs):
    defaults = dict(arguments=json.dumps({'prompt': '教學圖：效果量'}), user_id='u1', conversation_id='conv1',
                    language='zh-TW', attachments=[], latest_request='請根據附件產圖', request=chat_request)
    defaults.update(kwargs)
    return [block async for block in image_tool.stream_generated_image(**defaults) if block.get("type") == "image_block"]


@pytest.mark.asyncio
async def test_pending_then_generated_block_retains_storage_contract(chat_request, provider):
    blocks = await collect(chat_request)
    assert blocks[0]['status'] == 'pending'
    assert blocks[-1]['imageUrl'].endswith('private.png')
    assert blocks[-1]['slotId'] == blocks[0]['slotId']
    assert blocks[-1]['provider'] == 'generated_image'
    provider.quota.assert_awaited_once_with('u1')
    assert provider.generate.call_args.kwargs['language'] == 'zh-TW'
    assert provider.generate.call_args.args[0] == '教學圖：效果量'


@pytest.mark.asyncio
async def test_validated_attachments_are_prepared_only_after_tool_selection(chat_request, provider):
    attachments = [object()]
    await collect(chat_request, attachments=attachments)
    assert provider.reference.call_args.args[0] is attachments
    assert provider.generate.call_args.kwargs['reference_brief'] == 'bounded attachment facts'


@pytest.mark.asyncio
@pytest.mark.parametrize('arguments', ['invalid json', '{}', '{"prompt": "x"}', json.dumps({'prompt': 'x' * 1801})])
async def test_invalid_tool_arguments_do_not_spend_quota(chat_request, provider, arguments):
    blocks = await collect(chat_request, arguments=arguments)
    assert blocks[-1]['status'] == 'error'
    provider.generate.assert_not_awaited()
    provider.quota.assert_not_awaited()


@pytest.mark.asyncio
async def test_anonymous_tool_call_never_spends(chat_request, provider):
    blocks = await collect(chat_request, user_id='guest:ephemeral')
    assert blocks[-1]['status'] == 'error'
    provider.quota.assert_not_awaited()


@pytest.mark.asyncio
async def test_quota_failure_and_provider_failure_end_loading(chat_request, provider):
    provider.quota.return_value = False
    assert (await collect(chat_request))[-1]['status'] == 'error'
    provider.generate.assert_not_awaited()
    provider.quota.return_value = True
    provider.generate.side_effect = RuntimeError('private provider details')
    blocks = await collect(chat_request)
    assert blocks[0]['status'] == 'pending'
    assert blocks[-1]['status'] == 'error'
    assert 'private provider details' not in json.dumps(blocks)


@pytest.mark.asyncio
async def test_disconnect_cancels_provider_and_never_emits_late_result(chat_request, provider):
    started, cancelled = asyncio.Event(), asyncio.Event()
    async def slow_provider(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    provider.generate.side_effect = slow_provider
    chat_request.is_disconnected.side_effect = lambda: started.is_set()
    blocks = await collect(chat_request)
    assert len(blocks) == 1 and blocks[0]['status'] == 'pending'
    assert cancelled.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize('tool_selected', [False, True])
async def test_main_chat_model_owns_operation_without_classifier(chat_request, provider, tool_selected):
    async def chunks():
        if tool_selected:
            for name, args in [('generate_', '{"prompt":'), ('image', '"產生教學圖"}')]:
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[
                    SimpleNamespace(index=0, function=SimpleNamespace(name=name, arguments=args))]))])
        else:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='這是文字分析', tool_calls=None))])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=chunks())
    service = ConversationStreamService(client, ToolRegistry())
    events = [event async for event in service.stream(user_id='u1', conversation_id='conv1',
        last_user_msg='請解釋這張圖或依需求產圖', messages=[{'role': 'user', 'content': 'same input'}],
        force_think=False, max_tokens=100, temperature=0.7, top_p=0.9, repetition_penalty=1,
        request=chat_request, image_attachments=[object()], interface_language='zh-TW')]
    payload = json.loads(events[-1].split('data: ', 1)[1])
    assert client.chat.completions.create.await_count == 1
    assert any(tool['function']['name'] == 'generate_image' for tool in client.chat.completions.create.call_args.kwargs['tools'])
    if tool_selected:
        assert payload['accumulator'] == ''
        assert payload['generated_blocks'][0]['imageUrl']
        provider.generate.assert_awaited_once()
    else:
        assert payload['accumulator'] == '這是文字分析'
        assert payload['generated_blocks'] == []
        provider.generate.assert_not_awaited()
        provider.reference.assert_not_awaited()


@pytest.mark.asyncio
async def test_contextual_drawing_spec_is_not_truncated_by_long_source(chat_request, provider):
    source = '長篇教學內容' * 1000 + '最後需要呈現批判精神'
    specification = '教學圖需呈現統計限制、效果量，以及最後的批判精神'
    await collect(chat_request, latest_request=source, arguments=json.dumps({'prompt': specification}))
    assert provider.generate.call_args.args[0] == specification


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [False, True])
async def test_mixed_tool_preserves_analysis_and_sse_identity(chat_request, provider, failure):
    payload = json.dumps({'prompt': '教學圖片', 'presentation': 'text_and_image', 'explanation': '分析結果', 'reference': 'none'})
    if failure:
        provider.generate.side_effect = RuntimeError('provider down')
    async def chunks():
        if failure:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='Here is the diagram explanation.', tool_calls=None))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[
            SimpleNamespace(index=0, id='mixed_call', function=SimpleNamespace(name='generate_image', arguments=payload))]))])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=chunks())
    service = ConversationStreamService(client, ToolRegistry())
    events = [event async for event in service.stream(user_id='u1', conversation_id='conv1', last_user_msg='先分析再產圖',
        messages=[], force_think=False, max_tokens=100, temperature=0.7, top_p=0.9, repetition_penalty=1, request=chat_request)]
    final = json.loads(events[-1].split('data: ', 1)[1])
    assert final['accumulator'] == ('' if failure else '分析結果')
    if not failure:
        assert final['generated_blocks'][0] == {'type': 'paragraph', 'text': '分析結果'}
    block_events = [json.loads(event.split('data: ', 1)[1]) for event in events if event.startswith('event: answer_blocks')]
    image_index = 0 if failure else 1
    slot_id = final['generated_blocks'][image_index]['slotId']
    assert all(blocks[-1]['slotId'] == slot_id for blocks in block_events)
    assert slot_id != 'mixed_call'
    assert '"tool_call_id": "mixed_call"' in ''.join(events)
    assert ('event: tool_state' in ''.join(events))
    if failure:
        assert len(final['generated_blocks']) == 1
        assert final['generated_blocks'][0]['status'] == 'error'
        assert final['generated_blocks'][0]['caption'] == 'IMAGE_GENERATION_FAILED'
        assert 'Here is the diagram explanation.' not in json.dumps(final)


@pytest.mark.asyncio
async def test_storage_ids_are_server_owned_even_when_provider_call_ids_repeat(chat_request, provider):
    first = await collect(chat_request, tool_call_id='../provider/call')
    second = await collect(chat_request, tool_call_id='../provider/call')
    assert first[-1]['imageUrl'] and second[-1]['imageUrl']
    assert first[-1]['slotId'] != second[-1]['slotId']
    assert image_tool.SAFE_ID.fullmatch(first[-1]['slotId'])
    assert provider.generate.call_args.kwargs['image_id'] == second[-1]['slotId']


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [
    {'prompt': 'valid prompt', 'user_id': 'someone-else'},
    {'prompt': 'valid prompt', 'reference_image_id': '../private'},
    {'prompt': 'valid prompt', 'reference': 'current_attachments'},
    {'prompt': 'valid prompt', 'presentation': 'unknown'},
])
async def test_invalid_context_and_reference_never_reach_paid_provider(chat_request, provider, payload):
    blocks = await collect(chat_request, arguments=json.dumps(payload))
    assert blocks[-1]['status'] == 'error'
    provider.generate.assert_not_awaited()
    provider.quota.assert_not_awaited()


@pytest.mark.asyncio
async def test_historical_image_reference_is_loaded_only_with_authenticated_scope(chat_request, provider, monkeypatch):
    from services.attachments.storage import AttachmentImageStorageService
    download = AsyncMock(return_value=b'private image bytes')
    monkeypatch.setattr(AttachmentImageStorageService, 'download_generated_image', download)
    await collect(chat_request, arguments=json.dumps({'prompt': '修改上圖標題', 'reference': 'conversation_image', 'reference_image_id': 'previous-image'}))
    download.assert_awaited_once_with(user_id='u1', conversation_id='conv1', image_id='previous-image')
    assert provider.reference.call_args.args[0][0].media_type == 'image/png'
    assert provider.generate.call_args.kwargs['reference_brief'] == 'bounded attachment facts'
    download.return_value = None
    provider.generate.reset_mock()
    blocks = await collect(chat_request, arguments=json.dumps({'prompt': '修改其他對話的圖片', 'reference': 'conversation_image', 'reference_image_id': 'other-image'}))
    assert blocks[-1]['status'] == 'error'
    provider.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_image_api_uses_same_handler_and_charges_once(provider):
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.routes.generated_images import router
    from auth import get_current_user
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: 'u1'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/api/v1/images/generate', json={'prompt': '產生教學圖', 'conversation_id': 'conv1'})
    assert response.status_code == 200
    assert response.json()['block']['provider'] == 'generated_image'
    provider.quota.assert_awaited_once_with('u1')
    provider.generate.assert_awaited_once()
