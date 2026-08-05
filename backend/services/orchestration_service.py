"""
Orchestration Service Module.

This module provides the streaming controller for incoming chat requests. It
owns execution order and the established SSE compatibility boundary while
delegating memory ingestion, context construction, and post-turn work to
domain services.
"""

import json
import asyncio
import os
import re
import time
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional
from urllib.parse import urlparse
from fastapi import Request
from openai import AsyncOpenAI

from config import settings
from gum_integration import (
    push_observation,
    query_cold_memory_for_context,
    query_memory_for_context,
    get_hot_memory_snapshot,
    async_evaluate_and_update_state
)
from memory_gate import classify_user_message
from core import AgentEvent, ConversationRunState, ConversationRuntime, EventType, SearchMode
from agents import TutorAgent
from policies import CapabilityPolicy, MemoryPolicy, SearchDecision, SearchReason
from tools import DelayedMailTool, MemoryQueryTool, ToolDefinition, ToolRegistry, WebSearchTool
from services.conversation_context_service import ConversationContextService
from services.conversation_stream_service import ConversationStreamService
from services.post_turn_service import PostTurnService
from services.query_policy_service import (
    classify_dialogue_policy_impl,
    classify_response_policy_impl,
    default_response_policy,
    parse_and_decompose_query_impl,
    response_policy_from_legacy,
)
from services.turn_latency_trace import TurnLatencyTrace
from services.turn_plan_service import TurnPlan, TurnPlanService
from services.turn_intake_service import (
    TurnIntakeService,
    chat_avatar_key as _chat_avatar_key,
    extract_explicit_chat_avatar as _extract_explicit_chat_avatar,
    is_stop_roleplay_request as _is_stop_roleplay_request,
    normalize_avatar_name as _normalize_avatar_name,
)
from services.visual_answer_service import VisualAnswerService


logger = logging.getLogger(__name__)


def reorder_for_attention(results):
    """
    Reorder search results to mitigate the 'Lost in the Middle' problem.
    Places the highest scoring result first and the second highest last,
    with the rest in the middle.

    Args:
        results (list): A list of search result objects or dictionaries.

    Returns:
        list: The reordered list of results.
    """
    if len(results) <= 2:
        return results
    top = [results[0]]           
    bottom = [results[1]]       
    middle = results[2:]       
    return top + middle + bottom


