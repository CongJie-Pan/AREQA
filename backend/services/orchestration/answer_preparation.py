"""Answer preparation stage for a single conversation turn."""

from __future__ import annotations

import logging

from config import settings
from services.query_policy.models import (
    AttachmentTask,
)

logger = logging.getLogger("backend.services.orchestration_service")

async def prepare_answer(service, *, user_id, conversation_id, messages, use_rag, use_web_search,
                         force_think, context_results_obj, last_user_msg, run_state, trace,
                         turn_plan, turn_plan_enabled, response_policy, interface_language,
                         tutor_profile, response_mode, has_attachments, attachments,
                         attachment_visual_sources, pdf_attachment_count, max_tokens):
    """Assemble grounded prompts, verified visual inventory and generation limits.

    Returns:
        Prepared messages, token budget, slot limit and verified image inventory.
        All mutable data belongs to the current run.
    """
    self = service
    policy = response_policy.legacy_policy
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
        tutor_profile=tutor_profile,
        response_mode=response_mode,
        has_attachments=has_attachments,
    )
    trace.mark("prompt_assembly_finished")
    final_messages = self._attach_to_latest_user_message(final_messages, attachments or [])
    if has_attachments:
        final_messages = self._add_attachment_grounding_instruction(final_messages)
    else:
        final_messages, missing_visual_guard_applied = self._add_missing_visual_attachment_instruction(
            final_messages,
            last_user_msg,
        )
        if missing_visual_guard_applied:
            logger.info(
                "orchestration.missing_visual_attachment_guard_applied conversation_id=%s",
                conversation_id,
            )
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


    return final_messages, effective_max_tokens, max_image_slots, preverified_image_blocks
