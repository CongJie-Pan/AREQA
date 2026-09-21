from pathlib import Path

from backend.services.answer_style_service import (
    AREQA_TEACHING_PROFILE_VERSION,
    PEDAGOGY_TUTOR_SKILL_ID,
    PEDAGOGY_TUTOR_SKILL_PATH,
    evidence_mode_overlays,
    learning_technique_overlays,
    render_base_persona,
    render_learnlm_teaching_rules,
    render_paper_overview_style,
    render_response_strategy_style_reminder,
    response_policy_overlays,
)
from backend.services.query_policy_service import AnswerDepth, ResponseTone


ROOT = Path(__file__).resolve().parents[2]


def test_pedagogy_tutor_skill_spec_exists_and_declares_boundaries():
    """The human-maintained pedagogy skill should stay available to reviewers."""

    skill_path = ROOT / PEDAGOGY_TUTOR_SKILL_PATH
    content = skill_path.read_text(encoding="utf-8")

    assert f"Version: `{PEDAGOGY_TUTOR_SKILL_ID}`" in content
    assert "Response Modes" in content
    assert "`REFERENCE`: Answer directly and clearly" in content
    assert "Do not override RAG or web-search citation rules" in content
    assert "Do not authorize tools or memory access" in content
    assert "subject tutor profiles are overlays" in content


def test_base_persona_exposes_versioned_style_contract():
    """Base persona should render the shared AREQA style profile."""

    prompt = render_base_persona()

    assert f"profile: {AREQA_TEACHING_PROFILE_VERSION}" in prompt
    assert f"skill: {PEDAGOGY_TUTOR_SKILL_ID}" in prompt
    assert PEDAGOGY_TUTOR_SKILL_PATH not in prompt
    assert "【回答結構與風格】" in prompt
    assert "首段先貼合本回合學習模式" in prompt
    assert "PRACTICE 先回應卡點但不代做" in prompt
    assert "不主動把答覆深度改過深" in prompt
    assert "可以適當用一些Emoji表情符號" in prompt
    assert "先講白話直覺，再補必要術語" in prompt
    assert "用分步方式降低理解負擔" in prompt


def test_policy_overlays_reuse_shared_style_contract():
    """Response-policy overlays should reuse style rules instead of redefining them."""

    overlays = response_policy_overlays()

    assert "用分步方式降低理解負擔" in overlays["SCAFFOLDED"]
    assert "先講白話直覺，再補必要術語" in overlays["TUTORING"]


def test_paper_overview_adapter_uses_same_profile_marker():
    """Paper overview style should be an adapter over the shared profile."""

    prompt = render_paper_overview_style()

    assert f"profile: {AREQA_TEACHING_PROFILE_VERSION}" in prompt
    assert "不要把回答寫成僵硬的摘要模板" in prompt
    assert "首段先貼合本回合學習模式" in prompt
    assert "先講白話直覺，再補必要術語" in prompt


def test_learnlm_rules_render_from_shared_contract():
    """PARTS LearnLM prompt rules should come from the same style contract."""

    prompt = render_learnlm_teaching_rules()

    assert "啟發主動學習" in prompt
    assert "深層元認知與反思" in prompt
    assert "支持與引導" in prompt
    assert "好奇心與情緒安全" in prompt
    assert "適應性鷹架" in prompt
    assert "learner action" not in prompt
    assert "Author/Source、Audience、Purpose、Context、Evidence、Limitation" not in prompt
    assert "圖文並茂" in prompt


def test_response_strategy_style_reminder_skips_direct_answers():
    """Direct answers should not add a tutoring-style reminder."""

    assert (
        render_response_strategy_style_reminder(
            answer_depth=AnswerDepth.DIRECT,
            tone=ResponseTone.PLAIN,
        )
        == ""
    )


def test_response_strategy_style_reminder_marks_scaffolded_profile():
    """Scaffolded answers should carry the active style profile."""

    prompt = render_response_strategy_style_reminder(
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
    )

    assert f"profile: {AREQA_TEACHING_PROFILE_VERSION}" in prompt
    assert f"skill: {PEDAGOGY_TUTOR_SKILL_ID}" in prompt
    assert "首段先貼合本回合學習模式" in prompt


def test_learning_technique_overlays_cover_prompt_templates():
    """Learning overlays should turn reusable prompt techniques into policy snippets."""

    overlays = learning_technique_overlays()

    assert "10 次" in overlays["TWENTY_HOUR_PLAN"]
    assert "費曼技巧" in overlays["FEYNMAN_LOOP"]
    assert "5 分鐘" in overlays["ONE_PAGE_NOTE"]
    assert "逐步提高難度" in overlays["DIAGNOSTIC_QUIZ"]
    assert "Level 1" in overlays["LEVEL_PATH"]
    assert "最多列 5 個" in overlays["RESOURCE_CURATOR"]


def test_evidence_mode_overlays_cover_authoritative_source_behavior():
    """Evidence overlays should preserve source strictness outside the base persona."""

    overlays = evidence_mode_overlays()

    assert "最新外部資料" in overlays["CURRENT_REQUIRED"]
    assert "官方、學術、標準文件或專業機構來源" in overlays["AUTHORITY_REQUIRED"]
    assert "至少兩個權威來源" in overlays["MULTI_SOURCE_REQUIRED"]
