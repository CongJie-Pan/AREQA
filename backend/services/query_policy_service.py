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


class VisualSupport(str, Enum):
    """Whether the current turn should spend visual enrichment cost."""

    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class VisualReason(str, Enum):
    """Allowlisted reason for the visual enrichment decision."""

    EXPLICIT_VISUAL_REQUEST = "EXPLICIT_VISUAL_REQUEST"
    KNOWLEDGE_EXPLANATION = "KNOWLEDGE_EXPLANATION"
    ANSWER_SEEKING = "ANSWER_SEEKING"
    ATTACHMENT_FIGURE_EXPLANATION = "ATTACHMENT_FIGURE_EXPLANATION"
    NOT_NEEDED = "NOT_NEEDED"


class AttachmentTask(str, Enum):
    """Optional attachment-scoped task selected by the policy classifier."""

    NONE = "NONE"
    PAPER_AUTO_EXPLAIN = "PAPER_AUTO_EXPLAIN"
    PAPER_TARGETED_QA = "PAPER_TARGETED_QA"


class AttachmentReason(str, Enum):
    """Allowlisted reason for attachment task decisions."""

    NO_ATTACHMENT = "NO_ATTACHMENT"
    GENERIC_PAPER_EXPLANATION = "GENERIC_PAPER_EXPLANATION"
    TARGETED_ATTACHMENT_TASK = "TARGETED_ATTACHMENT_TASK"
    NOT_PAPER_TASK = "NOT_PAPER_TASK"


ALLOWED_LEGACY_POLICIES = {
    "PROBE_UNDERSTANDING",
    "SUGGEST_ACTION",
    "PUSH_LIMIT",
    "NORMAL",
}

_PDF_BROAD_AUTO_EXPLAIN_PATTERNS = (
    re.compile(
        r"\b(?:please\s+)?(?:help\s+me\s+)?explain\s+(?:this|the)\s+"
        r"(?:paper|pdf|document)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:please\s+)?(?:help\s+me\s+)?(?:summari[sz]e|read)\s+"
        r"(?:this|the)\s+(?:paper|pdf|document)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+is\s+(?:this|the)\s+(?:paper|pdf|document)\s+about\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:幫我|請)?(?:解釋|說明|導讀|摘要|總結|閱讀|讀)(?:一下)?"
        r"(?:這|這篇|這份|該)?(?:論文|PDF|文件|文獻)"
    ),
    re.compile(
        r"(?:這|這篇|這份|該)?(?:論文|PDF|文件|文獻)(?:在)?"
        r"(?:講|說|討論|研究)(?:什麼|甚麼)"
    ),
)

_PDF_TARGETED_TASK_PATTERN = re.compile(
    r"\b(?:method|methods|methodology|limitation|limitations|future\s+work|"
    r"translate|translation|proofread|rewrite|citation|citations|reference|"
    r"references|compare|comparison|page|section|formula|equation|only)\b|"
    r"(?:方法|局限|限制|未來|翻譯|改寫|潤稿|校對|引用|參考文獻|比較|第\s*\d+\s*頁|"
    r"第\s*\d+\s*章|公式|方程式|只看|只要)",
    re.IGNORECASE,
)


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
        visual_support: Whether this turn should spend image retrieval or PDF
            rendering cost.
        visual_reason: Sanitized reason for the visual support decision.
        attachment_task: Optional PDF-attachment task overlay selected by the
            same model policy call.
        attachment_reason: Sanitized reason for the attachment task decision.
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
    visual_support: VisualSupport = VisualSupport.NONE
    visual_reason: VisualReason = VisualReason.NOT_NEEDED
    attachment_task: AttachmentTask = AttachmentTask.NONE
    attachment_reason: AttachmentReason = AttachmentReason.NO_ATTACHMENT
    legacy_policy: str = "NORMAL"

    def safe_log_metadata(self) -> dict[str, str]:
        """Return privacy-safe enum metadata for structured logs."""

        return {
            "task_intent": self.task_intent.value,
            "answer_depth": self.answer_depth.value,
            "tone": self.tone.value,
            "structure": self.structure.value,
            "followup_mode": self.followup_mode.value,
            "visual_support": self.visual_support.value,
            "visual_reason": self.visual_reason.value,
            "attachment_task": self.attachment_task.value,
            "attachment_reason": self.attachment_reason.value,
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
        visual_support=VisualSupport.NONE,
        visual_reason=VisualReason.NOT_NEEDED,
        attachment_task=AttachmentTask.NONE,
        attachment_reason=AttachmentReason.NO_ATTACHMENT,
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
        visual_support=_coerce_enum(
            VisualSupport,
            payload.get("visual_support"),
            fallback.visual_support,
        ),
        visual_reason=_coerce_enum(
            VisualReason,
            payload.get("visual_reason"),
            fallback.visual_reason,
        ),
        attachment_task=_coerce_enum(
            AttachmentTask,
            payload.get("attachment_task"),
            fallback.attachment_task,
        ),
        attachment_reason=_coerce_enum(
            AttachmentReason,
            payload.get("attachment_reason"),
            fallback.attachment_reason,
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
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            attachment_task=AttachmentTask.NONE,
            attachment_reason=AttachmentReason.NO_ATTACHMENT,
            legacy_policy=legacy_policy,
        )
    if legacy_policy == "SUGGEST_ACTION":
        return ResponsePolicy(
            task_intent=TaskIntent.GENERAL_QA,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            attachment_task=AttachmentTask.NONE,
            attachment_reason=AttachmentReason.NO_ATTACHMENT,
            legacy_policy=legacy_policy,
        )
    if legacy_policy == "PROBE_UNDERSTANDING":
        return ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.REQUIRED,
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            attachment_task=AttachmentTask.NONE,
            attachment_reason=AttachmentReason.NO_ATTACHMENT,
            legacy_policy=legacy_policy,
        )
    return default_response_policy()


