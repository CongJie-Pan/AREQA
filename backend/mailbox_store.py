import json
import uuid
import time
import logging
import os
from typing import Dict, Any, List, Optional
import asyncio

from redis_client import get_redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = logging.getLogger(__name__)

class MailboxStore:
    def __init__(self):
        self.redis = get_redis()
        self._engine = None
        self._db_available: Optional[bool] = None

    def _database_url(self) -> str:
        return os.environ.get("MAILBOX_DATABASE_URL") or os.environ.get("DATABASE_URL", "")

    def _get_engine(self):
        if self._engine is None:
            db_url = self._database_url()
            if not db_url:
                return None
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            self._engine = create_async_engine(
                db_url,
                pool_size=5,
                max_overflow=10,
                connect_args={"statement_cache_size": 0},
            )
        return self._engine

    async def _has_db(self) -> bool:
        if self._db_available is not None:
            return self._db_available
        engine = self._get_engine()
        if engine is None:
            self._db_available = False
            return False
        try:
            async with AsyncSession(engine) as session:
                cursor = await session.execute(text("SELECT to_regclass('public.mailbox_messages')"))
                self._db_available = cursor.scalar() is not None
        except Exception as exc:
            logger.warning("[MailboxStore] Database mailbox unavailable; falling back to Redis: %s", exc)
            self._db_available = False
        return self._db_available

    def _mail_to_cache(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mail_id": row["mail_id"],
            "sender": row["sender"],
            "subject": row.get("subject") or "",
            "recipient": row["recipient"],
            "content": row["content"],
            "timestamp": row["created_at"].timestamp() if row.get("created_at") else time.time(),
            "is_read": bool(row.get("is_read")),
            "conversation_id": row.get("conversation_id"),
            "status": row.get("status", "delivered"),
            "deliver_at": row["deliver_at"].timestamp() if row.get("deliver_at") else None,
        }

    async def _cache_mails(self, user_id: str, mails: List[Dict[str, Any]]) -> None:
        try:
            await self.redis.set(f"areqa:mailbox:{user_id}", json.dumps(mails, ensure_ascii=False))
        except Exception as exc:
            logger.warning("[MailboxStore] Failed to update Redis mailbox cache for %s: %s", user_id, exc)

    async def get_all_mails(self, user_id: str) -> List[Dict[str, Any]]:
        # mails can be stored in a Redis list or just a JSON string of list.
        try:
            data = await self.redis.get(f"areqa:mailbox:{user_id}")
        except Exception as exc:
            logger.warning("[MailboxStore] Failed to read Redis mailbox cache for %s: %s", user_id, exc)
            data = None
        if data:
            return json.loads(data)

        if await self._has_db():
            mails = await self._fetch_mails_from_db(user_id)
            await self._cache_mails(user_id, mails)
            return mails

        return []

    async def add_mail(
        self,
        user_id: str,
        sender: str,
        content: str,
        subject: str = "",
        recipient: str = "User",
        conversation_id: Optional[str] = None,
        mail_id: Optional[str] = None,
        delivered_task_id: Optional[str] = None,
    ) -> str:
        mail_id = mail_id or str(uuid.uuid4())

        if await self._has_db():
            async with AsyncSession(self._get_engine()) as session:
                async with session.begin():
                    if delivered_task_id:
                        existing = await session.execute(
                            text(
                                """
                                SELECT mail_id
                                FROM mailbox_messages
                                WHERE user_id = :user_id AND delivered_task_id = :delivered_task_id
                                LIMIT 1
                                """
                            ),
                            {"user_id": user_id, "delivered_task_id": delivered_task_id},
                        )
                        row = existing.fetchone()
                        if row:
                            return row[0]

                    await session.execute(
                        text(
                            """
                            INSERT INTO mailbox_messages (
                                mail_id, user_id, sender, subject, recipient, content,
                                conversation_id, delivered_task_id, status, is_read,
                                delivered_at
                            )
                            VALUES (
                                :mail_id, :user_id, :sender, :subject, :recipient, :content,
                                :conversation_id, :delivered_task_id, 'delivered', false,
                                now()
                            )
                            ON CONFLICT (mail_id) DO NOTHING
                            """
                        ),
                        {
                            "mail_id": mail_id,
                            "user_id": user_id,
                            "sender": sender,
                            "subject": subject,
                            "recipient": recipient,
                            "content": content,
                            "conversation_id": conversation_id,
                            "delivered_task_id": delivered_task_id,
                        },
                    )

            await self._cache_mails(user_id, await self._fetch_mails_from_db(user_id))
            return mail_id

        mails = await self.get_all_mails(user_id)

        if delivered_task_id:
            for mail in mails:
                if mail.get("delivered_task_id") == delivered_task_id:
                    return mail["mail_id"]

        new_mail = {
            "mail_id": mail_id,
            "sender": sender,
            "subject": subject,
            "recipient": recipient,
            "content": content,
            "timestamp": time.time(),
            "is_read": False,
            "conversation_id": conversation_id
        }
        if delivered_task_id:
            new_mail["delivered_task_id"] = delivered_task_id
        
        mails.append(new_mail)
        await self._cache_mails(user_id, mails)
        return mail_id

    async def mark_as_read(self, user_id: str, mail_id: str) -> bool:
        if await self._has_db():
            async with AsyncSession(self._get_engine()) as session:
                async with session.begin():
                    cursor = await session.execute(
                        text(
                            """
                            UPDATE mailbox_messages
                            SET is_read = true, read_at = now(), updated_at = now()
                            WHERE user_id = :user_id AND mail_id = :mail_id
                            """
                        ),
                        {"user_id": user_id, "mail_id": mail_id},
                    )
                    found = cursor.rowcount > 0
            if found:
                await self._cache_mails(user_id, await self._fetch_mails_from_db(user_id))
            return found

        mails = await self.get_all_mails(user_id)
        found = False
        for mail in mails:
            if mail.get("mail_id") == mail_id:
                mail["is_read"] = True
                found = True
                break
                
        if found:
            await self._cache_mails(user_id, mails)
        return found

    async def get_unread_count(self, user_id: str) -> int:
        if await self._has_db():
            async with AsyncSession(self._get_engine()) as session:
                cursor = await session.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM mailbox_messages
                        WHERE user_id = :user_id
                          AND is_read = false
                          AND recipient = 'User'
                        """
                    ),
                    {"user_id": user_id},
                )
                return int(cursor.scalar() or 0)

        mails = await self.get_all_mails(user_id)
        return sum(1 for mail in mails if not mail.get("is_read", False) and mail.get("recipient") == "User")

    async def schedule_delayed_mail(self, user_id: str, mail_data: Dict[str, Any], delay_seconds: int = 300):
        mail_data = dict(mail_data)
        mail_data.setdefault("task_id", str(uuid.uuid4()))
        mail_data["user_id"] = user_id
        if not _mailbox_sending_enabled():
            logger.info(
                "mailbox.schedule_disabled task_id=%s user_id=%s kind=%s",
                mail_data["task_id"],
                user_id,
                mail_data.get("kind", "delayed_mail"),
            )
            return mail_data["task_id"]
        score = time.time() + delay_seconds
        should_enqueue_redis = True
        if await self._has_db():
            async with AsyncSession(self._get_engine()) as session:
                async with session.begin():
                    cursor = await session.execute(
                        text(
                            """
                            INSERT INTO mailbox_delayed_tasks (
                                task_id, user_id, payload, status, deliver_at
                            )
                            VALUES (
                                :task_id, :user_id, CAST(:payload AS jsonb), 'scheduled', to_timestamp(:deliver_at)
                            )
                            ON CONFLICT (task_id) DO NOTHING
                            RETURNING task_id
                            """
                        ),
                        {
                            "task_id": mail_data["task_id"],
                            "user_id": user_id,
                            "payload": json.dumps(mail_data, ensure_ascii=False),
                            "deliver_at": score,
                        },
                    )
                    should_enqueue_redis = cursor.scalar() is not None
                    if not should_enqueue_redis:
                        logger.info(
                            "[MailboxStore] Skipping duplicate delayed mail task %s for user %s",
                            mail_data["task_id"],
                            user_id,
                        )
                        return mail_data["task_id"]
        mail_data_json = json.dumps(mail_data, ensure_ascii=False)
        try:
            if not await self._has_db():
                key = f"areqa:delayed_mail:{user_id}"
                existing = await self.redis.zrange(key, 0, -1)
                for item in existing:
                    try:
                        queued = json.loads(item)
                    except Exception:
                        continue
                    if queued.get("task_id") == mail_data["task_id"]:
                        logger.info(
                            "[MailboxStore] Skipping duplicate Redis delayed mail task %s for user %s",
                            mail_data["task_id"],
                            user_id,
                        )
                        return mail_data["task_id"]

            if should_enqueue_redis:
                await self.redis.zadd(f"areqa:delayed_mail:{user_id}", {mail_data_json: score})
        except Exception as exc:
            if not await self._has_db():
                raise
            logger.warning("[MailboxStore] Failed to update Redis delayed queue for %s: %s", user_id, exc)
        logger.info(
            "mailbox.scheduled task_id=%s user_id=%s kind=%s delay_seconds=%s",
            mail_data["task_id"],
            user_id,
            mail_data.get("kind", "delayed_mail"),
            delay_seconds,
        )
        return mail_data["task_id"]

    async def _fetch_mails_from_db(self, user_id: str) -> List[Dict[str, Any]]:
        async with AsyncSession(self._get_engine()) as session:
            cursor = await session.execute(
                text(
                    """
                    SELECT mail_id, sender, subject, recipient, content, conversation_id,
                           status, is_read, created_at, delivered_at AS deliver_at
                    FROM mailbox_messages
                    WHERE user_id = :user_id
                    ORDER BY created_at ASC
                    """
                ),
                {"user_id": user_id},
            )
            return [self._mail_to_cache(dict(row)) for row in cursor.mappings().all()]

    async def mark_delayed_task_delivered(self, task_id: str, delivered_mail_id: str) -> None:
        if not await self._has_db():
            return
        async with AsyncSession(self._get_engine()) as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE mailbox_delayed_tasks
                        SET status = 'delivered',
                            delivered_mail_id = :delivered_mail_id,
                            lease_owner = NULL,
                            lease_expires_at = NULL,
                            updated_at = now()
                        WHERE task_id = :task_id
                        """
                    ),
                    {"task_id": task_id, "delivered_mail_id": delivered_mail_id},
                )

    async def ensure_delayed_task_schema(self) -> bool:
        """Ensure delayed-task lease columns exist before the worker restores.

        Some deployments may have the original mailbox persistence table without
        the later lease/retry migration. The delayed mail worker requires these
        columns for claim, retry, and reconciliation queries. Applying the same
        idempotent schema additions at startup prevents one missing migration
        from killing the worker before it can deliver already scheduled mail.

        Returns:
            True when the database is unavailable or the schema check succeeds.
        """
        if not await self._has_db():
            return True
        async with AsyncSession(self._get_engine()) as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        ALTER TABLE public.mailbox_delayed_tasks
                          ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0,
                          ADD COLUMN IF NOT EXISTS lease_owner text,
                          ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
                          ADD COLUMN IF NOT EXISTS last_error_code text
                        """
                    )
                )
                await session.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_mailbox_delayed_tasks_claimable
                          ON public.mailbox_delayed_tasks(status, lease_expires_at, deliver_at)
                        """
                    )
                )
        logger.info("mailbox.delayed_task_schema_ready")
        return True

    async def claim_delayed_task(self, task_id: str, worker_id: str, lease_seconds: int = 300) -> bool:
        """Atomically claim a durable task; Redis-only deployments use their lock."""
        if not await self._has_db():
            return True
        async with AsyncSession(self._get_engine()) as session:
            async with session.begin():
                cursor = await session.execute(
                    text(
                        """
                        UPDATE mailbox_delayed_tasks
                        SET status = 'claimed',
                            lease_owner = :worker_id,
                            lease_expires_at = now() + (:lease_seconds * interval '1 second'),
                            attempt_count = attempt_count + 1,
                            updated_at = now()
                        WHERE task_id = :task_id
                          AND deliver_at <= now()
                          AND (
                            status = 'scheduled'
                            OR status = 'retryable_failed'
                            OR (status = 'claimed' AND lease_expires_at < now())
                          )
                        RETURNING task_id
                        """
                    ),
                    {
                        "task_id": task_id,
                        "worker_id": worker_id,
                        "lease_seconds": lease_seconds,
                    },
                )
                return cursor.scalar() is not None

    async def mark_delayed_task_failed(
        self,
        task_id: str,
        worker_id: str,
        error_code: str,
        max_attempts: int = 3,
    ) -> str:
        if not await self._has_db():
            logger.warning(
                "mailbox.retryable_failed task_id=%s worker_id=%s reason=%s persistence=redis_only",
                task_id,
                worker_id,
                error_code[:120],
            )
            return "retryable_failed"
        async with AsyncSession(self._get_engine()) as session:
            async with session.begin():
                cursor = await session.execute(
                    text(
                        """
                        UPDATE mailbox_delayed_tasks
                        SET status = CASE WHEN attempt_count >= :max_attempts
                              THEN 'terminal_failed' ELSE 'retryable_failed' END,
                            deliver_at = CASE WHEN attempt_count >= :max_attempts
                              THEN deliver_at
                              ELSE now() + (LEAST(attempt_count, 6) * interval '30 seconds') END,
                            last_error_code = :error_code,
                            lease_owner = NULL,
                            lease_expires_at = NULL,
                            updated_at = now()
                        WHERE task_id = :task_id AND lease_owner = :worker_id
                        RETURNING status, attempt_count
                        """
                    ),
                    {
                        "task_id": task_id,
                        "worker_id": worker_id,
                        "error_code": error_code[:120],
                        "max_attempts": max_attempts,
                    },
                )
        row = cursor.fetchone() if hasattr(cursor, "fetchone") else None
        status = str(row[0]) if row else "retryable_failed"
        event_name = (
            "mailbox.terminal_failed"
            if status == "terminal_failed"
            else "mailbox.retryable_failed"
        )
        logger.warning(
            "%s task_id=%s worker_id=%s reason=%s attempt_count=%s",
            event_name,
            task_id,
            worker_id,
            error_code[:120],
            row[1] if row and len(row) > 1 else "unknown",
        )
        return status

    async def restore_delayed_queue_from_db(self) -> int:
        if not await self._has_db():
            return 0
        async with AsyncSession(self._get_engine()) as session:
            cursor = await session.execute(
                text(
                    """
                    SELECT task_id, user_id, payload, extract(epoch from deliver_at) AS deliver_at_epoch
                    FROM mailbox_delayed_tasks
                    WHERE status IN ('scheduled', 'retryable_failed')
                       OR (status = 'claimed' AND lease_expires_at < now())
                    """
                )
            )
            rows = cursor.mappings().all()

        restored = 0
        for row in rows:
            payload = row["payload"]
            if isinstance(payload, str):
                task = json.loads(payload)
            else:
                task = dict(payload)
            task["task_id"] = row["task_id"]
            task["user_id"] = row["user_id"]
            await self.redis.zadd(
                f"areqa:delayed_mail:{row['user_id']}",
                {json.dumps(task, ensure_ascii=False): float(row["deliver_at_epoch"])},
            )
            restored += 1
        if restored:
            logger.info("mailbox.reconciled restored=%s", restored)
        return restored

