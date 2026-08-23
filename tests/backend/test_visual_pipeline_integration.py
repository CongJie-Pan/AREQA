"""Opt-in integration tests for the live output-image pipeline.

These tests intentionally call external image providers and OpenRouter vision
models. They are skipped by default because they depend on live credentials,
network availability, provider rate limits, and paid model calls. Run them only
when validating production-like visual behavior.
"""

from __future__ import annotations

import os
from pathlib import Path
import uuid
import logging

from openai import AsyncOpenAI
import pytest
from dotenv import load_dotenv

# httpx INFO logs include full request URLs, and some provider APIs carry keys
# in query parameters. Keep this opt-in test debuggable through AREQA's own
# structured visual logs without exposing credentials in pytest output.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from backend.services.output_image_service import OutputImageService
from backend.services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
)
from backend.services.visual_answer_service import VisualAnswerService


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VISUAL_PIPELINE_INTEGRATION") != "1",
    reason="set RUN_VISUAL_PIPELINE_INTEGRATION=1 to call live visual APIs",
)


def _live_api_requirements_available() -> bool:
    """Return whether the live visual pipeline has enough credentials to run.

    Returns:
        ``True`` when OpenRouter and at least one configured image-search
        provider credential are present. Wikimedia/Openverse can be anonymous,
        but requiring one keyed provider keeps this integration test closer to
        the deployed production path.

    Side Effects:
        None. The helper reads environment variable presence only and never
        returns or logs credential values.
    """

    has_openrouter = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    has_image_provider = any(
        os.environ.get(name, "").strip()
        for name in (
            "SERPAPI_API_KEY",
            "TAVILY_API_KEY",
            "PERPLEXITY_API_KEY",
        )
    )
    return has_openrouter and has_image_provider


@pytest.mark.asyncio
async def test_live_mrna_question_image_pipeline_returns_vision_grounded_image():
    """Run the real visual pipeline for an mRNA vaccine question only.

    The test exercises the production image path without requesting a complete
    assistant answer: visual planning, provider image retrieval, grounding,
    selected-image download, data-URI conversion, and vision understanding.
    It intentionally fails if no image survives the current grounding and
    understanding gates, because that is the user-visible failure this
    integration test is meant to catch.
    """

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    if not _live_api_requirements_available():
        pytest.skip("live visual pipeline credentials are not configured")

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        structure=ResponseStructure.STEP_BY_STEP,
        tone=ResponseTone.TUTORING,
        followup_mode=FollowupMode.OPTIONAL,
    )

    blocks = await OutputImageService().prepare_preflight_image_blocks(
        visual_answer_service=VisualAnswerService(redis_factory=lambda *args, **kwargs: None),
        user_msg="mRNA疫苗如何抵抗病毒，其過程為何 ?",
        response_policy=response_policy,
        existing_web_results=[],
        tool_registry=None,
        tool_budget=None,
        user_id="integration-user",
        conversation_id=f"integration-visual-{uuid.uuid4().hex}",
        model_client=client,
        turn_plan=None,
    )

    assert blocks, "live visual pipeline returned no image blocks"
    block = next(iter(blocks.values()))
    frontend_payload = block.to_frontend()

    assert frontend_payload["type"] == "image_block"
    assert frontend_payload["status"] == "resolved"
    assert block.image_url.startswith(("http://", "https://"))
    assert block.thumbnail_url.startswith(("http://", "https://"))
    assert block.source_url.startswith(("http://", "https://"))
    assert block.source_domain
    assert block.provider
    assert block.vision_source == "vision_model"
    assert block.vision_summary.strip()
    assert block.visible_elements or block.how_to_read
