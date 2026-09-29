"""Execute model-selected generation within the authenticated chat stream."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, AsyncGenerator

from services.generated_image_quota import consume_image_quota
from services.generated_image_service import generated_image_block, generate_teaching_image, prepare_image_reference

logger = logging.getLogger(__name__)
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": (
            "Create a new image when the user requests image generation or an image edit, "
            "including requests based on uploaded material or prior conversation. "
            "For explaining, analyzing, reading or discussing an existing image, answer normally. "
            "If the intended operation is ambiguous, ask the user instead of calling this tool. "
            "Call at most once per turn. Do not announce completion or add a text preamble; "
            "the tool displays its own loading state and image."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "maxLength": 1800, "minLength": 3,
                           "description": "A faithful drawing request based on the user's instructions and relevant conversation. Preserve requested style, layout, facts, and the user's language for all image labels."},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
}


async def stream_generated_image(*, arguments: str, user_id: str, conversation_id: str,
                                 language: str, attachments: list[Any], request: Any,
                                 latest_request: str) -> AsyncGenerator[dict, None]:
    """Emit one pending card and its result; cancellation never publishes late results.

    Image generation uses the dedicated image quota, rather than the short
    retrieval budget. Attachments have already been validated by the stream route.
    """
    image_id = uuid.uuid4().hex
    block = {"type": "image_block", "slotId": image_id, "provider": "generated_image",
             "purpose": "diagram", "status": "pending", "imageUrl": "", "caption": "",
             "safetyStatus": "unavailable", "matchConfidence": 0}
    task = None
    try:
        if not user_id or user_id.startswith("guest:"):
            raise PermissionError("Authentication required")
        if not SAFE_ID.fullmatch(conversation_id):
            raise ValueError("Invalid conversation identifier")
        payload = json.loads(arguments)
        prompt = payload.get("prompt") if isinstance(payload, dict) else None
        if not isinstance(prompt, str) or not 3 <= len(prompt.strip()) <= 1800:
            raise ValueError("Invalid drawing request")
        if await request.is_disconnected():
            return
        if not await consume_image_quota(user_id):
            raise PermissionError("Image quota exhausted")
        # The chat model compiles the full turn and conversation into the bounded drawing specification.
        drawing_request = prompt.strip()
        block["generationRequest"] = {
            "prompt": drawing_request, "language": language,
            "requiresReference": bool(attachments),
        }
        yield block
        logger.info("chat.image_tool_started conversation_id=%s attachment_count=%s", conversation_id, len(attachments))

        async def generate():
            brief = ""
            if attachments:
                if not await consume_image_quota(f"{user_id}:reference"):
                    raise PermissionError("Reference quota exhausted")
                brief = await prepare_image_reference(attachments, request=latest_request, language=language, conversation_id=conversation_id)
            result = await generate_teaching_image(drawing_request, language=language, user_id=user_id,
                                                   conversation_id=conversation_id, image_id=image_id, reference_brief=brief)
            return generated_image_block(result, image_id=image_id, prompt=drawing_request, language=language, reference_brief=brief)

        task = asyncio.create_task(generate())
        while not task.done():
            await asyncio.wait([task], timeout=1.0)
            if await request.is_disconnected():
                return
            if not task.done():
                # The caller converts this to an SSE heartbeat, not fabricated progress.
                yield {"heartbeat": True}
        resolved = await task
        if not await request.is_disconnected():
            logger.info("chat.image_tool_completed conversation_id=%s", conversation_id)
            yield resolved
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("chat.image_tool_failed conversation_id=%s reason=%s", conversation_id, type(exc).__name__)
        yield {**block, "status": "error", "caption": "圖片未完成，請確認登入狀態或稍後重試。"}
    finally:
        if task is not None and not task.done():
            logger.info("chat.image_tool_cancelled conversation_id=%s", conversation_id)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
