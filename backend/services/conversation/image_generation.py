"""Execute model-selected generation within the authenticated chat stream."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
import base64
import hashlib
from typing import Any, AsyncGenerator, Literal, Mapping
from pydantic import BaseModel, ConfigDict, Field

from config import settings
from core import ToolBudget, ToolBudgetTracker
from tools import ToolDefinition, ToolRegistry
from services.generated_image_quota import consume_image_quota
from services.generated_image_service import generated_image_block, generate_teaching_image, prepare_image_reference

logger = logging.getLogger(__name__)
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
class ImageToolInput(BaseModel):
    """Public drawing arguments; authorization and filesystem context are server-owned."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    prompt: str = Field(min_length=3, max_length=1800, description="Faithfully compile the user's full drawing request and relevant context. Preserve facts, style, layout, and label language.")
    presentation: Literal["image_only", "text_and_image"] = Field(default="image_only", description="Use text_and_image when the user requests analysis with an image; otherwise image_only.")
    explanation: str = Field(default="", max_length=4000, description="Requested grounded analysis for text_and_image if it has not already been answered; no completion announcement.")
    reference: Literal["none", "current_attachments", "conversation_image"] | None = Field(default=None, description="Select the relevant reference; conversation_image requires its ID from conversation context.")
    reference_image_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


def validate_image_payload(payload: Any) -> dict:
    """Validate model input before quota/provider calls; reject ownership overrides.

    Args:
        payload: Untrusted decoded model arguments.
    Returns:
        Bounded drawing fields with defaults applied.
    Raises:
        ValueError: Invalid or unknown fields, including user IDs and raw URLs.
    """
    return ImageToolInput.model_validate(payload).model_dump(exclude_none=True)


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
        "parameters": ImageToolInput.model_json_schema(),
    },
}


def image_tool_definition() -> ToolDefinition:
    """Register the paid image capability with its own total deadline and run budget."""
    return ToolDefinition(
        name="generate_image", external=True, stream_handler=stream_image_tool_events,
        timeout_seconds=settings.generated_image_tool_timeout_seconds,
        budget_scope="image_generation",
        budget_limits=ToolBudget(max_tool_calls_per_run=1, max_external_calls=1,
                                 max_total_tool_latency_ms=int(settings.generated_image_tool_timeout_seconds * 1000)),
    )


