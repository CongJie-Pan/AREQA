"""Tests for automatic paper explanation policy on PDF attachments."""

from backend.services.paper_attachment_policy_service import (
    PaperAttachmentPolicyService,
    PaperAttachmentTask,
)


def _pdf_attachment(filename: str = "paper.pdf") -> dict:
    """Return one OpenRouter-compatible PDF attachment part."""

    return {
        "type": "file",
        "file": {
            "filename": filename,
            "file_data": "data:application/pdf;base64,AA==",
        },
    }


def test_auto_explain_for_generic_pdf_paper_request():
    """Generic PDF requests should receive the default paper overview task."""

    decision = PaperAttachmentPolicyService().evaluate(
        user_msg="這篇論文在講什麼",
        attachments=[_pdf_attachment()],
    )

    assert decision.task is PaperAttachmentTask.AUTO_EXPLAIN
    assert decision.auto_explain is True
    assert decision.reason == "generic_pdf_paper_request"
    assert decision.pdf_count == 1
    assert decision.generic_request is True


def test_auto_explain_for_generic_pdf_reference():
    """Generic PDF references from the upload flow should trigger the overview."""

    decision = PaperAttachmentPolicyService().evaluate(
        user_msg="請幫我看這篇論文",
        attachments=[_pdf_attachment()],
    )

    assert decision.auto_explain is True
    assert decision.reason == "generic_pdf_paper_request"


def test_auto_explain_for_empty_pdf_request():
    """Empty attachment prompts should use the default paper overview task."""

    decision = PaperAttachmentPolicyService().evaluate(
        user_msg="",
        attachments=[_pdf_attachment()],
    )

    assert decision.auto_explain is True
    assert decision.reason == "generic_pdf_paper_request"


def test_does_not_override_explicit_pdf_task():
    """Explicit user tasks should not be replaced by the paper overview."""

    decision = PaperAttachmentPolicyService().evaluate(
        user_msg="請只翻譯第 3 頁",
        attachments=[_pdf_attachment()],
    )

    assert decision.task is PaperAttachmentTask.NONE
    assert decision.auto_explain is False
    assert decision.reason == "explicit_user_task"
    assert decision.pdf_count == 1
    assert decision.generic_request is False


def test_non_pdf_attachment_does_not_trigger_auto_explain():
    """The default paper overview is scoped to PDF file attachments."""

    decision = PaperAttachmentPolicyService().evaluate(
        user_msg="請分析附件",
        attachments=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}],
    )

    assert decision.task is PaperAttachmentTask.NONE
    assert decision.reason == "no_pdf_attachment"
    assert decision.pdf_count == 0


def test_disabled_decision_preserves_pdf_count_for_logs():
    """Disabled policy decisions should still expose safe PDF counts."""

    decision = PaperAttachmentPolicyService().disabled_decision([_pdf_attachment()])

    assert decision.task is PaperAttachmentTask.NONE
    assert decision.auto_explain is False
    assert decision.reason == "feature_disabled"
    assert decision.pdf_count == 1
    assert decision.generic_request is False


def test_instruction_contains_required_paper_sections():
    """The injected task should cover the requested paper-reading structure."""

    instruction = PaperAttachmentPolicyService.instruction_text()

    assert "研究動機與目標" in instruction
    assert "研究方法" in instruction
    assert "實驗過程與設定" in instruction
    assert "實驗結果" in instruction
    assert "研究結論" in instruction
    assert "局限與可延伸方向" in instruction
    assert "不得根據檔名" in instruction
