"""Tests for converting PDF attachment visuals into answer image blocks."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.services.output_image_service import OutputImageService
from backend.services.pdf_visual_extraction_service import PdfVisualCandidate
from backend.services.visual_understanding_agent import VisualUnderstandingResult


@dataclass
class FakeUnderstandingAgent:
    """Test double that returns bounded vision evidence for PDF data URIs."""

    async def analyze(self, **kwargs):
        """Return deterministic vision output for the selected PDF image."""

        return VisualUnderstandingResult(
            image_type="chart",
            summary="A line chart is visible on the PDF page.",
            visible_elements=("x-axis", "line series"),
            how_to_read=("Read the x-axis first.",),
            confidence="high",
            source="vision_model",
        )


def make_candidate() -> PdfVisualCandidate:
    """Build one small request-scoped PDF visual candidate."""

    return PdfVisualCandidate(
        slot_id="pdf_img_1",
        filename="paper.pdf",
        page_number=3,
        image_data_uri="data:image/png;base64,iVBORw0KGgo=",
        width=640,
        height=480,
        caption_hint="Figure 2. Result chart",
        visual_score=8,
        sha256="abc123",
    )


@pytest.mark.asyncio
async def test_prepare_attachment_image_blocks_uses_pdf_candidate_and_vision():
    """PDF attachment candidates become understood image blocks."""

    service = OutputImageService(understanding_agent=FakeUnderstandingAgent())

    blocks = await service.prepare_attachment_image_blocks(
        candidates=[make_candidate()],
        user_msg="Explain the paper figure.",
        conversation_id="conversation-1",
        model_client=object(),
    )

    block = blocks["pdf_img_1"]
    payload = block.to_frontend()

    assert payload["provider"] == "pdf_attachment"
    assert payload["imageUrl"].startswith("data:image/png;base64,")
    assert payload["sourceDomain"] == "uploaded PDF"
    assert payload["visionSource"] == "vision_model"
    assert payload["visionSummary"] == "A line chart is visible on the PDF page."
    assert payload["transient"] is True
