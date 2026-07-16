from unittest.mock import AsyncMock, patch

import pytest

from backend.mailbox_store import MailboxStore, _release_owned_lock


class FakeCursor:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value

    def fetchone(self):
        return self.value if isinstance(self.value, tuple) else None


class FakeSession:
    def __init__(self, value):
        self.value = value
        self.statement = None
        self.parameters = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def execute(self, statement, parameters):
        self.statement = str(statement)
        self.parameters = parameters
        return FakeCursor(self.value)


@pytest.mark.asyncio
async def test_claim_delayed_task_uses_atomic_lease_transition():
    store = MailboxStore()
    store._has_db = AsyncMock(return_value=True)
    store._get_engine = lambda: object()
    session = FakeSession("task-1")

    with patch("backend.mailbox_store.AsyncSession", return_value=session):
        claimed = await store.claim_delayed_task("task-1", "worker-1", lease_seconds=90)

    assert claimed is True
    assert "status = 'claimed'" in session.statement
    assert "lease_expires_at < now()" in session.statement
    assert session.parameters == {
        "task_id": "task-1",
        "worker_id": "worker-1",
        "lease_seconds": 90,
    }


@pytest.mark.asyncio
async def test_claim_delayed_task_rejects_task_owned_by_active_worker():
    store = MailboxStore()
    store._has_db = AsyncMock(return_value=True)
    store._get_engine = lambda: object()

    with patch("backend.mailbox_store.AsyncSession", return_value=FakeSession(None)):
        assert await store.claim_delayed_task("task-1", "worker-2") is False


@pytest.mark.asyncio
async def test_redis_only_claim_remains_backward_compatible():
    store = MailboxStore()
    store._has_db = AsyncMock(return_value=False)
    assert await store.claim_delayed_task("task-1", "worker-1") is True


@pytest.mark.asyncio
async def test_lock_release_is_owner_checked():
    redis = AsyncMock()
    await _release_owned_lock(redis, "lock:task-1", "worker-1")

    redis.eval.assert_awaited_once()
    args = redis.eval.await_args.args
    assert "redis.call('get', KEYS[1]) == ARGV[1]" in args[0]
    assert args[1:] == (1, "lock:task-1", "worker-1")


@pytest.mark.asyncio
async def test_failed_task_records_retryable_or_terminal_transition(caplog):
    store = MailboxStore()
    store._has_db = AsyncMock(return_value=True)
    store._get_engine = lambda: object()
    session = FakeSession(("retryable_failed", 1))

    with patch("backend.mailbox_store.AsyncSession", return_value=session):
        await store.mark_delayed_task_failed(
            "task-1", "worker-1", "ProviderTimeout", max_attempts=3
        )

    assert "retryable_failed" in session.statement
    assert "terminal_failed" in session.statement
    assert session.parameters["error_code"] == "ProviderTimeout"
    assert "mailbox.retryable_failed" in caplog.text


@pytest.mark.asyncio
async def test_terminal_failure_emits_distinct_event(caplog):
    store = MailboxStore()
    store._has_db = AsyncMock(return_value=True)
    store._get_engine = lambda: object()

    with patch(
        "backend.mailbox_store.AsyncSession",
        return_value=FakeSession(("terminal_failed", 3)),
    ):
        status = await store.mark_delayed_task_failed(
            "task-2", "worker-1", "ProviderRejected", max_attempts=3
        )

    assert status == "terminal_failed"
    assert "mailbox.terminal_failed" in caplog.text
