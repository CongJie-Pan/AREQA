"""Own model-assisted query decomposition and EDF response-policy selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import logging
import re
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class TaskIntent(str, Enum):
    """Supported user-task intents for EDF response shaping."""

    EXPLAIN_TEXT = "EXPLAIN_TEXT"
    ANSWER_EXAM = "ANSWER_EXAM"
    DISCUSS_IDEA = "DISCUSS_IDEA"
    WRITE_NOTE = "WRITE_NOTE"
    GENERAL_QA = "GENERAL_QA"


class AnswerDepth(str, Enum):
    """How much conceptual depth the feedback stage should open."""

    DIRECT = "DIRECT"
    SCAFFOLDED = "SCAFFOLDED"
    REFLECTIVE = "REFLECTIVE"
    DEEP_DIVE = "DEEP_DIVE"


class ResponseTone(str, Enum):
    """The voice used by the feedback stage for the current turn."""

    PLAIN = "PLAIN"
    TUTORING = "TUTORING"
    ANALYTICAL = "ANALYTICAL"
    LITERARY = "LITERARY"


class ResponseStructure(str, Enum):
    """The visible answer format selected by the EDF decision stage."""

    SHORT = "SHORT"
    STEP_BY_STEP = "STEP_BY_STEP"
    NOTE_DRAFT = "NOTE_DRAFT"
    ARGUMENT = "ARGUMENT"


class FollowupMode(str, Enum):
    """Whether the final answer should include an invitation to continue."""

    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


ALLOWED_LEGACY_POLICIES = {
    "PROBE_UNDERSTANDING",
    "SUGGEST_ACTION",
    "PUSH_LIMIT",
    "NORMAL",
}


@dataclass(frozen=True, slots=True)
class ResponsePolicy:
    """Structured EDF decision that constrains final answer generation.

    Args:
        task_intent: The user's immediate task type.
        answer_depth: The maximum depth the feedback stage should use.
        tone: The response voice for this turn.
        structure: The expected answer shape.
        followup_mode: Whether a follow-up question should be omitted, optional,
            or required.
        legacy_policy: Compatibility policy used by older orchestration code for
            token budgeting and tests.

    Compatibility:
        This object is an internal backend contract. It does not change the
        public chat API or SSE payloads. Logs must contain only enum values and
        correlation IDs, never raw user text, prompts, or model output.
    """

    task_intent: TaskIntent
    answer_depth: AnswerDepth
    tone: ResponseTone
    structure: ResponseStructure
    followup_mode: FollowupMode
    legacy_policy: str = "NORMAL"

    def safe_log_metadata(self) -> dict[str, str]:
        """Return privacy-safe enum metadata for structured logs."""

        return {
            "task_intent": self.task_intent.value,
            "answer_depth": self.answer_depth.value,
            "tone": self.tone.value,
            "structure": self.structure.value,
            "followup_mode": self.followup_mode.value,
            "legacy_policy": self.legacy_policy,
        }


def default_response_policy() -> ResponsePolicy:
    """Return a conservative EDF fallback policy for classifier failures.

    The fallback intentionally favors plain scaffolding over reflective depth so
    malformed model output cannot reopen AREQA's always-on essay style.
    """

    return ResponsePolicy(
        task_intent=TaskIntent.GENERAL_QA,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        legacy_policy="NORMAL",
    )


def _coerce_enum(enum_type: type[Enum], value: Any, fallback: Enum) -> Enum:
    """Coerce untrusted model output into an allowlisted enum value."""

    try:
        return enum_type(str(value).strip())
    except Exception:
        return fallback


def response_policy_from_dict(payload: Any) -> ResponsePolicy:
    """Build a sanitized ``ResponsePolicy`` from untrusted JSON.

    Args:
        payload: Model-produced JSON decoded into a Python object.

    Returns:
        A fully allowlisted ``ResponsePolicy``. Unknown values are replaced with
        conservative defaults rather than failing open into deep analysis.
    """

    fallback = default_response_policy()
    if not isinstance(payload, dict):
        return fallback
    legacy_policy = str(payload.get("legacy_policy") or fallback.legacy_policy).strip()
    if legacy_policy not in ALLOWED_LEGACY_POLICIES:
        legacy_policy = fallback.legacy_policy
    return ResponsePolicy(
        task_intent=_coerce_enum(TaskIntent, payload.get("task_intent"), fallback.task_intent),
        answer_depth=_coerce_enum(AnswerDepth, payload.get("answer_depth"), fallback.answer_depth),
        tone=_coerce_enum(ResponseTone, payload.get("tone"), fallback.tone),
        structure=_coerce_enum(
            ResponseStructure,
            payload.get("structure"),
            fallback.structure,
        ),
        followup_mode=_coerce_enum(
            FollowupMode,
            payload.get("followup_mode"),
            fallback.followup_mode,
        ),
        legacy_policy=legacy_policy,
    )


def response_policy_from_legacy(policy: Any) -> ResponsePolicy:
    """Bridge older string-only policies into a conservative response policy.

    Args:
        policy: A legacy dialogue policy string, often supplied by older tests
            through mocks.

    Returns:
        A structured policy that preserves old token-budget intent without
        enabling deep style unless the legacy policy was explicitly
        ``PUSH_LIMIT``.
    """

    legacy_policy = str(policy or "NORMAL").strip()
    if legacy_policy not in ALLOWED_LEGACY_POLICIES:
        legacy_policy = "NORMAL"
    if legacy_policy == "PUSH_LIMIT":
        return ResponsePolicy(
            task_intent=TaskIntent.DISCUSS_IDEA,
            answer_depth=AnswerDepth.REFLECTIVE,
            tone=ResponseTone.ANALYTICAL,
            structure=ResponseStructure.ARGUMENT,
            followup_mode=FollowupMode.OPTIONAL,
            legacy_policy=legacy_policy,
        )
    if legacy_policy == "SUGGEST_ACTION":
        return ResponsePolicy(
            task_intent=TaskIntent.GENERAL_QA,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            legacy_policy=legacy_policy,
        )
    if legacy_policy == "PROBE_UNDERSTANDING":
        return ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.REQUIRED,
            legacy_policy=legacy_policy,
        )
    return default_response_policy()


async def parse_and_decompose_query_impl(
    query: str,
    client: Any,
) -> List[Dict[str, str]]:
    """Return validated hybrid-retrieval subqueries with a safe fallback."""

    prompt = f"""你是一個檢索分析師。將問題拆成適合 BM25 與 FAISS 的乾淨檢索詞。
