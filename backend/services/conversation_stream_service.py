"""Own provider streaming and authorized post-response tool execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List

from core import PublicAnswerFilter
from services.response_boundary_validator import StreamingResponseBoundaryFilter


logger = logging.getLogger(__name__)

_IMAGE_REQUEST_START = "[[AREQA_IMAGE_REQUEST"
_VERIFIED_IMAGE_START = "[[AREQA_VERIFIED_IMAGE"
_IMAGE_SLOT_START = "<AREQA_IMAGE_SLOT"
_IMAGE_REQUEST_END = "]]"
_IMAGE_REQUEST_PATTERN = re.compile(r"\[\[AREQA_IMAGE_REQUEST(?P<body>.*?)\]\]", re.DOTALL)
_VERIFIED_IMAGE_PATTERN = re.compile(r"\[\[AREQA_VERIFIED_IMAGE(?P<body>.*?)\]\]", re.DOTALL)
_IMAGE_SLOT_PATTERN = re.compile(r"<AREQA_IMAGE_SLOT(?P<body>.*?)/?>", re.DOTALL)
_IMAGE_REQUEST_ATTR_PATTERN = re.compile(
    r"""(?P<key>id|query|caption_hint|caption|alt)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
_MAX_IMAGE_REQUEST_BUFFER_CHARS = 2000


@dataclass(slots=True)
class ImageRequestSlot:
    """Model-planned visual slot stripped from the public answer stream.

    Args:
        slot_id: Stable model-provided slot identifier after validation.
        query: Short provider-search query. This is treated as sensitive model
            output and is never written to structured logs.
        caption_hint: Optional pedagogical intent for the visual. This is
            display metadata, not a verified image description.
        anchor_after_paragraph: Zero-based public paragraph index after which
            the resolved image should be inserted.
    """

    slot_id: str
    query: str
    caption_hint: str
    anchor_after_paragraph: int

    def to_payload(self) -> dict[str, Any]:
        """Return the internal accumulator payload used by orchestration."""

        return {
            "slot_id": self.slot_id,
            "query": self.query,
            "caption_hint": self.caption_hint,
            "anchor_after_paragraph": self.anchor_after_paragraph,
        }


