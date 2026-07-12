from __future__ import annotations

import re


class PublicAnswerFilter:
    """Remove model reasoning tags from streamed public answer content."""

    def __init__(self) -> None:
        self._hidden = False
        self._tag_buffer: str | None = None

    def feed(self, text: str) -> str:
        output: list[str] = []
        for char in text:
            if self._tag_buffer is not None:
                self._tag_buffer += char
                if char == ">":
                    normalized = re.sub(r"\s+", "", self._tag_buffer.lower())
                    if normalized == "<think>":
                        self._hidden = True
                    elif normalized == "</think>":
                        self._hidden = False
                    elif not self._hidden:
                        output.append(self._tag_buffer)
                    self._tag_buffer = None
                continue

            if char == "<":
                self._tag_buffer = char
            elif not self._hidden:
                output.append(char)
        return "".join(output)

    def finish(self) -> str:
        if self._tag_buffer is None or self._hidden:
            self._tag_buffer = None
            return ""
        pending = self._tag_buffer
        self._tag_buffer = None
        return pending
