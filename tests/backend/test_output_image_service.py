import pytest

from backend.services.output_image_service import OutputImageService
from backend.services.visual_answer_service import ImageBlock
from backend.services.visual_understanding_agent import VisualUnderstandingResult


class _FakeVisualAnswerService:
    """Small double for existing preflight image retrieval."""

    async def prepare_preflight_image_blocks(self, **kwargs):
        return {
            "img_1": ImageBlock(
                slot_id="img_1",
                topic="Forest plot",
                purpose="diagram",
                image_url="https://example.edu/forest.png",
                thumbnail_url="https://example.edu/forest.png",
                source_url="https://example.edu/source",
                source_domain="example.edu",
                caption="Forest plot example",
            )
        }


class _FakeUnderstandingAgent:
    """Vision-understanding double that returns deterministic analysis."""

    def __init__(self):
        self.last_kwargs = {}

    async def analyze(self, **kwargs):
        self.last_kwargs = kwargs
        return VisualUnderstandingResult(
            image_type="forest_plot",
            summary="A forest plot with confidence intervals and a summary diamond.",
            visible_elements=("95% CI", "summary diamond"),
            how_to_read=("Read the diamond as the pooled effect.",),
            confidence="high",
            source="vision_model",
        )


class _FakeVisualInputService:
    """Image input double that returns an attachment-style data URI part."""

    async def prepare_image_part(self, **kwargs):
        return type(
            "FakeVisualImageInput",
            (),
            {
                "content_part": {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AA=="},
                }
            },
        )()


@pytest.mark.asyncio
async def test_output_image_service_enriches_preflight_blocks():
    """OutputImageService should coordinate retrieval and vision understanding."""

    understanding_agent = _FakeUnderstandingAgent()
    service = OutputImageService(
        understanding_agent=understanding_agent,
        visual_input_service=_FakeVisualInputService(),
    )

    blocks = await service.prepare_preflight_image_blocks(
        visual_answer_service=_FakeVisualAnswerService(),
        user_msg="什麼是 meta analysis 統合分析",
        response_policy=None,
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=None,
        turn_plan=None,
    )

    block = blocks["img_1"]
    assert block.vision_summary.startswith("A forest plot")
    assert block.visible_elements == ("95% CI", "summary diamond")
    assert block.how_to_read == ("Read the diamond as the pooled effect.",)
    assert block.explanatory_caption == block.vision_summary
    assert understanding_agent.last_kwargs["image_part"] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AA=="},
    }
