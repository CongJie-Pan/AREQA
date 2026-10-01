"""Own realtime diagnostics behavior independently of route registration."""

from __future__ import annotations

import hashlib

from config import settings
from fastapi import HTTPException


def _realtime_debug_logs_enabled() -> bool:
    """Return whether detailed OpenAI Realtime diagnostics should be emitted.

    Returns:
        True when backend settings allow safe Realtime debug logs.

    Side Effects:
        None.

    Compatibility:
        This guards only verbose operational diagnostics. Warnings and errors
        remain unguarded so provider failures are still visible in production.
    """

    return bool(settings.enable_realtime_debug_logs)


def _live_tutor_debug_logs_enabled() -> bool:
    """Return whether detailed AREQA Live Tutor diagnostics should be emitted.

    Returns:
        True when backend settings allow safe Live Tutor debug logs.

    Side Effects:
        None.

    Compatibility:
        The Live Tutor switch covers AREQA app-side context assembly and
        tutoring-session metadata, not provider credentials or transcript text.
    """

    return bool(settings.enable_live_tutor_debug_logs)


def _safe_realtime_user_identifier(user_id: str | None) -> str | None:
    """Return a privacy-preserving identifier for OpenAI safety telemetry.

    Args:
        user_id: Authenticated internal user id, when available.

    Returns:
        A stable SHA-256 digest prefix suitable for provider-side abuse
        monitoring, or None for anonymous requests.

    Compatibility:
        The raw application user id is never logged or sent to OpenAI. Guest
        calls omit the header because there is no stable server-owned id.
    """

    if not user_id:
        return None
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def _realtime_upstream_error(status_code: int) -> HTTPException:
    """Map OpenAI Realtime failures to client-safe FastAPI errors.

    Args:
        status_code: HTTP status returned by OpenAI.

    Returns:
        An HTTPException with a stable AREQA error code and a status that keeps
        retryable rate-limit failures distinct from backend/provider outages.

    Side Effects:
        None. Callers are responsible for structured logging with safe metadata.
    """

    if status_code == 429:
        return HTTPException(
            status_code=429,
            detail={
                "code": "OPENAI_REALTIME_RATE_LIMITED",
                "message": "OpenAI Realtime is rate limited. Please wait and try again.",
            },
        )
    if status_code in {401, 403}:
        return HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_REALTIME_AUTH_FAILED",
                "message": "OpenAI Realtime access is not available for this server configuration.",
            },
        )
    if status_code >= 500:
        return HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_REALTIME_UNAVAILABLE",
                "message": "OpenAI Realtime is temporarily unavailable.",
            },
        )
    return HTTPException(
        status_code=502,
        detail={
            "code": "OPENAI_REALTIME_SESSION_FAILED",
            "message": "Unable to create realtime session.",
        },
    )
