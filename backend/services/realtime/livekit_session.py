"""Own realtime livekit session behavior independently of route registration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from config import settings
from fastapi import HTTPException
from services.realtime.diagnostics import _live_tutor_debug_logs_enabled
from services.realtime.livekit_metadata import (
    _livekit_avatar_agent_metadata,
    _livekit_avatar_memory_items,
    _livekit_avatar_room_name,
    _livekit_avatar_session_id,
    _livekit_participant_identity,
)
from services.realtime.models import (
    LiveKitAvatarSessionRequest,
    LiveKitAvatarSessionResponse,
)
from services.tutor_profile_service import normalize_tutor_profile

logger = logging.getLogger("backend.main")

async def create_livekit_avatar_session(
    payload: LiveKitAvatarSessionRequest,
    current_user_id: str | None = None,
) -> LiveKitAvatarSessionResponse:
    """Mint a LiveKit room token for optional Anam avatar mode.

    Args:
        payload: Language and correlation metadata from the browser.
        current_user_id: Optional authenticated user from Supabase JWT.

    Returns:
        LiveKit URL, short-lived participant token, room name, participant
        identity, target agent name, and token TTL.

    Raises:
        HTTPException: If avatar mode is disabled, LiveKit credentials are
            missing, the LiveKit SDK is not installed, or token construction
            fails.

    Side Effects:
        Emits safe structured logs with room, auth state, agent name, TTL, and
        elapsed time. The signed token and provider secrets are never logged.

    Compatibility:
        The token embeds a room agent dispatch so a deployed LiveKit agent named
        by ``settings.livekit_agent_name`` can join the room. The existing
        OpenAI-direct Realtime route remains the fallback when this endpoint is
        unavailable.
    """

    started_at = time.time()
    if not settings.enable_livekit_avatar_mode:
        logger.info(
            "livekit.avatar_session_skipped reason=feature_disabled conversation_id=%s authenticated=%s",
            payload.conversation_id,
            bool(current_user_id),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LIVEKIT_AVATAR_DISABLED",
                "message": "LiveKit avatar mode is disabled.",
            },
        )

    livekit_url = settings.livekit_url.strip()
    api_key = settings.livekit_api_key.strip()
    api_secret = settings.livekit_api_secret.strip()
    agent_name = settings.livekit_agent_name.strip() or "areqa-live-tutor"
    ttl_seconds = max(60, min(int(settings.livekit_avatar_token_ttl_seconds), 3600))
    missing = [
        name
        for name, value in {
            "LIVEKIT_URL": livekit_url,
            "LIVEKIT_API_KEY": api_key,
            "LIVEKIT_API_SECRET": api_secret,
        }.items()
        if not value
    ]
    if missing:
        logger.warning(
            "livekit.avatar_session_config_missing conversation_id=%s authenticated=%s missing=%s",
            payload.conversation_id,
            bool(current_user_id),
            ",".join(missing),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LIVEKIT_CONFIG_MISSING",
                "message": "LiveKit avatar mode is not configured.",
            },
        )

    try:
        from livekit import api as livekit_api
    except ImportError as exc:
        logger.exception(
            "livekit.avatar_session_sdk_missing conversation_id=%s",
            payload.conversation_id,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "LIVEKIT_SDK_MISSING",
                "message": "LiveKit server SDK is not installed.",
            },
        ) from exc

    session_id = _livekit_avatar_session_id()
    room_name = _livekit_avatar_room_name(payload.conversation_id, session_id)
    participant_identity = _livekit_participant_identity(current_user_id, payload.conversation_id)
    memory_items = await _livekit_avatar_memory_items(current_user_id, payload.conversation_id)
    metadata = _livekit_avatar_agent_metadata(
        payload, session_id=session_id, memory_items=memory_items,
        participant_identity=participant_identity,
    )

    try:
        room_config = livekit_api.RoomConfiguration(
            agents=[
                livekit_api.RoomAgentDispatch(
                    agent_name=agent_name,
                    metadata=metadata,
                )
            ]
        )
        token = (
            livekit_api.AccessToken(api_key, api_secret)
            .with_identity(participant_identity)
            .with_name("AREQA Learner")
            .with_ttl(timedelta(seconds=ttl_seconds))
            .with_grants(
                livekit_api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .with_room_config(room_config)
            .to_jwt()
        )
    except Exception as exc:
        logger.exception(
            "livekit.avatar_session_token_failed conversation_id=%s room_name=%s agent_name=%s reason=%s",
            payload.conversation_id,
            room_name,
            agent_name,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "LIVEKIT_TOKEN_FAILED",
                "message": "Unable to create LiveKit avatar session.",
            },
        ) from exc

    if _live_tutor_debug_logs_enabled():
        logger.info(
            "livekit.debug.avatar_session_token_created conversation_id=%s session_id=%s room_name=%s agent_name=%s authenticated=%s ttl_seconds=%s supplied_message_count=%s memory_count=%s elapsed_ms=%s",
            payload.conversation_id,
            session_id,
            room_name,
            agent_name,
            bool(current_user_id),
            ttl_seconds,
            len(payload.messages),
            len(memory_items),
            int((time.time() - started_at) * 1000),
        )
    logger.info(
        "livekit.avatar_session_created conversation_id=%s session_id=%s room_name=%s agent_name=%s authenticated=%s tutor_profile=%s elapsed_ms=%s",
        payload.conversation_id,
        session_id,
        room_name,
        agent_name,
        bool(current_user_id),
        normalize_tutor_profile(payload.tutor_profile),
        int((time.time() - started_at) * 1000),
    )
    return LiveKitAvatarSessionResponse(
        livekit_url=livekit_url,
        token=token,
        room_name=room_name,
        participant_identity=participant_identity,
        agent_name=agent_name,
        session_id=session_id,
        expires_in=ttl_seconds,
    )
