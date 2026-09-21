from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.query_policy_service import (
    AnswerDepth,
    AttachmentReason,
    AttachmentTask,
    EvidenceMode,
    FollowupMode,
    LearningTechnique,
    LearningMode,
    PedagogicalAction,
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
              "learning_mode": "LEARN",
              "pedagogical_action": "EXPLAIN_PREREQ",
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
    assert policy.learning_technique is LearningTechnique.NONE
    assert policy.learning_mode is LearningMode.LEARN
    assert policy.pedagogical_action is PedagogicalAction.EXPLAIN_PREREQ
    assert policy.evidence_mode is EvidenceMode.NONE
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
            "learning_technique": "MAGIC",
            "learning_mode": "SPOONFEED",
            "pedagogical_action": "DO_HOMEWORK",
            "evidence_mode": "TRUST_ME",
            "attachment_task": "AUTORUN",
            "attachment_reason": "GUESS",
            "legacy_policy": "BAD",
        }
    )

    assert policy == default_response_policy()


def test_response_policy_from_dict_accepts_learning_and_evidence_fields():
    """Learning and evidence fields should be parsed as allowlisted policy metadata."""

    policy = response_policy_from_dict(
        {
            "task_intent": "GENERAL_QA",
            "answer_depth": "SCAFFOLDED",
            "tone": "TUTORING",
            "structure": "STEP_BY_STEP",
            "followup_mode": "OPTIONAL",
            "learning_technique": "TWENTY_HOUR_PLAN",
            "learning_mode": "REFERENCE",
            "pedagogical_action": "ANSWER",
            "evidence_mode": "MULTI_SOURCE_REQUIRED",
            "legacy_policy": "NORMAL",
        }
    )

    assert policy.learning_technique is LearningTechnique.TWENTY_HOUR_PLAN
    assert policy.learning_mode is LearningMode.REFERENCE
    assert policy.pedagogical_action is PedagogicalAction.ANSWER
    assert policy.evidence_mode is EvidenceMode.MULTI_SOURCE_REQUIRED


@pytest.mark.asyncio
async def test_practice_pressure_keeps_learner_owned_step(caplog):
    """Answer pressure inside homework-like practice should become EDF scaffolding."""

    caplog.set_level("INFO")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "ANSWER_EXAM",
              "answer_depth": "DIRECT",
              "tone": "PLAIN",
              "structure": "SHORT",
              "followup_mode": "NONE",
              "learning_mode": "REFERENCE",
              "pedagogical_action": "ANSWER",
              "visual_support": "NONE",
              "visual_reason": "NOT_NEEDED",
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
        "My essay is due in one hour. Please just tell me the actual root cause.",
        [],
    )

    assert policy.task_intent is TaskIntent.ANSWER_EXAM
    assert policy.answer_depth is AnswerDepth.SCAFFOLDED
    assert policy.tone is ResponseTone.TUTORING
    assert policy.structure is ResponseStructure.STEP_BY_STEP
    assert policy.followup_mode is FollowupMode.REQUIRED
    assert policy.learning_mode is LearningMode.PRACTICE
    assert policy.pedagogical_action is PedagogicalAction.HINT
    assert policy.legacy_policy == "PROBE_UNDERSTANDING"
    assert "orchestration.response_policy_learning_guardrail_applied" in caplog.text
    assert "actual root cause" not in caplog.text


@pytest.mark.asyncio
async def test_answer_exam_policy_normalizes_to_practice_ownership():
    """Assessment intent should be structurally incompatible with direct answer ownership."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "ANSWER_EXAM",
              "answer_depth": "DIRECT",
              "tone": "PLAIN",
              "structure": "SHORT",
              "followup_mode": "NONE",
              "learning_mode": "REFERENCE",
              "pedagogical_action": "ANSWER",
              "visual_support": "NONE",
              "visual_reason": "NOT_NEEDED",
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
        "This is for a quiz. Which is the best answer, A or B? Please only choose one.",
        [],
    )

    assert policy.task_intent is TaskIntent.ANSWER_EXAM
    assert policy.answer_depth is AnswerDepth.SCAFFOLDED
    assert policy.followup_mode is FollowupMode.REQUIRED
    assert policy.learning_mode is LearningMode.PRACTICE
    assert policy.pedagogical_action is PedagogicalAction.HINT
    assert policy.legacy_policy == "PROBE_UNDERSTANDING"


@pytest.mark.asyncio
async def test_reference_mode_allows_direct_answer_request():
    """Explicit reference/self-study mode should still allow direct answers."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "GENERAL_QA",
              "answer_depth": "DIRECT",
              "tone": "PLAIN",
              "structure": "SHORT",
              "followup_mode": "NONE",
              "learning_mode": "REFERENCE",
              "pedagogical_action": "ANSWER",
              "visual_support": "NONE",
              "visual_reason": "NOT_NEEDED",
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
        "Reference mode, not homework: just tell me which option is correct.",
        [],
    )

    assert policy.answer_depth is AnswerDepth.DIRECT
    assert policy.task_intent is TaskIntent.GENERAL_QA
    assert policy.learning_mode is LearningMode.REFERENCE
    assert policy.pedagogical_action is PedagogicalAction.ANSWER