def _build_valid_web_sources(results: List[Dict[str, Any]]) -> tuple[List[str], List[Dict[str, Any]]]:
    """Build prompt context and structured source payload from valid web results.

    Structured sources are the citation authority for the UI. Records without a
    valid HTTP(S) URL are excluded before they can become clickable citations or
    shift the visible source index mapping.
    """

    context_texts: List[str] = []
    sources_payload: List[Dict[str, Any]] = []
    for source_index, result in enumerate(results, 1):
        title = str(result.get("title") or "").strip()
        url = str(result.get("url") or "").strip()
        snippet = str(result.get("snippet") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.info(
                "orchestration.web_source_omitted reason=invalid_url source_index=%s",
                source_index,
            )
            continue

        citation_index = len(sources_payload) + 1
        context_texts.append(f"[文獻{citation_index}] {title}\nURL: {url}\n內容段落: {snippet}")
        sources_payload.append({
            "title": title,
            "chunk_id": url,
            "url": url,
            "snippet": snippet,
            "score": float(result.get("score", 1.0) or 1.0),
        })
    return context_texts, sources_payload

async def parse_and_decompose_query(query: str, client: AsyncOpenAI) -> List[Dict[str, str]]:
    """
    Parse and decompose a complex user query into sub-queries suitable for hybrid retrieval.

    Args:
        query (str): The raw user query.
        client (AsyncOpenAI): The OpenAI async client instance.

    Returns:
        List[Dict[str, str]]: A list of dictionaries, each containing a sub-query and its type.
    """
    return await parse_and_decompose_query_impl(query, client)

async def classify_dialogue_policy(client: AsyncOpenAI, model: str, user_msg: str, chat_history: list):
    """Return the structured EDF response policy for orchestration.

    Args:
        client: OpenAI-compatible async client.
        model: Policy classifier model identifier.
        user_msg: Latest user-authored message. It is sent to the classifier but
            never logged here.
        chat_history: Recent conversation messages for policy context.

    Returns:
        A ``ResponsePolicy`` from ``query_policy_service``. The function name is
        intentionally kept for compatibility with existing tests and patch
        points that used the previous string-only dialogue policy.
    """

    return await classify_response_policy_impl(client, model, user_msg, chat_history)


class OrchestrationService:
    """
    The main orchestration service managing the conversational flow, tools, and retrievals.
    """

    def __init__(self, router_service, rag_service, suggestion_service, client):
        """
        Initialize the OrchestrationService with required sub-services.

        Args:
            router_service (Any): Service for routing decisions.
            rag_service (Any): Service for RAG retrieval operations.
            suggestion_service (Any): Service for generating post-answer suggestions.
            client (AsyncOpenAI): The OpenAI async client instance.
        """
        self.router = router_service
        self.rag = rag_service
        self.suggestion = suggestion_service
        self.client = client
        self.runtime = ConversationRuntime()
        self.tutor_agent = TutorAgent()
        self.memory_policy = MemoryPolicy()
        self.memory_query_tool = MemoryQueryTool(
            lambda *args, **kwargs: query_cold_memory_for_context(*args, **kwargs),
            lambda *args, **kwargs: query_memory_for_context(*args, **kwargs),
        )
        self.context_service = ConversationContextService(
            self.memory_policy,
            self.memory_query_tool,
        )
        self.post_turn_service = PostTurnService(suggestion_service)
        self.visual_answer_service = VisualAnswerService()
        self.turn_intake_service = TurnIntakeService(client)
        self.turn_plan_service = TurnPlanService(self.memory_policy)
        self.web_search_tool = WebSearchTool()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(ToolDefinition(
            name="web_search",
            external=True,
            handler=self.web_search_tool.execute,
        ))
        self.delayed_mail_tool = DelayedMailTool(
            lambda: __import__("mailbox_store").get_mailbox_store()
        )
        self.tool_registry.register(ToolDefinition(
            name="schedule_letter",
            external=False,
            handler=self.delayed_mail_tool.execute,
        ))
        self.stream_service = ConversationStreamService(client, self.tool_registry)

    async def execute(self, messages: List[Dict[str, str]], conversation_id: str, use_rag: bool, use_web_search: bool, force_think: bool,
                      max_tokens: int, temperature: float, top_p: float,
                      repetition_penalty: float, request: Request, user_id: str,
                      search_mode: Optional[str] = None,
                      attachments: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[str, None]:
        """
        Execute the main conversational flow, yielding server-sent events (SSE) back to the client.

        Args:
            messages (List[Dict[str, str]]): The conversation history.
            conversation_id (str): The unique identifier for the conversation.
            use_rag (bool): Whether to use local RAG retrieval.
            use_web_search (bool): Whether to allow web search.
            force_think (bool): Whether to force deep thinking (reasoning) models.
            max_tokens (int): Maximum tokens for the generation.
            temperature (float): Sampling temperature.
            top_p (float): Nucleus sampling parameter.
            repetition_penalty (float): Repetition penalty parameter.
            request (Request): The FastAPI request object.
            user_id (str): The unique identifier for the user.
            search_mode (Optional[str]): Explicit search mode override. Defaults to None.
            attachments (Optional[List[Dict[str, Any]]]): Files or attachments provided by the user. Defaults to None.

        Yields:
            str: SSE formatted string events representing status updates and token chunks.
        """
        
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        request_id_header = request.headers.get("x-request-id") if request and request.headers else None
        effective_search_mode = (
            SearchMode(search_mode)
            if search_mode is not None
            else (SearchMode.ALWAYS if use_web_search else SearchMode.NEVER)
        )
        has_attachments = bool(attachments)
        from config import settings
        auto_routing_enabled = CapabilityPolicy.rollout_enabled(
            feature_enabled=settings.enable_agent_search_routing,
            rollout_percentage=settings.agent_search_rollout_percentage,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        session = self.runtime.start_session(
            user_id=user_id,
            conversation_id=conversation_id,
            request_id=request_id_header,
            search_mode=effective_search_mode,
        )
        run_context = session.context
        sse_adapter = session.transport
        run_state = session.state
        trace = TurnLatencyTrace(
            run_id=run_context.run_id,
            conversation_id=run_context.conversation_id,
        )
        trace.mark("request_accepted")
        trace_logged = False

        def log_trace() -> None:
            nonlocal trace_logged
            if trace_logged:
                return
            trace_logged = True
            trace_summary = trace.diagnostic_summary(
                slow_total_threshold_ms=settings.turn_trace_slow_total_threshold_ms,
                slow_first_token_threshold_ms=settings.turn_trace_slow_first_token_threshold_ms,
                top_phase_count=settings.turn_trace_top_phase_count,
            )
            logger.info(
                "orchestration.turn_trace_completed run_id=%s conversation_id=%s trace=%s",
                run_context.run_id,
                run_context.conversation_id,
                trace.snapshot(),
            )
            if settings.enable_production_turn_trace_summary:
                logger.info(
                    "orchestration.turn_trace_summary run_id=%s conversation_id=%s summary=%s",
                    run_context.run_id,
                    run_context.conversation_id,
                    json.dumps(trace_summary, ensure_ascii=False, sort_keys=True),
                )
                if trace_summary["is_slow"]:
                    logger.warning(
                        "orchestration.turn_trace_slow run_id=%s conversation_id=%s summary=%s",
                        run_context.run_id,
                        run_context.conversation_id,
                        json.dumps(trace_summary, ensure_ascii=False, sort_keys=True),
                    )

        # Send a user-visible event before memory and policy work enters the
        # critical path. This keeps the transport responsive even when an
        # external dependency is slow.
        yield sse_adapter.encode(AgentEvent(
            EventType.METADATA,
            {
                "promptTokens": 1024,
                "completionTokens": 0,
                "totalTokens": 1024,
                "runtimeVersion": "conversation-runtime-v1",
                "policyVersion": "controlled-agency-v1",
                "promptVersion": "legacy-compatible-v1",
                "toolVersion": "registry-v1",
            },
            run_context.run_id,
            1,
        ))
        yield sse_adapter.encode(AgentEvent(
            EventType.STATUS,
            {"status": "routing", "message": "🔍 正在分析問題"},
            run_context.run_id,
            2,
        ))
        yield sse_adapter.encode(AgentEvent(
            EventType.STATUS,
            {"status": "routing", "message": "🧭 正在判斷是否需要外部搜尋"},
            run_context.run_id,
            3,
        ))

        trace.mark("search_routing_started")
        if effective_search_mode == SearchMode.AUTO and has_attachments:
            # In AUTO mode the uploaded document is the primary source. Generic
            # search would answer from the filename/query instead of file content.
            search_decision = SearchDecision(False, SearchReason.ATTACHMENT_CONTEXT_PRIORITY)
        elif effective_search_mode == SearchMode.AUTO and auto_routing_enabled:
            trace.increment_model_call("search_routing")
            search_decision = await self.tutor_agent.decide_search(
                last_user_msg,
                run_context,
                client=self.client,
                model=settings.model_policy_classifier,
                timeout_seconds=1.5,
            )
        elif effective_search_mode == SearchMode.AUTO:
            search_decision = self.tutor_agent.search_policy.evaluate(
                last_user_msg, effective_search_mode
            )
        else:
            search_decision = self.tutor_agent.search_policy.evaluate(
                last_user_msg, effective_search_mode
            )
        trace.mark("search_routing_finished")
        use_web_search = search_decision.should_search
        if has_attachments and effective_search_mode == SearchMode.AUTO:
            use_rag = False
            attachment_types = [
                part.get("type", "unknown")
                for part in attachments or []
                if isinstance(part, dict)
            ]
            logger.info(
                "orchestration.attachment_routing conversation_id=%s count=%s types=%s",
                conversation_id,
                len(attachment_types),
                attachment_types,
            )

        turn_plan = self.turn_plan_service.plan(
            user_message=last_user_msg,
            use_rag=use_rag,
            has_attachments=has_attachments,
            search_decision=search_decision,
            settings=settings,
        )
        turn_plan_enabled = bool(settings.enable_turn_plan_runtime)
        trace.mark(f"turn_plan_{turn_plan.route.value.lower()}")
        logger.info(
            "orchestration.turn_plan_selected run_id=%s conversation_id=%s route=%s enabled=%s reason=%s max_foreground_model_calls=%s",
            run_context.run_id,
            run_context.conversation_id,
            turn_plan.route.value,
            turn_plan_enabled,
            turn_plan.reason_code,
            turn_plan.max_foreground_model_calls,
        )

        if settings.enable_tutor_shadow_routing and not auto_routing_enabled and last_user_msg and not has_attachments:
            shadow_task = asyncio.create_task(
                self.tutor_agent.evaluate_search_shadow(
                    last_user_msg,
                    run_context,
                    client=self.client,
                    model=settings.model_policy_classifier,
                )
            )
            shadow_task.add_done_callback(
                lambda task: task.exception() if not task.cancelled() else None
            )

        yield sse_adapter.encode(AgentEvent(
            EventType.ACTION,
            {
                "phase": "tool_selection",
                "action": "web_search" if use_web_search else "answer_directly",
                "reason_code": search_decision.reason.value,
                "display_message": "🌐 正在查找最新資料" if use_web_search else "🧠 正在整理回答脈絡",
                "attempt": 1,
            },
            run_context.run_id,
            4,
        ))
        yield sse_adapter.encode(AgentEvent(
            EventType.STATUS,
            {
                "status": "routing",
                "message": "🚦 已判斷回答路徑，正在檢查可用記憶與背景任務",
            },
            run_context.run_id,
            5,
        ))
        
        # Node 1: Intent Routing (DISABLED BY USER REQUEST)
        denied = False
        # async for event in self._node_intent_routing(last_user_msg):
        #     if event == "event: REFUSED\n\n":
        #         denied = True
        #         continue
        #     yield event
                
        # if denied:
        #     yield "data: [DONE]\n\n"
        #     return

            
        if last_user_msg:
            if self.turn_intake_service.store_available():
                yield sse_adapter.encode_legacy(
                    f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '📖 正在回顧你過去的學習紀錄'}, ensure_ascii=False)}\n\n",
                    run_context.run_id,
                )
            trace.mark("turn_intake_started")
            await self.turn_intake_service.process(
                user_id=user_id,
                conversation_id=conversation_id,
                user_message=last_user_msg,
                run_id=run_context.run_id,
            )
            trace.mark("turn_intake_finished")
            if self.client:
                yield sse_adapter.encode_legacy(
                    f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '🎯 正在分析目前用戶的學習狀態'}, ensure_ascii=False)}\n\n",
                    run_context.run_id,
                )

        if last_user_msg and not classify_user_message(last_user_msg).should_prompt:
            greeting_reply = "你好，我在。你可以直接告訴我現在想處理什麼。"
            yield sse_adapter.encode_legacy(
                f"data: {json.dumps({'choices': [{'delta': {'content': greeting_reply}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n",
                run_context.run_id,
            )
            trace.mark_once("first_answer_delta")
            trace.mark("terminal_sent")
            log_trace()
            yield sse_adapter.encode_legacy("data: [DONE]\n\n", run_context.run_id)
            return

        yield sse_adapter.encode_legacy(
            f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '📚 正在準備檢索策略與教學策略'}, ensure_ascii=False)}\n\n",
            run_context.run_id,
        )

        # Node 2 & 3: Parallel Tasks (HyDE & Policy)
        policy_task = None
        should_run_policy_classifier = (
            last_user_msg
            and self.client
            and (not turn_plan_enabled or turn_plan.requires_policy_classifier)
        )
        if should_run_policy_classifier:
            from config import settings
            trace.mark("policy_classifier_started")
            trace.increment_model_call("policy_classifier")
            policy_task = asyncio.create_task(
                classify_dialogue_policy(self.client, settings.model_policy_classifier, last_user_msg, messages)
            )
        elif last_user_msg and self.client and turn_plan_enabled:
            trace.mark("policy_classifier_skipped")

        rag_queries = []
        cached_results = None
        if use_rag and not use_web_search and self.rag and last_user_msg:
            trace.mark("rag_started")
            from main import get_query_fingerprint, rag_cache
            fingerprint = get_query_fingerprint(last_user_msg)
            if rag_cache:
                cached_results = await rag_cache.get(fingerprint)
                
            if not cached_results:
                yield sse_adapter.encode_legacy(
                    f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '🧩 正在拆解問題'}, ensure_ascii=False)}\n\n",
                    run_context.run_id,
                )
                trace.increment_model_call("query_decomposition")
                rag_queries = await parse_and_decompose_query(last_user_msg, self.client)
            else:
                rag_queries = None
        else:
            trace.mark("rag_skipped")

        # Node 4: RAG Retrieval
        context_results_obj = None
        if use_web_search and last_user_msg:
            async for event in self._node_perplexity_search(last_user_msg, conversation_id, messages, run_state, user_id=user_id, trace=trace):
                if event.startswith("event: results_obj"):
                    context_results_obj = run_state.context_results
                    continue
                if event == "event: REFUSED\n\n":
                    trace.mark("terminal_sent")
                    log_trace()
                    yield sse_adapter.encode_legacy("data: [DONE]\n\n", run_context.run_id)
                    return
                yield sse_adapter.encode_legacy(event, run_context.run_id)
        elif use_rag and self.rag and last_user_msg:
            async for event in self._node_rag_retrieval(last_user_msg, rag_queries, cached_results, run_state):
                if event.startswith("event: results_obj"):
                    context_results_obj = run_state.context_results
                    continue
                if event == "event: REFUSED\n\n":
                    trace.mark("terminal_sent")
                    log_trace()
                    yield sse_adapter.encode_legacy("data: [DONE]\n\n", run_context.run_id)
                    return
                yield sse_adapter.encode_legacy(event, run_context.run_id)

        # Node 5: Prompt Assembly
        response_policy = default_response_policy()
        response_policy_source = "default"
        policy = response_policy.legacy_policy
        if policy_task:
            try:
                policy_result = await asyncio.wait_for(policy_task, timeout=1.5)
                response_policy = (
                    policy_result
                    if hasattr(policy_result, "legacy_policy")
                    else response_policy_from_legacy(policy_result)
                )
                response_policy_source = (
                    "classifier"
                    if hasattr(policy_result, "legacy_policy")
                    else "legacy"
                )
                policy = response_policy.legacy_policy
                trace.mark("policy_classifier_finished")
                logger.info(
                    "orchestration.dialogue_policy_selected conversation_id=%s policy=%s",
                    conversation_id,
                    policy,
                )
            except asyncio.TimeoutError:
                policy_task.cancel()
                response_policy_source = "timeout_fallback"
                trace.mark("policy_classifier_timeout")
                logger.warning(
                    "orchestration.dialogue_policy_timeout conversation_id=%s fallback=NORMAL",
                    conversation_id,
                )
                yield sse_adapter.encode_legacy(
                    f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '✅ 已完成基本分析，正在組織回答'}, ensure_ascii=False)}\n\n",
                    run_context.run_id,
                )

        logger.info(
            "orchestration.response_policy_applied conversation_id=%s source=%s metadata=%s",
            conversation_id,
            response_policy_source,
            json.dumps(
                response_policy.safe_log_metadata(),
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

        yield sse_adapter.encode_legacy(
            f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '➡️ 正在思考撰寫回答內容'}, ensure_ascii=False)}\n\n",
            run_context.run_id,
        )

        trace.mark("prompt_assembly_started")
        final_messages = await self._node_prompt_assembly(
            user_id,
            conversation_id,
            messages,
            use_rag,
            use_web_search,
            force_think,
            context_results_obj,
            last_user_msg,
            context_prompt=run_state.context_prompt,
            trace=trace,
            turn_plan=turn_plan if turn_plan_enabled else None,
            response_policy=response_policy,
        )
        trace.mark("prompt_assembly_finished")
        final_messages = self._attach_to_latest_user_message(final_messages, attachments or [])
        if has_attachments:
            final_messages = self._add_attachment_grounding_instruction(final_messages)

        preverified_image_blocks = None
        if settings.enable_visual_preflight:
            trace.mark("visual_preflight_started")
            preverified_image_blocks = await self.visual_answer_service.prepare_preflight_image_blocks(
                user_msg=last_user_msg,
                response_policy=response_policy,
                existing_web_results=run_state.web_search_results,
                tool_registry=self.tool_registry,
                tool_budget=run_state.tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
                model_client=self.client,
                turn_plan=turn_plan if turn_plan_enabled else None,
            )
            trace.mark("visual_preflight_finished")
            final_messages = self._add_verified_visual_instruction(
                final_messages,
                preverified_image_blocks,
            )

        effective_max_tokens = max_tokens
        if policy in ["PROBE_UNDERSTANDING", "SUGGEST_ACTION"]:
            effective_max_tokens = 1500
        elif (use_rag or use_web_search) and max_tokens == 2048:
            effective_max_tokens = 2500
            
        if force_think:
            effective_max_tokens = 3200

        # Node 6: Main LLM Stream
        answer_content_accumulator = ""
        planned_image_slots: list[dict[str, Any]] = []
        async for event in self._node_llm_stream(user_id, conversation_id, last_user_msg, final_messages, force_think, effective_max_tokens, temperature, top_p, repetition_penalty, request, run_state.tool_budget, trace=trace):
            if event.startswith("event: accumulator\n"):
                try:
                    data_line = next(line for line in event.splitlines() if line.startswith("data: "))
                    accumulator_payload = json.loads(data_line[6:])
                    answer_content_accumulator = accumulator_payload.get("accumulator", "")
                    image_slots_payload = accumulator_payload.get("image_slots", [])
                    if isinstance(image_slots_payload, list):
                        planned_image_slots = [
                            slot for slot in image_slots_payload if isinstance(slot, dict)
                        ]
                except (StopIteration, json.JSONDecodeError, TypeError):
                    answer_content_accumulator = ""
                    planned_image_slots = []
                continue
            yield sse_adapter.encode_legacy(event, run_context.run_id)
        if planned_image_slots:
            logger.info(
                "visual.answer_slots_collected conversation_id=%s slot_count=%s",
                conversation_id,
                len(planned_image_slots),
            )

        # Node 7: Post-generation
        answer_blocks = await self.visual_answer_service.build_answer_blocks(
            answer_text=answer_content_accumulator,
            user_msg=last_user_msg,
            response_policy=response_policy,
            planned_image_slots=planned_image_slots,
            tool_registry=self.tool_registry,
            tool_budget=run_state.tool_budget,
            existing_web_results=run_state.web_search_results,
            user_id=user_id,
            conversation_id=conversation_id,
            model_client=self.client,
            preverified_image_blocks=preverified_image_blocks,
        )
        if answer_blocks:
            resolved_image_block_count = sum(
                1
                for block in answer_blocks
                if block.get("type") == "image_block" and block.get("status", "resolved") == "resolved"
            )
            pending_image_slot_count = sum(
                1
                for block in answer_blocks
                if block.get("type") == "image_block" and block.get("status") == "pending"
            )
            logger.info(
                "visual.answer_blocks_emitted conversation_id=%s block_count=%s resolved_image_block_count=%s pending_image_slot_count=%s",
                conversation_id,
                len(answer_blocks),
                resolved_image_block_count,
                pending_image_slot_count,
            )
            yield sse_adapter.encode_legacy(
                f"event: answer_blocks\ndata: {json.dumps(answer_blocks, ensure_ascii=False)}\n\n",
                run_context.run_id,
            )

        async for event in self._node_post_generation(last_user_msg, answer_content_accumulator, context_results_obj, use_rag, use_web_search, trace=trace):
            yield sse_adapter.encode_legacy(event, run_context.run_id)

        if last_user_msg and self.client:
            from gum_integration import push_reflection_observation

            self.post_turn_service.queue_post_turn_work(
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=run_context.run_id,
                messages=messages,
                model=settings.model_policy_classifier,
                client=self.client,
                reflection_fallback=push_reflection_observation,
                evaluation_fallback=async_evaluate_and_update_state,
            )
            logger.info(
                "orchestration.post_turn_queued run_id=%s conversation_id=%s",
                run_context.run_id,
                conversation_id,
            )
            trace.mark("post_turn_queued")
            
        trace.mark("terminal_sent")
        log_trace()
        yield sse_adapter.encode_legacy("data: [DONE]\n\n", run_context.run_id)


    async def _node_intent_routing(self, query: str) -> AsyncGenerator[str, None]:
        """
        Perform fast intent checking to reject harmful or out-of-scope queries (Currently Disabled).

        Args:
            query (str): The user query to evaluate.

        Yields:
            str: SSE formatted events if rejection occurs.
        """
        if not query or not self.client:
            return
            
        # Fast intent check to quickly reject truly harmful or out-of-scope queries
        # Router LLM is currently DISABLED. All queries pass through.
        # If re-enabled in the future, the prompt should be updated to reflect
        # the new universal learning scope of AREQA.
        pass

    @staticmethod
    def _attach_to_latest_user_message(
        messages: List[Dict[str, Any]], attachments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Attach request-scoped multimodal content only to the latest user turn.

        Args:
            messages (List[Dict[str, Any]]): The list of conversation messages.
            attachments (List[Dict[str, Any]]): The list of attachment data dictionaries.

        Returns:
            List[Dict[str, Any]]: The updated list of messages with attachments embedded.
        """
        if not attachments:
            return messages

        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            text = content if isinstance(content, str) and content.strip() else "請分析我附加的檔案。"
            message["content"] = [{"type": "text", "text": text}, *attachments]
            break
        return messages

    @staticmethod
    def _add_attachment_grounding_instruction(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Require answers to be grounded in content actually read from attachments.

        Args:
            messages (List[Dict[str, Any]]): The list of conversation messages.

        Returns:
            List[Dict[str, Any]]: The updated list of messages with grounding instructions added to the system prompt.
        """
        instruction = (
            "【附件事實邊界】本回合包含使用者附件。只能根據實際可讀取的附件內容回答；"
            "不得根據檔名、作者、建立時間、metadata 或常識猜測文件正文。"
            "若附件內容為空、解析失敗或只有 metadata，必須明確告知目前無法讀取文件內容，"
            "並請使用者改傳可讀版本。"
        )
        for message in messages:
            if message.get("role") == "system" and isinstance(message.get("content"), str):
                message["content"] = f'{message["content"]}\n\n{instruction}'
                return messages
        messages.insert(0, {"role": "system", "content": instruction})
        return messages

    @staticmethod
    def _add_verified_visual_instruction(
        messages: List[Dict[str, Any]],
        image_blocks: dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Add verified image inventory and marker rules to the answer prompt."""

        instruction: str
        if not image_blocks:
            instruction = (
                "【已驗證圖片狀態】本回合沒有可用的已驗證圖片。"
                "不得輸出 [[AREQA_IMAGE_REQUEST ...]] 或 [[AREQA_VERIFIED_IMAGE ...]]；"
                "若需要視覺輔助，請只用文字描述，不要假裝已插入圖片。"
            )
        else:
            inventory = [
                {
                    "id": slot_id,
                    "topic": block.topic,
                    "caption": block.caption,
                    "source_domain": block.source_domain,
                    "license": block.license,
                    "width": block.width,
                    "height": block.height,
                }
                for slot_id, block in image_blocks.items()
            ]
            instruction = (
                "【已驗證圖片清單】以下圖片已由系統搜尋與驗證，可在回答中自然引用。"
                "你只能使用清單中的 id，不能自行編造圖片、URL 或來源。"
                "若圖片能幫助理解，請在最自然的位置輸出標記："
                '[[AREQA_VERIFIED_IMAGE id="img_1"]]。'
                "標記前後要用自然文字銜接，並依據圖片 caption/source 寫解釋；"
                "不得輸出 [[AREQA_IMAGE_REQUEST ...]]。"
                f"\n<verified_images>{json.dumps(inventory, ensure_ascii=False)}</verified_images>"
            )

        for message in messages:
            if message.get("role") == "system" and isinstance(message.get("content"), str):
                message["content"] = f'{message["content"]}\n\n{instruction}'
                return messages
        messages.insert(0, {"role": "system", "content": instruction})
        return messages


    async def _node_rag_retrieval(self, last_user_msg: str, rag_queries: List[Dict[str, str]], cached_results=None, run_state: Optional[ConversationRunState] = None) -> AsyncGenerator[str, None]:
        """
        Execute the local RAG retrieval node.

        Args:
            last_user_msg (str): The latest user message.
            rag_queries (List[Dict[str, str]]): Decomposed queries for retrieval.
            cached_results (Optional[Any]): Cached retrieval results, if any. Defaults to None.
            run_state (Optional[ConversationRunState]): The current conversation state object. Defaults to None.

        Yields:
            str: SSE formatted status updates and retrieved sources.
        """
        run_state = run_state or ConversationRunState()
        from main import get_query_fingerprint, rag_cache, _thread_pool
        fingerprint = get_query_fingerprint(last_user_msg)
        context_results_obj = cached_results
        
        if not context_results_obj and rag_queries is not None:
            if self.rag:
                gen = self.rag.retrieve_with_events(rag_queries)
                while True:
                    rag_task = asyncio.get_running_loop().run_in_executor(_thread_pool, next, gen, None)
                    while not rag_task.done():
                        done, pending = await asyncio.wait([rag_task], timeout=5.0)
                        if not done:
                            yield f": heartbeat\n\n"
                    event = await rag_task
                    if event is None:
                        break
                    if event["type"] == "status":
                        yield f"event: status\ndata: {json.dumps({'status': event['status'], 'message': event['message']}, ensure_ascii=False)}\n\n"
                    elif event["type"] == "results":
                        context_results_obj = event["data"]
            else:
                yield f"event: status\ndata: {json.dumps({'status': 'RAG disabled (missing index)', 'message': 'Skipping local vector retrieval.'}, ensure_ascii=False)}\n\n"
                context_results_obj = {"fused_results": []}
                    
            if context_results_obj and rag_cache:
                await rag_cache.set(fingerprint, context_results_obj)
                
        if context_results_obj:
            is_reranked = False
            if context_results_obj.final_results and len(context_results_obj.final_results) > 0:
                first_res = context_results_obj.final_results[0]
                is_reranked = hasattr(first_res, 'reranker_score') or (isinstance(first_res, dict) and 'reranker_score' in first_res)
            
            effective_threshold = 0.35 if is_reranked else 0.005
            if context_results_obj.highest_score < effective_threshold:
                refusal = "AREQA查閱了相關文獻，暫時沒能找到與您問題直接相關的內容。為了保證回答的準確性，AREQA建議您換個方式提問，或詢問其他相關問題喔！ 😊"
                yield f"data: {json.dumps({'choices': [{'delta': {'content': refusal}, 'index': 0, 'finish_reason': 'stop'}]}, ensure_ascii=False)}\n\n"
                yield "event: REFUSED\n\n"
                return
                
            valid_results = [r for r in context_results_obj.final_results if r.text and r.text.strip()]
            highest_score = context_results_obj.highest_score
            
            dynamic_results = []
            for doc in valid_results:
                if len(dynamic_results) >= 7: break
                if doc.score < 0.005: continue
                if (highest_score - doc.score) > 0.60: continue
                dynamic_results.append(doc)
                
            valid_results = reorder_for_attention(dynamic_results)
            
            sources_payload = []
            context_texts = []
            for idx, chunk in enumerate(valid_results, 1):
                raw_source = (getattr(chunk, 'source', None) or getattr(getattr(chunk, 'metadata', None), 'source', None) or getattr(getattr(chunk, 'metadata', None), 'book', None) or getattr(getattr(chunk, 'metadata', None), 'book_name', None))
                chunk_id = getattr(chunk, 'chunk_id', None) or "N/A"
                if not raw_source and chunk_id != "N/A":
                    raw_source = chunk_id.split('_')[0] if '_' in str(chunk_id) else None
                source = raw_source or "古籍文獻"
                context_texts.append(f"[文獻{idx}] {source}\n{chunk.text}")
                sources_payload.append({"title": source, "snippet": chunk.text, "score": float(chunk.score), "chunk_id": chunk_id})
                
            yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': 'generating', 'message': '✍️ 援引文獻，生成解說...' }, ensure_ascii=False)}\n\n"
            
            context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
            run_state.context_results = context_results_obj
            run_state.context_prompt = context_prompt
            yield "event: results_obj\n\n"

    async def _node_perplexity_search(self, last_user_msg: str, conversation_id: str, messages: List[Dict[str, str]] = None, run_state: Optional[ConversationRunState] = None, user_id: str = "", trace: Optional[TurnLatencyTrace] = None) -> AsyncGenerator[str, None]:
        """
        Execute the web search node using Perplexity or a configured web search tool.

        Args:
            last_user_msg (str): The latest user message.
            conversation_id (str): The conversation identifier.
            messages (Optional[List[Dict[str, str]]]): The conversation history. Defaults to None.
            run_state (Optional[ConversationRunState]): The current conversation state object. Defaults to None.
            user_id (str): The user identifier. Defaults to "".

        Yields:
            str: SSE formatted status updates and search results.
        """
        node_start = time.time()
        run_state = run_state or ConversationRunState()
        logger.info(
            "orchestration.web_search_started conversation_id=%s user_id=%s",
            conversation_id,
            user_id,
        )
        if trace:
            trace.mark("web_search_started")
        yield f"event: status\ndata: {json.dumps({'status': 'searching_dense', 'message': '🌐 網路檢索中...'}, ensure_ascii=False)}\n\n"

        
        api_key = os.environ.get("PERPLEXITY_API_KEY", "")
        if not api_key:
            yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 未設定 PERPLEXITY_API_KEY，改用一般對話...'}, ensure_ascii=False)}\n\n"
            run_state.context_prompt = ""
            return
            
        rewritten_query = last_user_msg
        max_results = min(max(int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "15")), 3), 20)
        search_context_size = os.environ.get("WEB_SEARCH_CONTEXT_SIZE", "high").lower()
        if search_context_size not in {"low", "medium", "high"}:
            search_context_size = "high"
        rewrite_start = time.time()
        enable_query_rewrite = os.environ.get("ENABLE_WEB_QUERY_REWRITE", "true").lower() in {"1", "true", "yes", "on"}
        if enable_query_rewrite and self.client and messages:
            try:
                if trace:
                    trace.increment_model_call("web_query_rewrite")
                history_str = "\n".join([f'{m["role"]}: {m["content"]}' for m in messages[-4:]])
                rewrite_prompt = f"""請根據以下對話歷史，將最後一個使用者的提問重寫為適合在搜尋引擎上查詢的『獨立關鍵字』（Standalone Query）。同時請分析該問題的「複雜度」，並決定需要參考的文獻數量（3到20篇之間）。
請嚴格以 JSON 格式回傳，格式如下：
{{"query": "獨立關鍵字", "max_results": 15}}
不要有任何其他解釋。

對話歷史：
{history_str}"""
                from config import settings
                rewrite_res = await self.client.chat.completions.create(
                    model=settings.model_hyde_decomposer,
                    messages=[{"role": "user", "content": rewrite_prompt}],
                    temperature=0.1,
                    max_tokens=150,
                )
                if rewrite_res.choices and rewrite_res.choices[0].message.content:
                    content = rewrite_res.choices[0].message.content.strip()
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group(0))
                        rewritten_query = parsed.get("query", last_user_msg)
                        max_results = min(max(int(parsed.get("max_results", 15)), 3), 20)
                    else:
                        rewritten_query = content
            except Exception as exc:
                logger.warning(
                    "orchestration.web_query_rewrite_failed conversation_id=%s reason=%s",
                    conversation_id,
                    type(exc).__name__,
                )

        logger.info(
            "orchestration.web_query_ready conversation_id=%s elapsed_ms=%s max_results=%s context_size=%s rewritten=%s",
            conversation_id,
            int((time.time() - rewrite_start) * 1000),
            max_results,
            search_context_size,
            enable_query_rewrite,
        )

        yield f"event: tool_started\ndata: {json.dumps({'tool_name': 'web_search', 'display_message': '🌐 正在查找最新資料'}, ensure_ascii=False)}\n\n"
        try:
            tool_result = await self.tool_registry.execute(
                "web_search",
                {
                    "query": rewritten_query,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "api_key": api_key,
                    "max_results": max_results,
                    "search_context_size": search_context_size,
                    "redis_url": os.environ.get("REDIS_URL", "redis://localhost:6379"),
                },
                run_state.tool_budget,
            )
            if trace:
                trace.increment_tool_call("web_search", tool_result.cache_status)
        except Exception as exc:
            logger.exception(
                "orchestration.web_search_failed conversation_id=%s reason=%s",
                conversation_id,
                type(exc).__name__,
            )
            yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 聯網搜尋服務暫時無法使用，改用一般對話...'}, ensure_ascii=False)}\n\n"
            run_state.context_prompt = ""
            return

        results = tool_result.content["results"]
        run_state.web_search_results = list(results)
        yield f"event: tool_completed\ndata: {json.dumps({'tool_name': 'web_search', 'display_message': '已完成資料查找', 'result_count': len(results), 'latency_ms': tool_result.latency_ms, 'cache_status': tool_result.cache_status}, ensure_ascii=False)}\n\n"
        
        logger.info(
            "orchestration.web_search_completed conversation_id=%s result_count=%s latency_ms=%s",
            conversation_id,
            len(results),
            tool_result.latency_ms,
        )
        yield f"event: status\ndata: {json.dumps({'status': 'reranking', 'message': '⚡ 篩選與統整網路資訊...'}, ensure_ascii=False)}\n\n"
        
        context_texts, sources_payload = _build_valid_web_sources(results)
        if sources_payload:
            yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': 'sources_ready', 'message': f'已取得 {len(sources_payload)} 筆網路文獻'}, ensure_ascii=False)}\n\n"
        
        run_state.context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
        run_state.context_results = {"source": "web_search"}
        logger.info(
            "orchestration.web_search_node_completed conversation_id=%s elapsed_ms=%s",
            conversation_id,
            int((time.time() - node_start) * 1000),
        )
        if trace:
            trace.mark("web_search_finished")
        yield "event: results_obj\n\n"

    async def _node_prompt_assembly(self, user_id: str, conversation_id: str, messages: List[Dict[str, str]], use_rag: bool, use_web_search: bool, force_think: bool, context_results_obj: Any, last_user_msg: str, context_prompt: str = "", trace: Optional[TurnLatencyTrace] = None, turn_plan: Optional[TurnPlan] = None, response_policy: Any = None) -> List[Dict[str, str]]:
        """
        Assemble the final system prompt and inject context retrieved from RAG, Web Search, and Memory.

        Args:
            user_id (str): The user identifier.
            conversation_id (str): The conversation identifier.
            messages (List[Dict[str, str]]): The base conversation messages.
            use_rag (bool): Whether RAG was used.
            use_web_search (bool): Whether web search was used.
            force_think (bool): Whether reasoning output is enforced.
            context_results_obj (Any): The retrieval results object.
            last_user_msg (str): The latest user message.
            context_prompt (str): The formatted context text block. Defaults to "".
            response_policy (Any): Structured EDF policy controlling answer
                depth, tone, structure, and follow-up behavior. Accepts ``None``
                for legacy call sites, which lets context assembly use its
                conservative default.

        Returns:
            List[Dict[str, str]]: The finalized list of messages ready to be sent to the LLM.
        """
        from config import settings
        from memory_store import get_global_store

        context = await self.context_service.build_conversation_context(
            user_id=user_id,
            conversation_id=conversation_id,
            messages=messages,
            use_rag=use_rag,
            use_web_search=use_web_search,
            force_think=force_think,
            context_results_obj=context_results_obj,
            last_user_msg=last_user_msg,
            context_prompt=context_prompt,
            client=self.client,
            snapshot_loader=get_hot_memory_snapshot,
            store=get_global_store(),
            chat_avatar_key=_chat_avatar_key(conversation_id),
            trace=trace,
            allow_long_term_memory_query=(
                turn_plan.allow_long_term_memory_query
                if turn_plan is not None
                else None
            ),
            memory_skip_reason=(
                turn_plan.reason_code
                if turn_plan is not None
                else ""
            ),
            explicit_recall_memory_timeout_ms=settings.explicit_recall_memory_timeout_ms,
            enable_explicit_recall_memory_cache=settings.enable_explicit_recall_memory_cache,
            explicit_recall_memory_cache_ttl_seconds=settings.explicit_recall_memory_cache_ttl_seconds,
            response_policy=response_policy,
        )
        logger.info(
            "orchestration.context_prepared conversation_id=%s learner_understanding=%s retrieved_memory=%s",
            conversation_id,
            context.learner_understanding,
            context.retrieved_memory,
        )
        return context.messages


    async def _node_llm_stream(self, user_id: str, conversation_id: str, last_user_msg: str, messages: List[Dict[str, Any]], force_think: bool, max_tokens: int, temperature: float, top_p: float, repetition_penalty: float, request: Request, tool_budget=None, trace: Optional[TurnLatencyTrace] = None) -> AsyncGenerator[str, None]:
        """
        Execute the main LLM generation stream, handling tool calls and yielding tokens.

        Args:
            user_id (str): The user identifier.
            conversation_id (str): The conversation identifier.
            last_user_msg (str): The latest user message.
            messages (List[Dict[str, Any]]): The finalized prompt messages.
            force_think (bool): Whether reasoning mode is enabled.
            max_tokens (int): Maximum tokens to generate.
            temperature (float): Sampling temperature.
            top_p (float): Nucleus sampling top-p.
            repetition_penalty (float): Repetition penalty.
            request (Request): The incoming FastAPI request.
            tool_budget (Optional[Any]): The tracker for tool usage limits. Defaults to None.

        Yields:
            str: SSE formatted token chunks and tool status updates.
        """
        async for event in self.stream_service.stream(
            user_id=user_id,
            conversation_id=conversation_id,
            last_user_msg=last_user_msg,
            messages=messages,
            force_think=force_think,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            request=request,
            tool_budget=tool_budget,
            trace=trace,
        ):
            yield event

    async def _node_post_generation(self, last_user_msg: str, answer_content_accumulator: str, context_results_obj: Any, use_rag: bool, use_web_search: bool, trace: Optional[TurnLatencyTrace] = None) -> AsyncGenerator[str, None]:
        """
        Perform post-generation tasks such as generating follow-up suggestions.

        Args:
            last_user_msg (str): The user's input message.
            answer_content_accumulator (str): The full text generated by the LLM.
            context_results_obj (Any): The retrieval results object.
            use_rag (bool): Whether RAG was used.
            use_web_search (bool): Whether web search was used.

        Yields:
            str: SSE formatted events containing suggestions or completion signals.
        """
        from config import settings

        events = await self.post_turn_service.suggestion_events(
            last_user_msg=last_user_msg,
            answer_text=answer_content_accumulator,
            context_results_obj=context_results_obj,
            use_rag=use_rag,
            use_web_search=use_web_search,
            timeout_ms=settings.suggestion_generation_timeout_ms,
            trace=trace,
        )
        for event in events:
            yield event
                
        # (Removed AI observation push to prevent GUM from generating user attributes based on AI responses)
