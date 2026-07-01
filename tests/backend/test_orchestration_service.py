import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from backend.services.orchestration_service import OrchestrationService

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
async def test_orchestration_routing_deny(mock_router, mock_rag, mock_suggestion, mock_client):
    # Mock the router to DENY
    mock_router.check_query_intent.return_value = {
        "action": "DENY", 
        "refusal_message": "這是數學問題"
    }
    
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    messages = [{"role": "user", "content": "1+1=?"}]
    request = MagicMock()
    
    events = []
    async for event in service.execute(messages, False, False, 100, 0.7, 0.9, 1.0, request):
        events.append(event)
        
    assert len(events) >= 2
    assert "refused" in events[0]
    assert "這是數學問題" in events[0]
    assert "data: [DONE]" in events[-1]

@pytest.mark.asyncio
async def test_orchestration_routing_allow(mock_router, mock_rag, mock_suggestion, mock_client):
    # Mock the router to ALLOW
    mock_router.check_query_intent.return_value = {
        "action": "ALLOW"
    }
    
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    messages = [{"role": "user", "content": "紅樓夢"}]
    request = MagicMock()
    
    events = []
    async for event in service.execute(messages, False, False, 100, 0.7, 0.9, 1.0, request):
        events.append(event)
        
    # Since we are in Gate 1A, it yields dummy processing and OK messages
    assert any("processing" in e for e in events)
    assert any("Orchestrator OK" in e for e in events)
    assert "data: [DONE]" in events[-1]
