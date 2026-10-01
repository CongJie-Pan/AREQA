"""Apply visual policy gates and prepare grounded images before answer generation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import settings
from services.query_policy.classifier import ResponsePolicy, VisualSupport
from services.visual_affordance_registry import match_visual_affordance

logger = logging.getLogger(__name__)

from services.visual_answer.constants import (
    _VISUAL_KEYWORDS,
)
from services.visual_answer.models import (
    ImageBlock,
    PlannedImageSlot,
    VisualPreflightDecision,
)


def preflight_decision(
    service,
    response_policy: ResponsePolicy,
    user_msg: str,
    turn_plan: Any = None,
) -> VisualPreflightDecision:
    """Return privacy-safe metadata for the visual preflight gate.

        Args:
            response_policy: EDF policy selected for the current turn.
            user_msg: Latest user message used only for bounded visual intent
                checks; it must not be logged by callers.
            turn_plan: Optional deterministic turn plan retained for signature
                compatibility with orchestration paths.

        Returns:
            A ``VisualPreflightDecision`` containing only enum values, booleans,
            counters, and reason buckets suitable for backend logs.

        Side Effects:
            None. The stable log event emitted by orchestration is
            ``visual.preflight_policy_gate`` with request correlation metadata.
        """

    del turn_plan
    normalized = user_msg.lower()
    explicit_visual_request = any(keyword in normalized for keyword in _VISUAL_KEYWORDS)
    affordance = match_visual_affordance(user_msg)
    known_visual_affordance = bool(affordance and affordance.preflight_trigger)
    visual_support_value = getattr(
        response_policy.visual_support,
        "value",
        response_policy.visual_support,
    )
    agent_requires_visuals = visual_support_value == VisualSupport.REQUIRED.value
    agent_allows_visuals = visual_support_value in {
        VisualSupport.OPTIONAL.value,
        VisualSupport.REQUIRED.value,
    }
    allowed = bool(
        service.max_images > 0
        and (
            explicit_visual_request
            or known_visual_affordance
            or agent_allows_visuals
        )
    )
    blocking_allowed = bool(
        service.max_images > 0
        and (
            explicit_visual_request
            or agent_requires_visuals
        )
    )
    if service.max_images <= 0:
        trigger = "disabled"
    elif explicit_visual_request:
        trigger = "explicit_visual_request"
    elif known_visual_affordance:
        trigger = "known_visual_affordance"
    elif agent_requires_visuals:
        trigger = "response_policy_required"
    elif agent_allows_visuals:
        trigger = "response_policy_optional"
    else:
        trigger = "policy_gate"
    return VisualPreflightDecision(
        allowed=allowed,
        blocking_allowed=blocking_allowed,
        trigger=trigger,
        visual_support=response_policy.visual_support.value,
        visual_reason=response_policy.visual_reason.value,
        explicit_visual_request=explicit_visual_request,
        known_visual_affordance=known_visual_affordance,
        max_images=service.max_images,
    )


def _should_attempt_preflight(
    service,
    response_policy: ResponsePolicy,
    user_msg: str,
    turn_plan: Any = None,
) -> bool:
    """Return whether the current turn should attempt visual retrieval.

        Response policy classification is the primary agent-level gate. Visual
        retrieval runs only when the EDF decision allows visual support, when
        the user explicitly asks for an image, or when a narrow deterministic
        affordance identifies a known graph-heavy educational concept. This
        keeps broad semantic classification out of this service and avoids paid
        provider/PDF-rendering cost for ordinary responses.
        """

    return service.preflight_decision(response_policy, user_msg, turn_plan).allowed


async def prepare_preflight_image_blocks(
    service,
    *,
    user_msg: str,
    response_policy: ResponsePolicy,
    existing_web_results: list[dict[str, Any]] | None,
    tool_registry: Any,
    tool_budget: Any,
    user_id: str,
    conversation_id: str,
    model_client: Any = None,
    turn_plan: Any = None,
) -> dict[str, ImageBlock]:
    """Resolve verified images before the main answer model runs.

        The preflight path lets the answer model write with knowledge of actual
        verified images instead of requesting images after generation. It keeps
        image selection fail-soft: if no verified image is found, the main model
        simply receives no visual inventory.
        """

    if not settings.enable_visual_preflight:
        return {}
    if not _should_attempt_preflight(service, response_policy, user_msg, turn_plan):
        return {}

    visual_query, rewrite_rule = service._visual_search_query(user_msg)
    if rewrite_rule != "identity":
        logger.info(
            "visual.preflight_query_rewritten conversation_id=%s rule=%s",
            conversation_id,
            rewrite_rule,
        )
    brief = await service._visual_grounding_agent.plan(
        client=model_client,
        model=settings.model_policy_classifier,
        user_msg=user_msg,
        fallback_query=visual_query,
        conversation_id=conversation_id,
        response_policy=response_policy,
        turn_plan=turn_plan,
    )
    slot = PlannedImageSlot(
        slot_id="img_1",
        query=brief.search_query,
        caption_hint="",
        anchor_after_paragraph=0,
    )
    logger.info(
        "visual.preflight_started conversation_id=%s slot_count=1 visual_type=%s brief_source=%s",
        conversation_id,
        brief.visual_type,
        brief.source,
    )
    timeout_seconds = max(0.1, float(settings.visual_preflight_timeout_seconds))
    try:
        blocks = await asyncio.wait_for(
            service._resolve_planned_image_blocks(
                planned_slots=[slot],
                existing_web_results=existing_web_results,
                tool_registry=tool_registry,
                tool_budget=tool_budget,
                user_id=user_id,
                conversation_id=conversation_id,
                model_client=model_client,
                visual_brief=brief,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.info(
            "visual.preflight_timeout conversation_id=%s timeout_seconds=%.1f",
            conversation_id,
            timeout_seconds,
        )
        blocks = {}
    logger.info(
        "visual.preflight_completed conversation_id=%s resolved_image_count=%s",
        conversation_id,
        len(blocks),
    )
    return blocks
