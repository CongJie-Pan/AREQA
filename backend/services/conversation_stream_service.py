"""Own provider streaming and authorized post-response tool execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List

from core import PublicAnswerFilter
from services.response_boundary_validator import StreamingResponseBoundaryFilter


logger = logging.getLogger(__name__)


def letter_task_id(
    user_id: str,
    conversation_id: str,
    avatar_name: str,
    source_text: str,
) -> str:
    """Build a stable idempotency key without retaining source text."""

    from services.turn_intake_service import normalize_avatar_name

    source_hash = hashlib.sha256(source_text.strip().encode("utf-8")).hexdigest()[:24]
    raw = f"{user_id}|{conversation_id or ''}|{normalize_avatar_name(avatar_name)}|{source_hash}"
    return f"letter-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


class ConversationStreamService:
    """Stream provider output while enforcing filtering and tool boundaries."""

    def __init__(self, client: Any, tool_registry: Any):
        self.client = client
        self.tool_registry = tool_registry

    async def stream(
        self,
        *,
        user_id: str,
        conversation_id: str,
        last_user_msg: str,
        messages: List[Dict[str, Any]],
        force_think: bool,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repetition_penalty: float,
        request: Any,
        tool_budget: Any = None,
        trace: Any = None,
    ) -> AsyncGenerator[str, None]:
        """Yield legacy-compatible SSE chunks and a final accumulator event."""

        if not self.client:
            yield f"data: {json.dumps({'choices': [{'delta': {'content': '[System Error] OPENROUTER_API_KEY is missing.'}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            return

        from config import settings

        started_at = time.time()
        target_model = settings.model_main_thinking if force_think else settings.model_main_instruct
        extra_body = {"repetition_penalty": repetition_penalty}
        has_pdf = any(
            isinstance(message.get("content"), list)
            and any(
                part.get("type") == "file"
                for part in message["content"]
                if isinstance(part, dict)
            )
            for message in messages
        )
        if has_pdf:
            extra_body["plugins"] = [{"id": "file-parser", "pdf": {"engine": "native"}}]
        if force_think:
            extra_body["reasoning"] = {"enabled": True, "max_tokens": 512}

        tools = [{
            "type": "function",
            "function": {
                "name": "send_epistolary_letter",
                "description": "Schedule a requested avatar letter after answering the user in chat.",
                "parameters": {
                    "type": "object",
                    "properties": {"avatar_name": {"type": "string"}},
                    "required": ["avatar_name"],
                },
            },
        }]
        if tool_budget is None:
            from core import ToolBudget, ToolBudgetTracker

            tool_budget = ToolBudgetTracker(ToolBudget())

        accumulator = ""
        output_filter = PublicAnswerFilter()
        boundary_filter = StreamingResponseBoundaryFilter()
        tool_call_name = ""
        tool_call_args = ""
        logger.info(
            "orchestration.stream_started conversation_id=%s model=%s attachment_parser=%s",
            conversation_id,
            target_model,
            has_pdf,
        )
        try:
            if trace:
                trace.increment_model_call("main_answer")
                trace.mark_once("main_model_started")
            generation = asyncio.create_task(
                self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    stream=True,
                    max_tokens=max_tokens,
                    temperature=temperature if temperature > 0 else 0.001,
                    top_p=top_p,
                    extra_body=extra_body,
                    tools=tools,
                    tool_choice="auto",
                )
            )
            while not generation.done():
                done, _ = await asyncio.wait([generation], timeout=5.0)
                if not done:
                    yield ": heartbeat\n\n"
            response = await generation
            async for chunk in response:
                if await request.is_disconnected():
                    logger.info("orchestration.stream_cancelled conversation_id=%s", conversation_id)
                    break
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "tool_calls", None):
                    function = getattr(delta.tool_calls[0], "function", None)
                    if function:
                        tool_call_name = getattr(function, "name", None) or tool_call_name
                        tool_call_args += getattr(function, "arguments", None) or ""
                    continue
                content = getattr(delta, "content", None) or ""
                if content:
                    content = output_filter.feed(content)
                if content:
                    content, reasons = boundary_filter.feed(content)
                    for reason in reasons:
                        logger.warning(
                            "orchestration.response_boundary_blocked conversation_id=%s reason=%s",
                            conversation_id,
                            reason,
                        )
                if content:
                    if trace:
                        trace.mark_once("first_answer_delta")
                    accumulator += content
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': content}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
        except Exception as exc:
            if trace:
                trace.mark_once("main_model_failed")
            logger.exception("orchestration.stream_failed reason=%s", type(exc).__name__)
            error_message = "**[API Error]** 生成回答時發生錯誤，請稍後重試。"
            yield f"data: {json.dumps({'choices': [{'delta': {'content': error_message}, 'index': 0}]}, ensure_ascii=False)}\n\n"

        trailing = output_filter.finish()
        if trailing:
            safe_trailing, reasons = boundary_filter.feed(trailing)
            for reason in reasons:
                logger.warning(
                    "orchestration.response_boundary_blocked conversation_id=%s reason=%s",
                    conversation_id,
                    reason,
                )
            if safe_trailing:
                accumulator += safe_trailing
                yield f"data: {json.dumps({'choices': [{'delta': {'content': safe_trailing}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
        final_text, final_reasons = boundary_filter.finish()
        for reason in final_reasons:
            logger.warning(
                "orchestration.response_boundary_blocked conversation_id=%s reason=%s",
                conversation_id,
                reason,
            )
        if final_text:
            accumulator += final_text
            yield f"data: {json.dumps({'choices': [{'delta': {'content': final_text}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
        logger.info(
            "orchestration.stream_completed conversation_id=%s elapsed_ms=%s",
            conversation_id,
            int((time.time() - started_at) * 1000),
        )
        if trace:
            trace.mark_once("main_model_finished")

        if tool_call_name == "send_epistolary_letter" and tool_call_args:
            try:
                arguments = json.loads(tool_call_args)
                avatar_name = arguments.get("avatar_name", "Unknown")
                await self.tool_registry.execute(
                    "schedule_letter",
                    {
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "user_message": last_user_msg,
                        "avatar_name": avatar_name,
                        "task_id": letter_task_id(
                            user_id, conversation_id, avatar_name, last_user_msg
                        ),
                    },
                    tool_budget,
                )
                notice = f"\n\n*(系統通知：已為您呼叫 {avatar_name or '對應角色'}，信件正在撰寫中，預計 5 分鐘後寄達。)*"
                accumulator += notice
                yield f"data: {json.dumps({'choices': [{'delta': {'content': notice}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.warning("orchestration.mail_tool_failed reason=%s", type(exc).__name__)
        yield f"event: accumulator\ndata: {json.dumps({'accumulator': accumulator})}\n\n"
