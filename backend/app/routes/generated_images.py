"""Authenticated image generation endpoint for text and live voice surfaces."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from services.generated_image_service import generate_teaching_image

router = APIRouter()
logger = logging.getLogger(__name__)
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class GenerateImageRequest(BaseModel):
    """Bounded request shared by text composer and Live Tutor."""

    prompt: str = Field(min_length=3, max_length=1800)
    conversation_id: str = Field(min_length=1, max_length=128)
    interface_language: Literal["zh-TW", "zh-CN", "en"] = "zh-TW"


@router.post("/api/v1/images/generate")
async def generate_image_endpoint(
    payload: GenerateImageRequest, current_user_id: str = Depends(get_current_user),
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
    image_id = uuid.uuid4().hex
    try:
        result = await generate_teaching_image(
            payload.prompt, language=payload.interface_language,
            conversation_id=payload.conversation_id, image_id=image_id,
        )
    except (RuntimeError, ValueError) as error:
        logger.warning(
            "image_generation.request_failed conversation_id=%s user_id=%s reason=%s",
            payload.conversation_id, current_user_id, type(error).__name__,
        )
        raise HTTPException(status_code=503, detail="Image generation is unavailable") from error

    return {
        "block": {
            "type": "image_block", "slotId": image_id, "topic": result.caption,
            "purpose": "diagram", "imageUrl": result.image_url,
            "thumbnailUrl": result.image_url, "sourceUrl": "",
            "sourceDomain": "", "caption": result.caption,
            "provider": "generated_image", "model": result.model,
            "safetyStatus": "pass", "matchConfidence": 1.0,
            "transient": result.transient,
            "storageBucket": result.storage_bucket,
            "storagePath": result.storage_path,
            "storageExpiresAt": result.storage_expires_at,
            "visionSummary": result.vision_summary,
            "howToRead": list(result.how_to_read),
            "explanatoryCaption": result.vision_summary,
        },
        "cost_usd": result.cost_usd,
    }
