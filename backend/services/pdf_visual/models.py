"""Data contracts for PDF visual extraction.

``PdfVisualCandidate`` is re-exported from
``services.pdf_visual_extraction_service`` for compatibility. The frontend image
block conversion is part of the attachment visual contract and should change
only with coordinated tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.pdf_visual.constants import PDF_ATTACHMENT_IMAGE_PROVIDER, PDF_ATTACHMENT_SOURCE_DOMAIN
from services.visual_answer_service import ImageBlock

@dataclass(frozen=True, slots=True)
class PdfVisualCandidate:
    """One rendered PDF page candidate that can become an answer image.

    Args:
        slot_id: Stable slot identifier used by answer marker handling.
        filename: Sanitized display filename from the upload.
        page_number: One-based PDF page number.
        image_data_uri: PNG data URI for current-turn rendering/model input.
        width: Rendered PNG width in pixels.
        height: Rendered PNG height in pixels.
        caption_hint: Nearby visible text or generated page label.
        visual_score: Cheap page-level score from PDF drawings/images/caption
            hints. Higher values are selected first.
        sha256: SHA-256 of the rendered PNG bytes for deduplication and logs.
        crop_applied: Whether the image is a clipped figure region instead of
            a full-page thumbnail.
        crop_reason: Safe reason code explaining the crop decision.
        answer_section: Paper-explanation section where the main answer should
            introduce this visual.
        visual_type: Planner-selected visual purpose.
        target_caption: Planner-selected figure/table caption text used only for
            deterministic crop provenance.
        teaching_caption: Planner-authored explanation that may be shown to the
            user and passed to the main answer model.
        planner_rationale: Safe bounded reason for selection.
        selection_source: ``planner``/``fallback``/``heuristic`` source label.
        visual_quality_score: Deterministic geometry-only quality estimate for
            the rendered PDF visual. Higher means the image is more likely to
            be complete and useful.
        visual_quality_reason: Stable reason code for the quality decision.

    Returns:
        Immutable request-scoped candidate metadata.

    Side Effects:
        None.
    """

    slot_id: str
    filename: str
    page_number: int
    image_data_uri: str
    width: int
    height: int
    caption_hint: str
    visual_score: int
    sha256: str
    crop_applied: bool = False
    crop_reason: str = "full_page_fallback"
    answer_section: str = ""
    visual_type: str = "chart"
    target_caption: str = ""
    teaching_caption: str = ""
    planner_rationale: str = ""
    selection_source: str = "heuristic"
    visual_quality_score: float = 0.0
    visual_quality_reason: str = "unknown"

    def to_image_block(self) -> ImageBlock:
        """Convert the candidate into the existing frontend image block shape.

        Returns:
            ``ImageBlock`` with a data URI image and PDF attachment attribution.

        Side Effects:
            None.
        """

        topic = f"{self.filename} 第 {self.page_number} 頁"
        caption = (
            self.target_caption
            or self.caption_hint
            or f"上傳 PDF 第 {self.page_number} 頁的圖像內容"
        )
        vision_limitations = ()
        if self.visual_quality_reason.endswith("quality_fallback"):
            vision_limitations = ("PDF 圖表裁切品質不足，系統改用較完整的頁面截圖。",)
        return ImageBlock(
            slot_id=self.slot_id,
            topic=topic,
            purpose=self.visual_type or "chart",
            image_url=self.image_data_uri,
            thumbnail_url=self.image_data_uri,
            source_url=f"#pdf-attachment-page-{self.page_number}",
            source_domain=PDF_ATTACHMENT_SOURCE_DOMAIN,
            caption=caption,
            provider=PDF_ATTACHMENT_IMAGE_PROVIDER,
            license="user_provided_attachment",
            attribution_caption=f"{self.filename}，第 {self.page_number} 頁",
            explanatory_caption="",
            width=self.width,
            height=self.height,
            safety_status="pass",
            match_confidence=min(0.96, max(0.55, self.visual_quality_score)),
            heuristic_score=min(1.0, max(self.visual_quality_score, 0.5 + (self.visual_score / 20))),
            pedagogical_score=min(1.0, max(self.visual_quality_score, 0.55 + (self.visual_score / 20))),
            vision_limitations=vision_limitations,
            vision_source="unavailable",
            placement_section=self.answer_section,
            planner_hint=self.teaching_caption,
            transient=True,
        )


@dataclass(frozen=True, slots=True)
class _PdfCropChoice:
    """Geometry-only crop decision selected before rendering pixels.

    Args:
        clip: Optional PyMuPDF rectangle. ``None`` means render the full page.
        crop_applied: Whether the rendered PNG is clipped.
        crop_reason: Stable renderer reason code.
        quality_score: Conservative score derived from crop geometry only.
        quality_reason: Stable reason code explaining why this crop was chosen.

    Side Effects:
        None.
    """

    clip: Any | None
    crop_applied: bool
    crop_reason: str
    quality_score: float
    quality_reason: str
