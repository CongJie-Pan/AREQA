import pytest
import asyncio
from unittest.mock import patch, MagicMock

from backend.services.orchestration_service import OrchestrationService

@pytest.mark.asyncio
@patch("backend.services.orchestration_service.push_observation")
@patch("services.compeer_scheduler.set_last_interaction_time")
async def test_orchestration_service_execute_user_id(mock_set_last_interaction, mock_push_obs):
    """
    Test that OrchestrationService.execute accepts user_id parameter 
    and does not crash with AttributeError (previously self.user_id).
    """
    router_mock = MagicMock()
    rag_mock = MagicMock()
    suggestion_mock = MagicMock()
    client_mock = MagicMock()

    service = OrchestrationService(
        router_service=router_mock,
        rag_service=rag_mock,
        suggestion_service=suggestion_mock,
        client=client_mock
    )
    
    request_mock = MagicMock()
    request_mock.is_disconnected.return_value = False
    
    messages = [{"role": "user", "content": "Hello"}]
    
    # We just want to get the first event and verify it doesn't crash on user_id
    gen = service.execute(
        messages=messages,
        conversation_id="conv_123",
        use_rag=False,
        use_web_search=False,
        force_think=False,
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.0,
        request=request_mock,
        user_id="test_user_456"
    )
    
    try:
        first_event = await gen.__anext__()
        assert first_event.startswith("event: metadata")
    except StopAsyncIteration:
        pass
    
    # Allow background tasks to run briefly so we can assert if needed
    await asyncio.sleep(0.01)
    
    # Assert that the set_last_interaction_time was scheduled with the passed user_id
    mock_set_last_interaction.assert_called_once()
    args, _ = mock_set_last_interaction.call_args
    assert args[0] == "test_user_456"
