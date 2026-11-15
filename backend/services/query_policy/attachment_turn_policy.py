"""Response policy for turns that carry a PDF.

Two classifiers own different halves of the decision:

* JEV (paper intent) decides how to treat the attachment: whole-paper
  overview, targeted question, or not a paper task.
* EDF (dialogue policy) decides how to teach: learning mode, pedagogical
  action, depth, tone and structure.

Previously a PDF turn ran JEV only, so every pedagogy field fell back to the
default and the EDF learning boundary never applied to attachment turns. Both
now run in parallel and are merged. Each half fails soft on its own: a JEV
failure keeps EDF's teaching decision, and an EDF failure keeps the default
teaching policy with JEV's attachment decision.

``orchestration.attachment_policy_timing`` records how long each classifier
took, whether it succeeded, and the wall time of the parallel step, so the cost
of running both can be measured in production. It logs enum values and timings
only.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from time import perf_counter
from typing import Any, Awaitable, Callable

from config import settings
from services.query_policy.models import (
    AttachmentReason,
    AttachmentTask,
    ResponsePolicy,
    default_response_policy,
)
from services.query_policy.paper_intent import classify_pdf_response_policy

logger = logging.getLogger(__name__)

# Slack so the outer wait does not cut off the inner, individually bounded calls.
_OUTER_TIMEOUT_SLACK_MS = 150


def attachment_policy_timeout_ms() -> int:
    """Outer budget for the parallel step: the slower classifier plus slack."""
    return (
        max(settings.pdf_intent_classifier_timeout_ms, settings.policy_classifier_timeout_ms)
        + _OUTER_TIMEOUT_SLACK_MS
    )


def gate_paper_overview(policy: ResponsePolicy, *, user_msg: str, manifest: Any) -> ResponsePolicy:
    """Keep the whole-paper template for uploads that really are a paper.

    Args:
        policy: Policy after classification and deterministic PDF guardrails.
        user_msg: Current user message; inspected locally, never logged.
        manifest: ``AttachmentManifest`` for this turn's uploads, or ``None``
            on follow-up turns (no new upload), where the policy is unchanged.

    Returns:
        ``policy`` unchanged unless it selects ``PAPER_AUTO_EXPLAIN`` without
        evidence of a paper; then an attachment overview policy that asks the
        answer to cover every attachment.
    """
    if (
        manifest is None
        or policy.attachment_task is not AttachmentTask.PAPER_AUTO_EXPLAIN
        or manifest.allows_paper_overview(user_msg)
    ):
        return policy
    logger.info("orchestration.paper_overview_gated reason=no_paper_evidence %s", manifest.log_fields())
    return replace(
        policy,
        attachment_task=AttachmentTask.NONE,
        attachment_reason=AttachmentReason.ATTACHMENT_OVERVIEW,
    )


def merge_attachment_turn_policy(teaching: ResponsePolicy, attachment: ResponsePolicy) -> ResponsePolicy:
    """Teaching fields from EDF, attachment fields from JEV."""
    if attachment.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN:
        # The paper template needs figure support; keep JEV's visual decision.
        return replace(
            teaching,
            attachment_task=attachment.attachment_task,
            attachment_reason=attachment.attachment_reason,
            visual_support=attachment.visual_support,
            visual_reason=attachment.visual_reason,
        )
    return replace(
        teaching,
        attachment_task=attachment.attachment_task,
        attachment_reason=attachment.attachment_reason,
    )


async def _timed(call: Awaitable[ResponsePolicy], timeout_ms: int) -> tuple[ResponsePolicy | None, str, float]:
    started_at = perf_counter()
    try:
        result = await asyncio.wait_for(call, timeout=max(timeout_ms, 1) / 1000)
        status = "ok" if isinstance(result, ResponsePolicy) else "invalid"
        return (result if status == "ok" else None), status, (perf_counter() - started_at) * 1000
    except asyncio.TimeoutError:
        return None, "timeout", (perf_counter() - started_at) * 1000
    except asyncio.CancelledError:
        raise
    except Exception:
        return None, "error", (perf_counter() - started_at) * 1000


async def classify_attachment_turn_policy(
    client: Any,
    *,
    dialogue_classifier: Callable[..., Awaitable[ResponsePolicy]],
    dialogue_model: str,
    message: str,
    messages: list[dict[str, str]],
    pdf_attachment_count: int,
    manifest: Any = None,
    conversation_id: str = "",
) -> ResponsePolicy:
    """Run JEV and EDF in parallel and merge their decisions.

    Side Effects:
        Two model calls in parallel. Emits ``orchestration.attachment_policy_timing``
        with per-classifier durations and statuses, even when the caller cancels
        the step (status ``cancelled``).
    """
    started_at = perf_counter()
    inventory = manifest.classifier_state() if manifest is not None else None
    jev = (None, "cancelled", 0.0)
    edf = (None, "cancelled", 0.0)
    try:
        jev, edf = await asyncio.gather(
            _timed(
                classify_pdf_response_policy(
                    client, message, messages, conversation_id=conversation_id, inventory=inventory,
                ),
                # JEV enforces its own budget too; this bound only guards a hung call.
                settings.pdf_intent_classifier_timeout_ms + _OUTER_TIMEOUT_SLACK_MS // 2,
            ),
            _timed(
                dialogue_classifier(
                    client,
                    dialogue_model,
                    message,
                    messages,
                    has_pdf_attachment=True,
                    pdf_attachment_count=pdf_attachment_count,
                ),
                settings.policy_classifier_timeout_ms,
            ),
        )
    finally:
        jev_policy, jev_status, jev_ms = jev
        edf_policy, edf_status, edf_ms = edf
        teaching = edf_policy or default_response_policy()
        merged = merge_attachment_turn_policy(teaching, jev_policy or default_response_policy())
        logger.info(
            "orchestration.attachment_policy_timing conversation_id=%s jev_status=%s jev_ms=%.1f "
            "edf_status=%s edf_ms=%.1f parallel_wall_ms=%.1f teaching_source=%s attachment_source=%s "
            "attachment_task=%s learning_mode=%s pedagogical_action=%s",
            conversation_id,
            jev_status, jev_ms,
            edf_status, edf_ms,
            (perf_counter() - started_at) * 1000,
            "edf" if edf_policy else "default",
            "jev" if jev_policy else "default",
            merged.attachment_task.value,
            merged.learning_mode.value,
            merged.pedagogical_action.value,
        )
    logger.debug(
        "orchestration.attachment_policy_merged metadata=%s",
        json.dumps(merged.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
    )
    return merged