移除題幹指令語；多實體問題拆成獨立子查詢。type 只能是 exact_entity 或 abstract_concept。
只輸出 JSON array，每項包含 query 與 type。
問題：{query}"""
    queries: List[Dict[str, str]] = []
    try:
        from config import settings

        response = await client.chat.completions.create(
            model=settings.model_policy_classifier,
            messages=[
                {"role": "system", "content": "只輸出符合要求的 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        if response.choices and response.choices[0].message.content:
            content = response.choices[0].message.content.strip()
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
            parsed = json.loads(content)
            if isinstance(parsed, list):
                for item in parsed:
                    if not isinstance(item, dict) or not str(item.get("query", "")).strip():
                        continue
                    query_type = item.get("type")
                    if query_type not in {"exact_entity", "abstract_concept"}:
                        query_type = "abstract_concept"
                    queries.append({"query": str(item["query"]), "type": query_type})
    except Exception as exc:
        logger.warning("orchestration.query_decomposition_failed reason=%s", type(exc).__name__)
    return queries or [{"query": query, "type": "abstract_concept"}]


async def classify_dialogue_policy_impl(
    client: Any,
    model: str,
    user_msg: str,
    chat_history: list,
) -> str:
    """Return one allowlisted legacy pedagogical policy.

    Args:
        client: Chat-completions compatible model client.
        model: Policy classifier model identifier.
        user_msg: Current user message. It is sent to the classifier but never
            logged by this function.
        chat_history: Recent conversation history for compatibility with older
            callers.

    Returns:
        A legacy policy string used by existing orchestration token budgeting.
    """

    policy = await classify_response_policy_impl(client, model, user_msg, chat_history)
    return policy.legacy_policy


async def classify_response_policy_impl(
    client: Any,
    model: str,
    user_msg: str,
    chat_history: list,
) -> ResponsePolicy:
    """Select a structured EDF response policy for the current user turn.

    Args:
        client: Chat-completions compatible model client.
        model: Policy classifier model identifier.
        user_msg: Current user message. It is included only in the model prompt
            and must not be written to logs.
        chat_history: Recent conversation messages. Only the last few role names
            and contents are sent to the classifier to preserve conversational
            continuity.

    Returns:
        A sanitized ``ResponsePolicy``. Unexpected provider failures, malformed
        JSON, or unsupported enum values fall back to plain scaffolded tutoring.

    Side effects:
        Emits privacy-safe structured logs using stable event names
        ``orchestration.response_policy_selected`` and
        ``orchestration.response_policy_failed``. Log metadata contains only
        enum values and error type names, never raw user text, prompts, model
        output, credentials, or sensitive labels.
    """

    history_lines = []
    for item in (chat_history or [])[-4:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "unknown")
        content = str(item.get("content") or "")
        history_lines.append(f"{role}: {content[:500]}")
    history_text = "\n".join(history_lines) if history_lines else "(no recent history)"

    prompt = f"""You are AREQA's EDF Decision module. Select the response policy for the next Feedback message.

