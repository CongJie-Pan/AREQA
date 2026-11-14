"""Tests for local PDF page visual extraction."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image
import pytest

from backend.services.pdf_visual_extraction_service import PdfVisualExtractionService


fitz = pytest.importorskip("fitz")


def make_visual_pdf() -> bytes:
    """Create a tiny PDF containing visible figure-like vector content."""

    document = fitz.open()
    page = document.new_page(width=320, height=240)
    page.insert_text((36, 30), "This paragraph should not appear in the figure crop.", fontsize=9)
    page.draw_rect(fitz.Rect(40, 70, 280, 190), color=(0, 0, 0), width=1)
    page.draw_line((60, 170), (120, 130), color=(0, 0, 1), width=2)
    page.draw_line((120, 130), (180, 110), color=(0, 0, 1), width=2)
    page.draw_line((180, 110), (250, 82), color=(0, 0, 1), width=2)
    page.insert_text((42, 210), "Figure 1. Accuracy by epoch", fontsize=12)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def png_size_from_data_uri(data_uri: str) -> tuple[int, int]:
    """Return dimensions from a PNG data URI emitted by PDF visual extraction."""

    encoded = data_uri.split(",", 1)[1]
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
        return image.size


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


def test_extract_candidates_bounds_raster_before_rendering_large_page(monkeypatch):
    with fitz.open() as document:
        page = document.new_page(width=3000, height=4000)
        page.insert_text((30, 40), "Figure 1. A large-format page")
        pdf_bytes = document.tobytes()

    rendered_sizes = []
    original_get_pixmap = fitz.Page.get_pixmap

    def measure_render(page, *args, **kwargs):
        pixmap = original_get_pixmap(page, *args, **kwargs)
        rendered_sizes.append((pixmap.width, pixmap.height))
        return pixmap

    monkeypatch.setattr(fitz.Page, "get_pixmap", measure_render)
    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1)
    candidates = service.extract_candidates(pdf_bytes=pdf_bytes, filename="poster.pdf")

    assert len(candidates) == len(rendered_sizes) == 1
    assert max(rendered_sizes[0]) <= 1600
    assert candidates[0].page_number == 1
    assert png_size_from_data_uri(candidates[0].image_data_uri) == rendered_sizes[0]


def test_extract_candidates_crops_caption_adjacent_figure_region(caplog):
    """A captioned vector figure should render as a compact crop, not a full page."""

    caplog.set_level("INFO")
    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1, render_zoom=1.0)

    candidates = service.extract_candidates(
        pdf_bytes=make_visual_pdf(),
        filename="paper.pdf",
        conversation_id="crop-conversation",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    width, height = png_size_from_data_uri(candidate.image_data_uri)

    assert candidate.crop_applied is True
    assert candidate.crop_reason == "caption_visual_cluster"
    assert width == candidate.width
    assert height == candidate.height
    assert width < 320
    assert height < 240
    assert "pdf_visual.crop_selected" in caplog.text
    assert "conversation_id=crop-conversation" in caplog.text
    assert "crop_applied=True" in caplog.text
    assert candidate.visual_quality_score >= 0.7
    assert candidate.visual_quality_reason == "crop_quality_pass"


def test_extract_candidates_crops_real_transformer_pdf_figure_two(caplog):
    """The real Transformer PDF should expose Figure 2 as a compact page-4 crop."""

    caplog.set_level("INFO")
    fixture = Path("temp/Attention Is all you need.pdf")
    if not fixture.exists():
        pytest.skip("real Transformer PDF fixture is not available")
    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=5, render_zoom=1.0)

    candidates = service.extract_candidates(
        pdf_bytes=fixture.read_bytes(),
        filename="Attention Is all you need.pdf",
        conversation_id="transformer-crop",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    width, height = png_size_from_data_uri(candidate.image_data_uri)

    assert candidate.page_number == 4
    assert candidate.crop_applied is True
    assert candidate.crop_reason == "caption_visual_cluster"
    assert "Figure" in candidate.caption_hint
    assert width == candidate.width
    assert height == candidate.height
    assert width < 500
    assert height < 350
    assert "pdf_visual.crop_selected" in caplog.text
    assert "conversation_id=transformer-crop" in caplog.text


def test_pdf_crop_choice_expands_weak_target_strip():
    """A weak targeted crop should be enlarged before rendering."""

    service = PdfVisualExtractionService(max_candidates=1, max_pages_scanned=1, render_zoom=1.0)
    page_rect = fitz.Rect(0, 0, 400, 600)
    weak_strip = fitz.Rect(48, 230, 352, 282)

    choice = service._select_crop_choice(
        crop_rect=weak_strip,
        crop_reason="target_caption_visual_cluster",
        page_rect=page_rect,
        target_caption="Table 2: Dataset composition",
    )

    assert choice.crop_applied is True
    assert choice.crop_reason == "target_caption_visual_cluster_expanded"
    assert choice.quality_reason == "expanded_crop_quality_pass"
    assert choice.quality_score > 0.7
    assert choice.clip is not None
    assert choice.clip.height > weak_strip.height
