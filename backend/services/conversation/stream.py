"""Own provider streaming and authorized post-response tool execution."""

from __future__ import annotations

import asyncio
import json
import re
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List

from config import settings
from policies import CapabilityPolicy
from services.conversation.history import prepare_history
from services.conversation.summary_precompute import PrecomputeSettings
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
from services.conversation.prompt_cache import apply_document_cache_layout, apply_stable_prefix_layout, coverage_user_notice
from services.conversation.stream_request import build_stream_request, tools_for_image_slots
from services.conversation.response_boundary import StreamingResponseBoundaryFilter
from services.conversation.web_search_call import (
    SEARCH_FAILED_NOTE, WEB_SEARCH_TOOL_SCHEMA, format_web_results, search_tool_content,
    web_search_arguments, web_search_config,
)
from services.memory_diagnostics import log_memory_snapshot

logger = logging.getLogger(__name__)


def _cache_write_tokens(usage: Any) -> Any:
    """Return OpenRouter's prompt cache write count, or None when not reported.

    A cache write re-uploads the whole document prefix, which is the costly,
    slow-first-token case on attachment follow-ups.
    """
    details = usage.get("prompt_tokens_details") if isinstance(usage, dict) else getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return None
    return details.get("cache_write_tokens") if isinstance(details, dict) else getattr(details, "cache_write_tokens", None)


def _usage_counts(usage: Any) -> tuple[Any, Any, Any, Any]:
    """Return prompt, completion, reasoning and cached token counts (or None)."""
    def read(source: Any, name: str) -> Any:
        if source is None:
            return None
        return source.get(name) if isinstance(source, dict) else getattr(source, name, None)

    completion_details = read(usage, "completion_tokens_details")
    prompt_details = read(usage, "prompt_tokens_details")
    return (read(usage, "prompt_tokens"), read(usage, "completion_tokens"),
            read(completion_details, "reasoning_tokens"), read(prompt_details, "cached_tokens"))


def _delta_frame(content: str) -> str:
    return f"data: {json.dumps({'choices': [{'delta': {'content': content}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"


class StepOutcome(str, Enum):
    """How one provider step ended; the caller decides what happens next.

    A provider context rejection is not an outcome: it raises, and the caller's
    bounded retry owns recovery.
    """

    COMPLETED = "completed"
    OUTPUT_LIMIT = "output_limit"
    TOOL_CALLS = "tool_calls"


@dataclass
class _StepState:
    """What a provider step produced besides answer frames."""

    tool_calls: dict[int, dict[str, str]] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: Any = None
    generation_id: str | None = None
    # Whether the provider emitted any text or tool call during this attempt.
    started: bool = False

    @property
    def outcome(self) -> StepOutcome:
        if self.tool_calls:
            return StepOutcome.TOOL_CALLS
        if self.finish_reason == "length":
            return StepOutcome.OUTPUT_LIMIT
        return StepOutcome.COMPLETED


