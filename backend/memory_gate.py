import json
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


@dataclass(frozen=True)
class MemoryRetentionDecision:
    """Server-owned retention decision; model output is advisory only."""

    action: str
    reason: str
    expires_in_seconds: Optional[int] = None


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

SENSITIVE_CONTEXT_KEYWORDS = (
    "血壓", "心率", "脈搏", "胸痛", "呼吸", "頭暈", "藥物", "用藥", "醫生", "醫師",
    "健康", "生病", "焦慮", "憂鬱", "自殺", "心理", "家庭", "父親", "母親", "財務", "債務",
)
EXPLICIT_RECALL_KEYWORDS = ("延續", "接續", "之前", "上次", "昨天", "前一個對話", "結合先前")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def evaluate_memory_retention_policy(candidate: Dict[str, Any]) -> MemoryRetentionDecision:
    """Apply conservative, domain-neutral rules after LLM candidate extraction."""
    text = _clean_text(
        " ".join(
            str(candidate.get(key, ""))
            for key in ("text", "normalized_text", "evidence_quote")
        )
    ).lower()
    category = _clean_text(str(candidate.get("category", ""))).lower()

    if not text:
        return MemoryRetentionDecision("deny", "empty_candidate")
    if any(marker in text for marker in SENSITIVE_CONTEXT_KEYWORDS):
        return MemoryRetentionDecision("deny", "sensitive_or_high_impact_context")
    if any(marker in text for marker in _NEGATIVE_MARKERS):
        return MemoryRetentionDecision("deny", "negative_capability_label")
    if any(marker in text for marker in _TEMPORAL_MARKERS):
        return MemoryRetentionDecision("allow_with_expiry", "time_bound_context", 30 * 86400)
    if category in {"preference", "goal", "background", "stable_preference", "recurring_goal"}:
        return MemoryRetentionDecision("allow", "stable_user_evidence")
    return MemoryRetentionDecision("candidate_only", "requires_more_policy_evidence")


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


def is_sensitive_context_query(message: str) -> bool:
    """Return whether cross-conversation episodic recall should be conservative."""
    text = _clean_text(message).lower()
    return any(keyword in text for keyword in SENSITIVE_CONTEXT_KEYWORDS)


def requests_cross_conversation_recall(message: str) -> bool:
    """Return whether the user explicitly asks to reuse earlier context."""
    text = _clean_text(message).lower()
    return any(keyword in text for keyword in EXPLICIT_RECALL_KEYWORDS)


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
        await store.perform_memory_operation(
            user_id,
            "user",
            "add",
            decision.proposition,
            source="explicit_user_request",
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


async def apply_reflection_gate(
    store: Any,
    user_id: str,
    insight: str,
    *,
    conversation_id: str = "",
) -> MemoryGateDecision:
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


async def extract_user_memory_candidates(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract candidate memories from user-originated text with evidence only."""
    user_messages = [
        str(message.get("content", "")).strip()
        for message in messages
        if message.get("role") == "user" and str(message.get("content", "")).strip()
    ]
    if not client or not user_messages:
        return []

    prompt = f"""Analyze only the user messages below. Extract durable memory candidates that may be useful across future conversations.

User messages (numbered):
{json.dumps(user_messages, ensure_ascii=False)}

This policy is domain-neutral. Do not rely on topic keywords. A candidate must describe a stable preference, recurring goal, background fact, or enduring context explicitly supported by a user message. Do not infer a fact from an assistant answer, a teaching outcome, a guessed personality trait, or a one-off question. Mark information as sensitive when retaining it long term should require the user's approval.

Return JSON with a `candidates` list. Every item must contain: `text`, `normalized_text`, `category`, `confidence` (0 to 1), `requires_confirmation`, `evidence_index`, and `evidence_quote`. The evidence quote must be copied from the referenced user message. Return an empty list when there is no durable candidate."""
    try:
        from pydantic import BaseModel, Field

        class Candidate(BaseModel):
            text: str
            normalized_text: str
            category: str
            confidence: float = Field(ge=0.0, le=1.0)
            requires_confirmation: bool
            evidence_index: int = Field(ge=0)
            evidence_quote: str

        class CandidateResponse(BaseModel):
            candidates: list[Candidate]

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "memory_candidate_response",
                    "schema": CandidateResponse.model_json_schema(),
                },
            },
            temperature=0.0,
        )
        payload = json.loads(response.choices[0].message.content)
        result = []
        for candidate in payload.get("candidates", []):
            index = candidate.get("evidence_index")
            quote = _clean_text(candidate.get("evidence_quote", ""))
            if not isinstance(index, int) or index >= len(user_messages) or not quote:
                continue
            evidence_text = user_messages[index]
            if quote not in evidence_text:
                continue
            result.append({
                **candidate,
                "evidence": {"message": evidence_text, "quote": quote, "message_index": index},
            })
        return result
    except Exception as exc:
        print(f"[MemoryCandidate] Extraction failed: {type(exc).__name__}")
        return []
