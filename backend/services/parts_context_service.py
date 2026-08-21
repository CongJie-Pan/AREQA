"""Build compact LearnLM PARTS task context for main-answer prompts.

The service owns the per-turn prompt-engineering layer that converts the latest
user request and existing backend policy decisions into a stable PARTS task
card. It never changes the public chat API or SSE contracts, and it must not log
raw user text, generated prompt text, model output, credentials, or secrets.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    TaskIntent,
    default_response_policy,
)


logger = logging.getLogger(__name__)

_CONFIDENCE_VALUES = {"low", "medium", "high"}
_MAX_FIELD_CHARS = 80
_MAX_THEME_CHARS = 56
_MAX_MISSING_FIELDS = 5


@dataclass(frozen=True, slots=True)
class PartsContext:
    """A compact per-turn PARTS task card.

    Args:
        persona: The role AREQA should use for this answer turn.
        act: The concrete action the main model should perform.
        recipient: The learner or audience context, without unsupported mastery
            or ability assumptions.
        theme: A short topic summary derived from the latest user message.
        structure: The visible answer shape expected for this turn.
        confidence: Rewrite confidence. Must be one of ``low``, ``medium``, or
            ``high``.
        missing_fields: PARTS fields that remain underspecified. These are safe
            identifiers, not raw user text.

    Compatibility:
        This object is internal prompt context only. It does not authorize tool
        use, memory recall, citations, attachment claims, or learner-state
        assertions.
    """

    persona: str
    act: str
    recipient: str
    theme: str
    structure: str
    confidence: str
    missing_fields: tuple[str, ...] = ()

    def safe_log_metadata(self) -> dict[str, Any]:
        """Return privacy-safe metadata for structured logs.

        Returns:
            A dictionary containing only counts and categorical values. It never
            includes raw user text, prompt text, model output, or PARTS field
            values because those may derive from user content.
        """

        return {
            "confidence": self.confidence,
            "missing_field_count": len(self.missing_fields),
            "has_persona": bool(self.persona),
            "has_act": bool(self.act),
            "has_recipient": bool(self.recipient),
            "has_theme": bool(self.theme),
            "has_structure": bool(self.structure),
        }


class PartsContextService:
    """Create LearnLM PARTS context with bounded LLM rewrite and fallback.

    The main path uses the existing policy classifier model for a small
    JSON-only rewrite. The fallback path is deterministic and must be sufficient
    to keep the main answer flowing when the model times out, returns malformed
    JSON, or produces low-confidence output.
    """

    async def build(
        self,
        *,
        user_message: str,
        response_policy: ResponsePolicy | None,
        turn_plan: Any = None,
        use_rag: bool = False,
        use_web_search: bool = False,
        has_attachments: bool = False,
        client: Any = None,
        model: str | None = None,
        enable_llm_rewrite: bool = True,
        timeout_ms: int = 800,
    ) -> PartsContext:
        """Build a per-turn PARTS context.

        Args:
            user_message: Latest user-authored message. It is sent only to the
                rewrite model and is never logged by this service.
            response_policy: Existing EDF policy selected for the turn.
            turn_plan: Optional foreground route plan used for deterministic
                context shaping.
            use_rag: Whether the turn includes local RAG context.
            use_web_search: Whether the turn includes external web context.
            has_attachments: Whether the current turn is attachment-grounded.
            client: OpenAI-compatible async client for the optional rewrite.
            model: Existing policy classifier model identifier.
            enable_llm_rewrite: Whether the bounded LLM rewrite path is enabled.
            timeout_ms: Rewrite timeout in milliseconds.

        Returns:
            A validated ``PartsContext``. Fallback is returned for all provider,
            parse, validation, timeout, and low-confidence failures.

        Side effects:
            Emits privacy-safe structured logs with stable event names
            ``parts_context.rewrite_selected``, ``parts_context.rewrite_skipped``,
            and ``parts_context.rewrite_fallback``. Logs contain route names,
            enum values, failure type names, and field counts only.
        """

        policy = response_policy or default_response_policy()
        fallback = self.fallback(
            response_policy=policy,
            turn_plan=turn_plan,
            use_rag=use_rag,
            use_web_search=use_web_search,
            has_attachments=has_attachments,
        )
        route_name = self._route_name(turn_plan)
        if (
            not enable_llm_rewrite
            or client is None
            or not model
            or not str(user_message or "").strip()
        ):
            logger.info(
                "parts_context.rewrite_skipped route=%s reason=%s metadata=%s",
                route_name,
                "disabled_or_unavailable",
                json.dumps(fallback.safe_log_metadata(), sort_keys=True),
            )
            return fallback

        try:
            timeout_seconds = max(timeout_ms, 1) / 1000
            rewritten = await asyncio.wait_for(
                self._rewrite_with_model(
                    user_message=user_message,
                    response_policy=policy,
                    turn_plan=turn_plan,
                    use_rag=use_rag,
                    use_web_search=use_web_search,
                    has_attachments=has_attachments,
                    client=client,
                    model=model,
                ),
                timeout=timeout_seconds,
            )
            candidate = self._context_from_payload(rewritten, fallback, user_message)
            if candidate.confidence == "low":
                raise ValueError("low_confidence")
            logger.info(
                "parts_context.rewrite_selected route=%s metadata=%s",
                route_name,
                json.dumps(candidate.safe_log_metadata(), sort_keys=True),
            )
            return candidate
        except Exception as exc:
            logger.warning(
                "parts_context.rewrite_fallback route=%s reason=%s metadata=%s",
                route_name,
                type(exc).__name__,
                json.dumps(fallback.safe_log_metadata(), sort_keys=True),
            )
            return fallback

    def fallback(
        self,
        *,
        response_policy: ResponsePolicy | None,
        turn_plan: Any = None,
        use_rag: bool = False,
        use_web_search: bool = False,
        has_attachments: bool = False,
    ) -> PartsContext:
        """Return deterministic PARTS when rewrite is unavailable.

        Args:
            response_policy: Existing EDF policy selected for the turn.
            turn_plan: Optional foreground route plan.
            use_rag: Whether local RAG context is active.
            use_web_search: Whether web context is active.
            has_attachments: Whether request-scoped attachments are active.

        Returns:
            A conservative PARTS context based only on already-authorized
            backend policy signals.
        """

        policy = response_policy or default_response_policy()
        route_name = self._route_name(turn_plan)
        route_attachment = route_name == "ATTACHMENT_GROUNDED"
        route_rag = route_name == "RAG_EXPLICIT"
        route_web = route_name == "WEB_REQUIRED"
        grounded_attachment = has_attachments or route_attachment
        grounded_rag = use_rag or route_rag
        grounded_web = use_web_search or route_web

        if grounded_attachment:
            persona = "附件理解教練"
        elif grounded_rag:
            persona = "資料導讀教練"
        elif grounded_web:
            persona = "資訊整合教練"
        elif policy.task_intent == TaskIntent.ANSWER_EXAM:
            persona = "精簡解題助手"
        elif policy.task_intent == TaskIntent.WRITE_NOTE:
            persona = "筆記整理助教"
        elif policy.task_intent == TaskIntent.DISCUSS_IDEA:
            persona = "觀點討論教練"
        elif policy.task_intent == TaskIntent.EXPLAIN_TEXT:
            persona = "概念理解教練"
        else:
            persona = "AREQA 引導型學習助手"

        act = {
            TaskIntent.EXPLAIN_TEXT: "解釋使用者當前問題中的核心概念",
            TaskIntent.ANSWER_EXAM: "直接回答題目並提供必要理由",
            TaskIntent.DISCUSS_IDEA: "整理觀點、脈絡與可比較視角",
            TaskIntent.WRITE_NOTE: "產出可整理保存的筆記內容",
            TaskIntent.GENERAL_QA: "回答使用者當前問題",
        }[policy.task_intent]
        if grounded_attachment:
            act = "根據可讀取的附件內容回答使用者問題"
        elif grounded_rag:
            act = "根據提供的參考資料回答並維持引用格式"
        elif grounded_web:
            act = "整合外部搜尋結果回答使用者問題"

        structure = self._structure_for_policy(policy)
        missing_fields: tuple[str, ...] = ()
        if policy.task_intent != TaskIntent.ANSWER_EXAM:
            missing_fields = ("recipient_level",)

        return PartsContext(
            persona=persona,
            act=act,
            recipient="程度未知的學習者，不假設已掌握概念",
            theme="使用者當前問題中的核心概念",
            structure=structure,
            confidence="medium",
            missing_fields=missing_fields,
        )

    async def _rewrite_with_model(
        self,
        *,
        user_message: str,
        response_policy: ResponsePolicy,
        turn_plan: Any,
        use_rag: bool,
        use_web_search: bool,
        has_attachments: bool,
        client: Any,
        model: str,
    ) -> dict[str, Any]:
        """Call the policy model to rewrite latest query into strict PARTS JSON."""

        prompt = f"""Rewrite the latest user request into a compact LearnLM PARTS task context for AREQA.
