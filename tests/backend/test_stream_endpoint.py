import pytest
from httpx import AsyncClient, ASGITransport
import json
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Import the FastAPI app
from backend.main import app, get_current_user, get_optional_current_user
from backend.services.orchestration.prompting import OrchestrationPromptingMixin


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_user] = lambda: "default_user"
    app.dependency_overrides[get_optional_current_user] = lambda: "default_user"
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_optional_current_user, None)


@pytest.fixture(autouse=True)
def isolate_stream_memory_dependencies():
    """Stream contract tests must not reuse event-loop-bound global clients."""
    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.MemoryQueryTool.execute",
        new_callable=AsyncMock,
        return_value=MagicMock(content={"cold": "", "working": ""}),
    ), patch("memory_store.get_global_store", return_value=None):
        yield

class MockRagChunk:
    def __init__(self, text, score, chunk_id):
        self.text = text
        self.score = score
        self.chunk_id = chunk_id
        self.source = "test_source"

class MockRagResults:
    def __init__(self):
        self.final_results = [
            MockRagChunk("Document content here", 0.95, "test_doc_01")
        ]
        self.highest_score = 0.95


@pytest.mark.asyncio
async def test_stream_wrapper_emits_done_when_orchestrator_ends_early():
    class EarlyExitOrchestrator:
        def execute(self, **_kwargs):
            async def events():
                yield "event: status\ndata: {}\n\n"
            return events()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=EarlyExitOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/stream",
                json={"messages": [{"role": "user", "content": "測試"}]},
            )

    assert response.status_code == 200
    assert response.text.count("data: [DONE]") == 1


@pytest.mark.asyncio
async def test_stream_wrapper_emits_done_after_orchestrator_error():
    class FailingOrchestrator:
        def execute(self, **_kwargs):
            async def events():
                yield "event: status\ndata: {}\n\n"
                raise RuntimeError("test stream failure")
            return events()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=FailingOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/stream",
                json={"messages": [{"role": "user", "content": "測試"}]},
            )

    assert response.status_code == 200
    assert '"error": "stream_failed"' in response.text
    assert response.text.count("data: [DONE]") == 1


@pytest.mark.asyncio
async def test_stream_endpoint_forwards_voice_response_mode_to_orchestrator():
    captured = {}

    class VoiceModeOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=VoiceModeOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/stream",
                json={
                    "messages": [{"role": "user", "content": "請用語音說明"}],
                    "response_mode": "voice",
                },
            )

    assert response.status_code == 200
    assert captured["response_mode"] == "voice"


@pytest.mark.asyncio
async def test_stream_endpoint_forwards_english_tutor_profile_to_orchestrator():
    captured = {}

    class TutorProfileOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=TutorProfileOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/stream",
                json={
                    "messages": [{"role": "user", "content": "Help me analyze Macbeth"}],
                    "tutor_profile": "english",
                },
            )

    assert response.status_code == 200
    assert captured["tutor_profile"] == "english"


@pytest.mark.asyncio
async def test_english_voice_reuses_uploaded_transcript_from_backend(monkeypatch):
    captured = {}

    class TutorOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    from services import speaking_material_service

    async def saved_material(user_id, conversation_id):
        assert user_id == "default_user"
        assert conversation_id == "conv-speaking"
        return {"title": "dialogue.txt", "text": "Student: The library should stay open.", "truncated": False}

    monkeypatch.setattr(speaking_material_service, "load_material", saved_material)
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=TutorOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/v1/stream", json={
                "messages": [{"role": "user", "content": "依逐字稿陪我練托福口說"}],
                "conversation_id": "conv-speaking",
                "tutor_profile": "english",
                "response_mode": "voice",
                "speaking_practice": True,
            })

    assert response.status_code == 200
    assert captured["attachments"][0]["type"] == "text"
    assert "The library should stay open" in captured["attachments"][0]["text"]