_global_mailbox_store = None


def _mailbox_sending_enabled() -> bool:
    from config import settings

    return bool(settings.enable_mailbox_sending)


async def _release_owned_lock(redis, lock_key: str, owner: str) -> None:
    await redis.eval(
        """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """,
        1,
        lock_key,
        owner,
    )


async def _deliver_claimed_mail(store: MailboxStore, task: Dict[str, Any], task_id: str) -> tuple[str, str, str]:
    user_id = task.get("user_id", "default_user")
    active_avatar = task.get("active_avatar", "AREQA")
    conversation_id = task.get("conversation_id")
    subject = task.get("subject") or ""
    content = task.get("content") or ""

    if not content:
        from services.memory.gum.runtime import (
            generate_epistolary_letter_via_llm,
            get_hot_memory_snapshot,
            query_cold_memory_for_context,
        )

        reply_content = task.get("reply_content", "")
        snapshot = await get_hot_memory_snapshot(user_id)
        hot_context = f"使用者的回信內容：{reply_content}\n---\n目前對話脈絡：\n{snapshot}"
        event_summary = f"使用者回信給 {active_avatar} 探討：{reply_content[:50]}"
        cold_ctx = await query_cold_memory_for_context(user_id, event_summary)
        subject, content = await generate_epistolary_letter_via_llm(
            user_id=user_id,
            active_avatar=active_avatar,
            hot_memory_snapshot=hot_context,
            cold_memory_context=cold_ctx,
        )

    delivered_mail_id = await store.add_mail(
        user_id=user_id,
        sender=active_avatar,
        content=content,
        subject=subject,
        recipient="User",
        conversation_id=conversation_id,
        delivered_task_id=task_id,
    )
    await store.mark_delayed_task_delivered(task_id, delivered_mail_id)
    logger.info(
        "mailbox.delivered task_id=%s mail_id=%s user_id=%s",
        task_id,
        delivered_mail_id,
        user_id,
    )
    return delivered_mail_id, active_avatar, user_id

