"""Small intake helpers for orchestration execution."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("backend.services.orchestration_service")


async def record_interaction_timestamp(user_id: str, conversation_id: str, run_id: str) -> bool:
    """Record the user interaction timestamp before the first SSE event."""

    try:
        from services.compeer_scheduler import set_last_interaction_time

        await set_last_interaction_time(user_id, time.time())
        return True
    except Exception as exc:
        logger.warning(
            "orchestration.interaction_timestamp_failed run_id=%s conversation_id=%s reason=%s",
            run_id,
            conversation_id,
            type(exc).__name__,
        )
        return False
