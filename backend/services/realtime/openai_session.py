"""Own realtime openai session behavior independently of route registration."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException
from services.realtime.constants import REALTIME_CLIENT_SECRET_URL
from services.realtime.diagnostics import (
    _realtime_debug_logs_enabled,
    _realtime_upstream_error,
    _safe_realtime_user_identifier,
)
from services.realtime.models import RealtimeSessionRequest
from services.realtime.session_config import _build_realtime_session_config
from services.tutor_profile_service import normalize_tutor_profile

logger = logging.getLogger("backend.main")

def _client_secret_from_response(payload: dict[str, Any]) -> tuple[str, str | None]:
    """Extract a short-lived client secret from OpenAI's response shape.

    Args:
        payload: JSON body returned by OpenAI.

    Returns:
        Tuple of secret value and optional expiration value.

    Raises:
        ValueError: If the expected client secret is missing.

    Compatibility:
        OpenAI's WebRTC ephemeral-token examples return the token at root
        `value`. Older or alternate shapes may include `client_secret.value`.
        Accepting both keeps the route compatible without exposing the raw
        upstream payload in logs.
    """

    root_value = payload.get("value")
    if isinstance(root_value, str) and root_value:
        expires_at = payload.get("expires_at")
        return root_value, str(expires_at) if expires_at is not None else None

    client_secret = payload.get("client_secret")
    if not isinstance(client_secret, dict):
        raise ValueError("missing_client_secret")
    value = client_secret.get("value")
    if not isinstance(value, str) or not value:
        raise ValueError("missing_client_secret_value")
    expires_at = client_secret.get("expires_at")
    return value, str(expires_at) if expires_at is not None else None


async def create_realtime_session(
    payload: RealtimeSessionRequest,
    current_user_id: str | None = None,
) -> dict[str, Any]:
    """Mint a short-lived OpenAI Realtime client secret for the browser.

    Args:
        payload: Realtime model, voice, and conversation metadata.
        current_user_id: Optional authenticated user from Supabase JWT.

    Returns:
        Browser-safe Realtime connection metadata.

    Raises:
        HTTPException: For missing configuration, invalid model, OpenAI
            validation failures, or upstream connectivity errors.

    Side Effects:
        Emits structured logs using `realtime.session_*` event names. Logs only
        include safe metadata: auth state, conversation id, model, voice, status,
        and latency. API keys, client secrets, prompts, and transcript text are
        never logged.
    """

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "realtime.session_config_missing conversation_id=%s authenticated=%s",
            payload.conversation_id,
            bool(current_user_id),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_API_KEY_MISSING",
                "message": "OpenAI Realtime is not configured.",
            },
        )

    session_config = _build_realtime_session_config(payload)
    started_at = time.time()
    if _realtime_debug_logs_enabled():
        logger.info(
            "realtime.debug.session_config_built conversation_id=%s model=%s voice=%s interface_language=%s output_modalities=%s input_transcription_model=%s turn_detection_type=%s tool_count=%s tool_names=%s",
            payload.conversation_id,
            session_config["model"],
            session_config["audio"]["output"]["voice"],
            payload.interface_language,
            ",".join(session_config.get("output_modalities", [])),
            session_config["audio"]["input"]["transcription"].get("model"),
            session_config["audio"]["input"]["turn_detection"].get("type"),
            len(session_config.get("tools", [])),
            ",".join(tool.get("name", "") for tool in session_config.get("tools", [])),
        )
    logger.info(
        "realtime.session_create_started conversation_id=%s authenticated=%s model=%s voice=%s interface_language=%s tutor_profile=%s",
        payload.conversation_id,
        bool(current_user_id),
        session_config["model"],
        session_config["audio"]["output"]["voice"],
        payload.interface_language,
        normalize_tutor_profile(payload.tutor_profile),
    )
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        safety_identifier = _safe_realtime_user_identifier(current_user_id)
        if safety_identifier:
            headers["OpenAI-Safety-Identifier"] = safety_identifier
        if _realtime_debug_logs_enabled():
            logger.info(
                "realtime.debug.upstream_request_prepared conversation_id=%s authenticated=%s has_safety_identifier=%s timeout_seconds=%s",
                payload.conversation_id,
                bool(current_user_id),
                bool(safety_identifier),
                15.0,
            )
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                REALTIME_CLIENT_SECRET_URL,
                headers=headers,
                json={"session": session_config},
            )
        if _realtime_debug_logs_enabled():
            logger.info(
                "realtime.debug.upstream_response_received conversation_id=%s status=%s elapsed_ms=%s",
                payload.conversation_id,
                response.status_code,
                int((time.time() - started_at) * 1000),
            )
        if response.status_code >= 400:
            # Stable event: realtime.session_create_failed. Metadata is limited
            # to correlation ids, upstream status, and latency; no secrets,
            # prompts, transcripts, or provider response bodies are logged.
            logger.warning(
                "realtime.session_create_failed conversation_id=%s status=%s elapsed_ms=%s",
                payload.conversation_id,
                response.status_code,
                int((time.time() - started_at) * 1000),
            )
            raise _realtime_upstream_error(response.status_code)
        secret_value, expires_at = _client_secret_from_response(response.json())
        if _realtime_debug_logs_enabled():
            logger.info(
                "realtime.debug.client_secret_issued conversation_id=%s expires_at_present=%s client_secret_present=%s",
                payload.conversation_id,
                bool(expires_at),
                bool(secret_value),
            )
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        logger.exception(
            "realtime.session_create_unavailable conversation_id=%s reason=%s",
            payload.conversation_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "OPENAI_REALTIME_UNAVAILABLE",
                "message": "OpenAI Realtime is temporarily unavailable.",
            },
        ) from exc

    logger.info(
        "realtime.session_create_completed conversation_id=%s model=%s interface_language=%s elapsed_ms=%s",
        payload.conversation_id,
        session_config["model"],
        payload.interface_language,
        int((time.time() - started_at) * 1000),
    )
    return {
        "client_secret": secret_value,
        "model": session_config["model"],
        "voice": session_config["audio"]["output"]["voice"],
        "expires_at": expires_at,
    }
