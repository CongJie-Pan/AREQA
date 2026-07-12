from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from memory_gate import (
    classify_user_message,
    is_sensitive_context_query,
    requests_cross_conversation_recall,
)


class MemoryScope(StrEnum):
    DENY_MEMORY = "DENY_MEMORY"
    ALLOW_EXPLICIT_RECALL = "ALLOW_EXPLICIT_RECALL"
    ALLOW_PROFILE_ONLY = "ALLOW_PROFILE_ONLY"
    ALLOW_SESSION_ONLY = "ALLOW_SESSION_ONLY"
    ALLOW_AGENT_QUERY = "ALLOW_AGENT_QUERY"


@dataclass(frozen=True, slots=True)
class MemoryDecision:
    scope: MemoryScope
    allow_long_term_query: bool
    reason_code: str


class MemoryPolicy:
    _LOW_INFORMATION_MESSAGES = frozenset({
        "你好", "您好", "嗨", "哈囉", "hello", "hi", "謝謝", "感謝", "thanks", "thankyou",
    })

    def evaluate(self, query: str) -> MemoryDecision:
        normalized = "".join(query.strip().lower().split()).rstrip("!！?？。.")
        if normalized in self._LOW_INFORMATION_MESSAGES or not classify_user_message(query).should_prompt:
            return MemoryDecision(MemoryScope.DENY_MEMORY, False, "LOW_INFORMATION_MESSAGE")

        sensitive = is_sensitive_context_query(query)
        explicit_recall = requests_cross_conversation_recall(query)
        if sensitive and not explicit_recall:
            return MemoryDecision(MemoryScope.DENY_MEMORY, False, "SENSITIVE_WITHOUT_CONSENT")
        if explicit_recall:
            return MemoryDecision(MemoryScope.ALLOW_EXPLICIT_RECALL, True, "EXPLICIT_RECALL_REQUEST")
        return MemoryDecision(MemoryScope.ALLOW_AGENT_QUERY, True, "SUBSTANTIVE_QUERY")
