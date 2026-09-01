from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.query_policy_service import (
    AnswerDepth,
    AttachmentReason,
    AttachmentTask,
    FollowupMode,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualReason,
    VisualSupport,
    classify_dialogue_policy_impl,
    classify_response_policy_impl,
    count_pdf_attachments,
    default_response_policy,
    paper_auto_explain_instruction,
    response_policy_from_dict,
    response_policy_from_legacy,
)


def _mock_chat_response(content: str):
    """Build a minimal OpenAI-compatible chat completion response."""

    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


@pytest.mark.asyncio
async def test_classify_response_policy_parses_valid_json(caplog):
    """Valid classifier JSON should become an allowlisted ResponsePolicy."""

    caplog.set_level("INFO")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "EXPLAIN_TEXT",
              "answer_depth": "SCAFFOLDED",
              "tone": "PLAIN",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "visual_support": "OPTIONAL",
              "visual_reason": "KNOWLEDGE_EXPLANATION",
              "attachment_task": "NONE",
              "attachment_reason": "NO_ATTACHMENT",
              "legacy_policy": "NORMAL"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "我聽不懂，可以白話一點嗎？",
        [],
    )

    assert policy.task_intent is TaskIntent.EXPLAIN_TEXT
    assert policy.answer_depth is AnswerDepth.SCAFFOLDED
    assert policy.tone is ResponseTone.PLAIN
    assert policy.structure is ResponseStructure.STEP_BY_STEP
    assert policy.followup_mode is FollowupMode.OPTIONAL
    assert policy.visual_support is VisualSupport.OPTIONAL
    assert policy.visual_reason is VisualReason.KNOWLEDGE_EXPLANATION
    assert "orchestration.response_policy_selected" in caplog.text
    assert "我聽不懂" not in caplog.text


@pytest.mark.asyncio
async def test_classify_response_policy_falls_back_on_invalid_json(caplog):
    """Malformed model output should fail closed to plain scaffolded tutoring."""

    caplog.set_level("WARNING")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response("not-json")
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "任何問題",
        [],
    )

    assert policy == default_response_policy()
    assert "orchestration.response_policy_failed" in caplog.text
    assert "任何問題" not in caplog.text


def test_response_policy_from_dict_sanitizes_unknown_values():
    """Unsupported enum values should not reopen deep response behavior."""

    policy = response_policy_from_dict(
        {
            "task_intent": "UNKNOWN",
            "answer_depth": "TOO_DEEP",
            "tone": "DRAMATIC",
            "structure": "ESSAY",
            "followup_mode": "ALWAYS",
            "visual_support": "ALWAYS",
            "visual_reason": "DECORATIVE",
            "attachment_task": "AUTORUN",
            "attachment_reason": "GUESS",
            "legacy_policy": "BAD",
        }
    )

    assert policy == default_response_policy()


def test_response_policy_from_legacy_push_limit_allows_reflection():
    """Legacy PUSH_LIMIT should map to reflective depth for old call sites."""

    policy = response_policy_from_legacy("PUSH_LIMIT")

    assert policy.task_intent is TaskIntent.DISCUSS_IDEA
    assert policy.answer_depth is AnswerDepth.REFLECTIVE
    assert policy.tone is ResponseTone.ANALYTICAL
    assert policy.visual_support is VisualSupport.NONE
    assert policy.legacy_policy == "PUSH_LIMIT"


@pytest.mark.asyncio
async def test_classify_dialogue_policy_impl_preserves_string_contract():
    """The old classifier API should still return only the legacy policy name."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "DISCUSS_IDEA",
              "answer_depth": "DEEP_DIVE",
              "tone": "ANALYTICAL",
              "structure": "ARGUMENT",
              "followup_mode": "OPTIONAL",
              "legacy_policy": "PUSH_LIMIT"
            }
            """
        )
    )

    policy = await classify_dialogue_policy_impl(
        mock_client,
        "test-model",
        "你覺得這個問題的核心是什麼？",
        [],
    )

    assert policy == "PUSH_LIMIT"


