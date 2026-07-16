import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.turn_intake_service import TurnIntakeService


@pytest.mark.asyncio
async def test_roleplay_hot_memory_failure_does_not_fail_turn_intake(caplog):
    """A Redis roleplay-state failure must not block response generation."""

    caplog.set_level(logging.INFO)
    store = MagicMock()
    store.update_hot_memory_async = AsyncMock(side_effect=ConnectionError("redis unavailable"))
    ingestion_result = MagicMock()
    ingestion_result.state.value = "working_context_only"
    ingestion_result.reason_code = "operational_state"
    ingestion = MagicMock()
    ingestion.ingest_user_evidence = AsyncMock(return_value=ingestion_result)

    with patch("memory_store.get_global_store", return_value=store), patch(
        "services.compeer_scheduler.set_last_interaction_time",
        new_callable=AsyncMock,
    ), patch(
        "services.memory_ingestion_service.create_memory_ingestion_service",
        return_value=ingestion,
    ):
        result = await TurnIntakeService(client=MagicMock()).process(
            user_id="user-1",
            conversation_id="conversation-1",
            user_message="請你扮演孔子跟我對話",
            run_id="run-1",
        )

    assert result.store_available is True
    assert result.memory_state == "working_context_only"
    assert "orchestration.roleplay_state_failed" in caplog.text
