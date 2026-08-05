"""Prompt-driven visual grounding checks for image answer blocks.

The visual grounding agent is a specialist sub-agent: it does not answer the
user and it does not retrieve images. It receives the answer model's visual
intent plus one candidate's provider metadata, then decides whether displaying
that candidate would make the surrounding answer truthful. This prevents a
caption from being paired with a visually inconsistent candidate.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any, Protocol
from urllib.parse import urlparse

from config import settings


logger = logging.getLogger(__name__)


class VisualCandidate(Protocol):
    """Minimal candidate protocol consumed by the visual grounding agent."""

    title: str
    caption: str
    attribution_string: str
    creator: str
    license: str
    source_url: str
    width: int | None
    height: int | None


@dataclass(frozen=True, slots=True)
class VisualGroundingDecision:
    """Result of checking one image candidate against one visual intent.

    Args:
        accepted: Whether the image can be displayed with the intended answer.
        expected_visual_type: Model-inferred type requested by the visual intent.
        candidate_visual_type: Model-inferred type shown by candidate metadata.
        reason: Stable, bounded reason code safe for structured logs.
    """

    accepted: bool
    expected_visual_type: str
    candidate_visual_type: str
    reason: str


class VisualGroundingAgent:
    """Prompt-engineered sub-agent for visual/caption consistency.

    The agent uses an LLM JSON decision rather than domain-specific keyword
    rules. It only receives bounded metadata and never receives raw credentials,
    full source URLs, or the full assistant answer. If no model client is
    available or the check fails, callers can fail open to preserve answer
    availability while logging a safe reason code.
    """

    def __init__(self, *, timeout_seconds: float | None = None) -> None:
        """Initialize the visual grounding agent.

        Args:
            timeout_seconds: Optional per-candidate grounding timeout. Defaults
                to ``settings.visual_grounding_timeout_seconds`` when present,
                otherwise 1.5 seconds.
        """

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(getattr(settings, "visual_grounding_timeout_seconds", 1.5))
        )

    async def evaluate(
        self,
        *,
        client: Any,
        model: str,
        visual_intent: str,
        candidate: VisualCandidate,
        conversation_id: str,
    ) -> VisualGroundingDecision:
        """Ask the visual grounding model whether a candidate matches intent.

        Args:
            client: OpenAI-compatible async client. When absent, the check
                returns a fail-open decision.
            model: Lightweight model route used for JSON classification.
            visual_intent: Combined image query and caption intent. This is sent
                to the model but never logged.
            candidate: Provider-normalized image candidate metadata.
            conversation_id: Correlation id for safe operational logs.

        Returns:
            A bounded grounding decision. Unexpected model failures return a
            fail-open decision with ``reason=model_unavailable``.
        """

        if not client:
            return VisualGroundingDecision(True, "unknown", "unknown", "model_unavailable")
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=self._messages(visual_intent, candidate),
                    temperature=0,
                    max_tokens=180,
                ),
                timeout=self.timeout_seconds,
            )
            content = str(response.choices[0].message.content or "")
            payload = self._parse_json(content)
            decision = VisualGroundingDecision(
                accepted=bool(payload.get("accepted")),
                expected_visual_type=self._safe_label(payload.get("expected_visual_type")),
                candidate_visual_type=self._safe_label(payload.get("candidate_visual_type")),
                reason=self._safe_label(payload.get("reason")),
            )
            logger.info(
                "visual.grounding_checked conversation_id=%s accepted=%s expected_type=%s candidate_type=%s reason=%s",
                conversation_id,
                decision.accepted,
                decision.expected_visual_type,
                decision.candidate_visual_type,
                decision.reason,
            )
            return decision
        except Exception as exc:
            logger.info(
                "visual.grounding_failed conversation_id=%s reason=%s",
                conversation_id,
                type(exc).__name__,
            )
            return VisualGroundingDecision(True, "unknown", "unknown", "model_unavailable")

    def _messages(self, visual_intent: str, candidate: VisualCandidate) -> list[dict[str, str]]:
        """Build the prompt contract for one visual consistency decision."""

        candidate_payload = {
            "title": self._bound(candidate.title, 180),
            "caption": self._bound(candidate.caption, 240),
            "attribution": self._bound(candidate.attribution_string, 180),
            "creator": self._bound(candidate.creator, 120),
            "license": self._bound(candidate.license, 80),
            "source_domain": urlparse(candidate.source_url).netloc.replace("www.", "")[:120],
            "dimensions": {
                "width": candidate.width,
                "height": candidate.height,
            },
        }
        system_prompt = (
            "You are a visual grounding sub-agent for an educational chat app. "
            "Decide whether an image candidate can truthfully support the visual "
            "intent that will appear near it in an answer. Use only the provided "
            "metadata. Do not assume the image shows something unless the metadata "
            "supports it. Return only valid JSON with keys: accepted (boolean), "
            "expected_visual_type (short noun), candidate_visual_type (short noun), "
            "reason (short snake_case). Reject when the intent expects one kind of "
            "visual, such as a map, chart, diagram, portrait, timeline, or process, "
            "but the candidate metadata indicates a different subject or visual kind."
        )
        user_prompt = json.dumps(
            {
                "visual_intent": self._bound(visual_intent, 360),
                "candidate": candidate_payload,
            },
            ensure_ascii=False,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """Parse a strict or fenced JSON object from model output."""

        stripped = content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if fenced:
            stripped = fenced.group(1)
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _safe_label(value: Any) -> str:
        """Return a bounded log-safe label."""

        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "unknown").strip().lower())
        return cleaned[:60] or "unknown"

    @staticmethod
    def _bound(value: str, limit: int) -> str:
        """Collapse and bound metadata sent to the visual grounding model."""

        return re.sub(r"\s+", " ", value or "").strip()[:limit]
