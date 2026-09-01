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


class FakeAttachmentImageStorageService:
    """Test double that marks PDF image blocks as durably persisted."""

    async def persist_pdf_image_block(self, *, block, conversation_id):
        """Return a signed-url block without touching external storage."""

        return type(block)(
            slot_id=block.slot_id,
            topic=block.topic,
            purpose=block.purpose,
            image_url="https://example.supabase.co/storage/v1/object/sign/bucket/path?token=abc",
            thumbnail_url="https://example.supabase.co/storage/v1/object/sign/bucket/path?token=abc",
            source_url=block.source_url,
            source_domain=block.source_domain,
            caption=block.caption,
            provider=block.provider,
            license=block.license,
            license_url=block.license_url,
            creator=block.creator,
            attribution_string=block.attribution_string,
            attribution_caption=block.attribution_caption,
            explanatory_caption=block.explanatory_caption,
            width=block.width,
            height=block.height,
            safety_status=block.safety_status,
            match_confidence=block.match_confidence,
            heuristic_score=block.heuristic_score,
            pedagogical_score=block.pedagogical_score,
            vision_summary=block.vision_summary,
            visible_elements=block.visible_elements,
            how_to_read=block.how_to_read,
            vision_confidence=block.vision_confidence,
            vision_limitations=block.vision_limitations,
            vision_source=block.vision_source,
            storage_bucket="bucket",
            storage_path="path",
            storage_expires_at=1234567890,
            transient=False,
        )


@dataclass
class UnavailableUnderstandingAgent:
    """Test double that simulates an unavailable PDF vision model."""

    async def analyze(self, **kwargs):
        """Return a non-usable vision result without raising."""

        return VisualUnderstandingResult(source="provider_unavailable")


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
        answer_section="實驗結果與關鍵數據",
        visual_type="results_table",
        teaching_caption="這張表呈現 BLEU 結果，是理解論文實驗主張的關鍵。",
    )


def make_candidate_with_slot(slot_id: str, page_number: int) -> PdfVisualCandidate:
    """Build one request-scoped PDF visual candidate with a custom slot."""

    candidate = make_candidate()
    return PdfVisualCandidate(
        slot_id=slot_id,
        filename=candidate.filename,
        page_number=page_number,
        image_data_uri=candidate.image_data_uri,
        width=candidate.width,
        height=candidate.height,
        caption_hint=f"Figure {page_number}. Paper visual",
        visual_score=candidate.visual_score,
        sha256=f"sha-{page_number}",
        answer_section=candidate.answer_section,
        visual_type=candidate.visual_type,
        teaching_caption=candidate.teaching_caption,
    )


@pytest.mark.asyncio
async def test_prepare_attachment_image_blocks_uses_pdf_candidate_and_vision():
    """PDF attachment candidates become understood image blocks."""

    service = OutputImageService(
        understanding_agent=FakeUnderstandingAgent(),
        attachment_image_storage_service=FakeAttachmentImageStorageService(),
    )

    blocks = await service.prepare_attachment_image_blocks(
        candidates=[make_candidate()],
        user_msg="Explain the paper figure.",
        conversation_id="conversation-1",
        model_client=object(),
    )

    block = blocks["pdf_img_1"]
    payload = block.to_frontend()

    assert payload["provider"] == "pdf_attachment"
    assert payload["imageUrl"].startswith("https://example.supabase.co/")
    assert payload["sourceDomain"] == "uploaded PDF"
    assert payload["visionSource"] == "vision_model"
    assert payload["visionSummary"] == "A line chart is visible on the PDF page."
    assert payload["purpose"] == "results_table"
    assert "實驗結果" in payload["explanatoryCaption"]
    assert "BLEU" in payload["explanatoryCaption"]
    assert payload["storageBucket"] == "bucket"
    assert payload["storagePath"] == "path"
    assert payload["storageExpiresAt"] == 1234567890
    assert "transient" not in payload


@pytest.mark.asyncio
async def test_prepare_attachment_image_blocks_keeps_pdf_candidate_when_vision_unavailable(caplog):
    """PDF attachment visuals should fail soft when vision analysis is unavailable."""

    caplog.set_level("INFO")
    service = OutputImageService(
        understanding_agent=UnavailableUnderstandingAgent(),
        attachment_image_storage_service=FakeAttachmentImageStorageService(),
    )

    blocks = await service.prepare_attachment_image_blocks(
        candidates=[make_candidate()],
        user_msg="Explain the paper figure.",
        conversation_id="conversation-1",
        model_client=object(),
    )

    block = blocks["pdf_img_1"]
    payload = block.to_frontend()

    assert payload["provider"] == "pdf_attachment"
    assert payload["imageUrl"].startswith("https://example.supabase.co/")
    assert "visionSource" not in payload
    assert "visionSummary" not in payload
    assert "visual.attachment_understanding_failed_soft" in caplog.text
    assert "slot_id=pdf_img_1" in caplog.text


@pytest.mark.asyncio
async def test_prepare_attachment_image_blocks_accepts_four_pdf_candidates():
    """Paper auto-explain should be able to pass four verified PDF visuals."""

    service = OutputImageService(
        understanding_agent=FakeUnderstandingAgent(),
        attachment_image_storage_service=FakeAttachmentImageStorageService(),
    )

    blocks = await service.prepare_attachment_image_blocks(
        candidates=[
            make_candidate_with_slot("pdf_img_1", 1),
            make_candidate_with_slot("pdf_img_2", 2),
            make_candidate_with_slot("pdf_img_3", 3),
            make_candidate_with_slot("pdf_img_4", 4),
        ],
        user_msg="Explain the paper figure.",
        conversation_id="conversation-1",
        model_client=object(),
    )

    assert list(blocks) == ["pdf_img_1", "pdf_img_2", "pdf_img_3", "pdf_img_4"]
