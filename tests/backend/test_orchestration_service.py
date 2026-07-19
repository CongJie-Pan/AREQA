import pytest
import json
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from backend.services.orchestration_service import OrchestrationService
from unittest.mock import patch


def test_attaches_multimodal_parts_only_to_latest_user_turn():
    messages = [
        {"role": "user", "content": "先前問題"},
        {"role": "assistant", "content": "先前回答"},
        {"role": "user", "content": "請分析附件"},
    ]
    attachments = [{"type": "file", "file": {"filename": "lesson.pdf", "file_data": "data:application/pdf;base64,AA=="}}]

    result = OrchestrationService._attach_to_latest_user_message(messages, attachments)

    assert result[0]["content"] == "先前問題"
    assert result[-1]["content"] == [
        {"type": "text", "text": "請分析附件"},
        attachments[0],
    ]


def test_attachment_grounding_instruction_forbids_metadata_guessing():
    messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "請分析附件"},
    ]

    result = OrchestrationService._add_attachment_grounding_instruction(messages)

    assert "只能根據實際可讀取的附件內容回答" in result[0]["content"]
    assert "不得根據檔名" in result[0]["content"]
    assert "解析失敗" in result[0]["content"]


@pytest.mark.asyncio
async def test_pdf_stream_uses_openrouter_native_parser(
    mock_router, mock_rag, mock_suggestion, mock_client, caplog
):
    caplog.set_level(logging.INFO)
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)

    async def chunks():
        if False:
            yield None

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "請分析"},
            {"type": "file", "file": {"filename": "lesson.pdf", "file_data": "data:application/pdf;base64,AA=="}},
        ],
    }]

    _ = [event async for event in service._node_llm_stream(
        "u1", "conv", "請分析", messages, False, 100, 0.7, 0.9, 1.0, request
    )]

    kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"]["plugins"] == [
        {"id": "file-parser", "pdf": {"engine": "native"}}
    ]
    assert "orchestration.stream_started" in caplog.text

@pytest.fixture
def mock_router():
    router = AsyncMock()
    return router

@pytest.fixture
def mock_rag():
    rag = AsyncMock()
    return rag

@pytest.fixture
def mock_suggestion():
    suggestion = AsyncMock()
    return suggestion

