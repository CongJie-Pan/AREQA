"""Shared imports for orchestration service mixins."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
import sys
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Request

from config import settings
from memory_gate import classify_user_message
from core import AgentEvent, ConversationRunState, EventType, SearchMode
from policies import CapabilityPolicy, SearchDecision, SearchReason
from services.query_policy_service import (
    AttachmentTask,
    apply_pdf_auto_explain_guardrail,
    count_pdf_attachments,
    default_response_policy,
    paper_auto_explain_instruction,
    response_policy_from_legacy,
)
from services.turn_latency_trace import TurnLatencyTrace
from services.turn_plan_service import TurnPlan
from services.turn_intake_service import chat_avatar_key as _chat_avatar_key
from services.orchestration.utils import (
    _build_valid_web_sources,
    _localized_greeting_reply,
    classify_dialogue_policy,
    parse_and_decompose_query,
    reorder_for_attention,
)

logger = logging.getLogger(__name__)
InterfaceLanguage = str


def _orchestration_facade():
    return (
        sys.modules.get("backend.services.orchestration_service")
        or sys.modules.get("services.orchestration_service")
        or importlib.import_module("services.orchestration_service")
    )


class OrchestrationPromptingMixin:
    async def _node_prompt_assembly(self, user_id: str, conversation_id: str, messages: List[Dict[str, str]], use_rag: bool, use_web_search: bool, force_think: bool, context_results_obj: Any, last_user_msg: str, context_prompt: str = "", trace: Optional[TurnLatencyTrace] = None, turn_plan: Optional[TurnPlan] = None, response_policy: Any = None, interface_language: InterfaceLanguage = "zh-TW", response_mode: str = "text", has_attachments: bool = False) -> List[Dict[str, str]]:
        """
        Assemble the final system prompt and inject context retrieved from RAG, Web Search, and Memory.

        Args:
            user_id (str): The user identifier.
            conversation_id (str): The conversation identifier.
            messages (List[Dict[str, str]]): The base conversation messages.
            use_rag (bool): Whether RAG was used.
            use_web_search (bool): Whether web search was used.
            force_think (bool): Whether reasoning output is enforced.
            context_results_obj (Any): The retrieval results object.
            last_user_msg (str): The latest user message.
            context_prompt (str): The formatted context text block. Defaults to "".
            response_policy (Any): Structured EDF policy controlling answer
                depth, tone, structure, and follow-up behavior. Accepts ``None``
                for legacy call sites, which lets context assembly use its
                conservative default.

        Returns:
            List[Dict[str, str]]: The finalized list of messages ready to be sent to the LLM.
        """
        from config import settings
        from memory_store import get_global_store

        parts_context = None
        if settings.enable_parts_prompt_context:
            enable_parts_llm_rewrite = self._should_run_parts_llm_rewrite(
                global_enabled=settings.enable_parts_llm_rewrite,
                turn_plan=turn_plan,
                response_policy=response_policy,
                use_rag=use_rag,
                use_web_search=use_web_search,
                has_attachments=has_attachments,
                allow_ungrounded=getattr(
                    settings,
                    "enable_parts_llm_rewrite_for_ungrounded_turns",
                    False,
                ),
            )
            logger.info(
                "parts_context.rewrite_gate conversation_id=%s enabled=%s route=%s grounded=%s allow_ungrounded=%s",
                conversation_id,
                enable_parts_llm_rewrite,
                self._turn_plan_route_name(turn_plan),
                bool(use_rag or use_web_search or has_attachments),
                bool(getattr(settings, "enable_parts_llm_rewrite_for_ungrounded_turns", False)),
            )
            if trace:
                trace.mark("parts_context_started")
                if enable_parts_llm_rewrite and self.client:
                    trace.increment_model_call("parts_context_rewrite")
            parts_context = await self.parts_context_service.build(
                user_message=last_user_msg,
                response_policy=response_policy,
                recent_conversation_context=self._recent_conversation_context(messages),
                turn_plan=turn_plan,
                use_rag=use_rag,
                use_web_search=use_web_search,
                has_attachments=has_attachments,
                client=self.client,
                model=settings.model_policy_classifier,
                enable_llm_rewrite=enable_parts_llm_rewrite,
                timeout_ms=settings.parts_rewrite_timeout_ms,
                enable_debug_logs=settings.enable_parts_prompt_debug_logs,
            )
            if trace:
                trace.mark("parts_context_finished")

        context = await self.context_service.build_conversation_context(
            user_id=user_id,
            conversation_id=conversation_id,
            messages=messages,
            use_rag=use_rag,
            use_web_search=use_web_search,
            force_think=force_think,
            context_results_obj=context_results_obj,
            last_user_msg=last_user_msg,
            context_prompt=context_prompt,
            client=self.client,
            snapshot_loader=_orchestration_facade().get_hot_memory_snapshot,
            store=get_global_store(),
            chat_avatar_key=_chat_avatar_key(conversation_id),
            trace=trace,
            allow_long_term_memory_query=(
                turn_plan.allow_long_term_memory_query
                if turn_plan is not None
                else None
            ),
            memory_skip_reason=(
                turn_plan.reason_code
                if turn_plan is not None
                else ""
            ),
            explicit_recall_memory_timeout_ms=settings.explicit_recall_memory_timeout_ms,
            enable_explicit_recall_memory_cache=settings.enable_explicit_recall_memory_cache,
            explicit_recall_memory_cache_ttl_seconds=settings.explicit_recall_memory_cache_ttl_seconds,
            response_policy=response_policy,
            parts_context=parts_context,
            interface_language=interface_language,
        )
        final_messages = context.messages
        if response_mode == "voice":
            final_messages = self._apply_voice_response_instruction(final_messages)
            logger.info(
                "orchestration.voice_response_mode_applied conversation_id=%s",
                conversation_id,
            )

        logger.info(
            "orchestration.context_prepared conversation_id=%s learner_understanding=%s retrieved_memory=%s",
            conversation_id,
            context.learner_understanding,
            context.retrieved_memory,
        )
        return final_messages

    @staticmethod
    def _apply_voice_response_instruction(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Add speech-safe answer constraints to an assembled prompt.

        Args:
            messages: Final model messages after normal AREQA prompt assembly.

        Returns:
            A copied message list whose system prompt asks the model to produce
            oral, plain-text prose for live voice rendering.

        Side Effects:
            None. The caller emits `orchestration.voice_response_mode_applied`
            with only the conversation id. The instruction never logs prompt
            text or user content.

        Compatibility:
            This overlay changes answer shape only for live voice requests. It
            does not authorize tools, memory, citations, or retrieval behavior
            beyond the already-assembled AREQA prompt.
        """

        voice_instruction = (
            "\n\n【Live Voice 回答格式】本回合正在為即時語音輸出產生內容。"
            "正式回答必須是適合朗讀的純文字：不要使用 Markdown、標題、表格、列點、"
            "emoji、引用編號、程式碼區塊或任何只適合視覺閱讀的格式。"
            "請使用自然口語、短句和穩定節奏；依本回合 learning_mode 決定是否直接回答。"
            "REFERENCE 可以直接回答；LEARN 先補必要理解支點；PRACTICE 不代做學習者應練習的核心步驟。"
            "每次回答最多二到三句；如果內容較長，請先停下來問使用者要不要繼續。"
            "當使用者提出範圍很廣、可從多個角度展開的知識分享、介紹、講解或歷史脈絡請求時，"
            "不要直接展開長篇說明。先用一句自然口語的澄清問題請使用者選方向，"
            "例如想先看起因、人物、時間線、影響、案例或某個子題。"
            "只有當使用者已指定明確角度、範圍或深度時，才給短而聚焦的回答。"
            "除非使用者明確要求其他語言，中文回答一律使用繁體中文。"
        )
        copied = [message.copy() for message in messages]
        if copied and copied[0].get("role") == "system":
            copied[0]["content"] = f"{copied[0].get('content', '')}{voice_instruction}"
            return copied
        return [{"role": "system", "content": voice_instruction.strip()}, *copied]

    @staticmethod
    def _should_run_parts_llm_rewrite(
        *,
        global_enabled: bool,
        turn_plan: Optional[TurnPlan],
        response_policy: Any,
        use_rag: bool,
        use_web_search: bool,
        has_attachments: bool,
        allow_ungrounded: bool,
    ) -> bool:
        """Return whether PARTS should spend a blocking rewrite model call.

        Args:
            global_enabled: Runtime kill switch for all PARTS LLM rewrites.
            turn_plan: Optional foreground plan selected for this turn.
            response_policy: Structured response policy already selected or
                defaulted for prompt assembly.
            use_rag: Whether local RAG context is active.
            use_web_search: Whether web search context is active.
            has_attachments: Whether request-scoped attachments are active.
            allow_ungrounded: Rollout flag for spending rewrite cost on turns
                without document, retrieval, web, or attachment grounding.

        Returns:
            ``True`` only when the rewrite has grounding value that justifies
            delaying the first token, unless explicitly re-enabled for
            ungrounded turns.

        Side Effects:
            None. The caller emits ``parts_context.rewrite_gate`` with safe
            route and boolean metadata only.
        """

        if not global_enabled:
            return False
        if allow_ungrounded:
            return True
        attachment_task = getattr(response_policy, "attachment_task", AttachmentTask.NONE)
        attachment_task_value = getattr(attachment_task, "value", attachment_task)
        route_name = OrchestrationPromptingMixin._turn_plan_route_name(turn_plan)
        grounded_routes = {
            "ATTACHMENT_GROUNDED",
            "RAG_EXPLICIT",
            "WEB_REQUIRED",
        }
        return bool(
            use_rag
            or use_web_search
            or has_attachments
            or route_name in grounded_routes
            or attachment_task_value != AttachmentTask.NONE.value
        )

    @staticmethod
    def _turn_plan_route_name(turn_plan: Optional[TurnPlan]) -> str:
        """Return a safe route name for logs and latency gates."""

        route = getattr(turn_plan, "route", None)
        value = getattr(route, "value", route)
        return str(value or "UNKNOWN")

    @staticmethod
    def _recent_conversation_context(messages: List[Dict[str, Any]], max_turns: int = 5) -> str:
        """Return a bounded recent conversation window for PARTS reference resolution.

        Args:
            messages: Chat messages before prompt assembly. The latest user
                message may be present and is excluded because it is already
                passed separately as ``user_message``.
            max_turns: Number of prior user/assistant pairs to include.

        Returns:
            A role-labeled plain-text context window. The PARTS service performs
            citation/source cleanup so this helper can preserve headings,
            numbered lists, and bold subheadings from the original messages.
        """

        prior_messages = list(messages or [])
        if prior_messages and prior_messages[-1].get("role") == "user":
            prior_messages = prior_messages[:-1]

        max_messages = max(max_turns, 1) * 2
        selected = [
            message
            for message in prior_messages
            if message.get("role") in {"user", "assistant"} and str(message.get("content") or "").strip()
        ][-max_messages:]

        role_labels = {
            "user": "User",
            "assistant": "Assistant",
        }
        blocks: List[str] = []
        for message in selected:
            role = str(message.get("role") or "")
            content = str(message.get("content") or "").strip()
            blocks.append(f"{role_labels.get(role, role)}:\n{content}")
        return "\n\n".join(blocks)
