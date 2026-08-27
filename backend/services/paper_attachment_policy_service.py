"""Select request-scoped paper-reading defaults for PDF attachments.

The service owns the narrow product policy for generic PDF-paper uploads: when
the user attaches a PDF and gives only a broad "explain/read this" request, the
backend can add a structured paper overview instruction without requiring the
user to retype the same prompt every time. It deliberately does not parse PDF
content or infer facts from filenames; attachment grounding remains owned by
the model provider and the orchestration attachment boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any


class PaperAttachmentTask(str, Enum):
    """Supported automatic task overlays for paper-like PDF attachments."""

    NONE = "NONE"
    AUTO_EXPLAIN = "AUTO_EXPLAIN"


@dataclass(frozen=True, slots=True)
class PaperAttachmentDecision:
    """Privacy-safe decision for automatic paper explanation.

    Args:
        task: Selected automatic paper task.
        reason: Stable reason code for backend logs and tests.
        pdf_count: Number of PDF attachments detected in this request.
        generic_request: Whether the latest user message was broad enough for
            the backend to apply the default paper overview task.

    Side Effects:
        None. The decision contains only counts and reason codes; it excludes
        raw user text, PDF bytes, prompts, model output, filenames, and URLs.
    """

    task: PaperAttachmentTask
    reason: str
    pdf_count: int
    generic_request: bool

    @property
    def auto_explain(self) -> bool:
        """Return whether orchestration should inject the paper overview task."""

        return self.task is PaperAttachmentTask.AUTO_EXPLAIN


class PaperAttachmentPolicyService:
    """Decide whether a PDF upload should receive the default paper overview.

    This is intentionally deterministic and conservative. The LLM still reads
    and explains the PDF; this service only decides whether to add a reusable
    structure when the user's request is generic. Explicit user tasks always
    win so prompts like "translate page 3" or "only summarize limitations" are
    not overwritten by the automatic overview.
    """

    _GENERIC_EXACT_REQUESTS = {
        "",
        "請分析我附加的檔案。",
        "請分析我附加的檔案",
        "請分析附件",
        "分析附件",
        "幫我看",
        "幫我看一下",
        "幫我看這篇",
        "解釋這篇",
        "這篇在講什麼",
        "這篇論文在講什麼",
        "幫我解釋這篇論文",
        "解釋這篇論文",
        "請解釋該 pdf",
        "讀這篇論文",
        "看這篇論文",
        "analyze this pdf",
        "explain this pdf",
        "explain this paper",
        "summarize this paper",
        "what is this paper about",
        "what is this pdf about",
    }
    _GENERIC_PATTERNS = (
        re.compile(
            r"^(?:請|麻煩)?\s*(?:幫我)?\s*(?:看|讀|分析|解釋|說明|摘要|總結)\s*"
            r"(?:一下)?\s*(?:這篇|這份|這個|該)?\s*(?:pdf|paper|論文|文件|附件)?\s*[。.!？?]*$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:please\s+)?(?:analy[sz]e|explain|summari[sz]e|read)\s+"
            r"(?:this\s+)?(?:pdf|paper|attachment|file)\s*[.!?]*$",
            re.IGNORECASE,
        ),
    )
    _EXPLICIT_TASK_PATTERNS = (
        re.compile(r"(翻譯|translate|逐字|全文翻|第\s*\d+\s*頁|page\s*\d+)", re.IGNORECASE),
        re.compile(r"(只|only|solely|不要|不用).{0,12}(摘要|方法|結果|結論|限制|limitations?|method|result|conclusion)", re.IGNORECASE),
        re.compile(r"(找出|抽出|extract|cite|引用|格式|改寫|rewrite|proofread|校稿|潤飾|polish)", re.IGNORECASE),
    )

    def evaluate(
        self,
        *,
        user_msg: str,
        attachments: list[dict[str, Any]] | None,
    ) -> PaperAttachmentDecision:
        """Return whether this request should get automatic paper explanation.

        Args:
            user_msg: Latest user-authored message. Used only for bounded task
                classification and never returned in the decision.
            attachments: OpenRouter-compatible request-scoped attachment parts.

        Returns:
            A privacy-safe ``PaperAttachmentDecision``.

        Side Effects:
            None.
        """

        pdf_count = self._count_pdf_attachments(attachments or [])
        if pdf_count <= 0:
            return PaperAttachmentDecision(
                task=PaperAttachmentTask.NONE,
                reason="no_pdf_attachment",
                pdf_count=0,
                generic_request=False,
            )

        generic_request = self._is_generic_paper_request(user_msg)
        if not generic_request:
            return PaperAttachmentDecision(
                task=PaperAttachmentTask.NONE,
                reason="explicit_user_task",
                pdf_count=pdf_count,
                generic_request=False,
            )

        return PaperAttachmentDecision(
            task=PaperAttachmentTask.AUTO_EXPLAIN,
            reason="generic_pdf_paper_request",
            pdf_count=pdf_count,
            generic_request=True,
        )

    def disabled_decision(
        self,
        attachments: list[dict[str, Any]] | None,
    ) -> PaperAttachmentDecision:
        """Return a disabled decision while preserving PDF-count observability.

        Args:
            attachments: OpenRouter-compatible request-scoped attachment parts.

        Returns:
            A ``PaperAttachmentDecision`` with ``task=NONE`` and a safe disabled
            reason for backend logs.

        Side Effects:
            None.
        """

        return PaperAttachmentDecision(
            task=PaperAttachmentTask.NONE,
            reason="feature_disabled",
            pdf_count=self._count_pdf_attachments(attachments or []),
            generic_request=False,
        )

    @staticmethod
    def instruction_text() -> str:
        """Return the system prompt overlay for automatic paper explanation.

        Returns:
            Traditional Chinese prompt text. The existing answer-language rule
            still controls the final user-visible language.

        Side Effects:
            None.
        """

        return (
            "【PDF 論文自動解說任務】本回合使用者上傳 PDF，且沒有指定更細的任務。"
            "請把它視為一篇需要導讀的論文或技術文件，根據實際可讀取的 PDF 內容，自動用以下結構回答："
            "\n1. 研究動機與目標：說明作者想解決什麼問題、為什麼重要。"
            "\n2. 研究方法：說明核心方法、模型、資料、流程或理論設計。"
            "\n3. 實驗過程與設定：說明資料集、比較基準、實驗設計、評估指標或分析流程。"
            "\n4. 實驗結果：整理主要發現、圖表或數據代表的意思。"
            "\n5. 研究結論：說明作者最後主張什麼、貢獻是什麼。"
            "\n6. 局限與可延伸方向：若 PDF 有提到 limitation/future work，請整理；若沒有足夠資訊，明確說「PDF 中沒有足夠資訊」。"
            "\n不得根據檔名、metadata 或常識補齊 PDF 沒有支持的內容；資訊不足時要說明不確定，而不是猜測。"
        )

    @classmethod
    def _is_generic_paper_request(cls, user_msg: str) -> bool:
        """Return whether the user message leaves the paper task unspecified."""

        normalized = re.sub(r"\s+", " ", str(user_msg or "")).strip().lower()
        if normalized in cls._GENERIC_EXACT_REQUESTS:
            return True
        if any(pattern.search(normalized) for pattern in cls._EXPLICIT_TASK_PATTERNS):
            return False
        return any(pattern.search(normalized) for pattern in cls._GENERIC_PATTERNS)

    @staticmethod
    def _count_pdf_attachments(attachments: list[dict[str, Any]]) -> int:
        """Count request attachments that are OpenRouter PDF file parts."""

        count = 0
        for attachment in attachments:
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