def count_pdf_attachments(attachments: list[dict[str, Any]] | None) -> int:
    """Count OpenRouter-style PDF file parts without inspecting PDF content.

    Args:
        attachments: Request-scoped attachment parts already validated by the
            upload boundary.

    Returns:
        Number of file parts that look like PDFs by filename or data URI MIME
        type.

    Side Effects:
        None. This helper performs structural detection only; semantic
        attachment-task classification remains owned by the LLM policy call.
    """

    count = 0
    for attachment in attachments or []:
        if not isinstance(attachment, dict) or attachment.get("type") != "file":
            continue
        file_part = attachment.get("file")
        if not isinstance(file_part, dict):
            continue
        filename = str(file_part.get("filename") or "").lower()
        file_data = str(file_part.get("file_data") or "").lower()
        if filename.endswith(".pdf") or file_data.startswith("data:application/pdf;"):
            count += 1
    return count


def paper_auto_explain_instruction() -> str:
    """Return the prompt overlay for generic PDF paper explanation.

    Returns:
        Traditional Chinese task structure. The existing language policy can
        still ask the answer model to respond in the user's preferred language.

    Side Effects:
        None. The caller owns structured logging before this prompt is applied.
    """

    return (
        "【PDF 論文自動解說任務】本回合使用者上傳 PDF，且 policy classifier 判定使用者"
        "是在要求一般性的論文導讀，沒有指定更細的任務。請把它視為一篇需要導讀的論文或技術文件，"
        "根據實際可讀取的 PDF 內容，自動用以下結構回答："
        "\n1. 研究動機與目標：說明作者想解決什麼問題、為什麼重要。"
        "\n2. 研究方法：說明核心方法、模型、資料、流程或理論設計。"
        "\n3. 實驗過程與設定：說明資料集、比較基準、實驗設計、評估指標或分析流程。"
        "\n4. 實驗結果：整理主要發現、圖表或數據代表的意思。"
        "\n5. 研究結論：說明作者最後主張什麼、貢獻是什麼。"
        "\n6. 局限與可延伸方向：若 PDF 有提到 limitation/future work，請整理；"
        "若沒有足夠資訊，明確說「PDF 中沒有足夠資訊」。"
        "\n不得根據檔名、metadata 或常識補齊 PDF 沒有支持的內容；資訊不足時要說明不確定，而不是猜測。"
    )


def _apply_attachment_guardrails(
    policy: ResponsePolicy,
    *,
    has_pdf_attachment: bool,
) -> ResponsePolicy:
    """Keep attachment-task output within scope and internally consistent."""

    if has_pdf_attachment:
        if (
            policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
            and policy.visual_support is VisualSupport.NONE
        ):
            return ResponsePolicy(
                task_intent=policy.task_intent,
                answer_depth=policy.answer_depth,
                tone=policy.tone,
                structure=policy.structure,
                followup_mode=policy.followup_mode,
                visual_support=VisualSupport.OPTIONAL,
                visual_reason=VisualReason.ATTACHMENT_FIGURE_EXPLANATION,
                attachment_task=policy.attachment_task,
                attachment_reason=policy.attachment_reason,
                legacy_policy=policy.legacy_policy,
            )
        return policy
    if (
        policy.attachment_task is AttachmentTask.NONE
        and policy.attachment_reason is AttachmentReason.NO_ATTACHMENT
    ):
        return policy
    return ResponsePolicy(
        task_intent=policy.task_intent,
        answer_depth=policy.answer_depth,
        tone=policy.tone,
        structure=policy.structure,
        followup_mode=policy.followup_mode,
        visual_support=policy.visual_support,
        visual_reason=policy.visual_reason,
        attachment_task=AttachmentTask.NONE,
        attachment_reason=AttachmentReason.NO_ATTACHMENT,
        legacy_policy=policy.legacy_policy,
    )