@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_prompt_assembly_skips_long_term_memory_for_low_information_greeting(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_gum:
        messages = await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="new-conv",
            messages=[{"role": "user", "content": "你好"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="你好",
        )

    system_prompt = messages[0]["content"]
    assert "<retrieved_memory>" not in system_prompt
    assert "<memory>" not in system_prompt
    mock_cold.assert_not_awaited()
    mock_gum.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_assembly_keeps_long_term_memory_for_substantive_query(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="cold context",
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="<memory>gum context</memory>",
    ) as mock_gum:
        messages = await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="react-conv",
            messages=[{"role": "user", "content": "React useEffect dependency array 是什麼？"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="React useEffect dependency array 是什麼？",
        )

    system_prompt = messages[0]["content"]
    assert "<retrieved_memory>" in system_prompt
    assert "<memory>gum context</memory>" in system_prompt
    mock_cold.assert_awaited_once()
    mock_gum.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_newton_question_does_not_claim_verified_understanding(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

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
    ):
        messages = await service._node_prompt_assembly(
            user_id="new-user",
            conversation_id="newton-conversation",
            messages=[{"role": "user", "content": "請教我牛頓第一運動定律。"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="請教我牛頓第一運動定律。",
        )

    system_prompt = messages[0]["content"]
    assert "理解程度視為 unknown" in system_prompt
    assert "使用者目前已理解牛頓第一運動定律" not in system_prompt
    assert "使用者已掌握慣性" not in system_prompt


@pytest.mark.asyncio
async def test_prompt_assembly_skips_cross_conversation_memory_for_health_query(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_gum:
        messages = await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="health-conv",
            messages=[{"role": "user", "content": "血壓 118/77，脈搏 91 正常嗎？"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="血壓 118/77，脈搏 91 正常嗎？",
        )

    assert "<retrieved_memory>" not in messages[0]["content"]
    mock_cold.assert_not_awaited()
    mock_gum.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_assembly_allows_sensitive_recall_when_user_explicitly_requests_it(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="family context",
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ) as mock_gum:
        await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="health-conv",
            messages=[{"role": "user", "content": "請結合昨天家庭壓力的情況回答"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="請結合昨天家庭壓力的情況回答",
        )

    mock_cold.assert_awaited_once()
    mock_gum.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_short_circuits_low_information_greeting_without_llm(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock):
        events = []
        async for event in service.execute(
            [{"role": "user", "content": "你好"}],
            "greeting-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        ):
            events.append(event)

    joined = "".join(events)
    assert "你好，我在。你可以直接告訴我現在想處理什麼。" in joined
    assert "React" not in joined
    assert "useEffect" not in joined
    assert joined.endswith("data: [DONE]\n\n")


@pytest.mark.asyncio
async def test_execute_emits_visible_status_before_memory_work(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()

    store = MagicMock()
    with patch("memory_store.get_global_store", return_value=store), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock):
        stream = service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "latency-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )
        first = await anext(stream)
        second = await anext(stream)
        third = await anext(stream)
        fourth = await anext(stream)
        await stream.aclose()

    assert first.startswith("event: metadata")
    assert second.startswith("event: status")
    assert '"status": "routing"' in second
    assert third.startswith("event: status")
    assert "正在判斷是否需要外部搜尋" in third
    assert fourth.startswith("event: action")
    assert "請解釋 dependency injection" not in fourth
    assert '"reason_code": "USER_DISABLED"' in fourth


@pytest.mark.asyncio
async def test_execute_passes_accumulated_answer_to_suggestions(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    mock_suggestion.generate_suggestions.return_value = []

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "accumulator-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    assert not any(event.startswith("event: accumulator") for event in events)
    assert mock_suggestion.generate_suggestions.await_args.kwargs["answer_text"] == "answer"


@pytest.mark.asyncio
async def test_execute_logs_safe_turn_latency_trace(
    mock_router, mock_rag, mock_suggestion, caplog
):
    caplog.set_level(logging.INFO)
    service = OrchestrationService(mock_router, mock_rag, None, None)
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "trace-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    assert events[-1] == "data: [DONE]\n\n"
    assert "orchestration.turn_trace_completed" in caplog.text
    assert "orchestration.turn_trace_summary" in caplog.text
    assert "time_to_first_answer_ms" in caplog.text
    assert "phase_durations_ms" in caplog.text
    assert "prompt_assembly_started" in caplog.text
    assert "terminal_sent" in caplog.text
    assert "請解釋 dependency injection" not in caplog.text


@pytest.mark.asyncio
async def test_turn_plan_enabled_skips_general_policy_classifier(
    mock_router, mock_rag, mock_client, monkeypatch
):
    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", True)
    monkeypatch.setattr(runtime_config.settings, "enable_policy_classifier_for_general_chat", False)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock) as mock_policy, \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]) as prompt_assembly:
        events = [event async for event in service.execute(
            [{"role": "user", "content": "這部電影的節奏很奇怪"}],
            "turn-plan-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    mock_policy.assert_not_awaited()
    assert prompt_assembly.await_args.kwargs["turn_plan"].route.value == "GENERAL_CHAT"
    assert "data: [DONE]" in events[-1]


@pytest.mark.asyncio
async def test_turn_plan_disabled_keeps_legacy_policy_classifier(
    mock_router, mock_rag, mock_client, monkeypatch
):
    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", False)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL") as mock_policy, \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]) as prompt_assembly:
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "這部電影的節奏很奇怪"}],
            "legacy-turn-plan-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    mock_policy.assert_awaited_once()
    assert prompt_assembly.await_args.kwargs["turn_plan"] is None


@pytest.mark.asyncio
async def test_prompt_assembly_keeps_concurrent_run_contexts_isolated(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    async def assemble(conversation_id, marker):
        return await service._node_prompt_assembly(
            user_id="u1",
            conversation_id=conversation_id,
            messages=[{"role": "user", "content": "同一個問題"}],
            use_rag=False,
            use_web_search=True,
            force_think=False,
            context_results_obj={"source": "web_search"},
            last_user_msg="同一個問題",
            context_prompt=f"<context>{marker}</context>\n",
        )

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
    ):
        first, second = await asyncio.gather(
            assemble("conversation-a", "SOURCE_A"),
            assemble("conversation-b", "SOURCE_B"),
        )

    first_user = next(message["content"] for message in first if message["role"] == "user")
    second_user = next(message["content"] for message in second if message["role"] == "user")
    assert "SOURCE_A" in first_user and "SOURCE_B" not in first_user
    assert "SOURCE_B" in second_user and "SOURCE_A" not in second_user


@pytest.mark.asyncio
async def test_explicit_never_search_mode_overrides_legacy_search_boolean(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()

    async def fail_if_searched(*args, **kwargs):
        raise AssertionError("web search must not run in never mode")
        yield

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"offline"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"offline"}\n\n'

    service._node_perplexity_search = fail_if_searched
    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "搜尋今天最新新聞"}],
            "privacy-conv",
            False,
            True,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
            search_mode="never",
        )]

    assert "offline" in "".join(events)