class ImageRequestMarkerFilter:
    """Remove planned visual markers from public deltas while recording slots.

    The filter owns the streaming privacy boundary for model-emitted image
    markers. It accepts the legacy ``[[AREQA_IMAGE_REQUEST ...]]`` marker, the
    verified-image marker used by preflight, and the public ``<AREQA_IMAGE_SLOT
    .../>`` alias. It never logs marker bodies, queries, captions, alt text, or
    public text. Callers should use `feed()` before appending/yielding public
    content and `finish()` after the provider stream ends to release non-marker
    trailing text if the model emitted a malformed marker.
    """

    def __init__(self, *, max_slots: int = 2) -> None:
        """Initialize an incremental marker parser.

        Args:
            max_slots: Hard cap on accepted visual slots for one answer.
        """

        self.max_slots = max(0, min(max_slots, 2))
        self._pending = ""
        self._public_accumulator = ""
        self._slots: list[ImageRequestSlot] = []

    @property
    def slots(self) -> list[ImageRequestSlot]:
        """Return accepted slots in stream order."""

        return list(self._slots)

    def feed(self, content: str) -> str:
        """Strip complete visual markers from a streamed content fragment.

        Args:
            content: Provider text after public-output safety filters.

        Returns:
            Public text safe to append to the assistant message.
        """

        if not content and not self._pending:
            return ""
        text = self._pending + content
        self._pending = ""
        public_parts: list[str] = []

        while text:
            marker_start = self._next_marker_start(text)
            if marker_start < 0:
                partial_prefix_length = self._partial_marker_prefix_length(text)
                if partial_prefix_length:
                    public_parts.append(text[:-partial_prefix_length])
                    self._pending = text[-partial_prefix_length:]
                else:
                    public_parts.append(text)
                break
            public_parts.append(text[:marker_start])
            marker_end, marker_end_token = self._marker_end(text, marker_start)
            if marker_end < 0:
                self._pending = text[marker_start:]
                break
            marker = text[marker_start : marker_end + len(marker_end_token)]
            self._record_marker(marker)
            text = text[marker_end + len(marker_end_token) :]

        public_text = "".join(public_parts)
        self._public_accumulator += public_text
        if len(self._pending) > _MAX_IMAGE_REQUEST_BUFFER_CHARS:
            # Treat an overlong unfinished marker as malformed text and release
            # it. This prevents a model error from swallowing the rest of the
            # answer while keeping valid short markers hidden from users.
            self._public_accumulator += self._pending
            released = self._pending
            self._pending = ""
            return public_text + released
        return public_text

    def finish(self) -> str:
        """Release buffered malformed marker text after streaming completes."""

        trailing = self._pending
        self._pending = ""
        self._public_accumulator += trailing
        return trailing

    def _record_marker(self, marker: str) -> None:
        """Parse and store a complete image request marker if it is usable."""

        if len(self._slots) >= self.max_slots:
            return
        stripped_marker = marker.strip()
        match = _IMAGE_REQUEST_PATTERN.fullmatch(stripped_marker)
        marker_kind = "request"
        if not match:
            match = _VERIFIED_IMAGE_PATTERN.fullmatch(stripped_marker)
            marker_kind = "verified"
        if not match:
            match = _IMAGE_SLOT_PATTERN.fullmatch(stripped_marker)
            marker_kind = "slot"
        if not match:
            return
        attrs = {
            attr.group("key"): self._clean_attr(attr.group("value"))
            for attr in _IMAGE_REQUEST_ATTR_PATTERN.finditer(match.group("body"))
        }
        slot_id = self._clean_slot_id(attrs.get("id", ""))
        query = attrs.get("query", "")[:120].strip()
        if not slot_id or (marker_kind in {"request", "slot"} and not query):
            return
        caption_hint = (attrs.get("caption_hint") or attrs.get("caption") or attrs.get("alt") or "")[:180].strip()
        self._slots.append(
            ImageRequestSlot(
                slot_id=slot_id,
                query=query,
                caption_hint=caption_hint,
                anchor_after_paragraph=self._current_anchor_index(),
            )
        )

    @staticmethod
    def _next_marker_start(text: str) -> int:
        """Return the next supported marker start offset, or -1."""

        starts = [
            index
            for index in (
                text.find(_IMAGE_REQUEST_START),
                text.find(_VERIFIED_IMAGE_START),
                text.find(_IMAGE_SLOT_START),
            )
            if index >= 0
        ]
        return min(starts) if starts else -1

    @staticmethod
    def _marker_end(text: str, marker_start: int) -> tuple[int, str]:
        """Return the marker end offset and terminator for a supported marker.

        XML-like image slots are intentionally treated as internal control
        markers, not public HTML. The whole tag is stripped before any content
        reaches the client, and malformed trailing tags are released only at
        stream finish through the existing fallback path.
        """

        if text.startswith(_IMAGE_SLOT_START, marker_start):
            return text.find(">", marker_start), ">"
        return text.find(_IMAGE_REQUEST_END, marker_start), _IMAGE_REQUEST_END

    def _current_anchor_index(self) -> int:
        """Return the paragraph index that should own the next image slot."""

        paragraphs = [part.strip() for part in re.split(r"\n{2,}", self._public_accumulator) if part.strip()]
        return max(len(paragraphs) - 1, 0)

    @staticmethod
    def _clean_slot_id(value: str) -> str:
        """Normalize model-provided slot ids to a narrow internal shape."""

        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", value.strip())[:40]
        return cleaned

    @staticmethod
    def _clean_attr(value: str) -> str:
        """Collapse marker attribute whitespace without interpreting escapes."""

        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _partial_marker_prefix_length(text: str) -> int:
        """Return trailing chars that may be the next marker start."""

        marker_starts = (_IMAGE_REQUEST_START, _VERIFIED_IMAGE_START, _IMAGE_SLOT_START)
        max_length = min(len(text), max(len(start) for start in marker_starts) - 1)
        for length in range(max_length, 0, -1):
            if any(start.startswith(text[-length:]) for start in marker_starts):
                return length
        return 0


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
        image_marker_filter = ImageRequestMarkerFilter(max_slots=2)
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
                    content = image_marker_filter.feed(content)
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
                safe_trailing = image_marker_filter.feed(safe_trailing)
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
            final_text = image_marker_filter.feed(final_text)
        marker_trailing = image_marker_filter.finish()
        if marker_trailing:
            final_text = f"{final_text}{marker_trailing}"
        if final_text:
            accumulator += final_text
            yield f"data: {json.dumps({'choices': [{'delta': {'content': final_text}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
        if image_marker_filter.slots:
            logger.info(
                "visual.slot_marker_detected conversation_id=%s slot_count=%s",
                conversation_id,
                len(image_marker_filter.slots),
            )
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
                result = await self.tool_registry.execute(
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
                if result.status == "ok":
                    notice = f"\n\n*(系統通知：已為您呼叫 {avatar_name or '對應角色'}，信件正在撰寫中，預計 5 分鐘後寄達。)*"
                    accumulator += notice
                    yield f"data: {json.dumps({'choices': [{'delta': {'content': notice}, 'index': 0, 'finish_reason': None}]}, ensure_ascii=False)}\n\n"
                else:
                    logger.info(
                        "orchestration.mail_tool_disabled user_id=%s conversation_id=%s",
                        user_id,
                        conversation_id,
                    )
            except Exception as exc:
                logger.warning("orchestration.mail_tool_failed reason=%s", type(exc).__name__)
        yield f"event: accumulator\ndata: {json.dumps({'accumulator': accumulator, 'image_slots': [slot.to_payload() for slot in image_marker_filter.slots]}, ensure_ascii=False)}\n\n"
