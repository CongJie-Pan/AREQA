"""Search decisions must be correlatable without exposing the query."""
import logging
from types import SimpleNamespace

import pytest
from agents.tutor_agent import TutorAgent
from core import SearchMode
from config import settings
from services.orchestration.routing import plan_search
from services.orchestration.turn_plan import TurnPlanService
from services.orchestration.trace import TurnLatencyTrace


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,expected,reason', [('always', True, 'USER_FORCED'), ('never', False, 'USER_DISABLED')])
async def test_search_decision_logs_effective_mode_reason_and_correlation(caplog, monkeypatch, mode, expected, reason):
    monkeypatch.setattr(settings, 'enable_tutor_shadow_routing', False)
    caplog.set_level(logging.INFO)
    decision, _, _ = await plan_search(
        SimpleNamespace(tutor_agent=TutorAgent(), turn_plan_service=TurnPlanService()),
        last_user_msg='PRIVATE QUESTION',
        run_context=SimpleNamespace(run_id='run-1', conversation_id='chat-1', request_id='search-request-1'),
        trace=TurnLatencyTrace(run_id='run-1', conversation_id='chat-1'),
        effective_search_mode=SearchMode(mode), has_attachments=False,
        auto_routing_enabled=False, use_rag=False, attachments=[],
    )
    assert decision.should_search is expected
    assert 'orchestration.search_decision run_id=run-1 conversation_id=chat-1 request_id=search-request-1' in caplog.text
    assert f'effective_search_mode={mode} should_search={expected} reason={reason}' in caplog.text
    assert 'PRIVATE QUESTION' not in caplog.text