@pytest.mark.asyncio
async def test_english_voice_asks_for_source_when_transcript_is_unavailable(monkeypatch):
    from services import speaking_material_service

    monkeypatch.setattr(speaking_material_service, "load_material", AsyncMock(return_value=None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/stream", json={
            "messages": [{"role": "user", "content": "我給你了一個對話的逐字稿，想練習托福口說"}],
            "conversation_id": "conv-no-source",
            "tutor_profile": "english",
            "response_mode": "voice",
            "speaking_practice": True,
        })

    assert response.status_code == 200
    assert "我還沒有讀到逐字稿內容" in response.text
    assert "data: [DONE]" in response.text


@pytest.mark.asyncio
async def test_english_voice_finds_prior_pasted_dialogue_after_tag_switch(monkeypatch):
    captured = {}

    class TutorOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    from services import speaking_material_service

    save = AsyncMock(return_value=True)
    monkeypatch.setattr(speaking_material_service, "save_material", save)
    dialogue = (
        "Student: I think the campus library should stay open longer because we need a quiet place to study.\n"
        "Professor: What is the main reason students would use it at night?"
    )
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=TutorOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/v1/stream", json={
                "messages": [
                    {"role": "user", "content": dialogue},
                    {"role": "assistant", "content": "What would you like to practice?"},
                    {"role": "user", "content": "依逐字稿陪我練口說"},
                ],
                "conversation_id": "conv-pasted",
                "tutor_profile": "english",
                "response_mode": "voice",
                "speaking_practice": True,
            })

    assert response.status_code == 200
    assert dialogue in captured["attachments"][0]["text"]
    save.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_endpoint_falls_back_for_unknown_tutor_profile_json_payload():
    captured = {}

    class TutorProfileFallbackOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=TutorProfileFallbackOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/stream",
                json={
                    "messages": [{"role": "user", "content": "Help"}],
                    "tutor_profile": "history",
                },
            )

    assert response.status_code == 200
    assert captured["tutor_profile"] == "general"


def test_voice_response_instruction_forces_speech_safe_plain_text():
    messages = [{"role": "system", "content": "base prompt"}]

    result = OrchestrationPromptingMixin._apply_voice_response_instruction(messages)

    assert result[0]["content"].startswith("base prompt")
    assert "即時語音輸出" in result[0]["content"]
    assert "不要使用 Markdown" in result[0]["content"]
    assert "範圍很廣" in result[0]["content"]
    assert "多個角度" in result[0]["content"]
    assert "先用一句自然口語的澄清問題" in result[0]["content"]
    assert "中文回答一律使用繁體中文" in result[0]["content"]
    assert messages[0]["content"] == "base prompt"

@pytest.mark.asyncio
async def test_sse_streaming_sequence_with_rag():
    # Scenario 1: SSE Streaming sequence with RAG events
    
    def mock_retrieve_with_events(query):
        # Synchronous generator as in the original code
        yield {"type": "status", "status": "searching_dense", "message": "📖 翻閱古籍索引..."}
        yield {"type": "status", "status": "reranking", "message": "⚖️ 比較段落關聯性..."}
        yield {"type": "results", "data": MockRagResults()}
    
    # We patch the rag_service, router_service and suggestion_service instances in the main app
    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service') as mock_suggestion, \
         patch('backend.services.orchestration_service.parse_and_decompose_query', new_callable=AsyncMock) as mock_expand, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'):
        
        mock_expand.return_value = ["賈寶玉是誰？"]
        mock_rag.retrieve_with_events.side_effect = mock_retrieve_with_events
        mock_rag.score_threshold = 0.3
        
        # Mock Router to ALLOW
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        # Mock Suggestions
        mock_suggestion.generate_suggestions = AsyncMock(return_value=["延伸問題1", "延伸問題2", "延伸問題3"])
        
        # We also need to patch AsyncOpenAI so it doesn't try to call HF endpoint
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock()

            # Setup fake streaming completion
            class FakeAsyncIterator:
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    raise StopAsyncIteration

            mock_client.chat.completions.create.return_value = FakeAsyncIterator()
            
            mock_openai.return_value = mock_client
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "賈寶玉是誰？"}],
                    "use_rag": True
                }
                response = await ac.post("/api/v1/stream", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # Check for the sequence of SSE events
                assert "event: metadata" in content
                assert "event: status" in content
                assert "📖 翻閱古籍索引..." in content
                assert "⚖️ 比較段落關聯性..." in content
                assert "event: sources" in content
                assert "test_source" in content
                assert "event: suggestions" in content
                assert "延伸問題1" in content
                assert "data: [DONE]" in content


@pytest.mark.asyncio
async def test_anonymous_chat_can_open_stream_without_authorization():
    """Guest chat is allowed while authenticated-only endpoints remain protected."""
    app.dependency_overrides.pop(get_optional_current_user, None)
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}, clear=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/stream",
                json={"messages": [{"role": "user", "content": "訪客問題"}]},
            )

    assert response.status_code == 200
    assert "data: [DONE]" in response.text


