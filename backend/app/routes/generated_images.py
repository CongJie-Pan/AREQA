"""Authenticated image generation endpoint for text and live voice surfaces."""

from __future__ import annotations

import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from auth import get_current_user
from config import settings
from services.attachments.storage import AttachmentImageStorageService
from services.generated_image_quota import consume_image_quota
from services.message_intent_service import MessageIntentRequest, MessageIntent, classify_message_intent
from services.generated_image_service import prepare_image_reference

router = APIRouter()
logger = logging.getLogger(__name__)
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class GenerateImageRequest(BaseModel):
    """Bounded request shared by text composer and Live Tutor."""

    prompt: str = Field(min_length=3, max_length=1800)
    conversation_id: str = Field(min_length=1, max_length=128)
    interface_language: Literal["zh-TW", "zh-CN", "en"] = "zh-TW"
    reference_brief: str = Field(default="", max_length=4000)
    conversation_context: str = Field(default="", max_length=2000)


@router.post("/api/v1/images/intent")
async def message_intent_endpoint(
    payload: MessageIntentRequest, current_user_id: str = Depends(get_current_user),
) -> MessageIntent:
    """Classify an authenticated send with a separate per-user spending quota."""
    if not await consume_image_quota(f"{current_user_id}:intent", limit=30):
        raise HTTPException(status_code=429, detail="Message routing rate limit exceeded")
    try:
        return await classify_message_intent(payload)
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Message routing unavailable") from None


@router.post("/api/v1/images/reference")
async def prepare_image_reference_endpoint(
    prompt: str = Form(..., min_length=3, max_length=1800),
    conversation_id: str = Form(..., min_length=1, max_length=128),
    interface_language: Literal["zh-TW", "zh-CN", "en"] = Form("zh-TW"),
    attachments: list[UploadFile] = File(...),
    current_user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    """Reuse validated attachment parsing before any paid image request."""
    from services.attachment_service import process_attachments

    if not SAFE_ID.fullmatch(conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation identifier")
    if not await consume_image_quota(f"{current_user_id}:reference"):
        raise HTTPException(status_code=429, detail="Image reference rate limit exceeded")
    processed = await process_attachments(attachments, conversation_id=conversation_id)
    if settings.enable_generated_image_debug_logs:
        logger.info("image_generation.reference_received conversation_id=%s attachment_count=%s", conversation_id, len(processed))
    try:
        brief = await prepare_image_reference(processed, request=prompt, language=interface_language, conversation_id=conversation_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="The attachments contain no readable reference material") from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="Image reference preparation is unavailable") from error
    return {"reference_brief": brief}


@router.post("/api/v1/images/generate")
async def generate_image_endpoint(
    payload: GenerateImageRequest, request: Request, current_user_id: str = Depends(get_current_user),
) -> dict[str, object]:
    """Generate one image without exposing OpenRouter or storage credentials.

    Args:
        payload: Validated generation request.
        current_user_id: Authenticated caller, enforced by FastAPI dependency.

    Returns:
        A frontend ImageBlock and optional provider cost metadata.

    Raises:
        HTTPException: Invalid conversation id or unavailable generation.
    """

    if not SAFE_ID.fullmatch(payload.conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation identifier")
    if settings.enable_generated_image_debug_logs:
        logger.info(
            "image_generation.request_received conversation_id=%s language=%s request_chars=%s reference_chars=%s context_chars=%s",
            payload.conversation_id, payload.interface_language, len(payload.prompt), len(payload.reference_brief),
            len(payload.conversation_context),
        )
    from core import ToolBudget, ToolBudgetTracker
    from tools import ToolRegistry
    from services.conversation.image_generation import image_tool_definition

    registry = ToolRegistry()
    registry.register(image_tool_definition())
    result = await registry.execute("generate_image", {
        "payload": {"prompt": payload.prompt, "reference": "none"},
        "user_id": current_user_id, "conversation_id": payload.conversation_id,
        "language": payload.interface_language, "reference_brief": payload.reference_brief,
        "conversation_context": payload.conversation_context,
        "request": request,
    }, ToolBudgetTracker(ToolBudget()))
    if result.status != "ok":
        if result.content.get("reason") == "PermissionError" and settings.enable_generated_image_debug_logs:
            logger.info("image_generation.quota_rejected conversation_id=%s", payload.conversation_id)
        code = result.content.get("code", "IMAGE_GENERATION_FAILED")
        status = (429 if result.content.get("reason") == "PermissionError"
                  else 402 if code == "IMAGE_PROVIDER_HTTP_402" else 503)
        raise HTTPException(status_code=status, detail={"message": "Image generation is unavailable",
                                                        "code": code})
    return {"block": result.content["block"], "cost_usd": result.content.get("cost_usd")}


class RefreshImageRequest(BaseModel):
    """Stable identifiers needed to refresh a generated image's signed URL."""

    conversation_id: str = Field(min_length=1, max_length=128)
    image_id: str = Field(min_length=1, max_length=128)


@router.post("/api/v1/images/refresh")
async def refresh_image_endpoint(
    payload: RefreshImageRequest, current_user_id: str = Depends(get_current_user),
) -> dict[str, object]:
    if not SAFE_ID.fullmatch(payload.conversation_id) or not SAFE_ID.fullmatch(payload.image_id):
        raise HTTPException(status_code=400, detail="Invalid image identifier")
    renewed = await AttachmentImageStorageService().refresh_generated_image_url(
        user_id=current_user_id, conversation_id=payload.conversation_id, image_id=payload.image_id,
    )
    if not renewed:
        raise HTTPException(status_code=404, detail="Image unavailable")
    return {"imageUrl": renewed["url"], "storageExpiresAt": renewed["expires_at"]}


@router.post("/api/v1/images/download")
async def download_image_endpoint(
    payload: RefreshImageRequest, current_user_id: str = Depends(get_current_user),
) -> Response:
    if not SAFE_ID.fullmatch(payload.conversation_id) or not SAFE_ID.fullmatch(payload.image_id):
        raise HTTPException(status_code=400, detail="Invalid image identifier")
    png = await AttachmentImageStorageService().download_generated_image(
        user_id=current_user_id, conversation_id=payload.conversation_id, image_id=payload.image_id,
    )
    if png is None:
        raise HTTPException(status_code=404, detail="Image unavailable")
    return Response(
        content=png, media_type="image/png",
        headers={"Content-Disposition": 'attachment; filename="areqa-image.png"', "Cache-Control": "private, no-store"},
    )