@pytest.mark.asyncio
async def test_classify_response_policy_selects_pdf_auto_explain_for_english_generic_request():
    """Generic English PDF paper requests should keep the auto-explain task."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "EXPLAIN_TEXT",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "visual_support": "OPTIONAL",
              "visual_reason": "ATTACHMENT_FIGURE_EXPLANATION",
              "attachment_task": "PAPER_AUTO_EXPLAIN",
              "attachment_reason": "GENERIC_PAPER_EXPLANATION",
              "legacy_policy": "NORMAL"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "Please help me explain this paper.",
        [],
        has_pdf_attachment=True,
        pdf_attachment_count=1,
    )

    assert policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
    assert policy.attachment_reason is AttachmentReason.GENERIC_PAPER_EXPLANATION
    prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert '"has_pdf_attachment": true' in prompt
    assert "please help me explain this paper" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_msg",
    [
        "Please explain this paper",
        "Please help me explain this paper",
        "請幫我說明此篇論文",
        "請幫我導讀本篇論文",
        "幫我解釋該篇文獻",
    ],
)
async def test_pdf_broad_request_guardrail_overrides_missed_classifier_auto_explain(
    user_msg,
    caplog,
):
    """Clear whole-paper PDF overview requests should not drift into generic tutoring."""

    caplog.set_level("INFO")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "EXPLAIN_TEXT",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "REQUIRED",
              "visual_support": "NONE",
              "visual_reason": "NOT_NEEDED",
              "attachment_task": "NONE",
              "attachment_reason": "NOT_PAPER_TASK",
              "legacy_policy": "PROBE_UNDERSTANDING"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        user_msg,
        [],
        has_pdf_attachment=True,
        pdf_attachment_count=1,
    )

    assert policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
    assert policy.attachment_reason is AttachmentReason.GENERIC_PAPER_EXPLANATION
    assert policy.visual_support is VisualSupport.OPTIONAL
    assert policy.visual_reason is VisualReason.ATTACHMENT_FIGURE_EXPLANATION
    assert "orchestration.response_policy_pdf_guardrail_applied" in caplog.text
    assert user_msg not in caplog.text


@pytest.mark.asyncio
async def test_pdf_broad_request_guardrail_applies_to_classifier_failure(caplog):
    """Classifier outages should still route clear PDF overview prompts safely."""

    caplog.set_level("INFO")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response("not-json")
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "Please help me explain this paper",
        [],
        has_pdf_attachment=True,
        pdf_attachment_count=1,
    )

    assert policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
    assert policy.attachment_reason is AttachmentReason.GENERIC_PAPER_EXPLANATION
    assert policy.visual_support is VisualSupport.OPTIONAL
    assert "orchestration.response_policy_failed" in caplog.text
    assert "Please help me explain this paper" not in caplog.text


@pytest.mark.asyncio
async def test_pdf_semantic_fallback_recovers_ambiguous_overview_request(caplog):
    """A second LLM check should recover broad PDF requests missed by the main classifier."""

    caplog.set_level("INFO")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[
            _mock_chat_response(
                """
                {
                  "task_intent": "GENERAL_QA",
                  "answer_depth": "SCAFFOLDED",
                  "tone": "TUTORING",
                  "structure": "STEP_BY_STEP",
                  "followup_mode": "OPTIONAL",
                  "visual_support": "NONE",
                  "visual_reason": "NOT_NEEDED",
                  "attachment_task": "NONE",
                  "attachment_reason": "NOT_PAPER_TASK",
                  "legacy_policy": "NORMAL"
                }
                """
            ),
            _mock_chat_response('{"is_whole_paper_overview": true}'),
        ]
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "可以帶我看懂這份研究嗎？",
        [],
        has_pdf_attachment=True,
        pdf_attachment_count=1,
    )

    assert policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
    assert policy.attachment_reason is AttachmentReason.GENERIC_PAPER_EXPLANATION
    assert policy.visual_support is VisualSupport.OPTIONAL
    assert mock_client.chat.completions.create.await_count == 2
    assert "orchestration.response_policy_pdf_semantic_fallback_applied" in caplog.text
    assert "可以帶我看懂" not in caplog.text


@pytest.mark.asyncio
async def test_pdf_semantic_fallback_does_not_override_focused_pdf_task():
    """Focused PDF requests should not spend or apply the semantic overview fallback."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "EXPLAIN_TEXT",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "visual_support": "OPTIONAL",
              "visual_reason": "ATTACHMENT_FIGURE_EXPLANATION",
              "attachment_task": "PAPER_TARGETED_QA",
              "attachment_reason": "TARGETED_ATTACHMENT_TASK",
              "legacy_policy": "NORMAL"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "只說明這篇論文的 methods section",
        [],
        has_pdf_attachment=True,
        pdf_attachment_count=1,
    )

    assert policy.attachment_task is AttachmentTask.PAPER_TARGETED_QA
    assert policy.attachment_reason is AttachmentReason.TARGETED_ATTACHMENT_TASK
    assert mock_client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_pdf_broad_request_guardrail_does_not_override_focused_pdf_task():
    """Focused PDF requests should remain under classifier ownership."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "EXPLAIN_TEXT",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "visual_support": "OPTIONAL",
              "visual_reason": "ATTACHMENT_FIGURE_EXPLANATION",
              "attachment_task": "PAPER_TARGETED_QA",
              "attachment_reason": "TARGETED_ATTACHMENT_TASK",
              "legacy_policy": "NORMAL"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "Please explain this paper methods section only.",
        [],
        has_pdf_attachment=True,
        pdf_attachment_count=1,
    )

    assert policy.attachment_task is AttachmentTask.PAPER_TARGETED_QA
    assert policy.attachment_reason is AttachmentReason.TARGETED_ATTACHMENT_TASK


@pytest.mark.asyncio
async def test_classify_response_policy_clears_attachment_task_without_pdf():
    """Attachment guardrails prevent model hallucinated PDF tasks."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "EXPLAIN_TEXT",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "visual_support": "NONE",
              "visual_reason": "NOT_NEEDED",
              "attachment_task": "PAPER_AUTO_EXPLAIN",
              "attachment_reason": "GENERIC_PAPER_EXPLANATION",
              "legacy_policy": "NORMAL"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "Please help me explain this paper.",
        [],
        has_pdf_attachment=False,
        pdf_attachment_count=0,
    )

    assert policy.attachment_task is AttachmentTask.NONE
    assert policy.attachment_reason is AttachmentReason.NO_ATTACHMENT


