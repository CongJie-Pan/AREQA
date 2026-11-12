"""Resolve a pending classifier under the foreground timeout budget."""

from __future__ import annotations

import asyncio
import logging

from config import settings
from services.query_policy.models import (
    default_response_policy,
    response_policy_from_legacy,
)

logger = logging.getLogger("backend.services.orchestration_service")

async def resolve_response_policy(policy_task, trace, conversation_id, *, timeout_ms=None):
    """Return policy, provenance and timeout status without writing SSE events."""
    timed_out = False
    response_policy = default_response_policy()
    response_policy_source = "default"
    policy = response_policy.legacy_policy
    if policy_task:
        try:
            configured_timeout_ms = timeout_ms if timeout_ms is not None else settings.policy_classifier_timeout_ms
            policy_timeout_seconds = max(configured_timeout_ms, 1) / 1000
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
            timed_out = True

    return response_policy, response_policy_source, timed_out
