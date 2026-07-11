import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MemoryGateDecision:
    category: str
    should_prompt: bool
    should_cold_store: bool
    ttl_seconds: Optional[int]
    proposition: str
    reason: str
    weight: float = 1.0


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
    r"(?:我的名字|我叫)(?P<fact>.+)",
    r"(?:我是|我目前是)(?P<fact>.+)",
    r"(?:我喜歡|我不喜歡|我討厭|我偏好)(?P<fact>.+)",
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


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _extract_explicit_fact(message: str) -> str:
    text = _clean_text(message)
    if any(keyword in text for keyword in ROLEPLAY_KEYWORDS):
        return ""

    for pattern in EXPLICIT_MEMORY_PATTERNS:
        match = re.search(pattern, text)
        if match:
            fact = _clean_text(match.group("fact"))
            return fact.strip("：:，,。 ")
    return ""


def classify_user_message(message: str) -> MemoryGateDecision:
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

    return MemoryGateDecision(
        category="current_focus",
        should_prompt=True,
        should_cold_store=False,
        ttl_seconds=3600,
        proposition=text,
        reason="ordinary_user_message_for_current_turn",
        weight=1.0,
    )


def classify_action(action_type: str, context: Any) -> MemoryGateDecision:
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


async def apply_user_message_gate(store: Any, user_id: str, message: str, conversation_id: str = "") -> MemoryGateDecision:
    decision = classify_user_message(message)
    if not store or not decision.proposition:
        return decision

    if decision.category == "explicit_memory":
        await store.perform_memory_operation(user_id, "user", "add", decision.proposition)
        if hasattr(store, "append_cold_candidate"):
            await store.append_cold_candidate(
                user_id,
                decision.proposition,
                category=decision.category,
                source="user_message",
                reason=decision.reason,
                confidence=9.0,
                decay=2.0,
            )
    elif decision.should_prompt:
        updates = {"current_focus": decision.proposition}
        if conversation_id:
            updates["current_focus_conversation_id"] = conversation_id
        await store.update_working_memory(user_id, updates)
    return decision


async def apply_action_gate(store: Any, user_id: str, action_type: str, context: Dict[str, Any]) -> MemoryGateDecision:
    decision = classify_action(action_type, context)
    if store and decision.category == "behavior_signal":
        await store.append_behavior_signal(user_id, action_type, context, weight=decision.weight)
    return decision


async def apply_reflection_gate(store: Any, user_id: str, insight: str) -> MemoryGateDecision:
    decision = classify_reflection_insight(insight)
    if store and decision.should_prompt:
        await store.append_learning_observation(user_id, decision.proposition, confidence=9.0, decay=3.0)
        if decision.should_cold_store and hasattr(store, "append_cold_candidate"):
            await store.append_cold_candidate(
                user_id,
                decision.proposition,
                category=decision.category,
                source="reflection",
                reason=decision.reason,
                confidence=9.0,
                decay=3.0,
            )
        working = await store.get_working_memory(user_id)
        summary = _clean_text(working.get("session_summary", ""))
        if summary:
            summary = f"{summary} / {decision.proposition}"
        else:
            summary = decision.proposition
        await store.update_working_memory(user_id, {"session_summary": summary[-1200:]})
    return decision
