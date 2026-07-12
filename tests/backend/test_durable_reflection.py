from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import gum_integration


@pytest.mark.asyncio
async def test_session_reflection_is_persisted_when_job_store_is_available():
    store = MagicMock()
    store.schedule = AsyncMock(return_value="job-1")
    gum_integration.interaction_counts["user-1"] = 20
    gum_integration.importance_sums["user-1"] = 100

    with patch("job_store.get_agent_job_store", return_value=store), patch(
        "backend.gum_integration.run_reflection", new_callable=AsyncMock
    ) as reflection:
        job_id = await gum_integration.schedule_session_reflection(
            "user-1", conversation_id="conversation-1"
        )
        await __import__("asyncio").sleep(0)

    assert job_id == "job-1"
    assert store.schedule.await_args.kwargs["job_type"] == "session_reflection"
    reflection.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_reflection_falls_back_without_durable_database():
    store = MagicMock()
    store.schedule = AsyncMock(return_value=None)

    with patch("job_store.get_agent_job_store", return_value=store), patch(
        "backend.gum_integration.run_reflection", new_callable=AsyncMock
    ) as reflection:
        await gum_integration.schedule_session_reflection("user-2")
        await __import__("asyncio").sleep(0)

    reflection.assert_awaited_once_with("user-2", conversation_id="")


@pytest.mark.asyncio
async def test_compaction_is_persisted_when_job_store_is_available():
    store = MagicMock()
    store.schedule = AsyncMock(return_value="job-2")
    gum_integration.interaction_counts["user-3"] = 7
    gum_integration.importance_sums["user-3"] = 30

    with patch("job_store.get_agent_job_store", return_value=store), patch(
        "backend.gum_integration.run_compaction", new_callable=AsyncMock
    ) as compaction:
        job_id = await gum_integration.schedule_compaction("user-3")
        await __import__("asyncio").sleep(0)

    assert job_id == "job-2"
    assert store.schedule.await_args.kwargs["job_type"] == "memory_compaction"
    compaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_compaction_falls_back_without_durable_database():
    store = MagicMock()
    store.schedule = AsyncMock(return_value=None)

    with patch("job_store.get_agent_job_store", return_value=store), patch(
        "backend.gum_integration.run_compaction", new_callable=AsyncMock
    ) as compaction:
        await gum_integration.schedule_compaction("user-4")
        await __import__("asyncio").sleep(0)

    compaction.assert_awaited_once_with("user-4")
