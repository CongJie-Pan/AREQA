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


@dataclass(frozen=True, slots=True)
class VisualTeachingContext:
    """Privacy-safe teaching policy metadata for visual retrieval.

    Args:
        task_intent: EDF task intent selected for this turn.
        answer_depth: EDF answer-depth constraint selected for this turn.
        tone: EDF response tone selected for this turn.
        structure: EDF answer structure selected for this turn.
        followup_mode: EDF follow-up policy selected for this turn.
        legacy_policy: Compatibility policy label used by orchestration.
        turn_route: Deterministic turn-plan route when available.
        turn_reason: Deterministic turn-plan reason code when available.
    """

    task_intent: str = "unknown"
    answer_depth: str = "unknown"
    tone: str = "unknown"
    structure: str = "unknown"
    followup_mode: str = "unknown"
    legacy_policy: str = "unknown"
    turn_route: str = "unknown"
    turn_reason: str = "unknown"

    def to_prompt_payload(self) -> dict[str, str]:
        """Return bounded metadata safe to send to model-assisted retrieval."""

        return {
            "task_intent": self.task_intent,
            "answer_depth": self.answer_depth,
            "tone": self.tone,
            "structure": self.structure,
            "followup_mode": self.followup_mode,
            "legacy_policy": self.legacy_policy,
            "turn_route": self.turn_route,
            "turn_reason": self.turn_reason,
        }


