"""Collaborative conversation context for the stream endpoint.

A conversation becomes collaborative when its owner shares an edit link and a
signed-in member joins (see ``supabase/migrations/*_collaborative_conversations.sql``).
For those conversations the backend, not the client, decides the history: the
Supabase function ``get_collaborative_context`` runs with the caller's own JWT,
checks membership in the database, and returns the shared text history.

Collaborative turns never read or write personal memory, so one participant's
learning history cannot surface in answers the others can read. When the
lookup itself fails, the caller still gets an answer but memory stays off.
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

import httpx

logger = logging.getLogger(__name__)

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_LOOKUP_TIMEOUT_SECONDS = 3.0

# Shared conversations are a shared spend surface; cap AI replies per
# conversation on top of the per-user limits each participant already has.
COLLABORATIVE_TURN_LIMIT = 20
COLLABORATIVE_TURN_WINDOW_SECONDS = 300

CollaborationState = Literal["personal", "collaborative", "unknown"]


@dataclass
class CollaborationContext:
    """Outcome of the collaborative lookup for one stream request."""

    state: CollaborationState
    role: str | None = None
    messages: List[Dict[str, str]] = field(default_factory=list)


def _supabase_rest_config() -> tuple[str, str] | None:
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    anon_key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not url or not anon_key:
        return None
    return url.rstrip("/"), anon_key


def bearer_token(authorization: str | None) -> str | None:
    """Return the bearer token from an Authorization header value."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


def _normalize_history(raw_messages: Any) -> List[Dict[str, str]]:
    history: List[Dict[str, str]] = []
    if not isinstance(raw_messages, list):
        return history
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        history.append({"role": role, "content": content, "message_id": str(item.get("id") or "")})
    return history


async def load_collaboration_context(conversation_id: str, access_token: str | None) -> CollaborationContext:
    """Resolve whether this turn belongs to a collaborative conversation.

    Returns ``personal`` for ordinary conversations (including when the
    migration is not applied yet), ``collaborative`` with the server-side
    history for members, and ``unknown`` when Supabase could not be reached.
    """
    if not access_token or not _UUID_PATTERN.match(conversation_id or ""):
        return CollaborationContext(state="personal")
    config = _supabase_rest_config()
    if config is None:
        return CollaborationContext(state="personal")
    supabase_url, anon_key = config

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_LOOKUP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{supabase_url}/rest/v1/rpc/get_collaborative_context",
                headers={
                    "apikey": anon_key,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"p_conversation_id": conversation_id},
            )
    except httpx.HTTPError as error:
        logger.warning(
            "collaboration.lookup_failed conversation_id=%s error_type=%s elapsed_ms=%d",
            conversation_id, type(error).__name__, (time.perf_counter() - started) * 1000,
        )
        return CollaborationContext(state="unknown")

    elapsed_ms = (time.perf_counter() - started) * 1000
    if response.status_code == 404:
        # PostgREST answers 404 for a missing function: the migration is not applied.
        logger.info("collaboration.lookup_unavailable conversation_id=%s", conversation_id)
        return CollaborationContext(state="personal")
    if response.status_code != 200:
        logger.warning(
            "collaboration.lookup_failed conversation_id=%s status=%s elapsed_ms=%d",
            conversation_id, response.status_code, elapsed_ms,
        )
        return CollaborationContext(state="unknown")

    try:
        payload = response.json()
    except ValueError:
        logger.warning("collaboration.lookup_invalid_payload conversation_id=%s", conversation_id)
        return CollaborationContext(state="unknown")

    if not isinstance(payload, dict):
        return CollaborationContext(state="personal")

    history = _normalize_history(payload.get("messages"))
    logger.info(
        "collaboration.lookup_resolved conversation_id=%s role=%s message_count=%d elapsed_ms=%d",
        conversation_id, payload.get("role"), len(history), elapsed_ms,
    )
    return CollaborationContext(state="collaborative", role=str(payload.get("role") or ""), messages=history)


def merge_collaborative_history(
    server_history: List[Dict[str, str]],
    client_messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Use the stored history plus the client's newest user turn.

    The newest turn may or may not be stored yet (the owner's client syncs it
    asynchronously; members append it first), so it is deduplicated by id and
    always kept last with its transport fields intact.
    """
    latest_user_turn = next(
        (item for item in reversed(client_messages) if item.get("role") == "user"),
        None,
    )
    if latest_user_turn is None:
        return [{"role": item["role"], "content": item["content"]} for item in server_history]

    latest_id = latest_user_turn.get("message_id") or ""
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in server_history
        if not latest_id or item.get("message_id") != latest_id
    ]
    return [*history, latest_user_turn]


class ConversationTurnLimiter:
    """In-process sliding-window cap on AI replies per conversation."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._turns: Dict[str, deque[float]] = {}

    def allow(self, conversation_id: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        turns = self._turns.setdefault(conversation_id, deque())
        while turns and current - turns[0] >= self._window:
            turns.popleft()
        if len(turns) >= self._limit:
            return False
        turns.append(current)
        # Drop idle conversations so the map stays bounded by active ones.
        for key in [key for key, value in self._turns.items() if not value]:
            self._turns.pop(key, None)
        return True


collaborative_turn_limiter = ConversationTurnLimiter(
    COLLABORATIVE_TURN_LIMIT, COLLABORATIVE_TURN_WINDOW_SECONDS,
)
