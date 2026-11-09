"""Own provider streaming and authorized post-response tool execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List

from config import settings
from services.conversation.history import prepare_history
from services.conversation.context_recovery import is_provider_context_error, minimal_retry_context, UnavailableCitationFilter
from services.conversation.attachment_budget import is_attachment
from services.conversation.context_budget import ContextBudgetError, token_bound
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
        retrieval_context: str = "",
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
            retrieval_context: Exact request-scoped retrieval prefix supplied by orchestration.
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

        original_messages = messages
        citation_filter = None
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
            try:
                preparation = asyncio.create_task(prepare_history(
                    messages=messages, tools=tools, client=self.client,
                    user_id=user_id, conversation_id=conversation_id,
                    model=settings.model_conversation_summary, output_tokens=max_tokens,
                    context_tokens=settings.conversation_context_tokens,
                    summary_tokens=settings.conversation_summary_tokens,
                    timeout_seconds=settings.conversation_summary_timeout_seconds,
                    cold_timeout_seconds=settings.conversation_summary_cold_timeout_seconds,
                    summary_context_tokens=settings.conversation_summary_context_tokens,
                    enabled=settings.enable_conversation_compaction,
                    retrieval_context=retrieval_context,
                ))
                try:
                    done, _ = await asyncio.wait([preparation], timeout=1.0)
                    if not done:
                        yield f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '正在整理較早對話，準備回答'}, ensure_ascii=False)}\n\n"
                    while not preparation.done():
                        if await request.is_disconnected():
                            return
                        done, _ = await asyncio.wait([preparation], timeout=5.0)
                        if not done:
                            yield ": heartbeat\n\n"
                    prepared = await preparation
                finally:
                    if not preparation.done():
                        preparation.cancel()
                    # Await cancellation to prevent provider work surviving disconnects.
                    await asyncio.gather(preparation, return_exceptions=True)
            except ValueError as error:
                reasons = {'combined_context_too_large', 'attachment_parse_timeout', 'attachment_parse_failed', 'attachment_context_too_large', 'output_budget', 'compaction_disabled', 'missing_current_turn',
                           'current_turn_too_large', 'instructions_too_large', 'retrieval_budget',
                           'retrieval_prefix_mismatch', 'retrieval_unavailable'}
                reason = str(error) if str(error) in reasons else 'invalid_context'
                sizes = error.sizes if isinstance(error, ContextBudgetError) else {}
                logger.warning(
                    "history.rejected conversation_id=%s reason=%s budget=%s instructions_bytes=%s "
                    "current_turn_bytes=%s retrieval_bytes=%s tools_bytes=%d output_tokens=%d attachment_units=%s",
                    conversation_id, reason, sizes.get('budget'), sizes.get('instructions_bytes'),
                    sizes.get('current_turn_bytes'), sizes.get('retrieval_bytes'), token_bound(tools), max_tokens, sizes.get('attachment_units'),
                )
                content = "本次問題或必要上下文超過可處理容量，請縮短內容或減少附件後重試。"
                if reason == 'attachment_context_too_large':
                    content = "附件解析後的內容超過本次可閱讀容量，請改傳相關頁面、分批上傳，或提供較精簡的附件。"
                if reason == 'combined_context_too_large':
                    content = "聊天內容與附件合計超過本次可處理容量，請縮短問題或分批上傳附件。"
                elif reason in ('attachment_parse_timeout', 'attachment_parse_failed'):
                    content = "附件解析逾時或無法完成，請改傳相關頁面、較小的檔案，或可複製文字的版本。"
                yield f"data: {json.dumps({'choices': [{'delta': {'content': content}, 'index': 0}]}, ensure_ascii=False)}\n\n"
                return
            messages = prepared.messages
            if prepared.notice:
                citation_filter = UnavailableCitationFilter()
                yield f"data: {json.dumps({'choices': [{'delta': {'content': prepared.notice + chr(10) + chr(10)}, 'index': 0}]}, ensure_ascii=False)}\n\n"
            if trace:
                trace.increment_model_call("main_answer")
                trace.mark_once("main_model_started")
                trace.mark_once("main_model_provider_request_started")
            for attempt in range(2):
                provider_started = False
                generation = None
                response = None
                try:
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
                            provider_started = True
                            for call in delta.tool_calls:
                                entry = tool_calls.setdefault(getattr(call, "index", 0), {"name": "", "arguments": "", "id": getattr(call, "id", None) or uuid.uuid4().hex})
                                function = getattr(call, "function", None)
                                if function:
                                    entry["name"] += getattr(function, "name", None) or ""
                                    entry["arguments"] += getattr(function, "arguments", None) or ""
                            continue
                        content = getattr(delta, "content", None) or ""
                        if content:
                            provider_started = True
                        if citation_filter:
                            content = citation_filter.feed(content)
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
                    break
                except Exception as provider_error:
                    if not is_provider_context_error(provider_error):
                        raise
                    reduced, removed_sources = minimal_retry_context(messages, original_messages, retrieval_context)
                    if attempt == 0 and not provider_started and reduced != messages:
                        messages = reduced
                        if removed_sources:
                            citation_filter = UnavailableCitationFilter()
                        logger.warning('history.provider_context_retry attempt=1 selected_messages=%d removed_sources=%s', len(messages), removed_sources)
                        if trace:
                            trace.increment_model_call("main_answer")
                        yield 'event: status\ndata: {"status":"routing","message":"正在調整上下文並重新準備回答"}\n\n'
                        if removed_sources:
                            notice = "本回合搜尋摘錄已移除，回答無法依據這些來源。\n\n"
                            yield f"data: {json.dumps({'choices': [{'delta': {'content': notice}, 'index': 0}]}, ensure_ascii=False)}\n\n"
                        continue
                    has_attachment = any(isinstance(m.get('content'), list) and any(is_attachment(p) for p in m['content']) for m in messages)
                    raise ContextBudgetError('provider_attachment_context_too_large' if has_attachment else 'provider_context_too_large') from None
                finally:
                    if generation is not None and not generation.done():
                        generation.cancel()
                        await asyncio.gather(generation, return_exceptions=True)
                    if response is not None:
                        close = getattr(response, 'close', None) or getattr(response, 'aclose', None)
                        if close is not None:
                            try:
                                await close()
                            except Exception as close_error:
                                logger.warning('orchestration.provider_close_failed error_type=%s', type(close_error).__name__)

        except Exception as exc:
            if trace:
                trace.mark_once("main_model_failed")
            logger.warning("orchestration.stream_failed reason=%s", str(exc) if isinstance(exc, ContextBudgetError) else type(exc).__name__)
            error_message = "**[API Error]** 生成回答時發生錯誤，請稍後重試。"
            if isinstance(exc, ContextBudgetError):
                error_message = ("模型仍無法容納本次附件與問題，請改傳相關頁面或分批上傳。"
                                 if str(exc) == 'provider_attachment_context_too_large'
                                 else "模型仍無法容納本次必要上下文，請精簡問題後重試。")
            yield f"data: {json.dumps({'choices': [{'delta': {'content': error_message}, 'index': 0}]}, ensure_ascii=False)}\n\n"

        trailing = (output_filter.feed(citation_filter.finish()) if citation_filter else '') + output_filter.finish()
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