class _AnswerPipeline:
    """Filter provider text into public answer frames and own the accumulated answer."""

    def __init__(self, *, conversation_id: str, max_image_slots: int, trace: Any):
        self.conversation_id = conversation_id
        self.trace = trace
        self.citation_filter: Any = None
        self.output_filter = PublicAnswerFilter()
        self.boundary_filter = StreamingResponseBoundaryFilter()
        self.image_marker_filter = ImageRequestMarkerFilter(max_slots=max_image_slots)
        self.accumulator = ""

    def _log_blocked(self, reasons: list[str]) -> None:
        for reason in reasons:
            logger.warning(
                "orchestration.response_boundary_blocked conversation_id=%s reason=%s",
                self.conversation_id,
                reason,
            )

    def _slot_frames(self) -> list[str]:
        return [f"event: image_slot\ndata: {json.dumps(slot.to_stream_payload(), ensure_ascii=False)}\n\n"
                for slot in self.image_marker_filter.drain_new_slots()]

    def feed(self, content: str) -> list[str]:
        """Return the frames one provider text delta produces."""
        frames: list[str] = []
        if self.citation_filter:
            content = self.citation_filter.feed(content)
        if content:
            content = self.output_filter.feed(content)
        if content:
            content, reasons = self.boundary_filter.feed(content)
            self._log_blocked(reasons)
        if content:
            content = self.image_marker_filter.feed(content)
        if content:
            if self.trace:
                self.trace.mark_once("first_answer_delta")
            self.accumulator += content
            frames.append(_delta_frame(content))
        frames.extend(self._slot_frames())
        return frames

    def finish(self) -> list[str]:
        """Flush every filter once the provider stream has ended."""
        frames: list[str] = []
        trailing = (self.output_filter.feed(self.citation_filter.finish()) if self.citation_filter else '') + self.output_filter.finish()
        if trailing:
            safe_trailing, reasons = self.boundary_filter.feed(trailing)
            self._log_blocked(reasons)
            if safe_trailing:
                safe_trailing = self.image_marker_filter.feed(safe_trailing)
            if safe_trailing:
                self.accumulator += safe_trailing
                frames.append(_delta_frame(safe_trailing))
            frames.extend(self._slot_frames())
        final_text, final_reasons = self.boundary_filter.finish()
        self._log_blocked(final_reasons)
        if final_text:
            final_text = self.image_marker_filter.feed(final_text)
        marker_trailing = self.image_marker_filter.finish()
        if marker_trailing:
            final_text = f"{final_text}{marker_trailing}"
        if final_text:
            self.accumulator += final_text
            frames.append(_delta_frame(final_text))
        frames.extend(self._slot_frames())
        return frames


