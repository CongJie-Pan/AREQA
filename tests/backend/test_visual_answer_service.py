from types import SimpleNamespace

import pytest

from backend.services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
)
from backend.services.visual_answer_service import ImageBlock, VisualAnswerService


def _policy(task_intent=TaskIntent.GENERAL_QA):
    """Build a minimal response policy for visual service tests."""

    return ResponsePolicy(
        task_intent=task_intent,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.PLAIN,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        legacy_policy="NORMAL",
    )


def test_should_enrich_for_explain_text_policy():
    """Explain-text turns should allow visual enrichment in v1."""

    service = VisualAnswerService()

    assert service.should_enrich(_policy(TaskIntent.EXPLAIN_TEXT), "請說明森林圖")


def test_should_enrich_for_explicit_visual_request():
    """Explicit visual language should allow enrichment even for general QA."""

    service = VisualAnswerService()

    assert service.should_enrich(_policy(), "請給我一張 diagram")


def test_should_not_enrich_general_non_visual_prompt():
    """General reflective prompts should not trigger image retrieval."""

    service = VisualAnswerService()

    assert service.should_enrich(_policy(), "我在想產品定位") is False


@pytest.mark.asyncio
async def test_build_answer_blocks_interleaves_verified_images(monkeypatch, caplog):
    """Resolved images should be interleaved after early paragraphs."""

    caplog.set_level("INFO")
    service = VisualAnswerService()
    image = ImageBlock(
        slot_id="visual-1",
        topic="Forest plot",
        purpose="diagram",
        image_url="https://example.com/forest.png",
        thumbnail_url="https://example.com/forest.png",
        source_url="https://example.com/article",
        source_domain="example.com",
        caption="Forest plot example",
        license="unknown",
        safety_status="pass",
        match_confidence=0.6,
    )

    async def fake_search(**kwargs):
        return [{"url": "https://example.com/article"}]

    async def fake_resolve(results, conversation_id):
        return [image]

    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-key")
    monkeypatch.setattr(service, "_search_image_sources", fake_search)
    monkeypatch.setattr(service, "_resolve_images", fake_resolve)

    blocks = await service.build_answer_blocks(
        answer_text="第一段\n\n第二段",
        user_msg="請用圖解說明森林圖",
        response_policy=_policy(TaskIntent.EXPLAIN_TEXT),
        tool_registry=SimpleNamespace(),
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
    )

    assert [block["type"] for block in blocks] == ["paragraph", "image_block", "paragraph"]
    assert blocks[1]["sourceDomain"] == "example.com"
    assert "visual.slots_planned" in caplog.text
    assert "請用圖解" not in caplog.text
