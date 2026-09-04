"""Own model-assisted query decomposition and EDF response-policy selection."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List



logger = logging.getLogger(__name__)


from services.query_policy.models import (
    ALLOWED_LEGACY_POLICIES,
    AnswerDepth,
    AttachmentReason,
    AttachmentTask,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualReason,
    VisualSupport,
    default_response_policy,
    response_policy_from_dict,
    response_policy_from_legacy,
)
from services.query_policy.pdf_guardrails import (
    _apply_attachment_guardrails,
    _apply_pdf_auto_explain_guardrail,
    _apply_pdf_semantic_auto_explain_fallback,
    _is_broad_pdf_auto_explain_request,
    apply_pdf_auto_explain_guardrail,
    count_pdf_attachments,
    paper_auto_explain_instruction,
)


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
    *,
    has_pdf_attachment: bool = False,
    pdf_attachment_count: int = 0,
) -> str:
    """Return one allowlisted legacy pedagogical policy.

    Args:
        client: Chat-completions compatible model client.
        model: Policy classifier model identifier.
        user_msg: Current user message. It is sent to the classifier but never
            logged by this function.
        chat_history: Recent conversation history for compatibility with older
            callers.
        has_pdf_attachment: Whether the current turn contains at least one PDF
            file attachment.
        pdf_attachment_count: Number of PDF attachments in the current turn.

    Returns:
        A legacy policy string used by existing orchestration token budgeting.
    """

    policy = await classify_response_policy_impl(
        client,
        model,
        user_msg,
        chat_history,
        has_pdf_attachment=has_pdf_attachment,
        pdf_attachment_count=pdf_attachment_count,
    )
    return policy.legacy_policy


async def classify_response_policy_impl(
    client: Any,
    model: str,
    user_msg: str,
    chat_history: list,
    *,
    has_pdf_attachment: bool = False,
    pdf_attachment_count: int = 0,
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
        has_pdf_attachment: Whether request attachment metadata confirms a PDF
            exists in the current turn.
        pdf_attachment_count: Bounded PDF attachment count for policy context.

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

    bounded_pdf_count = max(0, min(int(pdf_attachment_count or 0), 10))
    attachment_context = {
        "has_pdf_attachment": bool(has_pdf_attachment),
        "pdf_attachment_count": bounded_pdf_count,
    }

    prompt = f"""You are AREQA's EDF Decision module. Select the response policy for the next Feedback message.

Return strict JSON only with these fields:
{{
  "task_intent": "EXPLAIN_TEXT" | "ANSWER_EXAM" | "DISCUSS_IDEA" | "WRITE_NOTE" | "GENERAL_QA",
  "answer_depth": "DIRECT" | "SCAFFOLDED" | "REFLECTIVE" | "DEEP_DIVE",
  "tone": "PLAIN" | "TUTORING" | "ANALYTICAL" | "LITERARY",
  "structure": "SHORT" | "STEP_BY_STEP" | "NOTE_DRAFT" | "ARGUMENT",
  "followup_mode": "NONE" | "OPTIONAL" | "REQUIRED",
  "visual_support": "NONE" | "OPTIONAL" | "REQUIRED",
  "visual_reason": "EXPLICIT_VISUAL_REQUEST" | "KNOWLEDGE_EXPLANATION" | "ANSWER_SEEKING" | "ATTACHMENT_FIGURE_EXPLANATION" | "NOT_NEEDED",
  "attachment_task": "NONE" | "PAPER_AUTO_EXPLAIN" | "PAPER_TARGETED_QA",
  "attachment_reason": "NO_ATTACHMENT" | "GENERIC_PAPER_EXPLANATION" | "TARGETED_ATTACHMENT_TASK" | "NOT_PAPER_TASK",
  "legacy_policy": "PROBE_UNDERSTANDING" | "SUGGEST_ACTION" | "PUSH_LIMIT" | "NORMAL"
}}

