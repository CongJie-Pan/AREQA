"""Completion stage for a single conversation turn."""

from __future__ import annotations

import json
import logging

from config import settings

logger = logging.getLogger("backend.services.orchestration_service")

async def complete_answer(service, *, user_id, conversation_id, last_user_msg, messages,
                          answer_content_accumulator, generated_blocks, planned_image_slots,
                          response_policy, preverified_image_blocks, context_results_obj,
                          use_rag, use_web_search, interface_language, session, trace):
    """Emit answer blocks and suggestions, then enqueue post-turn work.

    Yields:
        Legacy-compatible SSE events; the caller owns the terminal event.
    """
    self = service
    run_context, run_state, sse_adapter = session.context, session.state, session.transport
    # Node 7: Post-generation
    answer_blocks = generated_blocks or await self.visual_answer_service.build_answer_blocks(
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
            evaluation_fallback=self.evaluate_state,
        )
        logger.info(
            "orchestration.post_turn_queued run_id=%s conversation_id=%s",
            run_context.run_id,
            conversation_id,
        )
        trace.mark("post_turn_queued")
