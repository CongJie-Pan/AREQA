"""HTTP routes for realtime speech."""

from __future__ import annotations

from fastapi import APIRouter
from auth import get_optional_current_user
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import UploadFile
from fastapi.responses import Response
from services.realtime.models import SpeechReadRequest
from typing import Literal
from services.realtime import speech

router = APIRouter()


@router.post("/api/v1/speech/transcribe")
async def transcribe_speech(
    file: UploadFile = File(...),
    interface_language: Literal["zh-TW", "zh-CN", "en"] = Form("zh-TW"),
    current_user_id: str | None = Depends(get_optional_current_user),
) -> dict[str, str]:
    """Validate the HTTP request and delegate to the speech service."""
    return await speech.transcribe_speech(file=file, interface_language=interface_language, current_user_id=current_user_id)


@router.post("/api/v1/speech/read")
async def read_speech(
    payload: SpeechReadRequest,
    current_user_id: str | None = Depends(get_optional_current_user),
) -> Response:
    """Validate the HTTP request and delegate to the speech service."""
    return await speech.read_speech(payload=payload, current_user_id=current_user_id)
