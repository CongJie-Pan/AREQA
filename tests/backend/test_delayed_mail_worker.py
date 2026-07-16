import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.mailbox_store import run_delayed_mail_iteration


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
async def test_reconciled_task_is_delivered_exactly_once():
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

    with patch(
        "services.connection_manager.ws_manager.broadcast_mail_alert",
        new_callable=AsyncMock,
    ):
        first = await run_delayed_mail_iteration(redis, store, "worker-1", now=1e12)
        second = await run_delayed_mail_iteration(redis, store, "worker-1", now=1e12)

    assert first == 1
    assert second == 0
    store.add_mail.assert_awaited_once()
    store.mark_delayed_task_delivered.assert_awaited_once_with("task-1", "mail-1")


@pytest.mark.asyncio
async def test_notification_failure_does_not_undo_persisted_delivery(caplog):
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

    with patch(
        "services.connection_manager.ws_manager.broadcast_mail_alert",
        new_callable=AsyncMock,
        side_effect=RuntimeError("socket unavailable"),
    ):
        delivered = await run_delayed_mail_iteration(redis, store, "worker-2", now=1e12)

    assert delivered == 1
    store.mark_delayed_task_delivered.assert_awaited_once_with("task-2", "mail-2")
    assert "mailbox.notification_failed" in caplog.text


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
    with patch(
        "services.connection_manager.ws_manager.broadcast_mail_alert",
        new_callable=AsyncMock,
    ):
        delivered = await run_delayed_mail_iteration(
            redis, store, "worker-recovered", now=1e12
        )

    assert restored == 1
    assert delivered == 1
    store.add_mail.assert_awaited_once()
