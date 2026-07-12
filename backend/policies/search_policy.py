from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from core.run_context import SearchMode


class SearchReason(StrEnum):
    USER_FORCED = "USER_FORCED"
    USER_DISABLED = "USER_DISABLED"
    CURRENT_INFORMATION_REQUIRED = "CURRENT_INFORMATION_REQUIRED"
    STABLE_KNOWLEDGE = "STABLE_KNOWLEDGE"
    AGENT_ROUTING_DISABLED = "AGENT_ROUTING_DISABLED"


@dataclass(frozen=True, slots=True)
class SearchDecision:
    should_search: bool
    reason: SearchReason


class SearchPolicy:
    _CURRENT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
        r"\b(today|latest|current|recent|news|price|weather|schedule|version)\b",
        r"今天|目前|最新|近期|新聞|價格|天氣|時程|版本|現任|現在",
        r"20\d{2}",
    ))

    def evaluate(self, query: str, mode: SearchMode) -> SearchDecision:
        if mode == SearchMode.NEVER:
            return SearchDecision(False, SearchReason.USER_DISABLED)
        if mode == SearchMode.ALWAYS:
            return SearchDecision(True, SearchReason.USER_FORCED)

        requires_current_info = any(pattern.search(query) for pattern in self._CURRENT_PATTERNS)
        return SearchDecision(
            requires_current_info,
            SearchReason.CURRENT_INFORMATION_REQUIRED if requires_current_info else SearchReason.STABLE_KNOWLEDGE,
        )
