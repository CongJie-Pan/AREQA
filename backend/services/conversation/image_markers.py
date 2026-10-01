"""Parse incremental visual markers without exposing them in answer deltas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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
_VISUAL_LEAD_IN_PATTERN = re.compile(
    r"(?:下圖|上圖|圖中|這張圖|此圖|圖表|示意圖|流程圖|地圖|圖片|影像|照片|"
    r"\b(?:figure|image|diagram|chart|graph|map|photo)\b)",
    re.IGNORECASE,
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
        content_offset: UTF-16 code-unit offset in the public answer where the
            marker appeared. This matches JavaScript ``String.slice`` offsets.
    """

    slot_id: str
    query: str
    caption_hint: str
    anchor_after_paragraph: int
    content_offset: int

    def to_payload(self) -> dict[str, Any]:
        """Return the private accumulator payload used by orchestration.

        Returns:
            Complete slot metadata for backend-only image resolution. Unlike
            ``to_stream_payload``, this includes private retrieval context.
        """

        return {
            "slot_id": self.slot_id,
            "query": self.query,
            "caption_hint": self.caption_hint,
            "anchor_after_paragraph": self.anchor_after_paragraph,
            "content_offset": self.content_offset,
        }

    def to_stream_payload(self) -> dict[str, Any]:
        """Return privacy-safe positioning metadata for the public SSE stream.

        Returns:
            A camelCase payload containing only the stable slot identifier and
            public-text positions. Retrieval queries and captions remain inside
            the backend accumulator boundary.
        """

        return {
            "slotId": self.slot_id,
            "anchorAfterParagraph": self.anchor_after_paragraph,
            "contentOffset": self.content_offset,
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

        self.max_slots = max(0, min(max_slots, 4))
        self._pending = ""
        self._public_accumulator = ""
        self._slots: list[ImageRequestSlot] = []
        self._drained_slot_count = 0
        self._rejected_verified_marker_count = 0

    @property
    def slots(self) -> list[ImageRequestSlot]:
        """Return accepted slots in stream order."""

        return list(self._slots)

    @property
    def rejected_verified_marker_count(self) -> int:
        """Return verified markers rejected for missing visual lead-in prose."""

        return self._rejected_verified_marker_count

    def drain_new_slots(self) -> list[ImageRequestSlot]:
        """Return slots recorded since the previous drain call.

        Returns:
            Newly recorded slots in marker order. Existing slots remain
            available through ``slots`` for final answer-block construction.

        Side Effects:
            Advances an internal delivery cursor so each slot is emitted once.
        """

        new_slots = self._slots[self._drained_slot_count :]
        self._drained_slot_count = len(self._slots)
        return list(new_slots)

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
            self._record_marker(marker, "".join(public_parts))
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

    def _record_marker(self, marker: str, public_prefix: str) -> None:
        """Parse and store a complete image request marker if it is usable.

        Args:
            marker: Complete internal image marker.
            public_prefix: Public text accumulated in the current ``feed`` call
                before this marker. It is required because provider chunks may
                contain several paragraphs and a marker in one packet.
        """

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
        public_text_before_marker = self._public_accumulator + public_prefix
        if marker_kind == "verified" and not self._has_visual_lead_in(public_text_before_marker):
            self._rejected_verified_marker_count += 1
            return
        self._slots.append(
            ImageRequestSlot(
                slot_id=slot_id,
                query=query,
                caption_hint=caption_hint,
                anchor_after_paragraph=self._current_anchor_index(public_text_before_marker),
                content_offset=self._utf16_length(public_text_before_marker),
            )
        )

    @staticmethod
    def _has_visual_lead_in(public_text: str) -> bool:
        """Return whether the preceding paragraph explicitly introduces a visual.

        Verified preflight images are already known to the answer model, so a
        marker without nearby explanatory prose signals that the model did not
        integrate the image into its answer. Requiring a non-heading paragraph
        and an explicit visual reference prevents both live and persisted image
        blocks from appearing after unrelated opening text.

        Args:
            public_text: Public answer text emitted before the marker.

        Returns:
            ``True`` when the final paragraph is explanatory prose with a
            visual-reference cue; otherwise ``False``.
        """

        paragraphs = [part.strip() for part in re.split(r"\n{2,}", public_text) if part.strip()]
        if not paragraphs:
            return False
        paragraph = paragraphs[-1]
        if re.match(r"^\s{0,3}#{1,6}(?:\s|$)", paragraph):
            return False
        plain_text = re.sub(r"[*_`>#]", "", paragraph).strip()
        return len(plain_text) >= 12 and bool(_VISUAL_LEAD_IN_PATTERN.search(plain_text))

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

    @staticmethod
    def _current_anchor_index(public_text: str) -> int:
        """Return the paragraph index that owns a marker in ``public_text``."""

        paragraphs = [part.strip() for part in re.split(r"\n{2,}", public_text) if part.strip()]
        return max(len(paragraphs) - 1, 0)

    @staticmethod
    def _utf16_length(value: str) -> int:
        """Return the JavaScript-compatible string offset for ``value``."""

        return len(value.encode("utf-16-le")) // 2

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