Return strict JSON only with these fields:
{{
  "task_intent": "EXPLAIN_TEXT" | "ANSWER_EXAM" | "DISCUSS_IDEA" | "WRITE_NOTE" | "GENERAL_QA",
  "answer_depth": "DIRECT" | "SCAFFOLDED" | "REFLECTIVE" | "DEEP_DIVE",
  "tone": "PLAIN" | "TUTORING" | "ANALYTICAL" | "LITERARY",
  "structure": "SHORT" | "STEP_BY_STEP" | "NOTE_DRAFT" | "ARGUMENT",
  "followup_mode": "NONE" | "OPTIONAL" | "REQUIRED",
  "legacy_policy": "PROBE_UNDERSTANDING" | "SUGGEST_ACTION" | "PUSH_LIMIT" | "NORMAL"
}}

Decision rules:
- If the user asks "I do not understand", "what does this mean", or asks for a plain explanation, choose EXPLAIN_TEXT, SCAFFOLDED, PLAIN, STEP_BY_STEP.
- If the user asks for a forced-choice answer, exam answer, or "only choose one", choose ANSWER_EXAM, DIRECT, PLAIN, SHORT, followup NONE.
- If the user asks to complete, revise, or polish notes, choose WRITE_NOTE, SCAFFOLDED, TUTORING, NOTE_DRAFT.
- If the user asks for the core, essence, viewpoint, reflection, historical meaning, literary feeling, or "what do you think", choose DISCUSS_IDEA with REFLECTIVE or DEEP_DIVE.
- Prefer SCAFFOLDED over DEEP_DIVE unless the user explicitly requests deeper reflection.
- The legacy policy is for compatibility: PROBE_UNDERSTANDING for eliciting reasoning, SUGGEST_ACTION for concrete next steps, PUSH_LIMIT for reflective/deep extension, otherwise NORMAL.

Recent history:
{history_text}

Current user message:
{user_msg}"""
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return only valid JSON. Do not explain."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        if content in ALLOWED_LEGACY_POLICIES:
            policy = response_policy_from_legacy(content)
            logger.info(
                "orchestration.response_policy_selected metadata=%s",
                json.dumps(policy.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
            )
            return policy
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        policy = response_policy_from_dict(parsed)
        logger.info(
            "orchestration.response_policy_selected metadata=%s",
            json.dumps(policy.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
        )
        return policy
    except Exception as exc:
        fallback = default_response_policy()
        logger.warning(
            "orchestration.response_policy_failed reason=%s fallback=%s",
            type(exc).__name__,
            json.dumps(fallback.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
        )
        return fallback
