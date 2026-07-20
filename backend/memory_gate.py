"""
Memory Gate Module.

This module is responsible for analyzing and classifying incoming user messages, client telemetry actions,
and LLM-generated reflection insights. It serves as the primary "gatekeeper" (Memory Gate) that decides whether
a piece of information should be:
- Retained in working memory as the current conversation focus.
- Promoted to long-term explicit or cold storage.
- Discarded or treated as a low-information greeting.
- Evaluated for sensitive context or cross-conversation episodic recall.

It implements conservative, deterministic policies for memory retention, avoiding over-reliance on LLM
advisory outputs for critical storage decisions, and applying rules like TTL expirations for time-bound
or sensitive context.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MemoryGateDecision:
    """
    Represents a decision made by the memory gate regarding how to process a message or observation.

    Attributes:
        category (str): The category of the memory decision (e.g., 'explicit_memory', 'current_focus').
        should_prompt (bool): Whether the memory should be visible in the prompt context.
        should_cold_store (bool): Whether the memory should be stored in cold (long-term) storage.
        ttl_seconds (Optional[int]): Time-to-live for the memory in seconds, or None for indefinite.
        proposition (str): The extracted or generated proposition text.
        reason (str): The reason for the memory gate decision.
        weight (float): The importance or confidence weight of the memory, defaults to 1.0.
    """
    category: str
    should_prompt: bool
    should_cold_store: bool
    ttl_seconds: Optional[int]
    proposition: str
    reason: str
    weight: float = 1.0


_TEMPORAL_MARKERS = ("今天", "昨天", "這週", "下週", "目前", "現在", "最近", "這次")
_NEGATIVE_MARKERS = ("不及格", "很差", "不會", "不擅長", "有學習困難", "能力不足", "失敗", "很弱")


BEHAVIOR_ACTIONS = {
    "scroll",
    "reread",
    "click",
    "idle",
    "focus",
    "blur",
    "hint_opened",
    "compeer_rejected",
}

EXPLICIT_MEMORY_PATTERNS = [
    r"(?:請你|麻煩你)?(?:記住|記得)(?:一下)?(?P<fact>.+)",
]
PASSIVE_PREFERENCE_PATTERNS = [
    r"(?:我(?:真的)?(?:比較)?喜歡|我不喜歡|我討厭|我偏好)(?P<fact>.+)",
    r"(?:學|理解|讀書|練習).*(?:我希望|我想要|我習慣)(?P<fact>.+)",
]
STABLE_FACT_PATTERNS = [
    r"(?:我的名字|我叫)(?P<fact>.+)",
    r"(?:我是|我目前是)(?P<fact>.+)",
]

ROLEPLAY_KEYWORDS = ("扮演", "假扮", "飾演", "角色扮演")
LOW_INFORMATION_GREETINGS = {
    "你好",
    "嗨",
    "哈囉",
    "hello",
    "hi",
    "hey",
    "在嗎",
    "早安",
    "午安",
    "晚安",
}

SENSITIVE_CONTEXT_KEYWORDS = (
    "血壓", "心率", "脈搏", "胸痛", "呼吸", "頭暈", "藥物", "用藥", "醫生", "醫師",
    "健康", "生病", "焦慮", "憂鬱", "自殺", "心理", "家庭", "父親", "母親", "財務", "債務",
)
EXPLICIT_RECALL_KEYWORDS = ("延續", "接續", "之前", "上次", "昨天", "前一個對話", "結合先前")
RECENT_WORKING_CONTEXT_PATTERNS = (
    r"最近(?:在)?(?:讀|看|提|聊|討論|問|學|研究|處理|做|寫)",
    r"最近(?:讀|看|提|聊|討論|問|學|研究|處理|做|寫)(?:過)?(?:的)?(?:書|文章|作品|問題|主題|內容|事情|任務|專案)",
    r"(?:我|我們)最近(?:讀|看|提|聊|討論|問|學|研究|處理|做|寫)(?:過)?(?:的)?",
    r"(?:剛剛|前面)(?:提|聊|討論|問|說|講)(?:到|過)?",
)
TEMPORARY_GOAL_COMPLETION_MARKERS = ("已經完成", "完成了", "不要再提醒", "不用再提醒", "停止提醒")
TEMPORARY_GOAL_CONTEXT_MARKERS = ("目標", "複習", "學習計畫", "讀書計畫")


def _clean_text(value: str) -> str:
    """
    Clean and normalize text by stripping leading/trailing whitespace and condensing multiple spaces.

    Args:
        value (str): The raw text to clean.

    Returns:
        str: The cleaned and normalized text.
    """
    return re.sub(r"\s+", " ", (value or "").strip())


def _extract_explicit_fact(message: str) -> str:
    """
    Extract an explicitly stated fact from a user message based on predefined patterns.

    Args:
        message (str): The user message to analyze.

    Returns:
        str: The extracted explicit fact, or an empty string if no pattern matches or if roleplay is detected.
    """
    text = _clean_text(message)
    if any(keyword in text for keyword in ROLEPLAY_KEYWORDS):
        return ""

    for pattern in EXPLICIT_MEMORY_PATTERNS:
        match = re.search(pattern, text)
        if match:
            fact = _clean_text(match.group("fact"))
            return fact.strip("：:，,。 ")
    return ""


def _extract_pattern_fact(message: str, patterns: list[str]) -> str:
    """Extract a declarative fact from one allowlisted pattern group."""

    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return _clean_text(match.group("fact")).strip("：:，,。 ")
    return ""


def _is_interrogative(message: str) -> bool:
    """Detect questions before any preference or memory keyword matching."""

    text = _clean_text(message)
    if text.endswith(("?", "？")):
        return True
    markers = ("什麼", "為什麼", "怎麼", "如何", "哪個", "是否", "嗎", "呢")
    return any(marker in text for marker in markers)


def _is_temporary_goal_completion(message: str) -> bool:
    """Return whether a message explicitly retires a temporary learning goal.

    Completion evidence changes lifecycle state; it is not a durable learner
    fact. Requiring both a completion command and goal context prevents an
    ordinary statement such as completing one exercise from retiring memory.
    """

    text = _clean_text(message)
    has_completion = any(marker in text for marker in TEMPORARY_GOAL_COMPLETION_MARKERS)
    has_goal_context = any(marker in text for marker in TEMPORARY_GOAL_CONTEXT_MARKERS)
    return has_completion and has_goal_context


def classify_user_message(message: str) -> MemoryGateDecision:
    """
    Classify a user message to determine its memory category and retention properties.

    Args:
        message (str): The user message to classify.

    Returns:
        MemoryGateDecision: The decision detailing how the message should be processed in memory.
    """
    text = _clean_text(message)
    if not text:
        return MemoryGateDecision(
            category="empty",
            should_prompt=False,
            should_cold_store=False,
            ttl_seconds=0,
            proposition="",
            reason="empty_message",
        )

    normalized = text.lower().strip("。！？!?，,～~ ")
    if normalized in LOW_INFORMATION_GREETINGS:
        return MemoryGateDecision(
            category="smalltalk",
            should_prompt=False,
            should_cold_store=False,
            ttl_seconds=0,
            proposition="",
            reason="low_information_greeting",
            weight=0.0,
        )

    # Speech act is authoritative: wording such as "我偏好什麼方法？"
    # remains a question even though it contains a preference marker.
    if _is_interrogative(text):
        return MemoryGateDecision(
            category="current_focus",
            should_prompt=True,
            should_cold_store=False,
            ttl_seconds=3600,
            proposition=text,
            reason="interrogative_not_memory_evidence",
            weight=1.0,
        )

    if any(keyword in text for keyword in ROLEPLAY_KEYWORDS):
        return MemoryGateDecision(
            category="current_focus",
            should_prompt=True,
            should_cold_store=False,
            ttl_seconds=3600,
            proposition=text,
            reason="roleplay_not_memory_evidence",
            weight=1.0,
        )

    # Lifecycle commands must be classified before preference/fact patterns;
    # the completion statement retires state and must not create new memory.
    if _is_temporary_goal_completion(text):
        return MemoryGateDecision(
            category="temporary_goal_completed",
            should_prompt=True,
            should_cold_store=False,
            ttl_seconds=0,
            proposition=text,
            reason="temporary_goal_completion_request",
            weight=1.0,
        )

    explicit_fact = _extract_explicit_fact(text)
    if explicit_fact:
        return MemoryGateDecision(
            category="explicit_memory",
            should_prompt=True,
            should_cold_store=True,
            ttl_seconds=None,
            proposition=explicit_fact,
            reason="explicit_user_memory_request",
            weight=1.0,
        )

    preference = _extract_pattern_fact(text, PASSIVE_PREFERENCE_PATTERNS)
    if preference:
        return MemoryGateDecision(
            category="passive_preference",
            should_prompt=True,
            should_cold_store=True,
            ttl_seconds=90 * 86400,
            proposition=text,
            reason="declarative_low_risk_preference",
            weight=1.0,
        )

    stable_fact = _extract_pattern_fact(text, STABLE_FACT_PATTERNS)
    if stable_fact:
        return MemoryGateDecision(
            category="stable_fact_candidate",
            should_prompt=True,
            should_cold_store=True,
            ttl_seconds=None,
            proposition=text,
            reason="stable_fact_requires_supported_category",
            weight=1.0,
        )

    if any(marker in text for marker in ("這個月我想", "這週我想", "下週我想", "目前目標", "學習目標")):
        return MemoryGateDecision(
            category="temporary_goal",
            should_prompt=True,
            should_cold_store=True,
            ttl_seconds=30 * 86400,
            proposition=text,
            reason="explicit_temporary_learning_goal",
            weight=1.0,
        )

    return MemoryGateDecision(
        category="current_focus",
        should_prompt=True,
        should_cold_store=False,
        ttl_seconds=3600,
        proposition=text,
        reason="ordinary_user_message_for_current_turn",
        weight=1.0,
    )


def is_sensitive_context_query(message: str) -> bool:
    """
    Return whether cross-conversation episodic recall should be conservative due to sensitive keywords.

    Args:
        message (str): The user message to analyze.

    Returns:
        bool: True if the message contains sensitive keywords, False otherwise.
    """
    text = _clean_text(message).lower()
    return any(keyword in text for keyword in SENSITIVE_CONTEXT_KEYWORDS)


def requests_cross_conversation_recall(message: str) -> bool:
    """
    Return whether the user explicitly asks to reuse earlier context across conversations.

    Args:
        message (str): The user message to analyze.

    Returns:
        bool: True if the user asks for cross-conversation recall, False otherwise.
    """
    text = _clean_text(message).lower()
    return any(keyword in text for keyword in EXPLICIT_RECALL_KEYWORDS)


def requests_recent_working_context_recall(message: str) -> bool:
    """Return whether a turn asks for recent prompt-safe working context.

    This is intentionally narrower than long-term memory recall. It is a fast
    hot-memory bridge for phrases like "我最近讀的書", not permission to run
    cold-memory retrieval or inject arbitrary previous conversation focus.
    """

    text = _clean_text(message).lower()
    if not text:
        return False
    if requests_cross_conversation_recall(text):
        return True
    return any(re.search(pattern, text) for pattern in RECENT_WORKING_CONTEXT_PATTERNS)


def classify_action(action_type: str, context: Any) -> MemoryGateDecision:
    """
    Classify a client telemetry action to determine its memory gating decision.

    Args:
        action_type (str): The type of action performed by the client (e.g., 'scroll', 'focus').
        context (Any): Additional context associated with the action.

    Returns:
        MemoryGateDecision: The decision detailing how the action should be recorded.
    """
    normalized = _clean_text(action_type).lower()
    weight = 0.2 if normalized in {"scroll", "focus", "blur"} else 1.0
    category = "behavior_signal" if normalized in BEHAVIOR_ACTIONS else "behavior_signal"
    return MemoryGateDecision(
        category=category,
        should_prompt=False,
        should_cold_store=False,
        ttl_seconds=86400,
        proposition=normalized,
        reason="client_action_telemetry",
        weight=weight,
    )


def classify_learning_observation(text: str) -> MemoryGateDecision:
    """
    Classify a learning observation to determine its memory gating decision.

    Args:
        text (str): The text of the learning observation or user action.

    Returns:
        MemoryGateDecision: The decision detailing how the observation should be stored.
    """
    cleaned = _clean_text(text)
    if not cleaned:
        return MemoryGateDecision("empty", False, False, 0, "", "empty_observation")
    if cleaned.startswith("[User Action]"):
        return MemoryGateDecision(
            category="behavior_signal",
            should_prompt=False,
            should_cold_store=False,
            ttl_seconds=86400,
            proposition=cleaned,
            reason="legacy_action_observation",
            weight=0.5,
        )
    return MemoryGateDecision(
        category="learning_state",
        should_prompt=True,
        should_cold_store=False,
        ttl_seconds=3600,
        proposition=cleaned,
        reason="semantic_learning_observation",
        weight=1.0,
    )


def classify_reflection_insight(insight: str) -> MemoryGateDecision:
    """
    Classify a reflection insight to determine its memory gating decision.

    Args:
        insight (str): The insight generated during a reflection process.

    Returns:
        MemoryGateDecision: The decision detailing how the insight should be stored.
    """
    cleaned = _clean_text(insight)
    if not cleaned:
        return MemoryGateDecision("empty", False, False, 0, "", "empty_reflection")
    return MemoryGateDecision(
        category="session_reflection",
        should_prompt=True,
        should_cold_store=True,
        ttl_seconds=None,
        proposition=cleaned,
        reason="reflection_promotes_session_learning_context",
        weight=1.0,
    )


async def apply_action_gate(store: Any, user_id: str, action_type: str, context: Dict[str, Any]) -> MemoryGateDecision:
    """
    Apply the memory gate to a client action, appending it to the memory store if applicable.

    Args:
        store (Any): The memory store instance for persistence.
        user_id (str): The ID of the user.
        action_type (str): The type of action performed.
        context (Dict[str, Any]): Additional context data for the action.

    Returns:
        MemoryGateDecision: The memory decision generated for the action.
    """
    decision = classify_action(action_type, context)
    if store and decision.category == "behavior_signal":
        await store.append_behavior_signal(user_id, action_type, context, weight=decision.weight)
    return decision


async def apply_reflection_gate(
    store: Any,
    user_id: str,
    insight: str,
    *,
    conversation_id: str = "",
) -> MemoryGateDecision:
    """
    Apply the memory gate to a reflection insight, updating observations and working memory.

    Args:
        store (Any): The memory store instance for persistence.
        user_id (str): The ID of the user.
        insight (str): The reflection insight to process.
        conversation_id (str, optional): The ID of the current conversation. Defaults to "".

    Returns:
        MemoryGateDecision: The memory decision generated for the reflection insight.
    """
    decision = classify_reflection_insight(insight)
    if store and decision.should_prompt:
        await store.append_learning_observation(
            user_id,
            decision.proposition,
            confidence=9.0,
            decay=3.0,
            conversation_id=conversation_id,
            source="gum_reflection",
        )
        working = await store.get_working_memory(user_id)
        summary = _clean_text(working.get("session_summary", ""))
        if summary:
            summary = f"{summary} / {decision.proposition}"
        else:
            summary = decision.proposition
        summary_update = {"session_summary": summary[-1200:]}
        if conversation_id:
            summary_update["session_summary_conversation_id"] = conversation_id
        await store.update_working_memory(user_id, summary_update)
    return decision