def init_mailbox_store():
    global _global_mailbox_store
    _global_mailbox_store = MailboxStore()
    return _global_mailbox_store

def get_mailbox_store() -> MailboxStore:
    global _global_mailbox_store
    if _global_mailbox_store is None:
        init_mailbox_store()
    return _global_mailbox_store


async def run_delayed_mail_iteration(
    redis: Any,
    store: MailboxStore,
    worker_id: str,
    *,
    now: float | None = None,
) -> int:
    """Claim and deliver all currently due tasks once.

    The bounded iteration is independently testable so recovery and exactly-once
    behavior do not depend on controlling an infinite worker loop.
    """

    if not _mailbox_sending_enabled():
        logger.info("mailbox.worker_disabled worker_id=%s", worker_id)
        return 0

    delivered = 0
    due_tasks = 0
    claimed = 0
    delivery_failed = 0
    skipped_locked = 0
    skipped_unclaimable = 0
    cursor = 0
    due_before = time.time() if now is None else now
    while True:
        cursor, keys = await redis.scan(
            cursor=cursor,
            match="areqa:delayed_mail:*",
            count=100,
        )
        for key in keys:
            tasks = await redis.zrangebyscore(key, 0, due_before)
            for task_json in tasks:
                due_tasks += 1
                task = json.loads(task_json)
                user_id = task.get("user_id", "default_user")
                task_id = task.get("task_id") or task.get("mail_id") or task_json
                lock_key = f"areqa:delayed_mail_lock:{task_id}"
                if not await redis.set(lock_key, worker_id, nx=True, ex=600):
                    skipped_locked += 1
                    continue
                if not await store.claim_delayed_task(task_id, worker_id, lease_seconds=600):
                    await _release_owned_lock(redis, lock_key, worker_id)
                    # Redis is only an acceleration queue. If the durable DB row
                    # cannot be claimed, remove this stale queue copy so the
                    # worker does not retry an already delivered or otherwise
                    # non-claimable task every second.
                    await redis.zrem(key, task_json)
                    skipped_unclaimable += 1
                    continue
                claimed += 1
                logger.info(
                    "mailbox.claimed task_id=%s user_id=%s worker_id=%s",
                    task_id,
                    user_id,
                    worker_id,
                )
                try:
                    _, active_avatar, user_id = await _deliver_claimed_mail(store, task, task_id)
                    if task.get("kind") == "compeer_care":
                        from services.memory.store.service import get_global_store

                        memory_store = get_global_store()
                        if memory_store:
                            await memory_store.update_hot_memory_async(
                                user_id,
                                "last_compeer_message",
                                task.get("content", ""),
                            )
                except Exception as exc:
                    error_code = type(exc).__name__
                    logger.exception(
                        "mailbox.delivery_failed task_id=%s user_id=%s reason=%s",
                        task_id,
                        user_id,
                        error_code,
                    )
                    await store.mark_delayed_task_failed(task_id, worker_id, error_code)
                    await _release_owned_lock(redis, lock_key, worker_id)
                    delivery_failed += 1
                    continue

                from services.connection_manager import ws_manager

                try:
                    await ws_manager.broadcast_mail_alert(sender=active_avatar, user_id=user_id)
                except Exception as exc:
                    logger.warning(
                        "mailbox.notification_failed task_id=%s user_id=%s reason=%s",
                        task_id,
                        user_id,
                        type(exc).__name__,
                    )
                await redis.zrem(key, task_json)
                await _release_owned_lock(redis, lock_key, worker_id)
                delivered += 1
        if cursor == 0:
            break
    if due_tasks:
        logger.info(
            "mailbox.worker_iteration worker_id=%s due=%s claimed=%s delivered=%s "
            "failed=%s skipped_locked=%s skipped_unclaimable=%s",
            worker_id,
            due_tasks,
            claimed,
            delivered,
            delivery_failed,
            skipped_locked,
            skipped_unclaimable,
        )
    return delivered


# Background Worker for Delayed Mails
async def delayed_mail_worker():
    redis = get_redis()
    store = get_mailbox_store()
    worker_id = f"mailbox-{uuid.uuid4().hex}"
    logger.info("mailbox.worker_starting worker_id=%s", worker_id)
    if not _mailbox_sending_enabled():
        logger.info("mailbox.worker_disabled worker_id=%s", worker_id)
        return
    await store.ensure_delayed_task_schema()
    restored = await store.restore_delayed_queue_from_db()
    logger.info("mailbox.worker_restored worker_id=%s restored=%s", worker_id, restored)
    logger.info("mailbox.worker_started worker_id=%s", worker_id)
    last_reconciled_at = time.monotonic()
    while True:
        try:
            if time.monotonic() - last_reconciled_at >= 30:
                await store.restore_delayed_queue_from_db()
                last_reconciled_at = time.monotonic()
            await run_delayed_mail_iteration(redis, store, worker_id)
                        
            await asyncio.sleep(1)
        except Exception:
            logger.exception("mailbox.worker_iteration_failed worker_id=%s", worker_id)
            await asyncio.sleep(5)
