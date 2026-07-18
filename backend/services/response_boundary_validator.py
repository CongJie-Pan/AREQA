"""Fail closed for unsupported learner-state claims in generated responses."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ResponseBoundaryResult:
    """Describe whether a response can be safely shown to the user."""

    allowed: bool
    reason: str | None = None


class ResponseBoundaryValidator:
    """Detect unsupported claims that turn a disclosure into a user attribute.

    This deterministic guard deliberately has a small allowlist of high-risk
    patterns. It never stores user or model text; callers log only ``reason``.
    """

    _PATTERNS = (
        ("unsupported_understanding", re.compile(r"你已經(?:理解|掌握|熟悉)")),
        ("unsupported_ability", re.compile(r"(?:你的|你)\S{0,8}(?:基礎較弱|能力不足)")),
    )

    def validate(self, text: str) -> ResponseBoundaryResult:
        """Return a safe reason code when a high-risk assertion is present."""
        for reason, pattern in self._PATTERNS:
            if pattern.search(text or ""):
                return ResponseBoundaryResult(allowed=False, reason=reason)
        return ResponseBoundaryResult(allowed=True)


class StreamingResponseBoundaryFilter:
    """Hold one sentence until unsupported learner-state claims are checked."""

    _BOUNDARIES = frozenset("。！？!?\n")
    _SAFE_REPLACEMENT = "讓我們從目前的問題與具體例子開始。"

    def __init__(self, validator: ResponseBoundaryValidator | None = None) -> None:
        self._validator = validator or ResponseBoundaryValidator()
        self._buffer = ""

    def feed(self, text: str) -> tuple[str, list[str]]:
        """Return complete safe sentences and metadata-only violation reasons."""
        output: list[str] = []
        reasons: list[str] = []
        for char in text:
            self._buffer += char
            if char in self._BOUNDARIES:
                safe_text, reason = self._flush()
                output.append(safe_text)
                if reason:
                    reasons.append(reason)
        return "".join(output), reasons

    def finish(self) -> tuple[str, list[str]]:
        """Validate and release the final unterminated sentence."""
        if not self._buffer:
            return "", []
        safe_text, reason = self._flush()
        return safe_text, [reason] if reason else []

    def _flush(self) -> tuple[str, str | None]:
        candidate = self._buffer
        self._buffer = ""
        result = self._validator.validate(candidate)
        if result.allowed:
            return candidate, None
        return self._SAFE_REPLACEMENT, result.reason
