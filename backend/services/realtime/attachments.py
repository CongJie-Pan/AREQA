"""Own realtime attachments behavior independently of route registration."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, List

from fastapi import HTTPException, UploadFile

logger = logging.getLogger("backend.main")

async def upload_realtime_attachments(
    conversation_id: str,
    attachments: List[UploadFile],
    current_user_id: str | None = None,
) -> dict[str, Any]:
    """Prepare text or PDF source material without starting a chat response."""

    if not conversation_id or len(conversation_id) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", conversation_id):
        raise HTTPException(status_code=422, detail="Invalid conversation id")
    from services.attachments.parsing import process_attachments
    from services.realtime.speaking_material import (
        extract_material,
        save_material,
        voice_excerpt,
    )

    processed = await process_attachments(attachments, conversation_id=conversation_id)
    if any(item.media_type not in {"text/plain", "text/markdown", "application/pdf"} for item in processed):
        raise HTTPException(status_code=422, detail="Voice attachment upload supports text and text-based PDF files")
    material = extract_material(processed)
    if not material:
        raise HTTPException(status_code=422, detail="Voice can currently read text and text-based PDF attachments")
    material["version"] = uuid.uuid4().hex
    if not await save_material(current_user_id, conversation_id, material):
        raise HTTPException(status_code=503, detail="Attachment could not be prepared for voice")
    excerpt = voice_excerpt(material)
    logger.info(
        "realtime.attachments_ready conversation_id=%s count=%s excerpt_chars=%s truncated=%s",
        conversation_id,
        len(processed),
        len(excerpt["text"]),
        excerpt["truncated"],
    )
    return {"conversation_id": conversation_id, "version": material["version"], "material": excerpt}
