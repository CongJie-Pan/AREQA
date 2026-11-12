"""Classify PDF intent through OpenRouter's Decisions API."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from openai import AsyncOpenAI

from config import settings
from services.query_policy.models import (
    AttachmentReason,
    AttachmentTask,
    ResponsePolicy,
    default_response_policy,
)
from services.query_policy.pdf_guardrails import _pdf_auto_explain_policy_from

logger = logging.getLogger(__name__)
JEV_MODEL = "typesafe/jev-1.14"
JEV_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
LABELS = {
    "overview": "An introduction, explanation, or summary of the entire available paper.",
    "targeted": "A specific section, result, figure, concept, translation or other operation on the paper.",
    "other": "An unrelated request or a request whose relationship to the paper is unclear.",
}


async def classify_jev(client: AsyncOpenAI, message: str, context: str) -> str:
    response = await client.with_options(max_retries=0).post(
        JEV_ENDPOINT,
        cast_to=object,
        body={
            "model": JEV_MODEL,
            "state": {
                "pdf_available": True,
                "previous_topic": context[:500],
                "latest_user_message": message[:4000],
            },
            "questions": {
                "paper_intent": {
                    "type": "choice",
                    "instructions": "Classify the latest user's intent using the supplied conversation state.",
                    "criteria": LABELS,
                },
            },
        },
    )
    label = response["answers"]["paper_intent"]["choice"]
    if not isinstance(label, str) or label not in LABELS:
        raise ValueError("Unexpected paper intent")
    return label


async def classify_pdf_response_policy(
    client: AsyncOpenAI, message: str, messages: list[dict[str, str]],
) -> ResponsePolicy:
    """Map the decision to an attachment policy within the foreground budget."""
    policy = default_response_policy()
    current_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].get("role") == "user"),
        0,
    )
    previous = messages[current_index - 1] if current_index > 0 else {}
    context = previous.get("content", "") if previous.get("role") in {"user", "assistant"} else ""
    try:
        label = await asyncio.wait_for(
            classify_jev(client, message, context if isinstance(context, str) else ""),
            timeout=max(settings.policy_classifier_timeout_ms, 1) / 1000,
        )
    except asyncio.TimeoutError:
        raise
    except Exception as exc:
        logger.warning("paper.intent_jev_failed reason=%s", type(exc).__name__)
        return policy

    logger.info("paper.intent_jev_selected label=%s", label)
    if label == "overview":
        return _pdf_auto_explain_policy_from(policy)
    if label == "targeted":
        return replace(
            policy,
            attachment_task=AttachmentTask.PAPER_TARGETED_QA,
            attachment_reason=AttachmentReason.TARGETED_ATTACHMENT_TASK,
        )
    return replace(policy, attachment_reason=AttachmentReason.NOT_PAPER_TASK)