@pytest.mark.asyncio
async def test_stream_endpoint_forwards_multipart_attachment_to_orchestrator():
    captured = {}

    class AttachmentOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    request_data = {
        "messages": json.dumps([{"role": "user", "content": "請閱讀附件"}]),
        "conversation_id": "attachment-conversation",
        "use_rag": "false",
    }
    files = {
        "attachments": ("notes.txt", b"attachment content", "text/plain"),
    }

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=AttachmentOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/v1/stream", data=request_data, files=files)

    assert response.status_code == 200
    assert captured["messages"][-1]["content"] == "請閱讀附件"
    assert captured["attachments"][0]["type"] == "text"


@pytest.mark.asyncio
async def test_stream_endpoint_accepts_complete_multipart_chat_payload():
    captured = {}

    class PayloadOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    request_payload = {
        "messages": [{"role": "user", "content": "請分析附件"}],
        "conversation_id": "complete-payload-conversation",
        "use_rag": True,
        "search_mode": "always",
        "tutor_profile": "english",
    }
    files = {
        "attachments": ("notes.txt", b"attachment content", "text/plain"),
    }

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=PayloadOrchestrator()), \
         patch("services.speaking_material_service.save_material", new_callable=AsyncMock, return_value=True) as save_material:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/stream",
                data={"messages": json.dumps(request_payload)},
                files=files,
            )

    assert response.status_code == 200
    assert captured["conversation_id"] == "complete-payload-conversation"
    assert captured["use_rag"] is True
    assert captured["search_mode"] == "always"
    assert captured["tutor_profile"] == "english"
    assert captured["attachments"][0]["type"] == "text"
    save_material.assert_awaited_once_with(
        "default_user",
        "complete-payload-conversation",
        {"title": "notes.txt", "text": "attachment content", "truncated": False},
    )


@pytest.mark.asyncio
async def test_stream_endpoint_rejects_malformed_multipart_payload():
    files = {
        "attachments": ("notes.txt", b"attachment content", "text/plain"),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/stream",
            data={"messages": "not-json"},
            files=files,
        )

    assert response.status_code == 400

@pytest.mark.asyncio
@pytest.mark.skip(reason="Router feature bypassed by user request")
async def test_gatekeeper_rejection():
    # Test that the Gatekeeper correctly rejects OOD queries in the stream endpoint
    with patch('backend.main.router_service') as mock_router, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval:
        refusal_msg = "這是數學領域的問題呢..."
        mock_router.check_query_intent = AsyncMock(return_value={
            "action": "DENY", 
            "domain": "數學", 
            "refusal_message": refusal_msg
        })
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            req_data = {
                "messages": [{"role": "user", "content": "1+1等於多少？"}],
                "use_rag": False
            }
            response = await ac.post("/api/v1/stream", json=req_data)
            
            assert response.status_code == 200
            content = response.text
            
            # Check that the refusal message is in the content
            assert refusal_msg in content
            
            # Now we yield a 'routing' status immediately, so we should see event: status
            assert "event: status" in content
            assert '"status": "routing"' in content
            assert '"status": "refused"' in content
            
            # Ensure no Metadata events were sent after rejection
            assert "event: metadata" not in content
            assert "data: [DONE]" in content

