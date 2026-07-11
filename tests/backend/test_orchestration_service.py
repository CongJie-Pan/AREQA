import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from backend.services.orchestration_service import OrchestrationService
from unittest.mock import patch

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