@pytest.mark.asyncio
async def test_pdf_auto_explain_policy_enables_optional_attachment_visuals():
    """Paper auto-explain should be internally consistent with PDF visuals."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "EXPLAIN_TEXT",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "visual_support": "NONE",
              "visual_reason": "NOT_NEEDED",
              "attachment_task": "PAPER_AUTO_EXPLAIN",
              "attachment_reason": "GENERIC_PAPER_EXPLANATION",
              "legacy_policy": "NORMAL"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "Please help me explain this paper.",
        [],
        has_pdf_attachment=True,
        pdf_attachment_count=1,
    )

    assert policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
    assert policy.visual_support is VisualSupport.OPTIONAL
    assert policy.visual_reason is VisualReason.ATTACHMENT_FIGURE_EXPLANATION


def test_count_pdf_attachments_counts_file_parts_only():
    """Structural PDF detection stays deterministic and content-free."""

    attachments = [
        {"type": "file", "file": {"filename": "paper.pdf", "file_data": ""}},
        {"type": "file", "file": {"filename": "image.png", "file_data": "data:application/pdf;base64,AAA"}},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
    ]

    assert count_pdf_attachments(attachments) == 2


def test_paper_auto_explain_instruction_contains_required_sections():
    """The reusable prompt overlay should preserve the paper overview template."""

    instruction = paper_auto_explain_instruction()

    assert "研究動機與目標" in instruction
    assert "研究方法" in instruction
    assert "實驗過程與設定" in instruction
    assert "實驗結果" in instruction
    assert "研究結論" in instruction
    assert "局限與可延伸方向" in instruction