@pytest.mark.asyncio
async def test_learning_guardrail_detects_short_quiz_request(caplog):
    """Explicit short learning-technique phrases should not depend on classifier accuracy."""

    caplog.set_level("INFO")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "GENERAL_QA",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "learning_technique": "NONE",
              "evidence_mode": "NONE",
              "visual_support": "NONE",
              "visual_reason": "NOT_NEEDED",
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
        "我剛學完貝葉斯定理，考我 10 題",
        [],
    )

    assert policy.learning_technique is LearningTechnique.DIAGNOSTIC_QUIZ
    assert "orchestration.response_policy_learning_guardrail_applied" in caplog.text
    assert "貝葉斯" not in caplog.text


@pytest.mark.asyncio
async def test_domain_orientation_request_uses_short_reference_policy(caplog):
    """Field-scope questions should not become a staged learning roadmap."""

    caplog.set_level("INFO")
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "GENERAL_QA",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "learning_technique": "LEVEL_PATH",
              "learning_mode": "LEARN",
              "pedagogical_action": "EXPLAIN_PREREQ",
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
        "產品設計學什麼？",
        [],
    )

    assert policy.task_intent is TaskIntent.GENERAL_QA
    assert policy.answer_depth is AnswerDepth.DIRECT
    assert policy.tone is ResponseTone.PLAIN
    assert policy.structure is ResponseStructure.SHORT
    assert policy.learning_mode is LearningMode.REFERENCE
    assert policy.learning_technique is LearningTechnique.NONE
    assert policy.pedagogical_action is PedagogicalAction.ANSWER
    assert policy.visual_support is VisualSupport.NONE
    assert "orchestration.response_policy_learning_guardrail_applied" in caplog.text
    assert "產品設計" not in caplog.text


@pytest.mark.asyncio
async def test_broad_learning_start_asks_need_before_full_plan():
    """Underspecified learning-start turns should clarify goals before planning."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "task_intent": "GENERAL_QA",
              "answer_depth": "SCAFFOLDED",
              "tone": "TUTORING",
              "structure": "STEP_BY_STEP",
              "followup_mode": "OPTIONAL",
              "learning_technique": "LEVEL_PATH",
              "learning_mode": "LEARN",
              "pedagogical_action": "EXPLAIN_PREREQ",
              "visual_support": "OPTIONAL",
              "visual_reason": "KNOWLEDGE_EXPLANATION",
              "attachment_task": "NONE",
              "attachment_reason": "NO_ATTACHMENT",
              "legacy_policy": "SUGGEST_ACTION"
            }
            """
        )
    )

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "我想學資料科學，該從哪裡開始？",
        [],
    )

    assert policy.answer_depth is AnswerDepth.SCAFFOLDED
    assert policy.structure is ResponseStructure.SHORT
    assert policy.followup_mode is FollowupMode.REQUIRED
    assert policy.learning_technique is LearningTechnique.NONE
    assert policy.learning_mode is LearningMode.LEARN
    assert policy.pedagogical_action is PedagogicalAction.DIAGNOSTIC_QUESTION
    assert policy.visual_support is VisualSupport.NONE
    assert policy.legacy_policy == "PROBE_UNDERSTANDING"


@pytest.mark.asyncio
async def test_evidence_guardrail_requires_multiple_sources_for_medical_topic():
    """Medical learning requests should carry stricter evidence requirements."""

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_mock_chat_response("NORMAL"))

    policy = await classify_response_policy_impl(
        mock_client,
        "test-model",
        "請幫我用 20 小時快速學會高血壓治療指引",
        [],
    )

    assert policy.learning_technique is LearningTechnique.TWENTY_HOUR_PLAN
    assert policy.evidence_mode is EvidenceMode.MULTI_SOURCE_REQUIRED


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
    """The paper overlay should preserve tutoring style and required coverage."""

    instruction = paper_auto_explain_instruction()

    assert "profile: AREQA_TEACHING_V1" in instruction
    assert "首段先貼合本回合學習模式" in instruction
    assert "分步方式降低理解負擔" in instruction
    assert "先講白話直覺" in instruction
    assert "研究動機與目的" in instruction
    assert "研究方法與模型架構" in instruction
    assert "實驗設計與資料集" in instruction
    assert "實驗結果與消融分析" in instruction
    assert "一般回答模式的白話教學感" in instruction
    assert "不要寫成正式審稿報告" in instruction
    assert "段落文字為主" in instruction
    assert "列點與表格只能作為輔助摘要" in instruction
    assert "研究結論" in instruction
    assert "局限與可延伸方向" in instruction
