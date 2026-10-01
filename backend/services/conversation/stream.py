"""Own provider streaming and authorized post-response tool execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List

from core import PublicAnswerFilter
from services.conversation.image_generation import stream_generated_image
from services.conversation.image_markers import ImageRequestMarkerFilter
from services.conversation.image_markers import ImageRequestSlot as ImageRequestSlot
from services.conversation.stream_request import (
    _openrouter_session_id as _openrouter_session_id,
)
from services.conversation.stream_request import build_stream_request
from services.conversation.response_boundary import StreamingResponseBoundaryFilter

logger = logging.getLogger(__name__)



def letter_task_id(
    user_id: str,
    conversation_id: str,
    avatar_name: str,
    source_text: str,
) -> str:
    """Build a stable idempotency key without retaining source text."""

    from services.orchestration.intake import normalize_avatar_name

    source_hash = hashlib.sha256(source_text.strip().encode("utf-8")).hexdigest()[:24]
    raw = f"{user_id}|{conversation_id or ''}|{normalize_avatar_name(avatar_name)}|{source_hash}"
    return f"letter-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


class ConversationStreamService:
    """Stream provider output while enforcing filtering and tool boundaries."""

    def __init__(self, client: Any, tool_registry: Any):
        self.client = client
        self.tool_registry = tool_registry

    async def stream(
        self,
        *,
        user_id: str,
        conversation_id: str,
        last_user_msg: str,
        messages: List[Dict[str, Any]],
        force_think: bool,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repetition_penalty: float,
        request: Any,
        tool_budget: Any = None,
        trace: Any = None,
        max_image_slots: int = 2,
        image_attachments: list[Any] | None = None,
        interface_language: str = "zh-TW",
    ) -> AsyncGenerator[str, None]:
        """Yield filtered answer deltas and typed metadata events.

        Args:
            user_id: Current user identifier for authorized tool execution.
            conversation_id: Correlation identifier for privacy-safe logs.
            last_user_msg: Latest user text, retained inside backend boundaries.
            messages: Provider-ready conversation messages.
            force_think: Whether the reasoning-capable model route is enabled.
            max_tokens: Maximum provider completion tokens.
            temperature: Provider sampling temperature.
            top_p: Provider nucleus sampling value.
            repetition_penalty: Provider repetition penalty.
            request: FastAPI request used to detect disconnects.
            tool_budget: Optional foreground tool budget tracker.
            trace: Optional turn latency trace.
            max_image_slots: Maximum image markers accepted for this turn.
                General answers keep the legacy cap of two, while paper
                overviews may allow more preverified PDF figures.

        Yields:
            Legacy-compatible SSE answer chunks, privacy-safe ``image_slot``
            events, and one private accumulator event consumed by orchestration.

        Side Effects:
            Calls the configured model and optional letter tool, and emits
            bounded structured lifecycle logs without raw prompts or markers.
        """

        if not self.client:
            yield f"data: {json.dumps({'choices': [{'delta': {'content': '[System Error] OPENROUTER_API_KEY is missing.'}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            return

        started_at = time.time()
        target_model, extra_body, tools, has_pdf = build_stream_request(
            force_think=force_think, repetition_penalty=repetition_penalty,
            conversation_id=conversation_id, messages=messages,
            interface_language=interface_language, last_user_msg=last_user_msg,
        )
        if tool_budget is None:
            from core import ToolBudget, ToolBudgetTracker

            tool_budget = ToolBudgetTracker(ToolBudget())

        accumulator = ""
        image_marker_filter = ImageRequestMarkerFilter(max_slots=max_image_slots)
        output_filter = PublicAnswerFilter()
        boundary_filter = StreamingResponseBoundaryFilter()
        tool_call_name = ""
        tool_call_args = ""
        tool_calls: dict[int, dict[str, str]] = {}
        generated_blocks: list[dict] = []
        logger.info(
            "orchestration.stream_started conversation_id=%s model=%s attachment_parser=%s image_slot_cap=%s openrouter_session=%s latency_routing=%s",
            conversation_id,
            target_model,
            has_pdf,
            image_marker_filter.max_slots,
            bool(extra_body.get("session_id")),
            bool(extra_body.get("provider")),
        )
        try:
            if trace:
                trace.increment_model_call("main_answer")
                trace.mark_once("main_model_started")
                trace.mark_once("main_model_provider_request_started")
            generation = asyncio.create_task(
                self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    stream=True,
                    max_tokens=max_tokens,
                    temperature=temperature if temperature > 0 else 0.001,
                    top_p=top_p,
                    extra_body=extra_body,
                    tools=tools,
                    tool_choice="auto",
                )
            )
            while not generation.done():
                done, _ = await asyncio.wait([generation], timeout=5.0)
                if not done:
                    yield ": heartbeat\n\n"
            response = await generation
            if trace:
                trace.mark_once("main_model_provider_stream_received")
            async for chunk in response:
                if await request.is_disconnected():
                    logger.info("orchestration.stream_cancelled conversation_id=%s", conversation_id)
                    break
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "tool_calls", None):
                    for call in delta.tool_calls:
                        entry = tool_calls.setdefault(getattr(call, "index", 0), {"name": "", "arguments": "", "id": getattr(call, "id", None) or uuid.uuid4().hex})
                        function = getattr(call, "function", None)
                        if function:
                            entry["name"] += getattr(function, "name", None) or ""
                            entry["arguments"] += getattr(function, "arguments", None) or ""
                    continue
                content = getattr(delta, "content", None) or ""
                if content:
                    content = output_filter.feed(content)
                if content:
                    content, reasons = boundary_filter.feed(content)
                    for reason in reasons:
                        logger.warning(
                            "orchestration.response_boundary_blocked conversation_id=%s reason=%s",
                            conversation_id,
                            reason,
                        )
                if content:
                    content = image_marker_filter.feed(content)
                if content:
                    if trace:
                        trace.mark_once("first_answer_delta")
                    accumulator += content
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': content}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                for slot in image_marker_filter.drain_new_slots():
                    yield f"event: image_slot\ndata: {json.dumps(slot.to_stream_payload(), ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
        except Exception as exc:
            if trace:
                trace.mark_once("main_model_failed")
            logger.exception("orchestration.stream_failed reason=%s", type(exc).__name__)
            error_message = "**[API Error]** 生成回答時發生錯誤，請稍後重試。"
            yield f"data: {json.dumps({'choices': [{'delta': {'content': error_message}, 'index': 0}]}, ensure_ascii=False)}\n\n"

        trailing = output_filter.finish()
        if trailing:
            safe_trailing, reasons = boundary_filter.feed(trailing)
            for reason in reasons:
                logger.warning(
                    "orchestration.response_boundary_blocked conversation_id=%s reason=%s",
                    conversation_id,
                    reason,
                )
            if safe_trailing:
                safe_trailing = image_marker_filter.feed(safe_trailing)
            if safe_trailing:
                accumulator += safe_trailing
                yield f"data: {json.dumps({'choices': [{'delta': {'content': safe_trailing}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            for slot in image_marker_filter.drain_new_slots():
                yield f"event: image_slot\ndata: {json.dumps(slot.to_stream_payload(), ensure_ascii=False)}\n\n"
        final_text, final_reasons = boundary_filter.finish()
        for reason in final_reasons:
            logger.warning(
                "orchestration.response_boundary_blocked conversation_id=%s reason=%s",
                conversation_id,
                reason,
            )
        if final_text:
            final_text = image_marker_filter.feed(final_text)
        marker_trailing = image_marker_filter.finish()
        if marker_trailing:
            final_text = f"{final_text}{marker_trailing}"
        if final_text:
            accumulator += final_text
            yield f"data: {json.dumps({'choices': [{'delta': {'content': final_text}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
        for slot in image_marker_filter.drain_new_slots():
            yield f"event: image_slot\ndata: {json.dumps(slot.to_stream_payload(), ensure_ascii=False)}\n\n"
        if image_marker_filter.slots:
            logger.info(
                "visual.slot_marker_detected conversation_id=%s slot_count=%s",
                conversation_id,
                len(image_marker_filter.slots),
            )
        if image_marker_filter.rejected_verified_marker_count:
            logger.info(
                "visual.verified_marker_rejected conversation_id=%s reason=missing_visual_lead_in marker_count=%s",
                conversation_id,
                image_marker_filter.rejected_verified_marker_count,
            )
        logger.info(
            "orchestration.stream_completed conversation_id=%s elapsed_ms=%s",
            conversation_id,
            int((time.time() - started_at) * 1000),
        )
        if trace:
            trace.mark_once("main_model_finished")

        for call in tool_calls.values():
            if call["name"] == "generate_image" and not generated_blocks:
                try:
                    image_arguments = json.loads(call["arguments"])
                except (ValueError, TypeError):
                    image_arguments = {}
                if isinstance(image_arguments, dict) and image_arguments.get("presentation", "image_only") == "image_only":
                    accumulator = ""
                elif not accumulator and isinstance(image_arguments, dict):
                    explanation = image_arguments.get("explanation", "")
                    if isinstance(explanation, str) and len(explanation) <= 4000:
                        accumulator = explanation
                async for block in stream_generated_image(
                    arguments=call["arguments"], user_id=user_id, conversation_id=conversation_id,
                    language=interface_language, attachments=image_attachments or [], request=request,
                    latest_request=last_user_msg, registry=self.tool_registry, budget=tool_budget,
                    tool_call_id=call["id"],
                ):
                    if block.get("tool_state"):
                        yield f"event: tool_state\ndata: {json.dumps(block['tool_state'], ensure_ascii=False)}\n\n"
                    elif block.get("heartbeat"):
                        yield ": heartbeat\n\n"
                    else:
                        if block.get("type") == "image_block" and block.get("status") == "error":
                            accumulator = ""
                            generated_blocks = [block]
                            yield f"event: answer_blocks\ndata: {json.dumps(generated_blocks, ensure_ascii=False)}\n\n"
                            continue
                        generated_blocks = ([{"type": "paragraph", "text": accumulator}] if accumulator else []) + [block]
                        yield f"event: answer_blocks\ndata: {json.dumps(generated_blocks, ensure_ascii=False)}\n\n"
            elif call["name"] == "send_epistolary_letter":
                tool_call_name, tool_call_args = call["name"], call["arguments"]
        if await request.is_disconnected():
            return

        if tool_call_name == "send_epistolary_letter" and tool_call_args:
            try:
                arguments = json.loads(tool_call_args)
                avatar_name = arguments.get("avatar_name", "Unknown")
                result = await self.tool_registry.execute(
                    "schedule_letter",
                    {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "user_message": last_user_msg,
                        "avatar_name": avatar_name,
                        "task_id": letter_task_id(
                            user_id, conversation_id, avatar_name, last_user_msg
                        ),
                    },
                    tool_budget,
                )
                if result.status == "ok":
                    notice = f"\n\n*(系統通知：已為您呼叫 {avatar_name or '對應角色'}，信件正在撰寫中，預計 5 分鐘後寄達。)*"
                    accumulator += notice
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': notice}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                else:
                    logger.info(
                        "orchestration.mail_tool_disabled user_id=%s conversation_id=%s",
                        user_id,
                        conversation_id,
                    )
            except Exception as exc:
                logger.warning("orchestration.mail_tool_failed reason=%s", type(exc).__name__)
        yield f"event: accumulator\ndata: {json.dumps({'accumulator': accumulator, 'image_slots': [slot.to_payload() for slot in image_marker_filter.slots], 'generated_blocks': generated_blocks}, ensure_ascii=False)}\n\n"
