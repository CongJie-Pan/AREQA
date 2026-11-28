"""Remember which tutor profile each conversation used on its previous turn.

Clients send only the currently selected profile, so a mid-conversation switch
is visible only by comparing it with what the server saw last time. Redis holds
one short value per conversation; any Redis failure returns ``None`` and the
turn simply gets no profile-transition note.
"""
from __future__ import annotations

import logging

from redis_client import get_redis

logger = logging.getLogger(__name__)

PROFILE_TTL_SECONDS = 7 * 86400


def _key(user_id: str | None, conversation_id: str) -> str:
    return f"tutor_profile:last:{user_id or 'anonymous'}:{conversation_id}"


async def swap_previous_profile(user_id: str | None, conversation_id: str, current: str) -> str | None:
    """Record ``current`` and return the profile this conversation used before.

    Args:
        user_id: Owner scope for the key; never logged.
        conversation_id: Conversation the profile belongs to.
        current: Normalized profile id selected for this turn.

    Returns:
        The previously recorded profile id, or ``None`` for a new conversation,
        a missing conversation id, or an unavailable Redis.
    """
    if not conversation_id:
        return None
    try:
        redis = get_redis()
        key = _key(user_id, conversation_id)
        previous = await redis.get(key)
        if previous != current:
            await redis.set(key, current, ex=PROFILE_TTL_SECONDS)
        else:
            await redis.expire(key, PROFILE_TTL_SECONDS)
    except Exception as exc:
        logger.warning("tutor_profile.history_unavailable reason=%s", type(exc).__name__)
        return None
    if previous is not None and previous != current:
        logger.info("orchestration.tutor_profile_transition conversation_id=%s from=%s to=%s",
                    conversation_id, previous, current)
    return previous
