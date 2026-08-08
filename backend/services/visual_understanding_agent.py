"""Vision-model image understanding for verified answer images.

This module owns the pixel-reading step for output images. It receives one
already-selected public image URL and asks a vision-capable OpenAI-compatible
model to produce bounded JSON that can be safely injected into the final answer
prompt. It does not retrieve candidates, choose images, or answer the user.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from config import settings
from services.visual_grounding_agent import VisualBrief


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VisualUnderstandingResult:
    """Structured summary of what a vision model saw in one image.

    Args:
        image_type: Bounded visual type inferred from visible image content.
        summary: Short factual explanation of the visible image.
        visible_elements: Concrete elements visible in the image.
        how_to_read: Ordered reading guidance for learners.
        limitations: Important uncertainty or unreadable details.
        confidence: Bounded confidence label.
        source: Stable source label, either ``vision_model`` or fallback code.

    Returns:
        The dataclass is immutable and safe to attach to image display metadata.

    Side Effects:
        None. Structured logging is emitted by ``VisualUnderstandingAgent``.
    """

    image_type: str = "unknown"
    summary: str = ""
    visible_elements: tuple[str, ...] = ()
    how_to_read: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    confidence: str = "unknown"
    source: str = "unavailable"


class VisualUnderstandingAgent:
    """Read selected images with a vision-capable model.

    The agent sends the image itself through an ``image_url`` content part, so
    downstream answer generation can rely on model-observed visual evidence
    instead of provider captions alone. Logs use only the conversation id,
    source domain, model name, bounded counts, and error class; they never log
    raw user text, prompts, model output, image URLs, credentials, or tokens.
    """

    def __init__(self, *, timeout_seconds: float | None = None) -> None:
        """Initialize the agent.

        Args:
            timeout_seconds: Optional per-image timeout. Defaults to
                ``settings.visual_understanding_timeout_seconds``.
        """

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(getattr(settings, "visual_understanding_timeout_seconds", 4.0))
        )

    async def analyze(
        self,
        *,
        client: Any,
        model: str,
        image_url: str,
        user_msg: str,
        visual_brief: VisualBrief | None,
        conversation_id: str,
    ) -> VisualUnderstandingResult:
        """Analyze one image URL with a vision-capable chat model.

        Args:
            client: OpenAI-compatible async client.
            model: Vision-capable model route.
            image_url: Public HTTP(S) image URL selected by visual grounding.
            user_msg: Latest user message. Sent to the model for task context
                but never written to logs.
            visual_brief: Optional visual plan used to focus the reading.
            conversation_id: Correlation id for privacy-safe structured logs.

        Returns:
            A bounded ``VisualUnderstandingResult``. On invalid input, missing
            client, timeout, provider failure, or malformed JSON, returns an
            unavailable result so image display can continue without blocking
            the answer.
        """

        source_domain = self._safe_domain(image_url)
        if not client:
            self._log_unavailable(conversation_id, model, source_domain, "missing_model_client")
            return VisualUnderstandingResult(source="missing_model_client")
        if not self._is_safe_image_url(image_url):
            self._log_unavailable(conversation_id, model, source_domain, "invalid_image_url")
            return VisualUnderstandingResult(source="invalid_image_url")

        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await client.chat.completions.create(
                    model=model,
                    messages=self._messages(
                        image_url=image_url,
                        user_msg=user_msg,
                        visual_brief=visual_brief,
                    ),
                    temperature=0,
                    max_tokens=500,
                )
            content = self._response_content(response)
            result = self._result_from_payload(self._parse_json(content))
        except Exception as exc:
            self._log_unavailable(conversation_id, model, source_domain, type(exc).__name__)
            return VisualUnderstandingResult(source="provider_unavailable")

        logger.info(
            "visual.understanding_completed conversation_id=%s model=%s source_domain=%s image_type=%s confidence=%s visible_element_count=%s how_to_read_count=%s",
            conversation_id,
            model,
            source_domain or "unknown",
            result.image_type,
            result.confidence,
            len(result.visible_elements),
            len(result.how_to_read),
        )
        return result

    @staticmethod
    def _messages(
        *,
        image_url: str,
        user_msg: str,
        visual_brief: VisualBrief | None,
    ) -> list[dict[str, Any]]:
        """Build the multimodal request sent to the vision model."""

        brief_payload = (
            {
                "visual_type": visual_brief.visual_type,
                "caption_goal": visual_brief.caption_goal,
                "reject_if": list(visual_brief.reject_if),
            }
            if visual_brief is not None
            else {}
        )
        task_payload = {
            "user_question": user_msg,
            "visual_brief": brief_payload,
            "required_json_schema": {
                "image_type": "short label",
                "summary": "one or two factual sentences about visible content",
                "visible_elements": ["concrete visible element"],
                "how_to_read": ["ordered learner-facing reading step"],
                "limitations": ["uncertainty or unreadable visual detail"],
                "confidence": "high | medium | low",
            },
        }
        return [
            {
                "role": "system",
                "content": (
                    "You are a visual understanding agent for educational answers. "
                    "Use only visible image content and the provided task context. "
                    "Return strict JSON only. Do not infer hidden facts from the "
                    "source domain, filename, prior knowledge, or surrounding page."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze this image for an educational explanation. "
                            "Identify what is visibly present and how a learner "
                            "should read it.\n"
                            + json.dumps(task_payload, ensure_ascii=False)
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ]

    @classmethod
    def _result_from_payload(cls, payload: dict[str, Any]) -> VisualUnderstandingResult:
        """Convert untrusted model JSON into bounded internal fields."""

        return VisualUnderstandingResult(
            image_type=cls._safe_label(payload.get("image_type")),
            summary=cls._bound_text(payload.get("summary"), 500),
            visible_elements=cls._safe_text_tuple(payload.get("visible_elements"), 10, 140),
            how_to_read=cls._safe_text_tuple(payload.get("how_to_read"), 8, 180),
            limitations=cls._safe_text_tuple(payload.get("limitations"), 6, 160),
            confidence=cls._safe_confidence(payload.get("confidence")),
            source="vision_model",
        )

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """Parse strict JSON or a JSON object embedded in model text."""

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                raise
            payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("visual_understanding_payload_not_object")
        return payload

    @staticmethod
    def _response_content(response: Any) -> str:
        """Extract text content from common OpenAI-compatible response shapes.

        Some providers return SDK objects while others return dictionary-like
        payloads or content-part arrays. The vision step should fail only when
        usable text is genuinely absent, not because a provider used a slightly
        different response container.
        """

        choices = (
            response.get("choices")
            if isinstance(response, dict)
            else getattr(response, "choices", None)
        )
        if not choices:
            raise ValueError("visual_understanding_missing_choices")
        first_choice = choices[0]
        message = (
            first_choice.get("message")
            if isinstance(first_choice, dict)
            else getattr(first_choice, "message", None)
        )
        if message is None:
            raise ValueError("visual_understanding_missing_message")
        content = (
            message.get("content")
            if isinstance(message, dict)
            else getattr(message, "content", None)
        )
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            joined = "\n".join(text_parts).strip()
            if joined:
                return joined
        raise ValueError("visual_understanding_missing_content")

    @staticmethod
    def _safe_text_tuple(value: Any, max_items: int, max_length: int) -> tuple[str, ...]:
        """Return a bounded tuple of non-empty plain strings."""

        if not isinstance(value, list):
            return ()
        output: list[str] = []
        for item in value[:max_items]:
            text = VisualUnderstandingAgent._bound_text(item, max_length)
            if text:
                output.append(text)
        return tuple(output)

    @staticmethod
    def _bound_text(value: Any, max_length: int) -> str:
        """Collapse whitespace and cap text returned by the model."""

        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:max_length]

    @staticmethod
    def _safe_label(value: Any) -> str:
        """Normalize model-provided labels for prompts and logs."""

        label = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "unknown").lower()).strip("_")
        return label[:48] or "unknown"

    @staticmethod
    def _safe_confidence(value: Any) -> str:
        """Return a stable confidence label."""

        label = VisualUnderstandingAgent._safe_label(value)
        return label if label in {"high", "medium", "low", "unknown"} else "unknown"

    @staticmethod
    def _is_safe_image_url(image_url: str) -> bool:
        """Validate the image URL shape before sending it to a model provider."""

        parsed = urlparse(str(image_url or ""))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _safe_domain(image_url: str) -> str:
        """Extract a privacy-safe domain label for structured logs."""

        return urlparse(str(image_url or "")).netloc.lower().removeprefix("www.")

    @staticmethod
    def _log_unavailable(
        conversation_id: str,
        model: str,
        source_domain: str,
        reason: str,
    ) -> None:
        """Emit the stable failure event for image-understanding fallbacks."""

        logger.info(
            "visual.understanding_unavailable conversation_id=%s model=%s source_domain=%s reason=%s",
            conversation_id,
            model,
            source_domain or "unknown",
            reason,
        )
