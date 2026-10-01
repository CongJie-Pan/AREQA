"""Routing stage for a single conversation turn."""

from __future__ import annotations

import asyncio
import logging

from config import settings
from core import SearchMode
from policies import SearchDecision, SearchReason

logger = logging.getLogger("backend.services.orchestration_service")

async def plan_search(service, *, last_user_msg, run_context, trace, effective_search_mode,
                      has_attachments, auto_routing_enabled, use_rag, attachments):
    """Choose search and turn policy without emitting transport events.

    Returns:
        Search decision, turn plan, and effective RAG flag for this run.
    """
    self = service
    conversation_id = run_context.conversation_id
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


    return search_decision, turn_plan, use_rag
