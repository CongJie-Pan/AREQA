"""Local-only E2E ASGI app: real chat routes, orchestration and tools; fake external providers.

Never deploy this app. Authentication, cloud memory/sync and provider responses
are test boundaries. Scenario control is isolated here, not in production routes.
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ['OPENROUTER_API_KEY'] = 'e2e-provider-is-replaced'
from fastapi import FastAPI
from fastapi.responses import Response, StreamingResponse
from app.routes.stream import router as chat_router
from app.routes.generated_images import router as image_router
from auth import get_optional_current_user, get_current_user
from services.generated_image_service import GeneratedImage
from services.conversation import image_generation
from services import orchestration_service as orchestration
from app import prompts
from services.query_policy_service import default_response_policy
from services.post_turn_service import PostTurnService
import memory_store

from config import settings

visual_defaults = (settings.enable_visual_preflight, settings.enable_pdf_attachment_visuals)

state = {'scenario': 'text', 'generated': 0, 'references': 0, 'cancelled': 0, 'uploads': 0}


class ContextProviderError(Exception):
    def __init__(self, status_code=400):
        super().__init__('controlled provider failure')
        self.status_code = status_code
        self.body = {'error': {'code': 'context_length_exceeded' if status_code == 400 else 'rate_limit_exceeded'}}


class Provider:
    def __init__(self, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        if not kwargs.get('stream'):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
        if state['scenario'].startswith('context_'):
            state['main_calls'] += 1
            state['message_counts'].append(len(kwargs['messages']))
            serialized = json.dumps(kwargs['messages'])
            state['tail_preserved'].append('ATTACHMENT_END_MARKER' in serialized)
            state['native_attachment'].append('file_data' in serialized or 'image_url' in serialized)
            if state['scenario'] == 'context_repeat' or (state['scenario'] == 'context_retry' and state['main_calls'] == 1):
                raise ContextProviderError()
            if state['scenario'] == 'context_rate_limit':
                raise ContextProviderError(429)
        async def chunks():
            if state['scenario'].startswith('context_'):
                content = '部分回答' if state['scenario'] == 'context_partial' else '附件分析完成'
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])
                if state['scenario'] == 'context_partial':
                    raise ContextProviderError()
                return
            state['uploads'] = sum(isinstance(item.get('content'), list) for item in kwargs['messages'])
            if state['scenario'] in {'text', 'attachment'}:
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='附件分析完成' if state['scenario'] == 'attachment' else '一般文字回答', tool_calls=None))])
            else:
                import json
                mixed = state['scenario'] in {'mixed', 'mixed_failure'}
                payload = json.dumps({'prompt': '繁體中文效果量教學圖', 'presentation': 'text_and_image' if mixed else 'image_only',
                                      'explanation': '統計顯著不代表效果重要。' if mixed else ''}, ensure_ascii=False)
                for name, args in [('generate_', payload[:15]), ('image', payload[15:])]:
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, tool_calls=[
                        SimpleNamespace(index=0, id='e2e_image', function=SimpleNamespace(name=name, arguments=args))]))])
        return chunks()


async def generate(*args, **kwargs):
    state['generated'] += 1
    try:
        await asyncio.sleep(2.5 if state['scenario'] == 'cancel' else 0.8)
        if state['scenario'] in {'failure', 'mixed_failure'}:
            raise RuntimeError('controlled provider failure')
        if kwargs.get('on_state'):
            kwargs['on_state']('storing')
        await asyncio.sleep(0.2)
        return GeneratedImage('/__test/image.png', 'fixture', '效果量教學圖', None, False,
                              storage_path=f"users/e2e-user/{kwargs['conversation_id']}/{kwargs['image_id']}.png")
    except asyncio.CancelledError:
        state['cancelled'] += 1
        raise


async def reference(*args, **kwargs):
    state['references'] += 1
    return 'Effects and sample sizes from the uploaded source.'


image_generation.generate_teaching_image = generate
image_generation.prepare_image_reference = reference
image_generation.consume_image_quota = AsyncMock(return_value=True)
memory_store.get_global_store = lambda: None
orchestration.get_hot_memory_snapshot = AsyncMock(return_value='')
orchestration.query_cold_memory_for_context = AsyncMock(return_value='')
orchestration.query_memory_for_context = AsyncMock(return_value='')
orchestration.classify_dialogue_policy = AsyncMock(return_value=default_response_policy())
PostTurnService.queue_post_turn_work = lambda *args, **kwargs: None
sys.modules['main'] = SimpleNamespace(AsyncOpenAI=Provider, router_service=AsyncMock(),
    init_rag_service=lambda: None, suggestion_service=SimpleNamespace(generate_suggestions=AsyncMock(return_value=[])),
    **{name: getattr(prompts, name) for name in ('SYSTEM_PROMPT_FORCE_THINK', 'SYSTEM_PROMPT_NORMAL', 'SYSTEM_PROMPT_WITH_RAG', 'SYSTEM_PROMPT_WITH_RAG_THINK', 'EVIDENCE_MODE_OVERLAYS', 'LEARNING_TECHNIQUE_OVERLAYS', 'RESPONSE_POLICY_OVERLAYS')})
app = FastAPI()
app.include_router(chat_router)
app.include_router(image_router)
app.dependency_overrides[get_optional_current_user] = lambda: 'e2e-user'
app.dependency_overrides[get_current_user] = lambda: 'e2e-user'


@app.post('/__test/scenario')
async def scenario(payload: dict):
    state.update(scenario=payload['scenario'], generated=0, references=0, cancelled=0, uploads=0,
                 main_calls=0, message_counts=[], tail_preserved=[], native_attachment=[])
    # Disable only optional visual enrichment; parsing and context inspection stay real.
    context_test = payload['scenario'].startswith('context_')
    settings.enable_visual_preflight = False if context_test else visual_defaults[0]
    settings.enable_pdf_attachment_visuals = False if context_test else visual_defaults[1]
    return state


@app.get('/__test/state')
async def counters():
    return state


@app.get('/__test/image.png')
async def image():
    from io import BytesIO
    from PIL import Image
    output = BytesIO()
    Image.new('RGB', (400, 200), '#63b5a0').save(output, format='PNG')
    return Response(output.getvalue(), media_type='image/png')


@app.post('/api/title')
async def title():
    return StreamingResponse(iter(['data: {"content":"效果量教學"}\n\n', 'data: [DONE]\n\n']), media_type='text/event-stream')


@app.get('/__test/document.pdf')
async def document():
    import fitz
    import random
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Sample size and effect size.')
        pdf.embfile_add('padding.bin', random.Random(42).randbytes(400_000))
        return Response(pdf.tobytes(), media_type='application/pdf')