Decision rules:
- If the user asks "I do not understand", "what does this mean", or asks for a plain explanation, choose EXPLAIN_TEXT, SCAFFOLDED, PLAIN, STEP_BY_STEP.
- If the user asks for a forced-choice answer, exam answer, or "only choose one", choose ANSWER_EXAM, DIRECT, PLAIN, SHORT, followup NONE.
- If the user asks to complete, revise, or polish notes, choose WRITE_NOTE, SCAFFOLDED, TUTORING, NOTE_DRAFT.
- If the user asks for the core, essence, viewpoint, reflection, historical meaning, literary feeling, or "what do you think", choose DISCUSS_IDEA with REFLECTIVE or DEEP_DIVE.
- Set visual_support REQUIRED only when the user explicitly asks for a diagram, image, chart, graph, figure, map, or visual explanation.
- Set visual_support OPTIONAL when the user is asking for knowledge explanation, problem solving, answer seeking, paper/attachment figure interpretation, process/mechanism explanation, chart interpretation, or graph-heavy concepts where an image would materially improve the answer.
- Set visual_support NONE for casual chat, note writing/polishing, reflective discussion, administrative requests, short factual answers, and any case where an image would be decorative.
- Set visual_reason to the closest reason for the visual_support decision. Use NOT_NEEDED when visual_support is NONE.
- Attachment task policy:
  - If attachment_context.has_pdf_attachment is false, set attachment_task NONE and attachment_reason NO_ATTACHMENT.
  - If a PDF is attached and the user gives a broad paper/PDF reading request such as "explain this paper", "please help me explain this paper", "summarize this PDF", "read this paper", "what is this paper about", "幫我解釋這篇論文", "讀這篇論文", or the message is empty/generic, set attachment_task PAPER_AUTO_EXPLAIN and attachment_reason GENERIC_PAPER_EXPLANATION.
  - If a PDF is attached but the user asks for a specific operation or focused section, such as translation, page-specific help, citation extraction, rewriting, proofreading, "only methods", "only limitations", "compare with X", or a direct question about one concept, set attachment_task PAPER_TARGETED_QA and attachment_reason TARGETED_ATTACHMENT_TASK.
  - If a PDF is attached but the user is not asking about the attachment, set attachment_task NONE and attachment_reason NOT_PAPER_TASK.
- Prefer SCAFFOLDED over DEEP_DIVE unless the user explicitly requests deeper reflection.
- The legacy policy is for compatibility: PROBE_UNDERSTANDING for eliciting reasoning, SUGGEST_ACTION for concrete next steps, PUSH_LIMIT for reflective/deep extension, otherwise NORMAL.

Attachment context:
{json.dumps(attachment_context, ensure_ascii=False, sort_keys=True)}

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
            max_tokens=280,
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        if content in ALLOWED_LEGACY_POLICIES:
            policy = _apply_attachment_guardrails(
                response_policy_from_legacy(content),
                has_pdf_attachment=has_pdf_attachment,
            )
            policy = _apply_pdf_auto_explain_guardrail(
                policy,
                user_msg=user_msg,
                has_pdf_attachment=has_pdf_attachment,
            )
            policy = await _apply_pdf_semantic_auto_explain_fallback(
                policy,
                client=client,
                model=model,
                user_msg=user_msg,
                has_pdf_attachment=has_pdf_attachment,
            )
            logger.info(
                "orchestration.response_policy_selected metadata=%s",
                json.dumps(policy.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
            )
            return policy
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        policy = _apply_attachment_guardrails(
            response_policy_from_dict(parsed),
            has_pdf_attachment=has_pdf_attachment,
        )
        policy = _apply_pdf_auto_explain_guardrail(
            policy,
            user_msg=user_msg,
            has_pdf_attachment=has_pdf_attachment,
        )
        policy = await _apply_pdf_semantic_auto_explain_fallback(
            policy,
            client=client,
            model=model,
            user_msg=user_msg,
            has_pdf_attachment=has_pdf_attachment,
        )
        logger.info(
            "orchestration.response_policy_selected metadata=%s",
            json.dumps(policy.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
        )
        return policy
    except Exception as exc:
        fallback = _apply_pdf_auto_explain_guardrail(
            default_response_policy(),
            user_msg=user_msg,
            has_pdf_attachment=has_pdf_attachment,
        )
        fallback = await _apply_pdf_semantic_auto_explain_fallback(
            fallback,
            client=client,
            model=model,
            user_msg=user_msg,
            has_pdf_attachment=has_pdf_attachment,
        )
        logger.warning(
            "orchestration.response_policy_failed reason=%s fallback=%s",
            type(exc).__name__,
            json.dumps(fallback.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
        )
        return fallback
