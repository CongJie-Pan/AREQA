from types import SimpleNamespace

import pytest

from backend.services.visual_answer_service import ImageCandidate
from backend.services.visual_grounding_agent import VisualBrief, VisualGroundingAgent


class _FakeCompletions:
    """OpenAI-compatible completion double for grounding tests."""

    def __init__(self, content: str):
        self.content = content
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content),
                )
            ]
        )


def _candidate() -> ImageCandidate:
    """Build a candidate with metadata safe for model grounding."""

    return ImageCandidate(
        provider="wikimedia",
        image_url="https://upload.wikimedia.org/example.png",
        thumbnail_url="https://upload.wikimedia.org/thumb.png",
        source_url="https://commons.wikimedia.org/wiki/File:Example.png",
        title="World War II aircraft",
        caption="A military aircraft photo",
        license="CC BY 2.0",
        width=900,
        height=500,
    )


@pytest.mark.asyncio
async def test_visual_grounding_agent_returns_json_decision_without_logging_raw_intent(caplog):
    """Grounding agent should parse model JSON and keep logs privacy-safe."""

    caplog.set_level("INFO")
    completions = _FakeCompletions(
        """
        {"accepted": false, "expected_visual_type": "map", "candidate_visual_type": "aircraft_photo", "reason": "visual_type_mismatch"}
        """
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = VisualGroundingAgent(timeout_seconds=1.0)

    decision = await agent.evaluate(
        client=client,
        model="test-model",
        visual_intent="private raw visual intent: show the Pacific War map",
        candidate=_candidate(),
        conversation_id="conversation-1",
    )

    assert decision.accepted is False
    assert decision.expected_visual_type == "map"
    assert decision.candidate_visual_type == "aircraft_photo"
    assert decision.reason == "visual_type_mismatch"
    assert completions.last_kwargs["model"] == "test-model"
    assert "visual.grounding_checked" in caplog.text
    assert "private raw visual intent" not in caplog.text
    assert "https://commons.wikimedia.org" not in caplog.text


@pytest.mark.asyncio
async def test_visual_grounding_agent_sends_domain_instead_of_full_source_url():
    """Grounding prompt should include useful source context without full URLs."""

    completions = _FakeCompletions('{"accepted": true, "expected_visual_type": "photo", "candidate_visual_type": "photo", "reason": "purpose_match"}')
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = VisualGroundingAgent(timeout_seconds=1.0)

    await agent.evaluate(
        client=client,
        model="test-model",
        visual_intent="show a photo",
        candidate=_candidate(),
        conversation_id="conversation-1",
    )

    user_message = completions.last_kwargs["messages"][1]["content"]
    assert "commons.wikimedia.org" in user_message
    assert "https://commons.wikimedia.org/wiki/File:Example.png" not in user_message


@pytest.mark.asyncio
async def test_visual_grounding_agent_plans_visual_brief_without_logging_raw_question(caplog):
    """Visual planning should produce a generic brief before image retrieval."""

    caplog.set_level("INFO")
    completions = _FakeCompletions(
        """
        {
          "visual_type": "map",
          "search_query": "Pacific War map Japanese expansion 1941 1945",
          "caption_goal": "Help the learner see Japan's expansion and retreat geographically.",
          "reject_if": ["book_cover", "document_scan", "portrait"]
        }
        """
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = VisualGroundingAgent(timeout_seconds=1.0)

    brief = await agent.plan(
        client=client,
        model="test-model",
        user_msg="private raw question about World War II Japan",
        fallback_query="World War II Japan",
        conversation_id="conversation-1",
    )

    assert brief.visual_type == "map"
    assert brief.search_query == "Pacific War map Japanese expansion 1941 1945"
    assert "document_scan" in brief.reject_if
    assert "visual.brief_planned" in caplog.text
    assert "private raw question" not in caplog.text


@pytest.mark.asyncio
async def test_visual_grounding_agent_includes_visual_brief_in_grounding_prompt():
    """Grounding should judge candidates against the planned visual brief."""

    completions = _FakeCompletions(
        '{"accepted": false, "expected_visual_type": "map", "candidate_visual_type": "document", "reason": "visual_type_mismatch"}'
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = VisualGroundingAgent(timeout_seconds=1.0)

    await agent.evaluate(
        client=client,
        model="test-model",
        visual_intent="Pacific War map Japanese expansion 1941 1945",
        visual_brief=VisualBrief(
            visual_type="map",
            search_query="Pacific War map Japanese expansion 1941 1945",
            caption_goal="Show the geography of the Pacific War.",
            reject_if=("document_scan", "book_cover"),
        ),
        candidate=_candidate(),
        conversation_id="conversation-1",
    )

    user_message = completions.last_kwargs["messages"][1]["content"]
    assert '"visual_type": "map"' in user_message
    assert "document_scan" in user_message