@pytest.mark.asyncio
async def test_auto_mode_with_attachment_skips_generic_search_and_rag(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()
    captured_messages = []

    async def fail_if_searched(*args, **kwargs):
        raise AssertionError("attachment-first AUTO mode must not use generic retrieval")
        yield

    async def llm_stream(*args, **kwargs):
        captured_messages.extend(args[3])
        yield 'event: accumulator\ndata: {"accumulator":"attachment answer"}\n\n'

    service._node_perplexity_search = fail_if_searched
    service._node_rag_retrieval = fail_if_searched
    service._node_llm_stream = llm_stream
    attachment = {
        "type": "file",
        "file": {"filename": "lesson.pdf", "file_data": "data:application/pdf;base64,AA=="},
    }

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[
             {"role": "system", "content": "base prompt"},
             {"role": "user", "content": "請解釋該 PDF"},
         ]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋該 PDF"}],
            "attachment-conv",
            True,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
            search_mode="auto",
            attachments=[attachment],
        )]

    joined = "".join(events)
    assert "ATTACHMENT_CONTEXT_PRIORITY" in joined
    assert any(
        isinstance(message.get("content"), list) and attachment in message["content"]
        for message in captured_messages
    )
    assert "不得根據檔名" in captured_messages[0]["content"]


@pytest.mark.asyncio
async def test_durable_jobs_suppress_in_process_edf_and_reflection_tasks(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()
    durable_store = MagicMock()
    durable_store.schedule = AsyncMock(return_value="job-1")
    memory_store = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=memory_store), \
         patch("job_store.get_agent_job_store", return_value=durable_store), \
         patch("gum_integration.push_reflection_observation", new_callable=AsyncMock) as reflection, \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock) as edf, \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "durable-conv", False, False, False, 100, 0.7, 0.9, 1.0,
            request, "u1",
        )]
        await asyncio.gather(*tuple(service.post_turn_service._background_tasks))

    assert durable_store.schedule.await_count == 2
    reflection.assert_not_awaited()
    edf.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Router feature bypassed by user request")
async def test_orchestration_routing_deny(mock_router, mock_rag, mock_suggestion, mock_client):
    # Mock the router to DENY
    mock_router.check_query_intent.return_value = {
        "action": "DENY", 
        "refusal_message": "這是數學問題"
    }
    
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    messages = [{"role": "user", "content": "1+1=?"}]
    request = MagicMock()
    
    with patch('backend.services.orchestration_service.push_observation', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock):
        
        events = []
        async for event in service.execute(messages, "test_conv_id", False, False, False, 100, 0.7, 0.9, 1.0, request):
            events.append(event)
            
        assert len(events) >= 2
        assert any("refused" in e for e in events)
        assert any("這是數學問題" in e for e in events)
        assert "data: [DONE]" in events[-1]

@pytest.mark.asyncio
@pytest.mark.skip(reason="Router feature bypassed by user request")
async def test_orchestration_routing_allow(mock_router, mock_rag, mock_suggestion, mock_client):
    # Mock the router to ALLOW
    mock_router.check_query_intent.return_value = {
        "action": "ALLOW"
    }
    
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    messages = [{"role": "user", "content": "紅樓夢"}]
    request = MagicMock()
    
    with patch('backend.services.orchestration_service.push_observation', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy:
         
        mock_policy.return_value = "NORMAL"
        
        events = []
        async for event in service.execute(messages, "test_conv_id", False, False, False, 100, 0.7, 0.9, 1.0, request):
            events.append(event)
            
        # Since we are in Gate 1A, it yields dummy processing and OK messages
        assert any("generating" in e for e in events) or any("status" in e for e in events)
        assert "data: [DONE]" in events[-1]
