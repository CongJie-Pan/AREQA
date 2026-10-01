"""Build compact LearnLM PARTS task context for main-answer prompts.

The service owns the per-turn prompt-engineering layer that converts the latest
user request and existing backend policy decisions into a stable PARTS task
card. It never changes the public chat API or SSE contracts, and it must not log
raw user text, generated prompt text, model output, credentials, or secrets
unless the explicit sensitive-debug flag is enabled for controlled diagnosis.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from services.answer_style_service import render_learnlm_teaching_rules
from services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    TaskIntent,
    default_response_policy,
)


logger = logging.getLogger(__name__)

from services.conversation.parts_models import PartsContext, format_parts_context
from services.conversation import parts_validation


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
        recent_conversation_context: Any = "",
        turn_plan: Any = None,
        use_rag: bool = False,
        use_web_search: bool = False,
        has_attachments: bool = False,
        client: Any = None,
        model: str | None = None,
        enable_llm_rewrite: bool = True,
        timeout_ms: int = 800,
        enable_debug_logs: bool = False,
    ) -> PartsContext:
        """Build a per-turn PARTS context.

        Args:
            user_message: Latest user-authored message. It is sent only to the
                rewrite model and is never logged by this service.
            response_policy: Existing EDF policy selected for the turn.
            recent_conversation_context: Recent cleaned conversation turns used
                only to resolve follow-up references. It should preserve roles,
                headings, numbered lists, and bold subheadings while excluding
                citations and source-list noise.
            turn_plan: Optional foreground route plan used for deterministic
                context shaping.
            use_rag: Whether the turn includes local RAG context.
            use_web_search: Whether the turn includes external web context.
            has_attachments: Whether the current turn is attachment-grounded.
            client: OpenAI-compatible async client for the optional rewrite.
            model: Existing policy classifier model identifier.
            enable_llm_rewrite: Whether the bounded LLM rewrite path is enabled.
            timeout_ms: Rewrite timeout in milliseconds.
            enable_debug_logs: Explicit sensitive-debug switch. When enabled,
                terminal logs include raw user text, the rewrite prompt, and
                PARTS field values for local diagnosis. Keep disabled outside
                controlled development sessions.

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
                    recent_conversation_context=recent_conversation_context,
                    response_policy=policy,
                    turn_plan=turn_plan,
                    use_rag=use_rag,
                    use_web_search=use_web_search,
                    has_attachments=has_attachments,
                    client=client,
                    model=model,
                    enable_debug_logs=enable_debug_logs,
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
            self._log_sensitive_debug(
                enabled=enable_debug_logs,
                event="parts_context.debug_rewrite_selected_sensitive",
                user_message=user_message,
                parts_context=candidate,
            )
            return candidate
        except Exception as exc:
            logger.warning(
                "parts_context.rewrite_fallback route=%s reason=%s metadata=%s",
                route_name,
                type(exc).__name__,
                json.dumps(fallback.safe_log_metadata(), sort_keys=True),
            )
            self._log_sensitive_debug(
                enabled=enable_debug_logs,
                event="parts_context.debug_rewrite_fallback_sensitive",
                user_message=user_message,
                parts_context=fallback,
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
            persona = "練習引導教練"
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
            TaskIntent.ANSWER_EXAM: "依本回合學習模式處理題目；練習模式下只給最小提示或診斷問題",
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
            composed_instruction=self._compose_instruction(
                persona=persona,
                act=act,
                recipient="程度未知的學習者，不假設已掌握概念",
                theme="使用者當前問題中的核心概念",
                structure=structure,
            ),
            confidence="medium",
            missing_fields=missing_fields,
        )

    async def _rewrite_with_model(
        self,
        *,
        user_message: str,
        recent_conversation_context: Any,
        response_policy: ResponsePolicy,
        turn_plan: Any,
        use_rag: bool,
        use_web_search: bool,
        has_attachments: bool,
        client: Any,
        model: str,
        enable_debug_logs: bool,
    ) -> dict[str, Any]:
        """Call the policy model to rewrite latest query into strict PARTS JSON."""

        recent_context = self.clean_recent_conversation_context(recent_conversation_context)
        prompt = f"""Rewrite the latest user request into AREQA LearnLM PARTS JSON.
Return JSON only:
{{
  "persona": "short zh-TW role",
  "act": "short zh-TW action",
  "recipient": "short zh-TW audience; use 程度未知的學習者 unless explicit/verified",
  "theme": "short zh-TW topic, not full user text",
  "structure": "short zh-TW answer shape",
  "composed_instruction": "one natural zh-TW instruction composed from PARTS",
  "confidence": "low|medium|high",
  "missing_fields": ["safe_identifier"]
}}

Rules:
- Short fields. Do not copy full user text into theme.
- composed_instruction is for the main answer model to follow; never ask it to print P/A/R/T/S labels.
- Do not infer learner level, grade, mood, or mastery unless explicit/verified.
- DIRECT/exam turns: keep direct; do not force tutoring/follow-up.
- Terse learning-topic turns without explicit "完整/總結/整理/列出/時間線/年表/答案/重點" are possible learning entry points.
- Learning entry points: prefer warm subject coach + first exploration step + 蘇格拉底式問答；一次一小步；一小段背景；一個開放式問題；不要一次列完整內容.
- Use Recent conversation context only to resolve follow-up references. If the latest request says 那/這個/為何/怎麼辦/第 N 階段/第 N 點/你說的, preserve the referenced prior topic in theme and composed_instruction.
- Do not copy citation markers or source-list noise into PARTS fields.
- PARTS never overrides citations, attachment grounding, memory, tools, or safety.

Route: {self._route_name(turn_plan)}
RAG active: {bool(use_rag)}
Web active: {bool(use_web_search)}
Attachment grounded: {bool(has_attachments)}
Response policy:
{json.dumps(response_policy.safe_log_metadata(), ensure_ascii=False, sort_keys=True)}

Recent conversation context:
{recent_context or "(none)"}

Latest user request:
{user_message}"""
        if enable_debug_logs:
            logger.warning(
                "parts_context.debug_rewrite_prompt_sensitive payload=%s",
                json.dumps(
                    {
                        "user_message": user_message,
                        "rewrite_prompt": prompt,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return only valid JSON. Do not explain."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=360,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        if not isinstance(parsed, dict):
            raise ValueError("non_object_parts_payload")
        return parsed








    @staticmethod
    def _log_sensitive_debug(
        *,
        enabled: bool,
        event: str,
        user_message: str,
        parts_context: PartsContext,
    ) -> None:
        """Emit opt-in sensitive PARTS debug logs.

        Args:
            enabled: Explicit runtime switch. No sensitive payload is logged
                when false.
            event: Stable debug event name ending with ``_sensitive``.
            user_message: Raw latest user text.
            parts_context: PARTS field values selected for prompt injection.

        Side effects:
            Writes a warning-level terminal log containing raw user text and
            PARTS field values. This is intentionally noisy and must remain
            opt-in because it may contain private user data.
        """

        if not enabled:
            return
        logger.warning(
            "%s payload=%s",
            event,
            json.dumps(
                {
                    "user_message": user_message,
                    "parts": {
                        "persona": parts_context.persona,
                        "act": parts_context.act,
                        "recipient": parts_context.recipient,
                        "theme": parts_context.theme,
                        "structure": parts_context.structure,
                        "composed_instruction": parts_context.composed_instruction,
                        "confidence": parts_context.confidence,
                        "missing_fields": list(parts_context.missing_fields),
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )



    clean_recent_conversation_context = staticmethod(parts_validation.clean_recent_conversation_context)
    _context_from_payload = staticmethod(parts_validation._context_from_payload)
    _clean_field = staticmethod(parts_validation._clean_field)
    _looks_like_raw_user_message = staticmethod(parts_validation._looks_like_raw_user_message)
    _route_name = staticmethod(parts_validation._route_name)
    _structure_for_policy = staticmethod(parts_validation._structure_for_policy)
    _compose_instruction = staticmethod(parts_validation._compose_instruction)
