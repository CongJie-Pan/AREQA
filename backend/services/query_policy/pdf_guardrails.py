"""PDF attachment guardrails for response-policy classification.

This module owns deterministic PDF overview routing and the narrow semantic
fallback classifier. Logs contain only enum metadata and safe reason codes; raw
user text, prompts, model output, credentials, and attachment content must not
be logged.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from services.conversation.answer_style import render_paper_overview_style
from services.query_policy.models import (
    AttachmentReason,
    AttachmentTask,
    ResponsePolicy,
    VisualReason,
    VisualSupport,
)

logger = logging.getLogger(__name__)

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
        r"(?:這|這篇|這份|此|此篇|本篇|該|該篇)?(?:論文|PDF|文件|文獻)"
    ),
    re.compile(
        r"(?:這|這篇|這份|此|此篇|本篇|該|該篇)?(?:論文|PDF|文件|文獻)(?:在)?"
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
        Traditional Chinese paper-task constraints that preserve the normal
        tutoring style while requiring complete paper overview coverage. The
        existing language policy can still ask the answer model to respond in
        the user's preferred language.

    Side Effects:
        None. The caller owns structured logging before this prompt is applied.
    """

    return (
        "【PDF 論文自動解說任務】本回合使用者上傳 PDF，且 policy classifier 判定使用者"
        "是在要求一般性的論文導讀，沒有指定更細的任務。請把它視為一篇需要導讀的論文或技術文件，"
        f"{render_paper_overview_style()}"
        "根據實際可讀取的 PDF 內容，回答必須自然覆蓋以下導讀要點："
        "\n1. 研究動機與目的：說明作者想解決什麼問題、為什麼重要。"
        "\n2. 研究方法與模型架構：說明核心方法、模型、資料、流程或理論設計。"
        "\n3. 實驗設計與資料集：說明資料集、比較基準、實驗設計、評估指標或分析流程。"
        "\n4. 實驗結果與消融分析：整理主要發現、圖表或數據代表的意思；若有消融分析，說明它驗證了哪些設計選擇。"
        "\n5. 研究結論：說明作者最後主張什麼、貢獻是什麼。"
        "\n6. 局限與可延伸方向：若 PDF 有提到 limitation/future work，請整理；"
        "若沒有足夠資訊，明確說「PDF 中沒有足夠資訊」。"
        "\n回答語氣請以一般回答模式的白話教學感為底，不要寫成正式審稿報告或僵硬摘要。"
        "第 2、3、4 節請維持段落文字為主：每節先用 1-2 句白話直覺帶路，"
        "再補 1-2 句論文術語、流程或數據；接著放對應圖，圖後再用 1-3 句解釋圖如何支撐剛才的段落。"
        "列點與表格只能作為輔助摘要，不可取代正文說明。"
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
                learning_technique=policy.learning_technique,
                learning_mode=policy.learning_mode,
                pedagogical_action=policy.pedagogical_action,
                evidence_mode=policy.evidence_mode,
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
        learning_technique=policy.learning_technique,
        learning_mode=policy.learning_mode,
        pedagogical_action=policy.pedagogical_action,
        evidence_mode=policy.evidence_mode,
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
        learning_technique=policy.learning_technique,
        learning_mode=policy.learning_mode,
        pedagogical_action=policy.pedagogical_action,
        evidence_mode=policy.evidence_mode,
        attachment_task=AttachmentTask.PAPER_AUTO_EXPLAIN,
        attachment_reason=AttachmentReason.GENERIC_PAPER_EXPLANATION,
        legacy_policy=policy.legacy_policy,
    )
    logger.info(
        "orchestration.response_policy_pdf_guardrail_applied reason=broad_pdf_auto_explain metadata=%s",
        json.dumps(guarded.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
    )
    return guarded


def _pdf_auto_explain_policy_from(
    policy: ResponsePolicy,
    *,
    reason: AttachmentReason = AttachmentReason.GENERIC_PAPER_EXPLANATION,
) -> ResponsePolicy:
    """Return ``policy`` converted to a whole-paper PDF overview task.

    Args:
        policy: Current response policy selected by the model or fallback path.
        reason: Stable attachment reason for the policy transition.

    Returns:
        A response policy that enables the paper overview prompt and optional
        attachment visual support.

    Side Effects:
        None. Callers own structured logs at their decision boundary.
    """

    return ResponsePolicy(
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
        learning_technique=policy.learning_technique,
        learning_mode=policy.learning_mode,
        pedagogical_action=policy.pedagogical_action,
        evidence_mode=policy.evidence_mode,
        attachment_task=AttachmentTask.PAPER_AUTO_EXPLAIN,
        attachment_reason=reason,
        legacy_policy=policy.legacy_policy,
    )


async def _apply_pdf_semantic_auto_explain_fallback(
    policy: ResponsePolicy,
    *,
    client: Any,
    model: str,
    user_msg: str,
    has_pdf_attachment: bool,
) -> ResponsePolicy:
    """Use a narrow second LLM check for ambiguous PDF overview requests.

    Args:
        policy: Current response policy after deterministic guardrails.
        client: Chat-completions compatible model client.
        model: Model identifier used by the policy classifier.
        user_msg: Current user message. It is sent to the fallback classifier
            but never logged.
        has_pdf_attachment: Whether request metadata confirms a PDF attachment.

    Returns:
        ``policy`` unchanged unless the fallback model explicitly classifies the
        turn as a whole-paper overview request.

    Side Effects:
        May make one small LLM call. Emits privacy-safe structured logs
        ``orchestration.response_policy_pdf_semantic_fallback_applied`` and
        ``orchestration.response_policy_pdf_semantic_fallback_failed`` with only
        enum metadata and reason codes, never raw user text or model output.
    """

    if (
        not has_pdf_attachment
        or policy.attachment_task is not AttachmentTask.NONE
        or _is_broad_pdf_auto_explain_request(user_msg)
        or _PDF_TARGETED_TASK_PATTERN.search(str(user_msg or ""))
    ):
        return policy

    prompt = (
        "A PDF is attached. Decide whether the user is asking for a broad, whole-paper "
        "overview/explanation/reading guide rather than a focused operation such as translation, "
        "citation extraction, proofreading, page-specific QA, comparison, or a single section only. "
        "Return strict JSON only: {\"is_whole_paper_overview\": true|false}.\n\n"
        f"User message:\n{user_msg}"
    )
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return only valid JSON. Do not explain."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=40,
            temperature=0.0,
        )
        content = str(response.choices[0].message.content or "").strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        match = re.search(r"\{.*\}", content, re.DOTALL)
        parsed = json.loads(match.group(0) if match else content)
        if isinstance(parsed, dict) and parsed.get("is_whole_paper_overview") is True:
            guarded = _pdf_auto_explain_policy_from(policy)
            logger.info(
                "orchestration.response_policy_pdf_semantic_fallback_applied metadata=%s",
                json.dumps(guarded.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
            )
            return guarded
    except Exception as exc:
        logger.info(
            "orchestration.response_policy_pdf_semantic_fallback_failed reason=%s",
            type(exc).__name__,
        )
    return policy


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
