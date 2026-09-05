from __future__ import annotations

import asyncio
import importlib
import json
import logging
import sys

from config import settings
from memory_gate import classify_user_message
from core import AgentEvent, EventType, SearchMode
from policies import CapabilityPolicy, SearchDecision, SearchReason
from services.query_policy_service import AttachmentTask, apply_pdf_auto_explain_guardrail, count_pdf_attachments
from services.query_policy_service import default_response_policy, response_policy_from_legacy
from services.turn_latency_trace import TurnLatencyTrace
from services.orchestration.intake import record_interaction_timestamp
from services.orchestration.utils import _localized_greeting_reply

logger = logging.getLogger("backend.services.orchestration_service")
InterfaceLanguage = str


def _orchestration_facade():
    return (
        sys.modules.get("backend.services.orchestration_service")
        or sys.modules.get("services.orchestration_service")
        or importlib.import_module("services.orchestration_service")
    )

class OrchestrationExecutionMixin:
    async def execute(self, messages: List[Dict[str, str]], conversation_id: str, use_rag: bool, use_web_search: bool,
                      force_think: bool, max_tokens: int, temperature: float, top_p: float,
                      repetition_penalty: float, request: Request, user_id: str, search_mode: Optional[str] = None,
                      interface_language: InterfaceLanguage = "zh-TW",
                      response_mode: str = "text",
                      attachments: Optional[List[Dict[str, Any]]] = None,
                      attachment_visual_sources: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[str, None]:
        last_user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

        request_id_header = request.headers.get("x-request-id") if request and request.headers else None
        effective_search_mode = (
            SearchMode(search_mode)
            if search_mode is not None
            else (SearchMode.ALWAYS if use_web_search else SearchMode.NEVER)
        )
        has_attachments = bool(attachments)
        pdf_attachment_count = count_pdf_attachments(attachments)
        has_pdf_attachment = pdf_attachment_count > 0
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
                skip_timestamp=timestamp_recorded,
            )
            trace.mark("turn_intake_finished")
            if self.client:
                yield sse_adapter.encode_legacy(
                    f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '🎯 正在分析目前用戶的學習狀態'}, ensure_ascii=False)}\n\n",
                    run_context.run_id,
                )

        if last_user_msg and not classify_user_message(last_user_msg).should_prompt:
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
            from config import settings
            trace.mark("policy_classifier_started")
            trace.increment_model_call("policy_classifier")
            policy_task = asyncio.create_task(
                _orchestration_facade().classify_dialogue_policy(
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
                rag_queries = await _orchestration_facade().parse_and_decompose_query(last_user_msg, self.client)
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
                policy_timeout_seconds = (
                    max(int(getattr(settings, "policy_classifier_timeout_ms", 700)), 1)
                    / 1000
                )
                policy_result = await asyncio.wait_for(
                    policy_task,
                    timeout=policy_timeout_seconds,
                )
                if (hasattr(policy_result, "legacy_policy")
                        and callable(getattr(policy_result, "safe_log_metadata", None))
                        and not policy_result.__class__.__module__.startswith("unittest.mock")):
                    response_policy = policy_result
                    response_policy_source = "classifier"
                elif isinstance(policy_result, str):
                    response_policy = response_policy_from_legacy(policy_result)
                    response_policy_source = "legacy"
                else:
                    response_policy = default_response_policy()
                    response_policy_source = "invalid_fallback"
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

        response_policy = apply_pdf_auto_explain_guardrail(
            response_policy,
            user_msg=last_user_msg,
            has_pdf_attachment=has_pdf_attachment,
        )
        policy = response_policy.legacy_policy
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
            interface_language=interface_language,
            response_mode=response_mode,
            has_attachments=has_attachments,
        )
        trace.mark("prompt_assembly_finished")
        final_messages = self._attach_to_latest_user_message(final_messages, attachments or [])
        if has_attachments:
            final_messages = self._add_attachment_grounding_instruction(final_messages)
        should_auto_explain_paper = (
            settings.enable_pdf_paper_auto_explain
            and getattr(response_policy.attachment_task, "value", response_policy.attachment_task)
            == AttachmentTask.PAPER_AUTO_EXPLAIN.value
        )
        logger.info(
            "paper.auto_explain_policy_selected conversation_id=%s enabled=%s applied=%s task=%s reason=%s pdf_count=%s",
            conversation_id,
            settings.enable_pdf_paper_auto_explain,
            should_auto_explain_paper,
            response_policy.attachment_task.value,
            response_policy.attachment_reason.value,
            pdf_attachment_count,
        )
        if should_auto_explain_paper:
            final_messages = self._add_paper_auto_explain_instruction(final_messages)
        max_image_slots = 4 if should_auto_explain_paper else 2

        preverified_image_blocks = None
        if settings.enable_visual_preflight:
            trace.mark("visual_preflight_started")
            visual_preflight_decision = self.visual_answer_service.preflight_decision(
                response_policy,
                last_user_msg,
                turn_plan if turn_plan_enabled else None,
            )
            logger.info(
                "visual.preflight_policy_gate conversation_id=%s allowed=%s blocking_allowed=%s trigger=%s visual_support=%s visual_reason=%s explicit_visual=%s known_affordance=%s max_images=%s has_attachment_visual_sources=%s",
                conversation_id,
                visual_preflight_decision.allowed,
                visual_preflight_decision.blocking_allowed,
                visual_preflight_decision.trigger,
                visual_preflight_decision.visual_support,
                visual_preflight_decision.visual_reason,
                visual_preflight_decision.explicit_visual_request,
                visual_preflight_decision.known_visual_affordance,
                visual_preflight_decision.max_images,
                bool(attachment_visual_sources),
            )
            visual_preflight_allowed = bool(
                visual_preflight_decision.blocking_allowed
                or attachment_visual_sources
            )
            if attachment_visual_sources and visual_preflight_allowed:
                attachment_visual_candidates = await self._extract_attachment_visual_candidates(
                    attachment_visual_sources,
                    conversation_id,
                    model_client=self.client,
                    use_paper_visual_planner=should_auto_explain_paper,
                )
                preverified_image_blocks = await self.output_image_service.prepare_attachment_image_blocks(
                    candidates=attachment_visual_candidates,
                    user_msg=last_user_msg,
                    conversation_id=conversation_id,
                    model_client=self.client,
                )
            elif attachment_visual_sources:
                logger.info(
                    "visual.attachment_preflight_skipped conversation_id=%s reason=policy_gate source_count=%s",
                    conversation_id,
                    len(attachment_visual_sources),
                )
                preverified_image_blocks = {}
            if preverified_image_blocks is None:
                if visual_preflight_allowed:
                    preverified_image_blocks = await self.output_image_service.prepare_preflight_image_blocks(
                        visual_answer_service=self.visual_answer_service,
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
                else:
                    logger.info(
                        "visual.preflight_blocking_skipped conversation_id=%s trigger=%s visual_support=%s explicit_visual=%s known_affordance=%s",
                        conversation_id,
                        visual_preflight_decision.trigger,
                        visual_preflight_decision.visual_support,
                        visual_preflight_decision.explicit_visual_request,
                        visual_preflight_decision.known_visual_affordance,
                    )
                    preverified_image_blocks = {}
            logger.info(
                "visual.preverified_inventory_ready conversation_id=%s available_image_count=%s has_attachment_visual_sources=%s",
                conversation_id,
                len(preverified_image_blocks),
                bool(attachment_visual_sources),
            )
            trace.mark("visual_preflight_finished")
            final_messages = self._add_verified_visual_instruction(
                final_messages,
                preverified_image_blocks,
                response_policy=response_policy,
            )

        effective_max_tokens = max_tokens
        if policy in ["PROBE_UNDERSTANDING", "SUGGEST_ACTION"]:
            effective_max_tokens = 1500
        elif (use_rag or use_web_search) and max_tokens == 2048:
            effective_max_tokens = 2500

        if force_think:
            effective_max_tokens = 3200
        if response_mode == "voice":
            effective_max_tokens = min(effective_max_tokens, 420)
            logger.info(
                "orchestration.voice_token_budget_applied conversation_id=%s max_tokens=%s",
                conversation_id,
                effective_max_tokens,
            )

        # Node 6: Main LLM Stream
        answer_content_accumulator = ""
        planned_image_slots: list[dict[str, Any]] = []
        async for event in self._node_llm_stream(user_id, conversation_id, last_user_msg, final_messages, force_think, effective_max_tokens, temperature, top_p, repetition_penalty, request, run_state.tool_budget, trace=trace, max_image_slots=max_image_slots):
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
        else:
            logger.info(
                "visual.answer_blocks_skipped conversation_id=%s planned_image_slot_count=%s preverified_image_count=%s",
                conversation_id,
                len(planned_image_slots),
                len(preverified_image_blocks or {}),
            )

        async for event in self._node_post_generation(
            last_user_msg,
            answer_content_accumulator,
            context_results_obj,
            use_rag,
            use_web_search,
            trace=trace,
            interface_language=interface_language,
        ):
            yield sse_adapter.encode_legacy(event, run_context.run_id)

        if last_user_msg and self.client:
            try:
                from gum_integration import push_reflection_observation
            except ModuleNotFoundError:
                from backend.gum_integration import push_reflection_observation

            self.post_turn_service.queue_post_turn_work(
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=run_context.run_id,
                messages=messages,
                model=settings.model_policy_classifier,
                client=self.client,
                reflection_fallback=push_reflection_observation,
                evaluation_fallback=_orchestration_facade().async_evaluate_and_update_state,
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
