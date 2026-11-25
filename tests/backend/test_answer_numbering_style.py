"""Regression: answers number points with 一、二、三、 instead of 第一步/第二步/Step 1.

Learners found "第一步、第二步…" abrupt in ordinary chat. Every prompt source that
asks for step-wise explanations must carry the numbering rule and must not
itself ask for "每一步" wording.
"""
from pathlib import Path

from backend.services.answer_style_service import PEDAGOGY_TUTOR_SKILL_PATH, render_base_persona
from backend.services.conversation_context_service import ConversationContextService
from backend.services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
)

ROOT = Path(__file__).resolve().parents[2]
NUMBERING = "「一、」「二、」「三、」"


def test_step_by_step_structure_asks_for_chinese_ordinal_numbering():
    instruction = ConversationContextService._response_policy_instruction(
        ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            legacy_policy="NORMAL",
        ),
        {},
    )
    assert NUMBERING in instruction
    assert "不要寫「第一步」「第二步」" in instruction
    assert "每一步" not in instruction


def test_base_persona_and_skill_file_share_the_numbering_rule():
    persona = render_base_persona()
    skill = (ROOT / PEDAGOGY_TUTOR_SKILL_PATH).read_text(encoding="utf-8")
    for text in (persona, skill):
        assert NUMBERING in text
        assert "用分步方式" not in text
