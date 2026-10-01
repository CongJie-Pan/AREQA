"""HTTP routes for realtime sessions."""

from __future__ import annotations

from fastapi import APIRouter
from auth import get_optional_current_user
from fastapi import Depends
from services.realtime.models import LiveKitAvatarSessionRequest
from services.realtime.models import LiveKitAvatarSessionResponse
from services.realtime.models import RealtimeSessionRequest
from typing import Any
from services.realtime import livekit_session
from services.realtime import openai_session

router = APIRouter()


@router.post("/api/v1/realtime/livekit-avatar-session", response_model=LiveKitAvatarSessionResponse)
async def create_livekit_avatar_session(
    payload: LiveKitAvatarSessionRequest,
    current_user_id: str | None = Depends(get_optional_current_user),
) -> LiveKitAvatarSessionResponse:
    """Validate the HTTP request and delegate to the livekit session service."""
    return await livekit_session.create_livekit_avatar_session(payload=payload, current_user_id=current_user_id)


@router.post("/api/v1/realtime/session")
async def create_realtime_session(
    payload: RealtimeSessionRequest,
    current_user_id: str | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Validate the HTTP request and delegate to the openai session service."""
    return await openai_session.create_realtime_session(payload=payload, current_user_id=current_user_id)
