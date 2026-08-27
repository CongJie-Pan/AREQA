"""Regression tests for stable visual-output understanding retries."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.services.output_image_service import OutputImageService
from backend.services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualReason,
    VisualSupport,
)
from backend.services.visual_answer_service import ImageBlock
from backend.services.visual_input_service import VisualImageInput
from backend.services.visual_understanding_agent import VisualUnderstandingResult


def _image_block(*, slot_id: str, image_url: str, alternative_blocks=()) -> ImageBlock:
    """Build one provider image block for output retry tests."""

    return ImageBlock(
        slot_id=slot_id,
        topic="mRNA vaccine diagram",
        purpose="diagram",
        image_url=image_url,
        thumbnail_url=image_url,
        source_url=f"{image_url}/source",
        source_domain=image_url.removeprefix("https://").split("/", 1)[0],
        caption="mRNA vaccine process diagram",
        provider="tavily_images",
        license="unknown",
        safety_status="pass",
        match_confidence=0.8,
        cache_key="visual_image:v6:preflight:key",
        cache_ttl_seconds=300,
        alternative_blocks=tuple(alternative_blocks),
    )


class FakeVisualAnswerService:
    """Return one blocked image and one usable fallback image."""

    def __init__(self) -> None:
        """Initialize captured cache commits."""

        self.committed_blocks: list[ImageBlock] = []

    async def prepare_preflight_image_blocks(self, **kwargs):
        """Return a primary image with one fallback candidate."""

        fallback = _image_block(slot_id="img_1", image_url="https://stable.example.org/fallback.png")
        primary = _image_block(
            slot_id="img_1",
            image_url="https://blocked.example.org/primary.png",
            alternative_blocks=(fallback,),
        )
        return {"img_1": primary}

    async def commit_positive_cache(self, block: ImageBlock, *, conversation_id: str) -> None:
        """Capture cache commits for assertion."""

        self.committed_blocks.append(block)


class FakeVisualInputService:
    """Return a 403-like input failure first, then a valid data URI."""

    timeout_seconds = 0.1

    async def prepare_image_part(self, *, image_url: str, conversation_id: str):
        """Return deterministic input outcomes by URL."""

        if "blocked.example.org" in image_url:
            return VisualImageInput(
                content_part={"type": "image_url", "image_url": {"url": image_url}},
                source="remote_url",
                reason="HTTPStatusError:403",
            )
        return VisualImageInput(
            content_part={"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
            source="data_uri",
            media_type="image/png",
            size_bytes=8,
        )


@dataclass
class FakeUnderstandingAgent:
    """Return usable vision evidence for data URI fallback candidates."""

    timeout_seconds: float = 0.1

    async def analyze(self, **kwargs):
        """Return deterministic usable vision evidence."""

        return VisualUnderstandingResult(
            image_type="diagram",
            summary="A diagram explains mRNA vaccine entry and translation.",
            visible_elements=("lipid nanoparticle", "ribosome"),
            how_to_read=("Follow the arrows from cell entry to protein production.",),
            confidence="high",
            source="vision_model",
        )


def _policy() -> ResponsePolicy:
    """Build a visual-enabled response policy."""

    return ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        visual_support=VisualSupport.OPTIONAL,
        visual_reason=VisualReason.KNOWLEDGE_EXPLANATION,
    )


@pytest.mark.asyncio
async def test_output_understanding_retries_fallback_candidate_and_commits_only_success(caplog):
    """A blocked selected image should not make the whole turn lose visuals."""

    caplog.set_level("INFO")
    visual_answer_service = FakeVisualAnswerService()
    output_service = OutputImageService(
        understanding_agent=FakeUnderstandingAgent(),
        visual_input_service=FakeVisualInputService(),
    )

    blocks = await output_service.prepare_preflight_image_blocks(
        visual_answer_service=visual_answer_service,
        user_msg="How does an mRNA vaccine work?",
        response_policy=_policy(),
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="user-1",
        conversation_id="conversation-1",
        model_client=object(),
    )

    block = blocks["img_1"]
    assert block.image_url == "https://stable.example.org/fallback.png"
    assert block.vision_source == "vision_model"
    assert len(visual_answer_service.committed_blocks) == 1
    assert visual_answer_service.committed_blocks[0].image_url == block.image_url
    assert "visual.output_candidate_retry" in caplog.text
    assert "visual.output_candidate_retry_succeeded" in caplog.text
