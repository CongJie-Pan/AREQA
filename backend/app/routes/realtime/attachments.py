"""HTTP routes for realtime attachments."""

from __future__ import annotations

from fastapi import APIRouter
from auth import get_optional_current_user
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import UploadFile
from typing import Any
from typing import List
from services.realtime import attachments as attachment_service

router = APIRouter()


@router.post("/api/v1/realtime/attachments")
async def upload_realtime_attachments(
    conversation_id: str = Form(...),
    attachments: List[UploadFile] = File(...),
    current_user_id: str | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Validate the HTTP request and delegate to the attachments service."""
    return await attachment_service.upload_realtime_attachments(conversation_id=conversation_id, attachments=attachments, current_user_id=current_user_id)