@dataclass(frozen=True, slots=True)
class VisualBrief:
    """Model-planned visual retrieval brief for one answer.

    Args:
        visual_type: Short visual type the answer needs, such as map or chart.
        search_query: Concrete provider-search query.
        caption_goal: What the image should help the learner understand.
        reject_if: Generic candidate traits that should be rejected.
        source: Safe source label for observability.
        teaching_context: Optional EDF teaching metadata used to align image
            retrieval with the answer strategy.
    """

    visual_type: str
    search_query: str
    caption_goal: str
    reject_if: tuple[str, ...]
    source: str = "agent"
    teaching_context: VisualTeachingContext | None = None

    def grounding_intent(self) -> str:
        """Return a compact JSON intent for candidate grounding."""

        payload = {
            "visual_type": self.visual_type,
            "caption_goal": self.caption_goal,
            "search_query": self.search_query,
            "reject_if": list(self.reject_if),
        }
        if self.teaching_context is not None:
            payload["teaching_context"] = self.teaching_context.to_prompt_payload()
        return json.dumps(payload, ensure_ascii=False)


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
        visual_brief: VisualBrief | None = None,
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
            visual_brief: Optional planned visual brief. When present, the
                model must judge fit against this explicit visual goal.

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
                    messages=self._messages(visual_intent, candidate, visual_brief),
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

    async def plan(
        self,
        *,
        client: Any,
        model: str,
        user_msg: str,
        fallback_query: str,
        conversation_id: str,
        response_policy: Any = None,
        turn_plan: Any = None,
    ) -> VisualBrief:
        """Ask the agent what kind of visual would best support the answer."""

        teaching_context = self._teaching_context(response_policy, turn_plan)
        if not client:
            brief = self._fallback_brief(
                user_msg=user_msg,
                fallback_query=fallback_query,
                teaching_context=teaching_context,
            )
            self._log_fallback_brief(conversation_id, brief, "missing_model_client")
            return brief

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=self._planning_messages(user_msg, fallback_query, teaching_context),
                    temperature=0,
                    max_tokens=220,
                ),
                timeout=self.timeout_seconds,
            )
            content = str(response.choices[0].message.content or "")
            payload = self._parse_json(content)
            reject_if = tuple(
                self._safe_label(item)
                for item in payload.get("reject_if", [])
                if item
            )[:6]
            brief = VisualBrief(
                visual_type=self._safe_label(payload.get("visual_type")),
                search_query=self._bound(str(payload.get("search_query") or fallback_query), 120),
                caption_goal=self._bound(str(payload.get("caption_goal") or ""), 180),
                reject_if=reject_if or ("wrong_visual_type", "decorative_or_generic_image"),
                source="agent",
                teaching_context=teaching_context,
            )
            logger.info(
                "visual.brief_planned conversation_id=%s visual_type=%s source=%s reject_count=%s task_intent=%s answer_depth=%s turn_route=%s",
                conversation_id,
                brief.visual_type,
                brief.source,
                len(brief.reject_if),
                teaching_context.task_intent,
                teaching_context.answer_depth,
                teaching_context.turn_route,
            )
            return brief
        except Exception as exc:
            logger.info(
                "visual.brief_planning_failed conversation_id=%s reason=%s",
                conversation_id,
                type(exc).__name__,
            )
            brief = self._fallback_brief(
                user_msg=user_msg,
                fallback_query=fallback_query,
                teaching_context=teaching_context,
            )
            self._log_fallback_brief(conversation_id, brief, type(exc).__name__)
            return brief

    def _messages(
        self,
        visual_intent: str,
        candidate: VisualCandidate,
        visual_brief: VisualBrief | None = None,
    ) -> list[dict[str, str]]:
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
            "reason (short snake_case). If a visual brief is provided, accept only "
            "candidates that match its visual_type and caption_goal. Reject images "
            "that are merely topically related but visually unsuitable, including "
            "book covers, document scans, portraits, logos, generic illustrations, "
            "or photos when the brief asks for another visual type."
        )
        user_prompt = json.dumps(
            {
                "visual_intent": self._bound(visual_intent, 360),
                "visual_brief": (
                    {
                        "visual_type": visual_brief.visual_type,
                        "caption_goal": visual_brief.caption_goal,
                        "search_query": visual_brief.search_query,
                        "reject_if": list(visual_brief.reject_if),
                    }
                    if visual_brief
                    else None
                ),
                "candidate": candidate_payload,
            },
            ensure_ascii=False,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _planning_messages(
        self,
        user_msg: str,
        fallback_query: str,
        teaching_context: VisualTeachingContext,
    ) -> list[dict[str, str]]:
        """Build the prompt contract for one visual planning decision."""

        system_prompt = (
            "You are a visual planning sub-agent for an educational chat app. "
            "Decide what single image would most concretely help the current "
            "teaching strategy, not merely what is topically related. "
            "Prefer visual forms that explain structure, geography, timelines, "
            "processes, comparison, data, or visual appearance. Return only JSON "
            "with keys: visual_type (short noun), search_query (concrete English "
            "image-search query), caption_goal (one sentence), reject_if (array "
            "of short snake_case candidate traits to reject). Do not choose a "
            "document, book cover, product image, shopping result, or generic "
            "decorative image unless the user explicitly asks for that object. "
            "Use the EDF teaching context to choose a visual suited to the "
            "answer depth, structure, and learner-facing explanation style."
        )
        user_prompt = json.dumps(
            {
                "user_question": self._bound(user_msg, 360),
                "fallback_query": self._bound(fallback_query, 120),
                "teaching_context": teaching_context.to_prompt_payload(),
            },
            ensure_ascii=False,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _fallback_brief(
        self,
        *,
        user_msg: str,
        fallback_query: str,
        teaching_context: VisualTeachingContext,
    ) -> VisualBrief:
        """Build a deterministic EDF-aligned brief when planning is unavailable.

        The fallback avoids a generic ``diagram`` query by combining safe EDF
        policy labels with broad visual-intent signals from the current prompt.
        It does not attempt domain-specific factual translation; provider
        prompts still receive the original bounded query for multilingual
        search.
        """

        visual_type = self._fallback_visual_type(user_msg, fallback_query, teaching_context)
        base_query = self._bound(fallback_query, 100) or self._bound(user_msg, 100) or "educational concept"
        query_suffixes = {
            "map": "educational labeled map",
            "timeline": "educational timeline chart",
            "flowchart": "educational flow diagram",
            "chart": "educational chart diagram",
            "comparison_chart": "educational comparison chart",
        }
        search_query = self._bound(
            f"{base_query} {query_suffixes.get(visual_type, 'educational explanatory diagram')}",
            120,
        )
        caption_goals = {
            "map": "Help the learner connect the explanation to geography or spatial relationships.",
            "timeline": "Help the learner see chronological order and major turning points.",
            "flowchart": "Help the learner understand the process as connected steps.",
            "chart": "Help the learner interpret the data or evidence pattern visually.",
            "comparison_chart": "Help the learner compare key categories or sides at a glance.",
        }
        return VisualBrief(
            visual_type=visual_type,
            search_query=search_query,
            caption_goal=caption_goals.get(visual_type, "Provide a concrete visual aid for the answer."),
            reject_if=(
                "wrong_visual_type",
                "wrong_context",
                "decorative_or_generic_image",
                "product_photo",
                "shopping_page",
                "book_cover",
            ),
            source="edf_fallback",
            teaching_context=teaching_context,
        )

    def _fallback_visual_type(
        self,
        user_msg: str,
        fallback_query: str,
        teaching_context: VisualTeachingContext,
    ) -> str:
        """Infer a broad visual type from EDF structure and prompt signals."""

        text = f"{user_msg} {fallback_query}".lower()
        if any(term in text for term in ("map", "geography", "geographic", "戰場", "戰役", "地圖", "地理", "版圖", "路線")):
            return "map"
        if any(term in text for term in ("timeline", "chronology", "history", "sequence", "年表", "時間線", "歷史", "演變")):
            return "timeline"
        if any(term in text for term in ("process", "workflow", "flow", "step", "流程", "步驟", "程序")):
            return "flowchart"
        if any(term in text for term in ("compare", "versus", "difference", "比較", "差異", "對照")):
            return "comparison_chart"
        if any(term in text for term in ("chart", "plot", "graph", "statistics", "data", "圖表", "統計", "數據", "效果量")):
            return "chart"
        if teaching_context.structure == "step_by_step":
            return "flowchart"
        return "diagram"

    @staticmethod
    def _log_fallback_brief(conversation_id: str, brief: VisualBrief, reason: str) -> None:
        """Log deterministic fallback brief metadata without raw query text."""

        teaching_context = brief.teaching_context or VisualTeachingContext()
        logger.info(
            "visual.brief_built conversation_id=%s visual_type=%s source=%s reason=%s reject_count=%s task_intent=%s answer_depth=%s turn_route=%s",
            conversation_id,
            brief.visual_type,
            brief.source,
            reason,
            len(brief.reject_if),
            teaching_context.task_intent,
            teaching_context.answer_depth,
            teaching_context.turn_route,
        )

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """Parse a strict or fenced JSON object from model output."""

        stripped = content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if fenced:
            stripped = fenced.group(1)
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _teaching_context(cls, response_policy: Any = None, turn_plan: Any = None) -> VisualTeachingContext:
        """Extract safe EDF/turn-plan labels without coupling to concrete types."""

        route = getattr(turn_plan, "route", None)
        return VisualTeachingContext(
            task_intent=cls._safe_enum_value(getattr(response_policy, "task_intent", None)),
            answer_depth=cls._safe_enum_value(getattr(response_policy, "answer_depth", None)),
            tone=cls._safe_enum_value(getattr(response_policy, "tone", None)),
            structure=cls._safe_enum_value(getattr(response_policy, "structure", None)),
            followup_mode=cls._safe_enum_value(getattr(response_policy, "followup_mode", None)),
            legacy_policy=cls._safe_label(getattr(response_policy, "legacy_policy", None)),
            turn_route=cls._safe_enum_value(route),
            turn_reason=cls._safe_label(getattr(turn_plan, "reason_code", None)),
        )

    @classmethod
    def _safe_enum_value(cls, value: Any) -> str:
        """Return a stable label from Enum-like values for prompts and logs."""

        return cls._safe_label(getattr(value, "value", value))

    @staticmethod
    def _safe_label(value: Any) -> str:
        """Return a bounded log-safe label."""

        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "unknown").strip().lower())
        return cleaned[:60] or "unknown"

    @staticmethod
    def _bound(value: str, limit: int) -> str:
        """Collapse and bound metadata sent to the visual grounding model."""

        return re.sub(r"\s+", " ", value or "").strip()[:limit]