class ConversationStreamService:
    """Stream provider output while enforcing filtering and tool boundaries."""

    def __init__(self, client: Any, tool_registry: Any):
        self.client = client
        self.tool_registry = tool_registry

    async def _run_provider_step(
        self, *, messages: List[Dict[str, Any]], state: _StepState, pipeline: _AnswerPipeline,
        request: Any, trace: Any, conversation_id: str, target_model: str, max_tokens: int,
        temperature: float, top_p: float, extra_body: Dict[str, Any], tools: list[dict[str, Any]] | None,
        attempt: int, attachment_count: int,
    ) -> AsyncGenerator[str, None]:
        """Run one provider request and yield its answer frames.

        Text goes through ``pipeline``; tool calls, finish reason and usage land
        in ``state``, whose ``outcome`` the caller reads once the step ends. A
        provider rejection propagates unchanged so the caller decides on a retry.
        The request and stream are always closed, including on ``aclose()``.
        ``tools=None`` sends no tools, as in a follow-up step that must answer.
        """
        tool_options: Dict[str, Any] = {} if tools is None else {"tools": tools, "tool_choice": "auto"}
        generation = None
        response = None
        try:
            logger.info(
                'orchestration.provider_request_started conversation_id=%s model=%s attempt=%d '
                'message_count=%d attachment_count=%d chat_bytes=%d output_tokens=%d',
                conversation_id, target_model, attempt + 1, len(messages),
                attachment_count, token_bound(messages), max_tokens,
            )
            if attachment_count:
                log_memory_snapshot("attachment_provider_request_started", conversation_id=conversation_id)
            generation = asyncio.create_task(
                self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    stream=True,
                    max_tokens=max_tokens,
                    temperature=temperature if temperature > 0 else 0.001,
                    top_p=top_p,
                    extra_body=extra_body,
                    **tool_options,
                )
            )
            while not generation.done():
                done, _ = await asyncio.wait([generation], timeout=5.0)
                if not done:
                    yield ": heartbeat\n\n"
            response = await generation
            if attachment_count:
                log_memory_snapshot("attachment_provider_stream_received", conversation_id=conversation_id)
            logger.info('orchestration.provider_stream_received conversation_id=%s model=%s attempt=%d',
                        conversation_id, target_model, attempt + 1)
            if trace:
                trace.mark_once("main_model_provider_stream_received")
            async for chunk in response:
                if await request.is_disconnected():
                    logger.info("orchestration.stream_cancelled conversation_id=%s", conversation_id)
                    break
                state.usage = getattr(chunk, "usage", None) or state.usage
                # Opaque OpenRouter id; lets /api/v1/generation explain provider latency.
                state.generation_id = getattr(chunk, "id", None) or state.generation_id
                if not chunk.choices:
                    continue
                state.finish_reason = getattr(chunk.choices[0], "finish_reason", None) or state.finish_reason
                delta = chunk.choices[0].delta
                if getattr(delta, "tool_calls", None):
                    state.started = True
                    for call in delta.tool_calls:
                        entry = state.tool_calls.setdefault(getattr(call, "index", 0), {"name": "", "arguments": "", "id": getattr(call, "id", None) or uuid.uuid4().hex})
                        function = getattr(call, "function", None)
                        if function:
                            entry["name"] += getattr(function, "name", None) or ""
                            entry["arguments"] += getattr(function, "arguments", None) or ""
                    continue
                content = getattr(delta, "content", None) or ""
                if content:
                    state.started = True
                for frame in pipeline.feed(content):
                    yield frame
                await asyncio.sleep(0)
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

    async def _model_search_frames(
        self, call: dict[str, str], *, user_id: str, conversation_id: str, tool_budget: Any,
        trace: Any, result: dict[str, str],
    ) -> AsyncGenerator[str, None]:
        """Run the model-requested web search and yield the same frames as pre-answer search.

        ``result["content"]`` receives the tool-result text for the follow-up
        step. Invalid arguments, a missing key, budget refusal or provider
        failure all yield a failure note there instead of raising, so the
        follow-up step still answers.
        """
        result["content"] = SEARCH_FAILED_NOTE
        try:
            arguments = json.loads(call["arguments"] or "{}")
        except (ValueError, TypeError):
            arguments = None
        query = arguments.get("query") if isinstance(arguments, dict) else None
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            logger.warning("orchestration.tool_arguments_invalid conversation_id=%s tool=web_search", conversation_id)
            return
        config = web_search_config()
        if not config.api_key:
            logger.warning("orchestration.model_search_unavailable conversation_id=%s reason=missing_key", conversation_id)
            return
        yield f"event: tool_started\ndata: {json.dumps({'tool_name': 'web_search', 'display_message': '🌐 正在查找最新資料'}, ensure_ascii=False)}\n\n"
        try:
            tool_result = await self.tool_registry.execute(
                "web_search",
                web_search_arguments(config, query=query.strip(), user_id=user_id, conversation_id=conversation_id),
                tool_budget,
            )
            results, context_texts, sources_payload, _ = format_web_results(tool_result.content)
        except Exception as exc:
            logger.warning("orchestration.model_search_failed conversation_id=%s reason=%s",
                           conversation_id, type(exc).__name__)
            yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 聯網搜尋服務暫時無法使用，改用一般對話...'}, ensure_ascii=False)}\n\n"
            return
        if trace:
            trace.increment_tool_call("web_search", tool_result.cache_status)
        yield f"event: tool_completed\ndata: {json.dumps({'tool_name': 'web_search', 'display_message': '已完成資料查找', 'result_count': len(results), 'latency_ms': tool_result.latency_ms, 'cache_status': tool_result.cache_status}, ensure_ascii=False)}\n\n"
        if sources_payload:
            yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': 'sources_ready', 'message': f'已取得 {len(sources_payload)} 筆網路文獻'}, ensure_ascii=False)}\n\n"
        logger.info("orchestration.model_search_completed conversation_id=%s result_count=%d source_count=%d latency_ms=%s",
                    conversation_id, len(results), len(sources_payload), tool_result.latency_ms)
        result["content"] = search_tool_content(context_texts)

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
        model_search: bool = False,
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
            model_search: Offer ``web_search`` to the model instead of a routing
                call before the answer. A search call runs once, then a second
                step without tools answers from its results.

        Yields:
            Legacy-compatible SSE answer chunks, privacy-safe ``image_slot``
            events, and one private accumulator event consumed by orchestration.

        Side Effects:
            Calls the configured model and optional image tool, and emits
            bounded structured lifecycle logs without raw prompts or markers.
            INFO provider_request_started/provider_stream_received record model,
            conversation ID, attempt and numeric counts. WARNING
            history.provider_context_rejected records only counts and stream state,
            never provider error bodies, attachment data or answer text.
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
        tools = tools_for_image_slots(tools, max_image_slots)
        if model_search:
            tools = [*(tools or []), WEB_SEARCH_TOOL_SCHEMA]
        if tool_budget is None:
            from core import ToolBudget, ToolBudgetTracker

            tool_budget = ToolBudgetTracker(ToolBudget())

        original_messages = messages
        pipeline = _AnswerPipeline(conversation_id=conversation_id, max_image_slots=max_image_slots, trace=trace)
        # Shared across the context-retry attempts, as the retry only follows a
        # rejection that arrived before any provider output.
        step_state = _StepState()
        generated_blocks: list[dict] = []
        logger.info(
            "orchestration.stream_started conversation_id=%s model=%s attachment_parser=%s image_slot_cap=%s openrouter_session=%s latency_routing=%s",
            conversation_id,
            target_model,
            has_pdf,
            pipeline.image_marker_filter.max_slots,
            bool(extra_body.get("session_id")),
            bool(extra_body.get("provider")),
        )
        if has_pdf or image_attachments:
            log_memory_snapshot("attachment_context_started", conversation_id=conversation_id)
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
                    precompute=PrecomputeSettings(
                        ratio=settings.conversation_summary_precompute_ratio,
                        tail_share=settings.conversation_summary_precompute_tail_share,
                        wait_seconds=settings.conversation_summary_precompute_wait_seconds,
                        timeout_seconds=settings.conversation_summary_cold_timeout_seconds,
                    ) if settings.enable_conversation_summary_precompute else None,
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
                if reason in ('attachment_parse_timeout', 'attachment_parse_failed'):
                    log_memory_snapshot(reason, conversation_id=conversation_id)
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
                # Report the visible notice as the final answer so post-turn work matches the UI.
                yield f"event: accumulator\ndata: {json.dumps({'accumulator': content, 'image_slots': [], 'generated_blocks': []}, ensure_ascii=False)}\n\n"
                return
            messages = prepared.messages
            retry_base = messages
            # Document-free turns keep per-turn instructions in the system message
            # unless the stable-prefix rollout covers this conversation.
            stable_prefix = CapabilityPolicy.rollout_enabled(
                feature_enabled=settings.enable_stable_system_prefix,
                rollout_percentage=settings.stable_system_prefix_rollout_percentage,
                user_id=user_id, conversation_id=conversation_id,
            )
            cache_layout = apply_stable_prefix_layout if stable_prefix else apply_document_cache_layout
            if getattr(settings, "chat_upload_prompt_cache", True):
                messages, layout = cache_layout(messages)
                if layout:
                    logger.info(
                        "orchestration.prompt_cache_layout conversation_id=%s document_parts=%d prefix_hash=%s stable_prefix=%s",
                        conversation_id, layout.document_parts, layout.prefix_hash, stable_prefix,
                    )
            if prepared.notice:
                pipeline.citation_filter = UnavailableCitationFilter()
                yield f"data: {json.dumps({'choices': [{'delta': {'content': prepared.notice + chr(10) + chr(10)}, 'index': 0}]}, ensure_ascii=False)}\n\n"
            if trace:
                trace.increment_model_call("main_answer")
                trace.mark_once("main_model_started")
                trace.mark_once("main_model_provider_request_started")
            for attempt in range(2):
                step_state.started = False
                # Count parts only; never serialize media or provider errors into logs.
                attachment_count = sum(
                    is_attachment(part) for message in messages
                    if isinstance(message.get('content'), list) for part in message['content'])
                step = self._run_provider_step(
                    messages=messages, state=step_state, pipeline=pipeline, request=request, trace=trace,
                    conversation_id=conversation_id, target_model=target_model, max_tokens=max_tokens,
                    temperature=temperature, top_p=top_p, extra_body=extra_body, tools=tools,
                    attempt=attempt, attachment_count=attachment_count,
                )
                try:
                    async for frame in step:
                        yield frame
                    break
                except Exception as provider_error:
                    if not is_provider_context_error(provider_error):
                        raise
                    logger.warning(
                        'history.provider_context_rejected conversation_id=%s model=%s attempt=%d '
                        'attachment_count=%d answer_started=%s',
                        conversation_id, target_model, attempt + 1, attachment_count, step_state.started,
                    )
                    # Retry from the pre-layout messages; the reducer understands that shape.
                    reduced, removed_sources = minimal_retry_context(retry_base, original_messages, retrieval_context)
                    reduced, _ = cache_layout(reduced) if getattr(
                        settings, "chat_upload_prompt_cache", True) else (reduced, None)
                    if attempt == 0 and not step_state.started and reduced != messages:
                        messages = reduced
                        if removed_sources:
                            pipeline.citation_filter = UnavailableCitationFilter()
                        logger.warning('history.provider_context_retry conversation_id=%s attempt=1 selected_messages=%d removed_sources=%s', conversation_id, len(messages), removed_sources)
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
                    # A disconnect closes only this generator; close the step explicitly
                    # so its provider request and stream never outlive the client.
                    await step.aclose()

            if model_search:
                search_call = next((call for call in step_state.tool_calls.values()
                                    if call["name"] == "web_search"), None)
                logger.info("orchestration.model_search_decision conversation_id=%s called=%s",
                            conversation_id, search_call is not None)
                if search_call is not None and not await request.is_disconnected():
                    # Step 2: answer from the search result with tools disabled, so
                    # the loop is bounded at two provider calls per turn.
                    search_result: dict[str, str] = {}
                    async for frame in self._model_search_frames(
                        search_call, user_id=user_id, conversation_id=conversation_id,
                        tool_budget=tool_budget, trace=trace, result=search_result,
                    ):
                        yield frame
                    followup = [
                        *messages,
                        {"role": "assistant", "content": pipeline.accumulator or None, "tool_calls": [{
                            "id": search_call["id"], "type": "function",
                            "function": {"name": "web_search", "arguments": search_call["arguments"]},
                        }]},
                        {"role": "tool", "tool_call_id": search_call["id"], "content": search_result["content"]},
                    ]
                    # Other calls from step 1 (an image) are dropped with the step.
                    step_state = _StepState()
                    if trace:
                        trace.increment_model_call("main_answer")
                    step = self._run_provider_step(
                        messages=followup, state=step_state, pipeline=pipeline, request=request, trace=trace,
                        conversation_id=conversation_id, target_model=target_model, max_tokens=max_tokens,
                        temperature=temperature, top_p=top_p, extra_body=extra_body, tools=None,
                        attempt=1, attachment_count=attachment_count,
                    )
                    try:
                        async for frame in step:
                            yield frame
                    finally:
                        await step.aclose()

        except Exception as exc:
            if isinstance(exc, MemoryError):
                log_memory_snapshot("stream_memory_error", conversation_id=conversation_id)
            if trace:
                trace.mark_once("main_model_failed")
            # Log only the innermost code location, never exception messages or locals.
            failure_frame = exc.__traceback__
            while failure_frame is not None and failure_frame.tb_next is not None:
                failure_frame = failure_frame.tb_next
            logger.warning(
                "orchestration.stream_failed conversation_id=%s reason=%s error_function=%s error_line=%s",
                conversation_id, str(exc) if isinstance(exc, ContextBudgetError) else type(exc).__name__,
                failure_frame.tb_frame.f_code.co_name if failure_frame else 'unknown',
                failure_frame.tb_lineno if failure_frame else 0,
            )
            error_message = "**[API Error]** 生成回答時發生錯誤，請稍後重試。"
            if isinstance(exc, ContextBudgetError):
                error_message = ("模型仍無法容納本次附件與問題，請改傳相關頁面或分批上傳。"
                                 if str(exc) == 'provider_attachment_context_too_large'
                                 else "模型仍無法容納本次必要上下文，請精簡問題後重試。")
            yield f"data: {json.dumps({'choices': [{'delta': {'content': error_message}, 'index': 0}]}, ensure_ascii=False)}\n\n"

        for frame in pipeline.finish():
            yield frame
        accumulator = pipeline.accumulator
        image_marker_filter = pipeline.image_marker_filter
        outcome = step_state.outcome
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
        coverage_notice = coverage_user_notice(original_messages) if outcome is not StepOutcome.TOOL_CALLS else ""
        if coverage_notice:
            accumulator += coverage_notice
            yield f"data: {json.dumps({'choices': [{'delta': {'content': coverage_notice}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            logger.info("chat_documents.partial_notice conversation_id=%s", conversation_id)
        if outcome is StepOutcome.OUTPUT_LIMIT:
            # Silent mid-sentence cuts looked like bugs; tell the learner how to resume.
            notice = "\n\n（回答已達單次長度上限而中斷，可以回覆「繼續」讓我接著說。）"
            accumulator += notice
            yield f"data: {json.dumps({'choices': [{'delta': {'content': notice}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
        logger.info(
            "orchestration.provider_finish conversation_id=%s finish_reason=%s prompt_tokens=%s "
            "completion_tokens=%s reasoning_tokens=%s cached_tokens=%s cache_write_tokens=%s generation_id=%s",
            conversation_id, step_state.finish_reason or "none", *_usage_counts(step_state.usage),
            _cache_write_tokens(step_state.usage),
            step_state.generation_id if isinstance(step_state.generation_id, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", step_state.generation_id) else "none",
        )
        logger.info(
            "orchestration.stream_completed conversation_id=%s elapsed_ms=%s",
            conversation_id,
            int((time.time() - started_at) * 1000),
        )
        if trace:
            trace.mark_once("main_model_finished")

        for call in (step_state.tool_calls.values() if outcome is StepOutcome.TOOL_CALLS else ()):
            if call["name"] == "generate_image" and not generated_blocks:
                try:
                    image_arguments = json.loads(call["arguments"])
                except (ValueError, TypeError):
                    # Unparseable arguments carry no presentation choice; keep the
                    # streamed answer instead of defaulting to image_only and erasing it.
                    image_arguments = None
                    logger.warning("orchestration.tool_arguments_invalid conversation_id=%s tool=generate_image",
                                   conversation_id)
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
                            generated_blocks = ([{"type": "paragraph", "text": accumulator}] if accumulator else []) + [block]
                            yield f"event: answer_blocks\ndata: {json.dumps(generated_blocks, ensure_ascii=False)}\n\n"
                            continue
                        generated_blocks = ([{"type": "paragraph", "text": accumulator}] if accumulator else []) + [block]
                        yield f"event: answer_blocks\ndata: {json.dumps(generated_blocks, ensure_ascii=False)}\n\n"
        if await request.is_disconnected():
            return

        yield f"event: accumulator\ndata: {json.dumps({'accumulator': accumulator, 'image_slots': [slot.to_payload() for slot in image_marker_filter.slots], 'generated_blocks': generated_blocks}, ensure_ascii=False)}\n\n"
