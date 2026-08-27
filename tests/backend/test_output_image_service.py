import asyncio

import pytest

from backend.services.output_image_service import OutputImageService
from backend.services.visual_answer_service import ImageBlock
from backend.services.visual_understanding_agent import VisualUnderstandingResult


class _FakeVisualAnswerService:
    """Small double for existing preflight image retrieval."""

    def __init__(
        self,
        *,
        image_url="https://example.edu/forest.png",
        thumbnail_url="https://example.edu/forest.png",
    ):
        self.image_url = image_url
        self.thumbnail_url = thumbnail_url

    async def prepare_preflight_image_blocks(self, **kwargs):
        return {
            "img_1": ImageBlock(
                slot_id="img_1",
                topic="Forest plot",
                purpose="diagram",
                image_url=self.image_url,
                thumbnail_url=self.thumbnail_url,
                source_url="https://example.edu/source",
                source_domain="example.edu",
                caption="Forest plot example",
            )
        }

    async def commit_positive_cache(self, block, *, conversation_id):
        """Match VisualAnswerService's cache write contract without persistence."""
        self.cached_block = block
        self.cache_conversation_id = conversation_id


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

    def __init__(self):
        self.image_urls = []

    async def prepare_image_part(self, **kwargs):
        self.image_urls.append(kwargs["image_url"])
        return type(
            "FakeVisualImageInput",
            (),
            {
                "content_part": {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AA=="},
                },
                "source": "data_uri",
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
    assert block.explanatory_caption == ""
    assert understanding_agent.last_kwargs["image_part"] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AA=="},
    }


@pytest.mark.asyncio
async def test_output_image_service_uses_python_310_compatible_timeout(monkeypatch):
    """Render deploys Python 3.10, where asyncio.timeout is unavailable."""

    monkeypatch.delattr(asyncio, "timeout", raising=False)
    service = OutputImageService(
        understanding_agent=_FakeUnderstandingAgent(),
        visual_input_service=_FakeVisualInputService(),
    )

    blocks = await service.prepare_preflight_image_blocks(
        visual_answer_service=_FakeVisualAnswerService(),
        user_msg="Compare frequentist and Bayesian statistics",
        response_policy=None,
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=None,
        turn_plan=None,
    )

    assert blocks["img_1"].vision_summary.startswith("A forest plot")


@pytest.mark.asyncio
async def test_output_image_service_retries_distinct_thumbnail_after_unavailable_original():
    """A readable thumbnail should recover vision understanding for the same image."""

    class _RetryingUnderstandingAgent:
        def __init__(self):
            self.image_urls = []

        async def analyze(self, **kwargs):
            self.image_urls.append(kwargs["image_url"])
            if len(self.image_urls) == 1:
                return VisualUnderstandingResult(source="provider_unavailable")
            return VisualUnderstandingResult(
                image_type="comparison_chart",
                summary="The chart compares fixed and random parameter assumptions.",
                visible_elements=("Frequentism panel", "Bayesian statistics panel"),
                how_to_read=("Compare the parameter row from left to right.",),
                confidence="high",
                source="vision_model",
            )

    input_service = _FakeVisualInputService()
    understanding_agent = _RetryingUnderstandingAgent()
    service = OutputImageService(
        understanding_agent=understanding_agent,
        visual_input_service=input_service,
    )

    blocks = await service.prepare_preflight_image_blocks(
        visual_answer_service=_FakeVisualAnswerService(
            image_url="https://blocked.example/original.png",
            thumbnail_url="https://cdn.example/thumbnail.png",
        ),
        user_msg="Compare frequentist and Bayesian statistics",
        response_policy=None,
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=None,
        turn_plan=None,
    )

    assert blocks["img_1"].vision_summary.startswith("The chart compares")
    assert input_service.image_urls == [
        "https://blocked.example/original.png",
        "https://cdn.example/thumbnail.png",
    ]
    assert understanding_agent.image_urls == input_service.image_urls


@pytest.mark.asyncio
async def test_output_image_service_skips_remote_url_input_and_retries_thumbnail(caplog):
    """Remote URL fallbacks should not be sent to vision providers."""

    class _FallbackThenDataUriInputService:
        def __init__(self):
            self.image_urls = []

        async def prepare_image_part(self, **kwargs):
            self.image_urls.append(kwargs["image_url"])
            source = "remote_url" if len(self.image_urls) == 1 else "data_uri"
            url = kwargs["image_url"] if source == "remote_url" else "data:image/png;base64,AA=="
            return type(
                "FakeVisualImageInput",
                (),
                {
                    "content_part": {"type": "image_url", "image_url": {"url": url}},
                    "source": source,
                },
            )()

    class _RecordingUnderstandingAgent(_FakeUnderstandingAgent):
        def __init__(self):
            super().__init__()
            self.image_urls = []

        async def analyze(self, **kwargs):
            self.image_urls.append(kwargs["image_url"])
            return await super().analyze(**kwargs)

    caplog.set_level("INFO")
    input_service = _FallbackThenDataUriInputService()
    understanding_agent = _RecordingUnderstandingAgent()
    service = OutputImageService(
        understanding_agent=understanding_agent,
        visual_input_service=input_service,
    )

    blocks = await service.prepare_preflight_image_blocks(
        visual_answer_service=_FakeVisualAnswerService(
            image_url="https://blocked.example/original.png",
            thumbnail_url="https://cdn.example/thumbnail.png",
        ),
        user_msg="Compare frequentist and Bayesian statistics",
        response_policy=None,
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=None,
        turn_plan=None,
    )

    assert blocks["img_1"].vision_summary.startswith("A forest plot")
    assert input_service.image_urls == [
        "https://blocked.example/original.png",
        "https://cdn.example/thumbnail.png",
    ]
    assert understanding_agent.image_urls == ["https://cdn.example/thumbnail.png"]
    assert "visual.output_understanding_input_unavailable" in caplog.text


@pytest.mark.asyncio
async def test_output_image_service_omits_block_when_all_understanding_attempts_fail(caplog):
    """Selected images must not reach the answer model without usable vision evidence."""

    class _UnavailableUnderstandingAgent:
        async def analyze(self, **kwargs):
            return VisualUnderstandingResult(source="provider_unavailable")

    caplog.set_level("INFO")
    service = OutputImageService(
        understanding_agent=_UnavailableUnderstandingAgent(),
        visual_input_service=_FakeVisualInputService(),
    )

    blocks = await service.prepare_preflight_image_blocks(
        visual_answer_service=_FakeVisualAnswerService(
            image_url="https://blocked.example/original.png",
            thumbnail_url="https://blocked.example/thumbnail.png",
        ),
        user_msg="Compare frequentist and Bayesian statistics",
        response_policy=None,
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=None,
        turn_plan=None,
    )

    assert blocks == {}
    assert "visual.output_image_omitted" in caplog.text
    assert "reason=understanding_unavailable" in caplog.text
    assert "selected_image_count=1" in caplog.text
    assert "understood_image_count=0" in caplog.text
    assert "omitted_image_count=1" in caplog.text


@pytest.mark.asyncio
async def test_output_image_service_bounds_all_understanding_attempts_to_shared_budget(
    monkeypatch,
    caplog,
):
    """Original and thumbnail attempts must share one foreground latency budget."""

    class _SlowVisualInputService:
        async def prepare_image_part(self, **kwargs):
            await asyncio.sleep(0.05)
            raise AssertionError("shared budget should cancel the slow input")

    caplog.set_level("INFO")
    service = OutputImageService(
        understanding_agent=_FakeUnderstandingAgent(),
        visual_input_service=_SlowVisualInputService(),
    )
    monkeypatch.setattr(service, "_understanding_budget_seconds", lambda: 0.01)

    blocks = await service.prepare_preflight_image_blocks(
        visual_answer_service=_FakeVisualAnswerService(
            image_url="https://slow.example/original.png",
            thumbnail_url="https://slow.example/thumbnail.png",
        ),
        user_msg="Compare frequentist and Bayesian statistics",
        response_policy=None,
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=None,
        turn_plan=None,
    )

    assert blocks == {}
    assert "visual.output_understanding_budget_exhausted" in caplog.text
    assert "budget_seconds=0.0" in caplog.text


def test_output_image_service_preserves_only_explicit_explanatory_caption():
    """Vision analysis must not replace reviewed user-facing caption copy."""

    original = ImageBlock(
        slot_id="img_1",
        topic="Forest plot",
        purpose="diagram",
        image_url="https://example.edu/forest.png",
        thumbnail_url="https://example.edu/forest.png",
        source_url="https://example.edu/source",
        source_domain="example.edu",
        caption="Forest plot example",
        explanatory_caption="這張圖呈現各研究的效果量。",
    )
    result = VisualUnderstandingResult(summary="An internal English summary.", source="vision_model")

    enriched = OutputImageService._apply_understanding(original, result)

    assert enriched.explanatory_caption == "這張圖呈現各研究的效果量。"
    assert enriched.vision_summary == "An internal English summary."
