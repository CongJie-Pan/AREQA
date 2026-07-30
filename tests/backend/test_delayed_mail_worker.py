import json
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.mailbox_store import delayed_mail_worker, run_delayed_mail_iteration


class WorkerRedis:
    def __init__(self, task):
        self.key = f"areqa:delayed_mail:{task['user_id']}"
        self.payload = json.dumps(task)
        self.locks = set()

    async def scan(self, **kwargs):
        return 0, [self.key] if self.payload else []

    async def zrangebyscore(self, key, minimum, maximum):
        return [self.payload] if self.payload else []

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.locks:
            return False
        self.locks.add(key)
        return True

    async def zrem(self, key, payload):
        if payload == self.payload:
            self.payload = ""

    async def eval(self, script, count, key, owner):
        self.locks.discard(key)
        return 1


@pytest.mark.asyncio
async def test_reconciled_task_is_delivered_exactly_once(caplog):
    caplog.set_level("INFO")
    task = {
        "task_id": "task-1",
        "user_id": "user-1",
        "sender": "AREQA",
        "content": "safe content",
        "subject": "subject",
    }
    redis = WorkerRedis(task)
    store = AsyncMock()
    store.claim_delayed_task.side_effect = [True, False]
    store.add_mail.return_value = "mail-1"

    with patch("backend.mailbox_store._mailbox_sending_enabled", return_value=True), patch(
        "services.connection_manager.ws_manager.broadcast_mail_alert",
        new_callable=AsyncMock,
    ):
        first = await run_delayed_mail_iteration(redis, store, "worker-1", now=1e12)
        second = await run_delayed_mail_iteration(redis, store, "worker-1", now=1e12)

    assert first == 1
    assert second == 0
    store.add_mail.assert_awaited_once()
    store.mark_delayed_task_delivered.assert_awaited_once_with("task-1", "mail-1")
    assert "mailbox.claimed task_id=task-1" in caplog.text
    assert "mailbox.delivered task_id=task-1 mail_id=mail-1 user_id=user-1" in caplog.text
    assert (
        "mailbox.worker_iteration worker_id=worker-1 due=1 claimed=1 delivered=1 "
        "failed=0 skipped_locked=0 skipped_unclaimable=0"
    ) in caplog.text
    assert "safe content" not in caplog.text


@pytest.mark.asyncio
async def test_notification_failure_does_not_undo_persisted_delivery(caplog):
    caplog.set_level("INFO")
    task = {
        "task_id": "task-2",
        "user_id": "user-2",
        "sender": "AREQA",
        "content": "safe content",
    }
    redis = WorkerRedis(task)
    store = AsyncMock()
    store.claim_delayed_task.return_value = True
    store.add_mail.return_value = "mail-2"

    with patch("backend.mailbox_store._mailbox_sending_enabled", return_value=True), patch(
        "services.connection_manager.ws_manager.broadcast_mail_alert",
        new_callable=AsyncMock,
        side_effect=RuntimeError("socket unavailable"),
    ):
        delivered = await run_delayed_mail_iteration(redis, store, "worker-2", now=1e12)

    assert delivered == 1
    store.mark_delayed_task_delivered.assert_awaited_once_with("task-2", "mail-2")
    assert "mailbox.notification_failed" in caplog.text
    assert "task_id=task-2" in caplog.text
    assert (
        "mailbox.worker_iteration worker_id=worker-2 due=1 claimed=1 delivered=1 "
        "failed=0 skipped_locked=0 skipped_unclaimable=0"
    ) in caplog.text
    assert "safe content" not in caplog.text


@pytest.mark.asyncio
async def test_unclaimable_due_task_is_removed_from_redis_queue(caplog):
    caplog.set_level("INFO")
    task = {
        "task_id": "task-already-delivered",
        "user_id": "user-1",
        "sender": "AREQA",
        "content": "safe content",
    }
    redis = WorkerRedis(task)
    store = AsyncMock()
    store.claim_delayed_task.return_value = False

    with patch("backend.mailbox_store._mailbox_sending_enabled", return_value=True):
        first = await run_delayed_mail_iteration(redis, store, "worker-1", now=1e12)
        second = await run_delayed_mail_iteration(redis, store, "worker-1", now=1e12)

    assert first == 0
    assert second == 0
    assert redis.payload == ""
    store.add_mail.assert_not_awaited()
    assert (
        "mailbox.worker_iteration worker_id=worker-1 due=1 claimed=0 delivered=0 "
        "failed=0 skipped_locked=0 skipped_unclaimable=1"
    ) in caplog.text


@pytest.mark.asyncio
async def test_database_reconciliation_restores_task_after_redis_enqueue_timeout():
    task = {
        "task_id": "task-recovered",
        "user_id": "user-recovered",
        "sender": "AREQA",
        "content": "recovered content",
    }
    redis = WorkerRedis(task)
    redis.payload = ""
    store = AsyncMock()
    store.claim_delayed_task.return_value = True
    store.add_mail.return_value = "mail-recovered"

    async def restore():
        redis.payload = json.dumps(task)
        return 1

    store.restore_delayed_queue_from_db.side_effect = restore
    restored = await store.restore_delayed_queue_from_db()
    with patch("backend.mailbox_store._mailbox_sending_enabled", return_value=True), patch(
        "services.connection_manager.ws_manager.broadcast_mail_alert",
        new_callable=AsyncMock,
    ):
        delivered = await run_delayed_mail_iteration(
            redis, store, "worker-recovered", now=1e12
        )

    assert restored == 1
    assert delivered == 1
    store.add_mail.assert_awaited_once()
    store.mark_delayed_task_delivered.assert_awaited_once_with(
        "task-recovered",
        "mail-recovered",
    )


@pytest.mark.asyncio
async def test_worker_ensures_schema_before_restore(caplog):
    caplog.set_level("INFO")
    calls = []
    store = AsyncMock()

    async def ensure_schema():
        calls.append("ensure")
        return True

    async def restore():
        calls.append("restore")
        return 0

    store.ensure_delayed_task_schema.side_effect = ensure_schema
    store.restore_delayed_queue_from_db.side_effect = restore

    with patch("backend.mailbox_store._mailbox_sending_enabled", return_value=True), patch(
        "backend.mailbox_store.get_redis",
        return_value=AsyncMock(),
    ), patch(
        "backend.mailbox_store.get_mailbox_store",
        return_value=store,
    ), patch(
        "backend.mailbox_store.run_delayed_mail_iteration",
        new=AsyncMock(side_effect=asyncio.CancelledError),
    ):
        with pytest.raises(asyncio.CancelledError):
            await delayed_mail_worker()

    assert calls == ["ensure", "restore"]
    assert "mailbox.worker_starting" in caplog.text
    assert "mailbox.worker_restored" in caplog.text
    assert "mailbox.worker_started" in caplog.text


@pytest.mark.asyncio
async def test_run_delayed_mail_iteration_is_disabled_by_default(caplog):
    caplog.set_level("INFO")
    task = {
        "task_id": "task-disabled",
        "user_id": "user-disabled",
        "sender": "AREQA",
        "content": "safe content",
    }
    redis = WorkerRedis(task)
    store = AsyncMock()

    delivered = await run_delayed_mail_iteration(redis, store, "worker-disabled", now=1e12)

    assert delivered == 0
    store.claim_delayed_task.assert_not_awaited()
    store.add_mail.assert_not_awaited()
    assert "mailbox.worker_disabled worker_id=worker-disabled" in caplog.text