async def stream_image_tool_events(arguments: Mapping[str, Any]) -> AsyncGenerator[dict, None]:
    """Execute a request-scoped image operation and emit safe lifecycle events.

    Args:
        arguments: Tool payload plus server-owned user, conversation, reference
            and cancellation context. Model arguments cannot supply these values.

    Yields:
        Pending blocks, factual phase transitions, and a terminal image or error.
        Cost metadata is returned only with the terminal result.

    Side Effects:
        Charges dedicated quotas, calls reference/image providers and private storage.
        Logs correlation IDs and exception classes without request or response text.
    """
    user_id = arguments["user_id"]
    conversation_id = arguments["conversation_id"]
    language = arguments.get("language", "zh-TW")
    request = arguments.get("request")
    attachments = arguments.get("attachments", [])
    image_id = arguments.get("image_id") or uuid.uuid4().hex
    block = {"type": "image_block", "slotId": image_id, "provider": "generated_image",
             "purpose": "diagram", "status": "pending", "imageUrl": "", "caption": "",
             "safetyStatus": "unavailable", "matchConfidence": 0}
    task = phase_task = None
    try:
        if not user_id or user_id.startswith("guest:"):
            raise PermissionError("Authentication required")
        if not SAFE_ID.fullmatch(conversation_id) or not SAFE_ID.fullmatch(image_id):
            raise ValueError("Invalid identifier")
        payload = validate_image_payload(arguments["payload"])
        prompt = payload["prompt"]
        if payload.get("reference") == "none":
            attachments = []
        elif payload.get("reference") == "current_attachments" and not attachments:
            raise ValueError("Missing attachments")
        elif payload.get("reference") == "conversation_image":
            from services.attachments.storage import AttachmentImageStorageService
            from services.attachments.parsing import ProcessedAttachment
            reference_id = payload.get("reference_image_id")
            if not reference_id:
                raise ValueError("Missing image reference")
            # Storage derives the object path from the authenticated owner and current conversation.
            png = await AttachmentImageStorageService().download_generated_image(
                user_id=user_id, conversation_id=conversation_id, image_id=reference_id)
            if png is None:
                raise ValueError("Reference image unavailable")
            attachments = [ProcessedAttachment(
                filename="generated-reference.png", media_type="image/png", size_bytes=len(png),
                sha256=hashlib.sha256(png).hexdigest(),
                content_part={"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
            )]
        if request and await request.is_disconnected():
            return
        block["generationRequest"] = {"prompt": prompt.strip(), "language": language,
                                      "requiresReference": bool(attachments)}
        if not await consume_image_quota(user_id):
            raise PermissionError("Image quota exhausted")
        yield {"state": "accepted", "block": block}
        phases = asyncio.Queue()

        async def generate():
            brief = arguments.get("reference_brief", "")
            if not isinstance(brief, str) or len(brief) > 4000:
                raise ValueError("Invalid reference brief")
            if attachments:
                phases.put_nowait("preparing_reference")
                if not await consume_image_quota(f"{user_id}:reference"):
                    raise PermissionError("Reference quota exhausted")
                brief = await prepare_image_reference(attachments, request=arguments.get("latest_request", prompt), language=language, conversation_id=conversation_id)
            # Publish the reusable brief before provider work so cancellation remains retryable.
            block["generationRequest"]["referenceBrief"] = brief
            phases.put_nowait("generating")
            result = await generate_teaching_image(prompt.strip(), language=language, user_id=user_id,
                conversation_id=conversation_id, image_id=image_id, reference_brief=brief,
                conversation_context=arguments.get("conversation_context", ""),
                on_state=phases.put_nowait)
            resolved = generated_image_block(result, image_id=image_id, prompt=prompt.strip(), language=language, reference_brief=brief)
            return {"state": "completed", "block": resolved, "cost_usd": result.cost_usd}

        logger.info("chat.image_tool_started conversation_id=%s attachment_count=%s", conversation_id, len(attachments))
        task = asyncio.create_task(generate())
        phase_task = asyncio.create_task(phases.get())
        while True:
            done, _ = await asyncio.wait([task, phase_task], timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
            if request and await request.is_disconnected():
                return
            if phase_task in done:
                phase = phase_task.result()
                yield {"state": phase, "block": {**block, "generationState": phase}}
                phase_task = asyncio.create_task(phases.get())
            if task in done:
                terminal = await task
                logger.info("chat.image_tool_completed conversation_id=%s", conversation_id)
                yield terminal
                return
            if not done:
                yield {"heartbeat": True}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None) or ("IMAGE_QUOTA_OR_AUTH_ERROR" if isinstance(exc, PermissionError) else "IMAGE_GENERATION_FAILED")
        logger.warning("chat.image_tool_failed conversation_id=%s reason=%s code=%s", conversation_id, type(exc).__name__, code)
        yield {"state": "failed", "reason": type(exc).__name__, "code": code,
               "block": {**block, "status": "error", "caption": code}}
    finally:
        pending = [item for item in (task, phase_task) if item is not None]
        for item in pending:
            if not item.done():
                item.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def stream_generated_image(*, arguments: str, user_id: str, conversation_id: str,
                                 language: str, attachments: list[Any], request: Any,
                                 latest_request: str, registry: ToolRegistry | None = None,
                                 budget: ToolBudgetTracker | None = None,
                                 tool_call_id: str | None = None) -> AsyncGenerator[dict, None]:
    """Adapt common tool events to the legacy image stream and stable SSE identity.

    The caller owns presentation. Invalid JSON never reaches quota or providers.
    Registry deadline failures reuse the pending slot rather than orphaning it.
    """
    registry = registry or ToolRegistry()
    if not registry.has("generate_image"):
        registry.register(image_tool_definition())
    budget = budget or ToolBudgetTracker(ToolBudget())
    call_id = tool_call_id or uuid.uuid4().hex
    # Provider call IDs correlate events; only server-minted IDs enter storage paths.
    image_id = uuid.uuid4().hex
    last_block = {"type": "image_block", "slotId": image_id, "provider": "generated_image", "imageUrl": "", "status": "error", "caption": "IMAGE_GENERATION_FAILED"}
    try:
        payload = json.loads(arguments)
    except (ValueError, TypeError):
        yield last_block
        return
    async for event in registry.stream("generate_image", {
        "payload": payload, "user_id": user_id, "conversation_id": conversation_id,
        "language": language, "attachments": attachments, "request": request,
        "latest_request": latest_request, "image_id": image_id,
    }, budget):
        state = event.get("state")
        if state:
            yield {"tool_state": {"tool_call_id": call_id, "tool": "generate_image", "state": state}}
        if event.get("heartbeat"):
            yield {"heartbeat": True}
        elif event.get("block"):
            last_block = event["block"]
            yield last_block
        elif state == "failed":
            yield {**last_block, "status": "error", "caption": "IMAGE_GENERATION_FAILED"}