Return strict JSON only with:
{{
  "persona": "short Traditional Chinese role",
  "act": "short Traditional Chinese action",
  "recipient": "short Traditional Chinese audience; use 程度未知的學習者 unless explicit or verified",
  "theme": "short Traditional Chinese topic summary, not the full user message",
  "structure": "short Traditional Chinese answer format",
  "confidence": "low|medium|high",
  "missing_fields": ["safe_identifier"]
}}

Rules:
- Keep every text field short.
- Do not copy the full user message into theme.
- Do not infer learner ability, grade, mood, or mastery unless explicitly provided in the latest request or verified context.
- For DIRECT answers or exam-choice turns, preserve directness and do not force tutoring or follow-up questions.
- PARTS must not override RAG citation rules, attachment grounding, memory boundaries, tool authorization, or safety.

Route: {self._route_name(turn_plan)}
RAG active: {bool(use_rag)}
Web active: {bool(use_web_search)}
Attachment grounded: {bool(has_attachments)}
Response policy:
{json.dumps(response_policy.safe_log_metadata(), ensure_ascii=False, sort_keys=True)}

Latest user request:
{user_message}"""
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return only valid JSON. Do not explain."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=260,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        if not isinstance(parsed, dict):
            raise ValueError("non_object_parts_payload")
        return parsed

    def _context_from_payload(
        self,
        payload: dict[str, Any],
        fallback: PartsContext,
        user_message: str,
    ) -> PartsContext:
        """Validate and sanitize untrusted rewrite output."""

        confidence = str(payload.get("confidence") or fallback.confidence).strip().lower()
        if confidence not in _CONFIDENCE_VALUES:
            confidence = fallback.confidence
        missing_fields = payload.get("missing_fields")
        safe_missing_fields: tuple[str, ...] = ()
        if isinstance(missing_fields, list):
            values = []
            for item in missing_fields[:_MAX_MISSING_FIELDS]:
                cleaned = re.sub(r"[^a-zA-Z0-9_:-]", "", str(item))[:40]
                if cleaned:
                    values.append(cleaned)
            safe_missing_fields = tuple(values)

        theme = self._clean_field(payload.get("theme"), fallback.theme, _MAX_THEME_CHARS)
        if self._looks_like_raw_user_message(theme, user_message):
            theme = fallback.theme

        return PartsContext(
            persona=self._clean_field(payload.get("persona"), fallback.persona),
            act=self._clean_field(payload.get("act"), fallback.act),
            recipient=self._clean_field(payload.get("recipient"), fallback.recipient),
            theme=theme,
            structure=self._clean_field(payload.get("structure"), fallback.structure),
            confidence=confidence,
            missing_fields=safe_missing_fields or fallback.missing_fields,
        )

    @staticmethod
    def _clean_field(value: Any, fallback: str, max_chars: int = _MAX_FIELD_CHARS) -> str:
        """Collapse untrusted text into one short prompt field."""

        cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
        if not cleaned:
            return fallback
        return cleaned[:max_chars]

    @staticmethod
    def _looks_like_raw_user_message(theme: str, user_message: str) -> bool:
        """Return whether a theme appears to copy too much of the raw request."""

        normalized_theme = re.sub(r"\s+", "", theme)
        normalized_user = re.sub(r"\s+", "", user_message)
        if not normalized_theme or not normalized_user:
            return False
        if normalized_theme == normalized_user:
            return True
        return len(normalized_theme) > 40 and normalized_theme in normalized_user

    @staticmethod
    def _route_name(turn_plan: Any) -> str:
        """Return a safe route name without depending on concrete plan classes."""

        route = getattr(turn_plan, "route", None)
        value = getattr(route, "value", route)
        return str(value or "UNKNOWN")

    @staticmethod
    def _structure_for_policy(policy: ResponsePolicy) -> str:
        """Map current EDF structure and follow-up policy into compact wording."""

        if policy.answer_depth == AnswerDepth.DIRECT or policy.followup_mode == FollowupMode.NONE:
            return "短回答 + 必要理由，不加引導問題"
        if policy.structure == ResponseStructure.SHORT:
            return "短回答 + 必要補充"
        if policy.structure == ResponseStructure.NOTE_DRAFT:
            return "可保存的筆記段落或列點"
        if policy.structure == ResponseStructure.ARGUMENT:
            return "核心判斷 + 理由 + 取捨"
        return "分步解釋 + 最多一個診斷性追問"


def format_parts_context(parts_context: PartsContext) -> str:
    """Render a ``PartsContext`` into a compact Traditional Chinese prompt block.

    Args:
        parts_context: Validated PARTS task context for the current turn.

    Returns:
        A prompt block that may be appended to the system prompt. The block
        explicitly states its lower priority than citation, grounding, memory,
        learner-state, tool, and safety boundaries.
    """

    missing = ", ".join(parts_context.missing_fields) if parts_context.missing_fields else "none"
    return (
        "\n\n【PARTS 任務上下文】"
        f"\nP: {parts_context.persona}"
        f"\nA: {parts_context.act}"
        f"\nR: {parts_context.recipient}"
        f"\nT: {parts_context.theme}"
        f"\nS: {parts_context.structure}"
        f"\nconfidence: {parts_context.confidence}"
        f"\nmissing_fields: {missing}"
        "\n若 missing_fields 會實質影響回答品質，最多提出一個簡短澄清問題；否則先回答。"
        "\n【PARTS 優先權邊界】PARTS 只控制回答角色、任務、對象、主題與格式。"
        "不得覆蓋文獻引用、檔案 grounding、記憶安全邊界、使用者狀態規則、工具授權或安全規則。"
    )
