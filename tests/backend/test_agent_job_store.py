import asyncio
import json
from unittest.mock import ANY, AsyncMock, patch

import pytest

from backend.job_store import AgentJob, AgentJobStore


class FakeMappings:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class FakeCursor:
    def __init__(self, *, scalar=None, row=None):
        self._scalar = scalar
        self._row = row

    def scalar(self):
        return self._scalar

    def mappings(self):
        return FakeMappings(self._row)


class FakeSession:
    def __init__(self, cursors):
        self.cursors = iter(cursors)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def execute(self, statement, parameters=None):
        self.calls.append((str(statement), parameters))
        return next(self.cursors)


@pytest.mark.asyncio
async def test_schedule_uses_idempotency_conflict_and_returns_job_id():
    store = AgentJobStore()
    store._has_db = AsyncMock(return_value=True)
    store._get_engine = lambda: object()
    session = FakeSession([FakeCursor(scalar="job-1")])

    with patch("backend.job_store.AsyncSession", return_value=session):
        job_id = await store.schedule(
            job_type="edf_evaluation",
            user_id="user-1",
            payload={"messages": []},
            idempotency_key="run-1:edf",
        )

    assert job_id == "job-1"
    assert "ON CONFLICT (idempotency_key)" in session.calls[0][0]
    assert json.loads(session.calls[0][1]["payload"]) == {"messages": []}


@pytest.mark.asyncio
async def test_claim_next_uses_skip_locked_and_returns_typed_job():
    store = AgentJobStore()
    store._has_db = AsyncMock(return_value=True)
    store._get_engine = lambda: object()
    session = FakeSession([FakeCursor(row={
        "job_id": "job-1",
        "job_type": "reflection_observation",
        "user_id": "user-1",
        "payload": {"text": "hello"},
        "attempt_count": 1,
    })])

    with patch("backend.job_store.AsyncSession", return_value=session):
        job = await store.claim_next("worker-1")

    assert job == AgentJob("job-1", "reflection_observation", "user-1", {"text": "hello"}, 1)
    assert "FOR UPDATE SKIP LOCKED" in session.calls[0][0]


@pytest.mark.asyncio
async def test_fail_transitions_to_terminal_after_max_attempts():
    store = AgentJobStore()
    store._has_db = AsyncMock(return_value=True)
    store._get_engine = lambda: object()
    session = FakeSession([FakeCursor()])
    job = AgentJob("job-1", "edf_evaluation", "user-1", {}, 3)

    with patch("backend.job_store.AsyncSession", return_value=session):
        await store.fail(job, "worker-1", "TIMEOUT", max_attempts=3)

    assert session.calls[0][1]["status"] == "terminal_failed"
    assert session.calls[0][1]["error_code"] == "TIMEOUT"


@pytest.mark.asyncio
async def test_schedule_returns_none_without_database():
    store = AgentJobStore()
    store._has_db = AsyncMock(return_value=False)
    assert await store.schedule(
        job_type="edf_evaluation",
        user_id="user-1",
        payload={},
        idempotency_key="run-1:edf",
    ) is None


@pytest.mark.asyncio
async def test_worker_handles_memory_compaction():
    from backend.job_store import agent_job_worker, get_agent_job_store

    store = get_agent_job_store()
    
    # Mock claim_next to return a memory_compaction job once, then raise CancelledError
    job = AgentJob(
        job_id="job-mc",
        job_type="memory_compaction",
        user_id="user-1",
        payload={},
        attempt_count=1
    )
    
    call_count = 0
    async def mock_claim_next(worker_id):
        nonlocal call_count
        if call_count == 0:
            call_count += 1
            return job
        raise asyncio.CancelledError()
        
    store.claim_next = AsyncMock(side_effect=mock_claim_next)
    store.complete = AsyncMock()
    
    with patch("backend.job_store.get_agent_job_store", return_value=store), \
         patch("gum_integration.run_compaction", new_callable=AsyncMock) as mock_run_compaction:
        
        try:
            await agent_job_worker()
        except asyncio.CancelledError:
            pass
            
        mock_run_compaction.assert_awaited_once_with("user-1")
        store.complete.assert_awaited_once_with("job-mc", ANY)