def _is_broad_pdf_auto_explain_request(user_msg: str) -> bool:
    """Return whether a PDF turn is an unambiguous whole-paper overview request.

    Args:
        user_msg: Current user message. The caller must not log this value.

    Returns:
        ``True`` only for narrow broad-reading prompts such as "explain this
        paper" or "summarize this PDF". Focused operations remain owned by the
        model classifier so section-specific PDF work is not collapsed into the
        generic paper overview template.

    Side Effects:
        None.
    """

    normalized = re.sub(r"\s+", " ", str(user_msg or "")).strip()
    if not normalized:
        return True
    if _PDF_TARGETED_TASK_PATTERN.search(normalized):
        return False
    return any(pattern.search(normalized) for pattern in _PDF_BROAD_AUTO_EXPLAIN_PATTERNS)


def _apply_pdf_auto_explain_guardrail(
    policy: ResponsePolicy,
    *,
    user_msg: str,
    has_pdf_attachment: bool,
) -> ResponsePolicy:
    """Stabilize deterministic PDF overview routing after model classification.

    Args:
        policy: Sanitized classifier output after attachment consistency checks.
        user_msg: Current user message. It is inspected locally but never
            logged by this helper.
        has_pdf_attachment: Whether request metadata confirms a PDF attachment.

    Returns:
        The original policy for non-PDF or focused requests. For unambiguous
        whole-paper overview requests with a PDF attachment, returns a policy
        with ``PAPER_AUTO_EXPLAIN`` and optional attachment visual support.

    Side Effects:
        Emits ``orchestration.response_policy_pdf_guardrail_applied`` only when
        this deterministic guardrail changes the classifier result. The log
        contains enum metadata and a reason code, never raw user text, prompts,
        model output, credentials, or attachment content.
    """

    if (
        not has_pdf_attachment
        or policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
        or not _is_broad_pdf_auto_explain_request(user_msg)
    ):
        return policy

    guarded = ResponsePolicy(
        task_intent=policy.task_intent,
        answer_depth=policy.answer_depth,
        tone=policy.tone,
        structure=policy.structure,
        followup_mode=policy.followup_mode,
        visual_support=(
            policy.visual_support
            if policy.visual_support is not VisualSupport.NONE
            else VisualSupport.OPTIONAL
        ),
        visual_reason=(
            policy.visual_reason
            if policy.visual_support is not VisualSupport.NONE
            else VisualReason.ATTACHMENT_FIGURE_EXPLANATION
        ),
        attachment_task=AttachmentTask.PAPER_AUTO_EXPLAIN,
        attachment_reason=AttachmentReason.GENERIC_PAPER_EXPLANATION,
        legacy_policy=policy.legacy_policy,
    )
    logger.info(
        "orchestration.response_policy_pdf_guardrail_applied reason=broad_pdf_auto_explain metadata=%s",
        json.dumps(guarded.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
    )
    return guarded


def apply_pdf_auto_explain_guardrail(
    policy: ResponsePolicy,
    *,
    user_msg: str,
    has_pdf_attachment: bool,
) -> ResponsePolicy:
    """Apply the final deterministic PDF overview invariant.

    Args:
        policy: Policy selected by a classifier, legacy bridge, skipped
            classifier path, or timeout fallback.
        user_msg: Current user message. It is inspected locally but must never
            be logged by callers.
        has_pdf_attachment: Whether request metadata confirms a PDF attachment.

    Returns:
        A policy normalized for unambiguous whole-paper PDF overview requests.

    Side Effects:
        Delegates privacy-safe structured logging to the internal guardrail only
        when a policy is changed.
    """

    return _apply_pdf_auto_explain_guardrail(
        policy,
        user_msg=user_msg,
        has_pdf_attachment=has_pdf_attachment,
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
        logger.warning(
            "orchestration.response_policy_failed reason=%s fallback=%s",
            type(exc).__name__,
            json.dumps(fallback.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
        )
        return fallback
