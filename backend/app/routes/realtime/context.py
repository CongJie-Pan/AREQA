"""HTTP routes for realtime context."""

from __future__ import annotations

from typing import Any

from auth import get_optional_current_user
from fastapi import APIRouter, Depends
from services.realtime import context
from services.realtime.models import RealtimeContextRequest

router = APIRouter()


@router.post("/api/v1/realtime/context")
async def get_realtime_context(
    payload: RealtimeContextRequest,
    current_user_id: str | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Validate the HTTP request and delegate to the context service."""
    return await context.get_realtime_context(payload=payload, current_user_id=current_user_id)
