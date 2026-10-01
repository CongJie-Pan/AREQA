"""Build deterministic foreground execution plans for chat turns.

The turn plan is a control layer, not an answering agent. It decides which
existing foreground components may run synchronously while preserving
deterministic authority for search mode, memory scope, SSE terminal behavior,
and durable side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from services.memory.gate import classify_user_message
from policies.memory_policy import MemoryDecision, MemoryPolicy, MemoryScope
from policies.search_policy import SearchDecision


class TurnRoute(str, Enum):
    """Stable safe route names for foreground chat planning."""

    STATIC_GREETING = "STATIC_GREETING"
    GENERAL_CHAT = "GENERAL_CHAT"
    LEARNING_HELP = "LEARNING_HELP"
    EXPLICIT_MEMORY_RECALL = "EXPLICIT_MEMORY_RECALL"
    SENSITIVE_NO_RECALL = "SENSITIVE_NO_RECALL"
    WEB_REQUIRED = "WEB_REQUIRED"
    ATTACHMENT_GROUNDED = "ATTACHMENT_GROUNDED"
    RAG_EXPLICIT = "RAG_EXPLICIT"


class BehaviorAnalysisLevel(str, Enum):
    """Bound foreground behavior analysis cost by route."""

    RULE_ONLY = "RULE_ONLY"
    LIGHTWEIGHT_MODEL = "LIGHTWEIGHT_MODEL"
    DEFERRED_DEEP = "DEFERRED_DEEP"


@dataclass(frozen=True, slots=True)
class TurnPlan:
    """Foreground execution permissions for one chat turn."""

    route: TurnRoute
    behavior_analysis_level: BehaviorAnalysisLevel
    requires_policy_classifier: bool
    allow_long_term_memory_query: bool
    requires_web_query_rewrite: bool
    requires_suggestions: bool
    max_foreground_model_calls: int
    memory_decision: MemoryDecision
    reason_code: str


class TurnPlanService:
    """Create conservative, deterministic foreground turn plans."""

    _LEARNING_KEYWORDS = (
        "教我",
        "解釋",
        "說明",
        "為什麼",
        "怎麼",
        "如何",
        "概念",
        "原理",
        "練習",
        "出題",
        "學習",
        "理解",
    )

    def __init__(self, memory_policy: MemoryPolicy | None = None) -> None:
        """Initialize with the existing deterministic memory policy."""

        self.memory_policy = memory_policy or MemoryPolicy()

    def plan(
        self,
        *,
        user_message: str,
        use_rag: bool,
        has_attachments: bool,
        search_decision: SearchDecision,
        settings: Any,
    ) -> TurnPlan:
        """Return foreground permissions without calling a model.

        Args:
            user_message: Latest user-authored message.
            use_rag: Whether legacy request flags explicitly asked for RAG.
            has_attachments: Whether this turn includes request-scoped files.
            search_decision: Deterministic or bounded-agent search decision
                already authorized by the search mode.
            settings: Runtime settings containing foreground budget flags.

        Returns:
            A run-local immutable foreground plan.
        """

        memory_decision = self.memory_policy.evaluate(user_message)
        classification = classify_user_message(user_message)

        if not classification.should_prompt:
            return self._build(
                TurnRoute.STATIC_GREETING,
                BehaviorAnalysisLevel.RULE_ONLY,
                memory_decision,
                settings,
                reason_code="LOW_INFORMATION_MESSAGE",
                policy_classifier=False,
                long_term_memory=False,
                web_query_rewrite=False,
            )

        if has_attachments:
            return self._build(
                TurnRoute.ATTACHMENT_GROUNDED,
                BehaviorAnalysisLevel.LIGHTWEIGHT_MODEL,
                memory_decision,
                settings,
                reason_code="ATTACHMENT_CONTEXT_PRIORITY",
                policy_classifier=True,
                long_term_memory=False,
                web_query_rewrite=False,
            )

        if use_rag:
            return self._build(
                TurnRoute.RAG_EXPLICIT,
                BehaviorAnalysisLevel.LIGHTWEIGHT_MODEL,
                memory_decision,
                settings,
                reason_code="RAG_EXPLICIT_REQUEST",
                policy_classifier=True,
                long_term_memory=memory_decision.allow_long_term_query,
                web_query_rewrite=False,
            )

        if search_decision.should_search:
            return self._build(
                TurnRoute.WEB_REQUIRED,
                BehaviorAnalysisLevel.LIGHTWEIGHT_MODEL,
                memory_decision,
                settings,
                reason_code=search_decision.reason.value,
                policy_classifier=True,
                long_term_memory=False,
                web_query_rewrite=True,
            )

        if memory_decision.scope == MemoryScope.ALLOW_EXPLICIT_RECALL:
            return self._build(
                TurnRoute.EXPLICIT_MEMORY_RECALL,
                BehaviorAnalysisLevel.LIGHTWEIGHT_MODEL,
                memory_decision,
                settings,
                reason_code=memory_decision.reason_code,
                policy_classifier=True,
                long_term_memory=True,
                web_query_rewrite=False,
            )

        if memory_decision.scope == MemoryScope.DENY_MEMORY:
            return self._build(
                TurnRoute.SENSITIVE_NO_RECALL,
                BehaviorAnalysisLevel.RULE_ONLY,
                memory_decision,
                settings,
                reason_code=memory_decision.reason_code,
                policy_classifier=False,
                long_term_memory=False,
                web_query_rewrite=False,
            )

        is_learning_help = any(keyword in user_message for keyword in self._LEARNING_KEYWORDS)
        route = TurnRoute.LEARNING_HELP if is_learning_help else TurnRoute.GENERAL_CHAT
        policy_classifier = bool(
            is_learning_help
            or getattr(settings, "enable_policy_classifier_for_general_chat", False)
        )
        long_term_memory = bool(
            getattr(settings, "enable_sync_long_term_memory_for_general_chat", False)
        )
        return self._build(
            route,
            BehaviorAnalysisLevel.LIGHTWEIGHT_MODEL if is_learning_help else BehaviorAnalysisLevel.RULE_ONLY,
            memory_decision,
            settings,
            reason_code="LEARNING_HELP" if is_learning_help else "GENERAL_CHAT",
            policy_classifier=policy_classifier,
            long_term_memory=long_term_memory,
            web_query_rewrite=False,
        )

    @staticmethod
    def _build(
        route: TurnRoute,
        behavior_analysis_level: BehaviorAnalysisLevel,
        memory_decision: MemoryDecision,
        settings: Any,
        *,
        reason_code: str,
        policy_classifier: bool,
        long_term_memory: bool,
        web_query_rewrite: bool,
    ) -> TurnPlan:
        """Create a plan with route-specific configurable model budget."""

        general_budget = int(getattr(settings, "foreground_model_call_budget_general", 2))
        learning_budget = int(getattr(settings, "foreground_model_call_budget_learning", 3))
        budget = learning_budget if behavior_analysis_level == BehaviorAnalysisLevel.LIGHTWEIGHT_MODEL else general_budget
        return TurnPlan(
            route=route,
            behavior_analysis_level=behavior_analysis_level,
            requires_policy_classifier=policy_classifier,
            allow_long_term_memory_query=long_term_memory and memory_decision.allow_long_term_query,
            requires_web_query_rewrite=web_query_rewrite,
            requires_suggestions=True,
            max_foreground_model_calls=max(budget, 1),
            memory_decision=memory_decision,
            reason_code=reason_code,
        )
