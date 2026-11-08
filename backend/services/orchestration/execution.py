from __future__ import annotations

import asyncio
import json
import logging

from config import settings
from core import AgentEvent, EventType, SearchMode
from policies import CapabilityPolicy
from services.memory.gate import classify_user_message
from services.orchestration.intake import record_interaction_timestamp
from services.orchestration.utils import _localized_greeting_reply
from services.query_policy.classifier import (
    apply_pdf_auto_explain_guardrail,
    count_pdf_attachments,
)
from services.orchestration.trace import TurnLatencyTrace

logger = logging.getLogger("backend.services.orchestration_service")
InterfaceLanguage = str


from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Request
from services.orchestration.answer_preparation import prepare_answer
from services.orchestration.completion import complete_answer
from services.orchestration.response_policy import resolve_response_policy
from services.orchestration.routing import plan_search


class OrchestrationExecutionMixin:
    async def execute(self, messages: List[Dict[str, str]], conversation_id: str, use_rag: bool, use_web_search: bool,
                      force_think: bool, max_tokens: int, temperature: float, top_p: float,
                      repetition_penalty: float, request: Request, user_id: str, search_mode: Optional[str] = None,
                      interface_language: InterfaceLanguage = "zh-TW",
                      tutor_profile: str = "general",
                      response_mode: str = "text",
                      attachments: Optional[List[Dict[str, Any]]] = None,
                      attachment_visual_sources: Optional[List[Dict[str, Any]]] = None,
                      image_attachments: Optional[List[Any]] = None) -> AsyncGenerator[str, None]:
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        request_id_header = request.headers.get("x-request-id") if request and request.headers else None
        requested_search_mode = (
            SearchMode(search_mode)
            if search_mode is not None
            else (SearchMode.ALWAYS if use_web_search else SearchMode.NEVER)
        )
        has_attachments = bool(attachments)
        effective_search_mode = requested_search_mode
        if (
            requested_search_mode == SearchMode.AUTO
            and not has_attachments
            and not settings.enable_auto_web_search
        ):
            effective_search_mode = SearchMode.NEVER
            logger.info(
                "orchestration.auto_web_search_disabled conversation_id=%s",
                conversation_id,
            )
        pdf_attachment_count = count_pdf_attachments(attachments)
        has_pdf_attachment = pdf_attachment_count > 0
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
        timestamp_recorded = (
            await record_interaction_timestamp(user_id, conversation_id, run_context.run_id)
            if last_user_msg
            else False
        )

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

        search_decision, turn_plan, use_rag = await plan_search(
            self, last_user_msg=last_user_msg, run_context=run_context, trace=trace,
            effective_search_mode=effective_search_mode, has_attachments=has_attachments,
            auto_routing_enabled=auto_routing_enabled, use_rag=use_rag, attachments=attachments,
        )
        use_web_search = search_decision.should_search
        turn_plan_enabled = bool(settings.enable_turn_plan_runtime)

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
                skip_timestamp=timestamp_recorded,
            )
            trace.mark("turn_intake_finished")
            if self.client:
                yield sse_adapter.encode_legacy(
                    f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '🎯 正在分析目前用戶的學習狀態'}, ensure_ascii=False)}\n\n",
                    run_context.run_id,
                )

        # A greeting with an upload is still an attachment task; memory eligibility
        # must not short-circuit the model's access to request-scoped material.
        if last_user_msg and not has_attachments and not classify_user_message(last_user_msg).should_prompt:
            greeting_reply = _localized_greeting_reply(interface_language)
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
            and (
                has_pdf_attachment
                or not turn_plan_enabled
                or turn_plan.requires_policy_classifier
            )
        )
        if should_run_policy_classifier:
            trace.mark("policy_classifier_started")
            trace.increment_model_call("policy_classifier")
            policy_task = asyncio.create_task(
                self.classify_dialogue_policy(
                    self.client,
                    settings.model_policy_classifier,
                    last_user_msg,
                    messages,
                    has_pdf_attachment=has_pdf_attachment,
                    pdf_attachment_count=pdf_attachment_count,
                )
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
                rag_queries = await self.parse_and_decompose_query(last_user_msg, self.client)
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
        response_policy, response_policy_source, policy_timed_out = await resolve_response_policy(
            policy_task, trace, conversation_id,
        )
        if policy_timed_out:
            yield sse_adapter.encode_legacy(
                f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '✅ 已完成基本分析，正在組織回答'}, ensure_ascii=False)}\n\n",
                run_context.run_id,
            )

        response_policy = apply_pdf_auto_explain_guardrail(
            response_policy,
            user_msg=last_user_msg,
            has_pdf_attachment=has_pdf_attachment,
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

        final_messages, effective_max_tokens, max_image_slots, preverified_image_blocks = await prepare_answer(
            self, user_id=user_id, conversation_id=conversation_id, messages=messages,
            use_rag=use_rag, use_web_search=use_web_search, force_think=force_think,
            context_results_obj=context_results_obj, last_user_msg=last_user_msg,
            run_state=run_state, trace=trace, turn_plan=turn_plan,
            turn_plan_enabled=turn_plan_enabled, response_policy=response_policy,
            interface_language=interface_language, tutor_profile=tutor_profile,
            response_mode=response_mode, has_attachments=has_attachments,
            attachments=attachments, attachment_visual_sources=attachment_visual_sources,
            pdf_attachment_count=pdf_attachment_count, max_tokens=max_tokens,
        )

        # Node 6: Main LLM Stream
        answer_content_accumulator = ""
        planned_image_slots: list[dict[str, Any]] = []
        generated_blocks: list[dict[str, Any]] = []
        async for event in self._node_llm_stream(
            user_id, conversation_id, last_user_msg, final_messages, force_think,
            effective_max_tokens, temperature, top_p, repetition_penalty, request,
            run_state.tool_budget, trace=trace, max_image_slots=max_image_slots,
            image_attachments=image_attachments, interface_language=interface_language,
            retrieval_context=run_state.context_prompt if context_results_obj and (use_rag or use_web_search) else "",
        ):
            if event.startswith("event: accumulator\n"):
                try:
                    data_line = next(line for line in event.splitlines() if line.startswith("data: "))
                    accumulator_payload = json.loads(data_line[6:])
                    answer_content_accumulator = accumulator_payload.get("accumulator", "")
                    generated_payload = accumulator_payload.get("generated_blocks", [])
                    if isinstance(generated_payload, list):
                        generated_blocks = [block for block in generated_payload if isinstance(block, dict)]
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

        async for event in complete_answer(
            self, user_id=user_id, conversation_id=conversation_id, last_user_msg=last_user_msg,
            messages=messages, answer_content_accumulator=answer_content_accumulator,
            generated_blocks=generated_blocks, planned_image_slots=planned_image_slots,
            response_policy=response_policy, preverified_image_blocks=preverified_image_blocks,
            context_results_obj=context_results_obj, use_rag=use_rag, use_web_search=use_web_search,
            interface_language=interface_language, session=session, trace=trace,
        ):
            yield event

        trace.mark("terminal_sent")
        log_trace()
        yield sse_adapter.encode_legacy("data: [DONE]\n\n", run_context.run_id)