@pytest.mark.asyncio
async def test_force_think_strips_think_tags_with_spaces():
    # Scenario: The streaming endpoint correctly strips <think> tags even with spaces
    # and doesn't inject pre-filled assistant message for native reasoning models.
    with patch('backend.main.rag_service', None), \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service', None), \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch.dict('os.environ', {'OPENROUTER_API_KEY': 'mock-token'}):
        
        mock_policy.return_value = "NORMAL"
        
        # Mock Router to ALLOW
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock()

            class FakeAsyncIterator:
                def __aiter__(self):
                    self.yielded = False
                    return self
                async def __anext__(self):
                    if not self.yielded:
                        self.yielded = True
                        chunk = MagicMock()
                        chunk.choices = [MagicMock()]
                        chunk.choices[0].delta = MagicMock()
                        chunk.choices[0].delta.content = "這裡有< think >被包含的思考文字< /think >還有正式文字"
                        chunk.choices[0].delta.tool_calls = None
                        chunk.choices[0].delta.reasoning = None
                        chunk.choices[0].delta.reasoning_details = None
                        return chunk
                    raise StopAsyncIteration

            mock_client.chat.completions.create.return_value = FakeAsyncIterator()
            mock_openai.return_value = mock_client
            
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "測試一下"}],
                    "use_rag": False,
                    "force_think": True
                }
                response = await ac.post("/api/v1/stream", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # 目前串流格式保留原始 chunk 內容，至少要能收到模型輸出
                assert "這裡有" in content
                assert "被包含的思考文字" not in content
                assert "還有正式文字" in content
                
                # 確保 backend 不再對 force_think 進行 assistant role 預填
                call_kwargs = mock_client.chat.completions.create.call_args.kwargs
                messages = call_kwargs['messages']
                has_prefill = any(msg.get("role") == "assistant" for msg in messages)
                assert not has_prefill

@pytest.mark.asyncio
async def test_rag_score_threshold_refusal():
    # Test that the system refuses to answer when RAG highest_score is below effective_threshold
    class LowScoreMockRagResults:
        def __init__(self):
            # is_reranked will be False, so effective_threshold is 0.005
            self.final_results = [
                MockRagChunk("Irrelevant document", 0.001, "test_doc_02")
            ]
            self.highest_score = 0.001

    def mock_retrieve_with_events(query):
        yield {"type": "results", "data": LowScoreMockRagResults()}

    with patch('backend.main.rag_service') as mock_rag, \
         patch('backend.main.router_service') as mock_router, \
         patch('backend.main.suggestion_service', None), \
         patch('backend.services.orchestration_service.parse_and_decompose_query', new_callable=AsyncMock) as mock_expand, \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy, \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock) as mock_eval, \
         patch('backend.main.HF_ENDPOINT_URL', 'http://mock-url'), \
         patch('backend.main.HF_TOKEN', 'mock-token'):
        
        mock_expand.return_value = [{"query": "無關", "type": "abstract_concept"}]
        mock_policy.return_value = "NORMAL"
        mock_rag.retrieve_with_events.side_effect = mock_retrieve_with_events
        mock_rag.score_threshold = 0.0
        
        mock_router.check_query_intent = AsyncMock(return_value={"action": "ALLOW", "domain": None, "refusal_message": None})
        
        # We don't even need to mock OpenAI because it shouldn't be called for generation!
        with patch('backend.main.AsyncOpenAI') as mock_openai:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                req_data = {
                    "messages": [{"role": "user", "content": "無關緊要的問題"}],
                    "use_rag": True
                }
                response = await ac.post("/api/v1/stream", json=req_data)
                
                assert response.status_code == 200
                content = response.text
                
                # Check that it returned the exact RAG refusal message
                assert "AREQA查閱了相關文獻，暫時沒能找到與您問題直接相關的內容" in content
                
                # OpenAI generation (stream) should NOT be called
                for call in mock_openai.return_value.chat.completions.create.call_args_list:
                    assert not call.kwargs.get('stream', False)
