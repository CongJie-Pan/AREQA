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

    This deterministic guard blocks assistant-authored learner-state judgments
    while allowing user-attributed acknowledgements such as "you mentioned...".
    It never stores user or model text; callers log only safe reason codes.
    """

    _ATTRIBUTION_PREFIXES = ("你提到", "你說", "你表示", "你剛剛說", "你提及")
    _PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("unsupported_understanding", re.compile(r"你(?:已經|現在)?(?:理解|懂得)")),
        ("unsupported_mastery", re.compile(r"你(?:已經|現在)?(?:掌握|熟悉|精通)")),
        ("unsupported_progress", re.compile(r"你(?:已經|正在|有|明顯)?(?:進步|會應用|能應用|學會)")),
        ("unsupported_ability", re.compile(r"(?:你的\S{0,10}(?:基礎較弱|能力不足)|你對\S{0,10}(?:不太熟|不擅長)|你(?:能力不足|不擅長))")),
        ("unsupported_emotional_state", re.compile(r"你(?:現在|目前|可能|應該|看起來|其實)?(?:很|非常|有點)?(?:焦慮|緊張|害怕|沮喪)")),
    )

    def validate(self, text: str) -> ResponseBoundaryResult:
        """Return a safe reason code when a high-risk assertion is present."""
        value = text or ""
        for reason, pattern in self._PATTERNS:
            match = pattern.search(value)
            if match and not self._is_user_attributed(value, match.start()):
                return ResponseBoundaryResult(allowed=False, reason=reason)
        return ResponseBoundaryResult(allowed=True)

    def _is_user_attributed(self, text: str, match_start: int) -> bool:
        """Return whether a matched claim is explicitly attributed to the user."""

        prefix = text[max(0, match_start - 8):match_start]
        return any(marker in prefix for marker in self._ATTRIBUTION_PREFIXES)


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
