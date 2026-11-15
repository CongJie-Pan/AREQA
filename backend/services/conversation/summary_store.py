"""Optional server-only PostgreSQL checkpoints, isolated by owner and source prefix.

Storage failure never blocks answering. SQL parameters and exceptions can contain
private data, so logs expose operation/error type only and engine parameters are hidden.
"""
from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config import settings

logger = logging.getLogger(__name__)
_TTL = 30 * 86400
Scope = tuple[str, str, str, str]
Checkpoint = tuple[str, int, str]


class SummaryStore:
    """Read/write bounded checkpoints using the existing DATABASE_URL convention.

    Args:
        engine: Optional async engine for integration tests; production is lazy.

    Missing configuration/schema, timeouts and database errors fail soft with a
    60-second circuit breaker. The migration owns RLS and deletion cascades.
    """

    def __init__(self, engine: AsyncEngine | None = None):
        self._engine = engine
        self._retry_after = 0.0

    def _get_engine(self) -> AsyncEngine | None:
        if self._engine is None and settings.database_url:
            url = settings.database_url
            for prefix in ('postgres://', 'postgresql://'):
                if url.startswith(prefix):
                    url = url.replace(prefix, 'postgresql+asyncpg://', 1)
                    break
            self._engine = create_async_engine(
                url, pool_size=2, max_overflow=1, hide_parameters=True,
                connect_args={'statement_cache_size': 0},
            )
        return self._engine

    async def _execute(self, operation: str, scope: Scope, *, prefix: str = '',
                       covered: int = 0, summary: str = '') -> list[Checkpoint]:
        # Unsaved/anonymous conversations remain eligible for the in-process cache.
        try:
            UUID(scope[0])
            UUID(scope[1])
        except (ValueError, TypeError, AttributeError):
            return []
        if time.monotonic() < self._retry_after:
            return []
        try:
            engine = self._get_engine()
            if engine is None:
                logger.info('history.checkpoint_skipped reason=database_unconfigured operation=%s', operation)
                return []
            params = dict(zip(('user_id', 'conversation_id', 'model', 'prompt_hash'), scope))
            params.update(prefix=prefix, covered=covered, summary=summary,
                          updated=int(time.time()), cutoff=int(time.time()) - _TTL)

            async def run() -> list[Checkpoint] | None:
                # None marks a completed write; a list is load output or a skipped write.
                async with engine.begin() as connection:
                    if operation == 'load':
                        result = await connection.execute(text('''
                            SELECT s.source_hash, s.covered, s.summary
                            FROM conversation_summary_checkpoints s
                            JOIN conversations c ON c.id = s.conversation_id AND c.user_id = s.user_id
                            WHERE s.user_id = :user_id AND s.conversation_id = :conversation_id
                              AND s.model = :model AND s.prompt_hash = :prompt_hash
                              AND s.updated_at >= :cutoff
                            ORDER BY s.updated_at DESC LIMIT 16
                        '''), params)
                        return [tuple(row) for row in result]
                    # A supplied conversation ID alone never authorizes checkpoint writes.
                    written = await connection.execute(text('''
                        INSERT INTO conversation_summary_checkpoints
                          (user_id, conversation_id, model, prompt_hash, source_hash, covered, summary, updated_at)
                        SELECT :user_id, :conversation_id, :model, :prompt_hash, :prefix, :covered, :summary, :updated
                        FROM conversations WHERE id = :conversation_id AND user_id = :user_id
                        ON CONFLICT (user_id, conversation_id, model, prompt_hash, source_hash)
                        DO UPDATE SET summary = excluded.summary, updated_at = excluded.updated_at
                    '''), params)
                    if written.rowcount == 0:
                        logger.info('history.checkpoint_skipped reason=conversation_unavailable')
                        return []
                    # Bound stored versions across model/prompt changes, not just one scope.
                    await connection.execute(text('''
                        DELETE FROM conversation_summary_checkpoints
                        WHERE user_id = :user_id AND conversation_id = :conversation_id
                          AND (updated_at < :cutoff OR (model, prompt_hash, source_hash) NOT IN (
                            SELECT model, prompt_hash, source_hash FROM conversation_summary_checkpoints
                            WHERE user_id = :user_id AND conversation_id = :conversation_id
                            ORDER BY updated_at DESC, covered DESC LIMIT 16
                          ))
                    '''), params)
                return None

            # wait_for keeps the 2-second bound on Python 3.10, where asyncio.timeout is absent.
            rows = await asyncio.wait_for(run(), timeout=2)
            if rows is not None:
                return rows
            logger.info('history.checkpoint_saved covered=%d', covered)
        except Exception as error:
            self._retry_after = time.monotonic() + 60
            logger.warning('history.checkpoint_unavailable operation=%s error_type=%s',
                           operation, type(error).__name__)
        return []

    async def load(self, scope: Scope) -> list[Checkpoint]:
        """Return owner-verified, unexpired checkpoints for a four-part scope.

        Args:
            scope: User, conversation, model and summary-instruction digest.

        Returns:
            Source digest, covered count and summary tuples; [] if unavailable.
        """
        return await self._execute('load', scope)

    async def save(self, scope: Scope, prefix: str, covered: int, summary: str) -> None:
        """Persist validated notes only when the conversation belongs to scope.

        Args:
            scope: User, conversation, model and summary-instruction digest.
            prefix: Content-addressed source digest, never raw transcript data.
            covered: Number of original source messages represented.
            summary: Validated provider output; never included in logs.

        Errors fail soft and emit only operation and exception type.
        """
        await self._execute('save', scope, prefix=prefix, covered=covered, summary=summary)


summary_store = SummaryStore()
