"""Routing stage for a single conversation turn."""

from __future__ import annotations

import asyncio
import logging
import re

from config import settings
from core import SearchMode
from policies import SearchDecision, SearchReason

logger = logging.getLogger("backend.services.orchestration_service")

async def plan_search(service, *, last_user_msg, run_context, trace, effective_search_mode,
                      has_attachments, auto_routing_enabled, use_rag, attachments,
                      model_tool_routing=False):
    """Choose search and turn policy without emitting transport events.

    Returns:
        Search decision, turn plan, and effective RAG flag for this run.
    """
    conversation_id = run_context.conversation_id
    trace.mark("search_routing_started")
    if effective_search_mode == SearchMode.AUTO and has_attachments:
        # In AUTO mode the uploaded document is the primary source. Generic
        # search would answer from the filename/query instead of file content.
        search_decision = SearchDecision(False, SearchReason.ATTACHMENT_CONTEXT_PRIORITY)
    elif effective_search_mode == SearchMode.AUTO and model_tool_routing:
        # The main model decides through its web_search tool; no routing call.
        search_decision = SearchDecision(False, SearchReason.MODEL_TOOL_ROUTING)
    elif effective_search_mode == SearchMode.AUTO and auto_routing_enabled:
        trace.increment_model_call("search_routing")
        search_decision = await service.tutor_agent.decide_search(
            last_user_msg,
            run_context,
            client=service.client,
            model=settings.model_policy_classifier,
            timeout_seconds=1.5,
        )
    elif effective_search_mode == SearchMode.AUTO:
        search_decision = service.tutor_agent.search_policy.evaluate(
            last_user_msg, effective_search_mode
        )
    else:
        search_decision = service.tutor_agent.search_policy.evaluate(
            last_user_msg, effective_search_mode
        )
    trace.mark("search_routing_finished")
    request_id = str(getattr(run_context, "request_id", ""))
    safe_request_id = request_id if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id) else "none"
    logger.info(
        "orchestration.search_decision run_id=%s conversation_id=%s request_id=%s "
        "effective_search_mode=%s should_search=%s reason=%s use_rag=%s has_attachments=%s",
        run_context.run_id, conversation_id, safe_request_id, effective_search_mode.value,
        search_decision.should_search, search_decision.reason.value, use_rag, has_attachments,
    )
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

    turn_plan = service.turn_plan_service.plan(
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
            service.tutor_agent.evaluate_search_shadow(
                last_user_msg,
                run_context,
                client=service.client,
                model=settings.model_policy_classifier,
            )
        )
        shadow_task.add_done_callback(
            lambda task: task.exception() if not task.cancelled() else None
        )

    if search_decision.reason is SearchReason.MODEL_TOOL_ROUTING and last_user_msg:
        # The classifier no longer gates this turn; running it off the critical
        # path keeps a per-turn comparison with what the model decides to do.
        task = asyncio.create_task(_model_search_shadow(service, last_user_msg, run_context))
        _SHADOW_TASKS.add(task)
        task.add_done_callback(_SHADOW_TASKS.discard)

    return search_decision, turn_plan, use_rag


# Strong references: the event loop keeps only weak ones to running tasks.
_SHADOW_TASKS: set[asyncio.Task] = set()


async def _model_search_shadow(service, last_user_msg, run_context) -> None:
    """Log what the routing classifier would have decided for a model-routed turn.

    Joined with ``orchestration.model_search_decision`` per conversation by
    ``scripts/performance/report_model_search.py``. Logs ids, the decision and
    latency only; never the message.
    """
    started = asyncio.get_running_loop().time()
    try:
        decision = await service.tutor_agent.decide_search(
            last_user_msg, run_context, client=service.client,
            model=settings.model_policy_classifier, timeout_seconds=1.5,
        )
    except Exception as exc:
        logger.warning("orchestration.model_search_shadow_failed conversation_id=%s reason=%s",
                       run_context.conversation_id, type(exc).__name__)
        return
    logger.info(
        "orchestration.model_search_shadow run_id=%s conversation_id=%s classifier_search=%s reason=%s latency_ms=%d",
        run_context.run_id, run_context.conversation_id, decision.should_search, decision.reason.value,
        int((asyncio.get_running_loop().time() - started) * 1000),
    )
