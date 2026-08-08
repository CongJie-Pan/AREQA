from types import SimpleNamespace

import pytest

from backend.services.visual_grounding_agent import VisualBrief
from backend.services.visual_understanding_agent import VisualUnderstandingAgent


class _FakeCompletions:
    """OpenAI-compatible completion double that records multimodal payloads."""

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


@pytest.mark.asyncio
async def test_visual_understanding_agent_sends_image_url_content_part():
    """The understanding agent should send the selected image itself to the model."""

    completions = _FakeCompletions(
        """
        {
          "image_type": "forest_plot",
          "summary": "The image is an annotated forest plot.",
          "visible_elements": ["null line OR=1", "95% CI", "summary diamond"],
          "how_to_read": ["Start with the null line.", "Compare intervals with the line."],
          "limitations": [],
          "confidence": "high"
        }
        """
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = VisualUnderstandingAgent(timeout_seconds=1.0)

    result = await agent.analyze(
        client=client,
        model="google/gemini-3.1-flash-lite",
        image_url="https://example.edu/forest-plot.webp",
        user_msg="什麼是 meta analysis 統合分析",
        visual_brief=VisualBrief(
            visual_type="forest_plot",
            search_query="meta analysis forest plot diagram",
            caption_goal="Help the learner read a forest plot.",
            reject_if=("not_meta_analysis",),
        ),
        conversation_id="conversation-1",
    )

    content = completions.last_kwargs["messages"][1]["content"]
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.edu/forest-plot.webp"},
    }
    assert result.image_type == "forest_plot"
    assert "summary diamond" in result.visible_elements
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_visual_understanding_agent_invalid_image_url_fails_soft():
    """Invalid image URLs should not trigger model calls or block image display."""

    completions = _FakeCompletions("{}")
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = VisualUnderstandingAgent(timeout_seconds=1.0)

    result = await agent.analyze(
        client=client,
        model="google/gemini-3.1-flash-lite",
        image_url="file:///tmp/private.png",
        user_msg="請解釋這張圖",
        visual_brief=None,
        conversation_id="conversation-1",
    )

    assert completions.last_kwargs is None
    assert result.source == "invalid_image_url"
