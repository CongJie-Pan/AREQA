from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from core.run_context import SearchMode


class SearchReason(str, Enum):
    USER_FORCED = "USER_FORCED"
    USER_DISABLED = "USER_DISABLED"
    EXTERNAL_SEARCH_REQUIRED = "EXTERNAL_SEARCH_REQUIRED"
    # Backward-compatible name used by the tutor routing contract.
    CURRENT_INFORMATION_REQUIRED = "EXTERNAL_SEARCH_REQUIRED"
    INTERNAL_KNOWLEDGE_SUFFICIENT = "INTERNAL_KNOWLEDGE_SUFFICIENT"
    AUTHORITATIVE_SOURCE_REQUIRED = "AUTHORITATIVE_SOURCE_REQUIRED"
    AGENT_ROUTING_DISABLED = "AGENT_ROUTING_DISABLED"
    ATTACHMENT_CONTEXT_PRIORITY = "ATTACHMENT_CONTEXT_PRIORITY"


@dataclass(frozen=True, slots=True)
class SearchDecision:
    should_search: bool
    reason: SearchReason


class SearchPolicy:
    _CURRENT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
        r"\b(today|latest|current|recent|news|price|weather|schedule|version|guideline)\b",
        r"今天|目前|最新|近期|新聞|價格|天氣|時程|版本|現任|現在|指引|指南",
        r"20\d{2}",
    ))
    _AUTHORITATIVE_SOURCE_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
        r"醫學|醫療|臨床|疾病|症狀|診斷|治療|藥物|劑量|副作用|疫苗|手術|癌症|感染",
        r"\b(medical|medicine|clinical|diagnosis|treatment|drug|medication|dose|vaccine|surgery|cancer|infection)\b",
        r"法律|法規|判例|合約|稅務|投資|保險|退休金|理財建議",
        r"\b(legal|law|regulation|contract|tax|investment|insurance|financial advice)\b",
    ))
    _REFERENCE_LOOKUP_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
        r"(有哪些|哪些|列出|清單|列表).*(書|作品|著作|小說|文章|代表作|出版)",
        r"(書|作品|著作|小說|文章|代表作|出版).*(有哪些|哪些|列出|清單|列表)",
        r"\b(what|which|list).*(books|works|novels|essays|publications).*(wrote|written|by|of)\b",
        r"\b(books|works|novels|essays|publications).*(by|of|from)\b",
    ))

    def evaluate(self, query: str, mode: SearchMode) -> SearchDecision:
        if mode == SearchMode.NEVER:
            return SearchDecision(False, SearchReason.USER_DISABLED)
        if mode == SearchMode.ALWAYS:
            return SearchDecision(True, SearchReason.USER_FORCED)

        requires_current_info = any(pattern.search(query) for pattern in self._CURRENT_PATTERNS)
        requires_authoritative_source = any(
            pattern.search(query) for pattern in self._AUTHORITATIVE_SOURCE_PATTERNS
        )
        requires_reference_lookup = any(
            pattern.search(query) for pattern in self._REFERENCE_LOOKUP_PATTERNS
        )
        should_search = (
            requires_current_info
            or requires_authoritative_source
            or requires_reference_lookup
        )
        if requires_authoritative_source:
            reason = SearchReason.AUTHORITATIVE_SOURCE_REQUIRED
        elif should_search:
            reason = SearchReason.EXTERNAL_SEARCH_REQUIRED
        else:
            reason = SearchReason.INTERNAL_KNOWLEDGE_SUFFICIENT
        return SearchDecision(
            should_search,
            reason,
        )
