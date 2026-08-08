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


class _DictCompletions:
    """Completion double returning dictionary/list content provider shape."""

    def __init__(self, content):
        self.content = content

    async def create(self, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": self.content,
                    }
                }
            ]
        }


class _MissingChoicesCompletions:
    """Completion double with malformed provider response."""

    async def create(self, **kwargs):
        return {"unexpected": "shape"}


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
        image_part={"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
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
        "image_url": {"url": "data:image/png;base64,AA=="},
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


@pytest.mark.asyncio
async def test_visual_understanding_agent_accepts_dict_content_parts():
    """Provider-specific response containers should not cause false failures."""

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=_DictCompletions(
                [
                    {
                        "type": "text",
                        "text": '{"image_type":"chart","summary":"A chart.","visible_elements":["axis"],"how_to_read":["Read the axis."],"limitations":[],"confidence":"medium"}',
                    }
                ]
            )
        )
    )
    agent = VisualUnderstandingAgent(timeout_seconds=1.0)

    result = await agent.analyze(
        client=client,
        model="google/gemini-3.1-flash-lite",
        image_url="https://example.edu/chart.png",
        user_msg="請解釋這張圖",
        visual_brief=None,
        conversation_id="conversation-1",
    )

    assert result.source == "vision_model"
    assert result.image_type == "chart"
    assert result.how_to_read == ("Read the axis.",)


@pytest.mark.asyncio
async def test_visual_understanding_agent_logs_provider_call_stage(caplog):
    """Provider-call failures should identify the failing stage."""

    caplog.set_level("INFO")
    agent = VisualUnderstandingAgent(timeout_seconds=1.0)

    result = await agent.analyze(
        client=SimpleNamespace(),
        model="google/gemini-3.1-flash-lite",
        image_url="https://example.edu/chart.png",
        user_msg="請解釋這張圖",
        visual_brief=None,
        conversation_id="conversation-1",
    )

    assert result.source == "provider_unavailable"
    assert "stage=provider_call" in caplog.text
    assert "reason=AttributeError" in caplog.text


@pytest.mark.asyncio
async def test_visual_understanding_agent_logs_response_extract_stage(caplog):
    """Malformed response containers should identify response extraction."""

    caplog.set_level("INFO")
    client = SimpleNamespace(chat=SimpleNamespace(completions=_MissingChoicesCompletions()))
    agent = VisualUnderstandingAgent(timeout_seconds=1.0)

    result = await agent.analyze(
        client=client,
        model="google/gemini-3.1-flash-lite",
        image_url="https://example.edu/chart.png",
        user_msg="請解釋這張圖",
        visual_brief=None,
        conversation_id="conversation-1",
    )

    assert result.source == "provider_unavailable"
    assert "stage=response_extract" in caplog.text
    assert "reason=ValueError" in caplog.text


@pytest.mark.asyncio
async def test_visual_understanding_agent_logs_client_shape(caplog):
    """Client capability logs should explain provider-call AttributeError cases."""

    caplog.set_level("INFO")
    completions = _FakeCompletions(
        '{"image_type":"chart","summary":"A chart.","visible_elements":[],"how_to_read":[],"limitations":[],"confidence":"medium"}'
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    agent = VisualUnderstandingAgent(timeout_seconds=1.0)

    await agent.analyze(
        client=client,
        model="google/gemini-3.1-flash-lite",
        image_url="https://example.edu/chart.png",
        user_msg="請解釋這張圖",
        visual_brief=None,
        conversation_id="conversation-1",
    )

    assert "visual.understanding_client_shape" in caplog.text
    assert "has_chat=True" in caplog.text
    assert "has_completions=True" in caplog.text
    assert "has_create=True" in caplog.text
