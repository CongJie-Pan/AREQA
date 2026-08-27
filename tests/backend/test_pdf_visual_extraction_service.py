"""Tests for local PDF page visual extraction."""

from __future__ import annotations

import pytest

from backend.services.pdf_visual_extraction_service import PdfVisualExtractionService


fitz = pytest.importorskip("fitz")


def make_visual_pdf() -> bytes:
    """Create a tiny PDF containing visible figure-like vector content."""

    document = fitz.open()
    page = document.new_page(width=320, height=240)
    page.insert_text((36, 36), "Figure 1. Accuracy by epoch", fontsize=12)
    page.draw_rect(fitz.Rect(40, 70, 280, 190), color=(0, 0, 0), width=1)
    page.draw_line((60, 170), (120, 130), color=(0, 0, 1), width=2)
    page.draw_line((120, 130), (180, 110), color=(0, 0, 1), width=2)
    page.draw_line((180, 110), (250, 82), color=(0, 0, 1), width=2)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def test_extract_candidates_renders_pdf_page_visual():
    """A vector chart page is rendered as a transient PNG data URI candidate."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1, render_zoom=1.0)

    candidates = service.extract_candidates(
        pdf_bytes=make_visual_pdf(),
        filename="paper.pdf",
        conversation_id="conversation-1",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    block = candidate.to_image_block().to_frontend()

    assert candidate.page_number == 1
    assert candidate.image_data_uri.startswith("data:image/png;base64,")
    assert "Figure 1" in candidate.caption_hint
    assert block["provider"] == "pdf_attachment"
    assert block["transient"] is True
