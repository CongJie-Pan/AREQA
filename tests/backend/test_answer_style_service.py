from backend.services.answer_style_service import (
    AREQA_TEACHING_PROFILE_VERSION,
    render_base_persona,
    render_learnlm_teaching_rules,
    render_paper_overview_style,
    render_response_strategy_style_reminder,
    response_policy_overlays,
)
from backend.services.query_policy_service import AnswerDepth, ResponseTone


def test_base_persona_exposes_versioned_style_contract():
    """Base persona should render the shared AREQA style profile."""

    prompt = render_base_persona()

    assert f"profile: {AREQA_TEACHING_PROFILE_VERSION}" in prompt
    assert "【回答結構與風格】" in prompt
    assert "首段用1-2句話直擊問題核心" in prompt
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
    assert "首段用1-2句話直擊問題核心" in prompt
    assert "先講白話直覺，再補必要術語" in prompt


def test_learnlm_rules_render_from_shared_contract():
    """PARTS LearnLM prompt rules should come from the same style contract."""

    prompt = render_learnlm_teaching_rules()

    assert "啟發主動學習" in prompt
    assert "深層元認知與反思" in prompt
    assert "支持與引導" in prompt
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
    assert "首段用1-2句話直擊問題核心" in prompt
