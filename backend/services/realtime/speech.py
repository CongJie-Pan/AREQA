"""Own realtime speech behavior independently of route registration."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Literal

import httpx
from fastapi import HTTPException, UploadFile
from fastapi.responses import Response
from services.realtime.constants import (
    MAX_SPEECH_AUDIO_BYTES,
    OPENAI_AUDIO_SPEECH_URL,
    OPENAI_AUDIO_TRANSCRIPTIONS_URL,
    SPEECH_READ_MODEL,
    SPEECH_READ_VOICE,
    SPEECH_TRANSCRIPTION_MODEL,
)
from services.realtime.diagnostics import _safe_realtime_user_identifier
from services.realtime.models import SpeechReadRequest
from services.realtime.session_config import _build_speech_transcription_prompt

logger = logging.getLogger("backend.main")

async def _read_bounded_upload(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an uploaded audio file while enforcing a hard byte limit."""

    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "SPEECH_AUDIO_TOO_LARGE",
                "message": "Speech audio is too large.",
            },
        )
    if not data:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SPEECH_AUDIO_EMPTY",
                "message": "Speech audio is empty.",
            },
        )
    return data


async def transcribe_speech(
    file: UploadFile,
    interface_language: Literal["zh-TW", "zh-CN", "en"] = "zh-TW",
    current_user_id: str | None = None,
) -> dict[str, str]:
    """Transcribe a short composer dictation clip with OpenAI audio models.

    Args:
        file: Browser-recorded audio clip.
        interface_language: UI language used only for script/style hints.
        current_user_id: Optional authenticated user from Supabase JWT.

    Returns:
        Trimmed transcript text.

    Raises:
        HTTPException: For missing OpenAI configuration, invalid uploads, or
            upstream provider failures.
    """

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("speech.transcription_config_missing authenticated=%s", bool(current_user_id))
        raise HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_API_KEY_MISSING",
                "message": "OpenAI speech transcription is not configured.",
            },
        )

    audio_bytes = await _read_bounded_upload(file, MAX_SPEECH_AUDIO_BYTES)
    filename = file.filename or "speech.webm"
    content_type = file.content_type or "audio/webm"
    started_at = time.time()
    logger.info(
        "speech.transcription_started authenticated=%s bytes=%s content_type=%s",
        bool(current_user_id),
        len(audio_bytes),
        content_type,
    )
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        safety_identifier = _safe_realtime_user_identifier(current_user_id)
        if safety_identifier:
            headers["OpenAI-Safety-Identifier"] = safety_identifier
        data = {
            "model": SPEECH_TRANSCRIPTION_MODEL,
            "response_format": "json",
            "prompt": _build_speech_transcription_prompt(interface_language),
        }
        files = {
            "file": (filename, audio_bytes, content_type),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENAI_AUDIO_TRANSCRIPTIONS_URL,
                headers=headers,
                data=data,
                files=files,
            )
        if response.status_code >= 400:
            logger.warning(
                "speech.transcription_failed status=%s elapsed_ms=%s",
                response.status_code,
                int((time.time() - started_at) * 1000),
            )
            raise HTTPException(
                status_code=429 if response.status_code == 429 else 503,
                detail={
                    "code": "OPENAI_SPEECH_TRANSCRIPTION_FAILED",
                    "message": "Unable to transcribe speech.",
                },
            )
        payload = response.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
        logger.exception("speech.transcription_unavailable reason=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_SPEECH_TRANSCRIPTION_UNAVAILABLE",
                "message": "OpenAI speech transcription is temporarily unavailable.",
            },
        ) from exc

    text = str(payload.get("text", "")).strip()
    logger.info(
        "speech.transcription_completed authenticated=%s chars=%s elapsed_ms=%s",
        bool(current_user_id),
        len(text),
        int((time.time() - started_at) * 1000),
    )
    return {"text": text}


async def read_speech(
    payload: SpeechReadRequest,
    current_user_id: str | None = None,
) -> Response:
    """Generate an MP3 read-out for assistant-authored text.

    Args:
        payload: Bounded speakable text prepared by the frontend.
        current_user_id: Optional authenticated user from Supabase JWT.

    Returns:
        MP3 audio bytes suitable for direct browser playback.

    Raises:
        HTTPException: For missing OpenAI configuration, empty text, or
            upstream provider failures.
    """

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("speech.read_config_missing authenticated=%s", bool(current_user_id))
        raise HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_API_KEY_MISSING",
                "message": "OpenAI speech generation is not configured.",
            },
        )

    text = payload.text.strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SPEECH_READ_TEXT_REQUIRED",
                "message": "Text is required.",
            },
        )

    started_at = time.time()
    logger.info(
        "speech.read_started authenticated=%s model=%s voice=%s chars=%s",
        bool(current_user_id),
        SPEECH_READ_MODEL,
        SPEECH_READ_VOICE,
        len(text),
    )
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        safety_identifier = _safe_realtime_user_identifier(current_user_id)
        if safety_identifier:
            headers["OpenAI-Safety-Identifier"] = safety_identifier

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                OPENAI_AUDIO_SPEECH_URL,
                headers=headers,
                json={
                    "model": SPEECH_READ_MODEL,
                    "voice": SPEECH_READ_VOICE,
                    "input": text,
                    "response_format": "mp3",
                    "instructions": "Read clearly in a warm, natural tutoring tone.",
                },
            )
        if response.status_code >= 400:
            logger.warning(
                "speech.read_failed status=%s elapsed_ms=%s",
                response.status_code,
                int((time.time() - started_at) * 1000),
            )
            raise HTTPException(
                status_code=429 if response.status_code == 429 else 503,
                detail={
                    "code": "OPENAI_SPEECH_READ_FAILED",
                    "message": "Unable to generate speech.",
                },
            )
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        logger.exception("speech.read_unavailable reason=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_SPEECH_READ_UNAVAILABLE",
                "message": "OpenAI speech generation is temporarily unavailable.",
            },
        ) from exc

    logger.info(
        "speech.read_completed authenticated=%s bytes=%s elapsed_ms=%s",
        bool(current_user_id),
        len(response.content),
        int((time.time() - started_at) * 1000),
    )
    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "audio/mpeg"),
        headers={"Cache-Control": "no-store"},
    )
