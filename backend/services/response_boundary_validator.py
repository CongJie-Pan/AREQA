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
