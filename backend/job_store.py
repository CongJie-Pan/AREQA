from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentJob:
    job_id: str
    job_type: str
    user_id: str
    payload: dict[str, Any]
    attempt_count: int


class AgentJobStore:
    def __init__(self) -> None:
        self._engine = None
        self._db_available: bool | None = None

    def _database_url(self) -> str:
        return os.environ.get("DATABASE_URL", "")

    def _get_engine(self):
        if self._engine is None:
            db_url = self._database_url()
            if not db_url:
                return None
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            self._engine = create_async_engine(
                db_url,
                pool_size=5,
                max_overflow=5,
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
                cursor = await session.execute(
                    text("SELECT to_regclass('public.agent_background_jobs')")
                )
                self._db_available = cursor.scalar() is not None
        except Exception as exc:
            logger.warning("Durable agent job store unavailable: %s", exc)
            self._db_available = False
        return self._db_available

    async def schedule(
        self,
        *,
        job_type: str,
        user_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> str | None:
        if not await self._has_db():
            return None
        job_id = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:40]
        async with AsyncSession(self._get_engine()) as session:
            async with session.begin():
                cursor = await session.execute(
                    text(
                        """
                        INSERT INTO agent_background_jobs (
                          job_id, idempotency_key, job_type, user_id, payload, status
                        ) VALUES (
                          :job_id, :idempotency_key, :job_type, :user_id,
                          CAST(:payload AS jsonb), 'scheduled'
                        )
                        ON CONFLICT (idempotency_key) DO UPDATE
                          SET updated_at = agent_background_jobs.updated_at
                        RETURNING job_id
                        """
                    ),
                    {
                        "job_id": job_id,
                        "idempotency_key": idempotency_key,
                        "job_type": job_type,
                        "user_id": user_id,
                        "payload": json.dumps(payload, ensure_ascii=False),
                    },
                )
                return cursor.scalar()

    async def claim_next(self, worker_id: str, lease_seconds: int = 300) -> AgentJob | None:
        if not await self._has_db():
            return None
        async with AsyncSession(self._get_engine()) as session:
            async with session.begin():
                cursor = await session.execute(
                    text(
                        """
                        WITH candidate AS (
                          SELECT job_id FROM agent_background_jobs
                          WHERE available_at <= now()
                            AND (
                              status IN ('scheduled', 'retryable_failed')
                              OR (status = 'claimed' AND lease_expires_at < now())
                            )
                          ORDER BY available_at, created_at
                          FOR UPDATE SKIP LOCKED
                          LIMIT 1
                        )
                        UPDATE agent_background_jobs AS jobs
                        SET status = 'claimed', lease_owner = :worker_id,
                            lease_expires_at = now() + (:lease_seconds * interval '1 second'),
                            attempt_count = attempt_count + 1, updated_at = now()
                        FROM candidate
                        WHERE jobs.job_id = candidate.job_id
                        RETURNING jobs.job_id, jobs.job_type, jobs.user_id,
                                  jobs.payload, jobs.attempt_count
                        """
                    ),
                    {"worker_id": worker_id, "lease_seconds": lease_seconds},
                )
                row = cursor.mappings().first()
                if not row:
                    return None
                payload = row["payload"]
                return AgentJob(
                    job_id=row["job_id"],
                    job_type=row["job_type"],
                    user_id=row["user_id"],
                    payload=json.loads(payload) if isinstance(payload, str) else dict(payload),
                    attempt_count=int(row["attempt_count"]),
                )

    async def complete(self, job_id: str, worker_id: str) -> None:
        await self._transition(job_id, worker_id, "completed", None)

    async def fail(self, job: AgentJob, worker_id: str, error_code: str, max_attempts: int = 3) -> None:
        status = "terminal_failed" if job.attempt_count >= max_attempts else "retryable_failed"
        await self._transition(job.job_id, worker_id, status, error_code)

    async def _transition(
        self, job_id: str, worker_id: str, status: str, error_code: str | None
    ) -> None:
        if not await self._has_db():
            return
        async with AsyncSession(self._get_engine()) as session:
            async with session.begin():
                await session.execute(
                    text(
                        """
                        UPDATE agent_background_jobs
                        SET status = :status, last_error_code = :error_code,
                            available_at = CASE WHEN :status = 'retryable_failed'
                              THEN now() + (LEAST(attempt_count, 6) * interval '30 seconds')
                              ELSE available_at END,
                            lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
                        WHERE job_id = :job_id AND lease_owner = :worker_id
                        """
                    ),
                    {
                        "job_id": job_id,
                        "worker_id": worker_id,
                        "status": status,
                        "error_code": error_code,
                    },
                )


_global_job_store: AgentJobStore | None = None


def init_agent_job_store() -> AgentJobStore:
    global _global_job_store
    _global_job_store = AgentJobStore()
    return _global_job_store


def get_agent_job_store() -> AgentJobStore:
    global _global_job_store
    return _global_job_store or init_agent_job_store()


async def agent_job_worker() -> None:
    worker_id = f"agent-jobs-{uuid.uuid4().hex}"
    store = get_agent_job_store()
    while True:
        job = await store.claim_next(worker_id)
        if job is None:
            await asyncio.sleep(1)
            continue
        try:
            if job.job_type == "reflection_observation":
                from services.memory.gum.runtime import push_reflection_observation

                await push_reflection_observation(
                    job.user_id,
                    job.payload["text"],
                    conversation_id=job.payload.get("conversation_id", ""),
                )
            elif job.job_type == "session_reflection":
                from services.memory.gum.runtime import run_reflection

                await run_reflection(
                    job.user_id,
                    conversation_id=job.payload.get("conversation_id", ""),
                )
            elif job.job_type == "edf_evaluation":
                from config import settings
                from services.memory.gum.runtime import async_evaluate_and_update_state
                from openai import AsyncOpenAI

                api_key = os.environ.get("OPENROUTER_API_KEY", "")
                if not api_key:
                    raise RuntimeError("OPENROUTER_API_KEY_MISSING")
                client = AsyncOpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=api_key,
                    timeout=120.0,
                )
                await async_evaluate_and_update_state(
                    client,
                    job.payload.get("model", settings.model_policy_classifier),
                    job.payload["messages"],
                    user_id=job.user_id,
                    conversation_id=job.payload.get("conversation_id", ""),
                    ingest_memory=job.payload.get("ingest_memory", False),
                )
            elif job.job_type == "memory_compaction":
                from services.memory.gum.runtime import run_compaction

                await run_compaction(job.user_id)
            else:
                raise ValueError(f"UNKNOWN_JOB_TYPE:{job.job_type}")
        except Exception as exc:
            error_code = str(exc).split(":", 1)[0][:120] or type(exc).__name__
            logger.exception("Agent job %s failed", job.job_id)
            await store.fail(job, worker_id, error_code)
        else:
            await store.complete(job.job_id, worker_id)
