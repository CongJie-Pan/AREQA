"""Extract request-scoped visual candidates from uploaded PDF attachments.

PDF figures in academic papers are often vector drawings rather than embedded
bitmap images. This service therefore renders likely visual pages into bounded
PNG thumbnails instead of relying only on raw image extraction. The rendered
bytes are kept in memory for the current chat request and are never written to
disk by this module.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from typing import Any, Iterable

from config import settings
from services.pdf_visual import geometry as _pdf_visual_geometry_module
from services.pdf_visual.constants import (
    DEFAULT_MAX_PDF_VISUAL_CANDIDATES,
    DEFAULT_MAX_PDF_VISUAL_PAGES_SCANNED,
    PDF_ATTACHMENT_IMAGE_PROVIDER,
    PDF_ATTACHMENT_SOURCE_DOMAIN,
    PDF_VISUAL_CROP_PADDING_POINTS,
    PDF_VISUAL_MAX_CAPTION_GAP_POINTS,
    PDF_VISUAL_MAX_CROP_AREA_RATIO,
    PDF_VISUAL_MAX_DATA_URI_BYTES,
    PDF_VISUAL_MAX_RENDER_EDGE,
    PDF_VISUAL_MAX_TARGET_CROP_ASPECT_RATIO,
    PDF_VISUAL_MIN_PAGE_SCORE,
    PDF_VISUAL_MIN_CROP_AREA_RATIO,
    PDF_VISUAL_MIN_TARGET_QUALITY_SCORE,
    PDF_VISUAL_MIN_THIN_RECT_POINTS,
    PDF_VISUAL_MIN_VISUAL_RECT_AREA,
    PDF_VISUAL_RENDER_ZOOM,
    _PDF_FIGURE_CAPTION_PATTERN,
)
from services.pdf_visual.geometry import PdfVisualGeometryMixin
from services.pdf_visual.models import PdfVisualCandidate, _PdfCropChoice
from services.pdf_visual.rendering import PdfVisualRenderingMixin


logger = logging.getLogger(__name__)


class PdfVisualExtractionService(PdfVisualGeometryMixin, PdfVisualRenderingMixin):
    """Render likely figure/chart pages from one uploaded PDF.

    The service intentionally performs deterministic local extraction only. It
    does not call a model, does not persist bytes, and emits only safe
    structured logs: correlation id, filename, page counts, selected counts,
    reason codes, and coarse scores. It never logs raw PDF text or image data.
    """

    def __init__(
        self,
        *,
        max_candidates: int | None = None,
        max_pages_scanned: int | None = None,
        render_zoom: float = PDF_VISUAL_RENDER_ZOOM,
    ) -> None:
        """Initialize bounded PDF visual extraction.

        Args:
            max_candidates: Maximum rendered page candidates returned.
            max_pages_scanned: Maximum pages inspected from the front of a PDF.
            render_zoom: PyMuPDF render zoom for page thumbnails.

        Side Effects:
            None.
        """

        configured_candidates = getattr(
            settings,
            "pdf_attachment_visual_max_candidates",
            DEFAULT_MAX_PDF_VISUAL_CANDIDATES,
        )
        configured_pages = getattr(
            settings,
            "pdf_attachment_visual_max_pages_scanned",
            DEFAULT_MAX_PDF_VISUAL_PAGES_SCANNED,
        )
        self.max_candidates = max(0, min(int(max_candidates or configured_candidates), 4))
        self.max_pages_scanned = max(1, min(int(max_pages_scanned or configured_pages), 20))
        self.render_zoom = max(0.5, min(float(render_zoom), 2.0))

    def extract_candidates(
        self,
        *,
        pdf_bytes: bytes,
        filename: str,
        conversation_id: str = "unknown",
        visual_plan: Iterable[Any] | None = None,
    ) -> tuple[PdfVisualCandidate, ...]:
        """Return rendered PDF page candidates for inline answer images.

        Args:
            pdf_bytes: Validated PDF bytes from the current upload.
            filename: Sanitized filename for display metadata.
            conversation_id: Correlation id for privacy-safe structured logs.
            visual_plan: Optional sanitized planner items. When present, page
                selection follows the planner order while crop geometry remains
                deterministic inside this renderer.

        Returns:
            A tuple of selected rendered PDF visual candidates. Empty means
            extraction is unavailable or no visual page passed the cheap score.

        Side Effects:
            Imports PyMuPDF lazily and renders selected PDF pages in memory.
        """

        if self.max_candidates <= 0:
            self._log_completed(conversation_id, filename, 0, 0, "disabled")
            return ()
        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError:
            logger.info(
                "pdf_visual.extraction_unavailable conversation_id=%s filename=%s reason=missing_pymupdf",
                conversation_id,
                filename,
            )
            return ()

        try:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            logger.info(
                "pdf_visual.extraction_unavailable conversation_id=%s filename=%s reason=%s",
                conversation_id,
                filename,
                type(exc).__name__,
            )
            return ()

        try:
            page_count = int(getattr(document, "page_count", 0) or len(document))
            planned_pages = self._planned_pages(visual_plan, page_count)
            if planned_pages:
                selected_pages = planned_pages[: self.max_candidates]
                selection_mode = "planner"
            else:
                scored_pages = self._score_pages(document, page_count)
                selected_pages = [
                    (page_index, score, caption_hint, None)
                    for page_index, score, caption_hint in sorted(
                        scored_pages,
                        key=lambda value: value[1],
                        reverse=True,
                    )
                    if score >= PDF_VISUAL_MIN_PAGE_SCORE
                ][: self.max_candidates]
                selection_mode = "heuristic"
            candidates: list[PdfVisualCandidate] = []
            for page_index, score, caption_hint, plan_item in selected_pages:
                candidate = self._render_candidate(
                    document=document,
                    page_index=page_index,
                    visual_score=score,
                    caption_hint=caption_hint,
                    filename=filename,
                    candidate_index=len(candidates) + 1,
                    conversation_id=conversation_id,
                    plan_item=plan_item,
                    selection_source=selection_mode,
                )
                if candidate:
                    candidates.append(candidate)
            self._log_completed(conversation_id, filename, page_count, len(candidates), "ok")
            return tuple(candidates)
        except Exception as exc:
            logger.info(
                "pdf_visual.extraction_failed conversation_id=%s filename=%s reason=%s",
                conversation_id,
                filename,
                type(exc).__name__,
            )
            return ()
        finally:
            document.close()

    @staticmethod
    def _planned_pages(
        visual_plan: Iterable[Any] | None,
        page_count: int,
    ) -> list[tuple[int, int, str, Any]]:
        """Return validated planner-selected pages in planner priority order."""

        if not visual_plan:
            return []
        selected: list[tuple[int, int, str, Any]] = []
        seen_pages: set[int] = set()
        for index, item in enumerate(visual_plan):
            try:
                page_number = int(getattr(item, "page_number"))
            except (TypeError, ValueError):
                continue
            if page_number < 1 or page_number > page_count or page_number in seen_pages:
                continue
            seen_pages.add(page_number)
            teaching_caption = str(getattr(item, "teaching_caption", "") or "").strip()
            answer_section = str(getattr(item, "answer_section", "") or "").strip()
            caption_hint = teaching_caption or answer_section or f"上傳 PDF 第 {page_number} 頁"
            selected.append((page_number - 1, max(1, 100 - index), caption_hint[:220], item))
        return selected

    def _score_pages(self, document: Any, page_count: int) -> list[tuple[int, int, str]]:
        """Score early PDF pages for visible charts, figures, or diagrams."""

        scored_pages: list[tuple[int, int, str]] = []
        pages_to_scan = min(page_count, self.max_pages_scanned)
        for page_index in range(pages_to_scan):
            page = document.load_page(page_index)
            image_count = len(page.get_images(full=True))
            drawing_count = len(page.get_drawings())
            text = self._safe_page_text(page)
            figure_hits = len(re.findall(r"\b(fig(?:ure)?|graph|chart|plot|diagram|table)\b|圖|表", text, re.I))
            score = image_count * 4 + min(drawing_count, 12) + figure_hits * 3
            if score <= 0 and page_index < 2:
                score = 1
            scored_pages.append((page_index, score, self._caption_hint(text, page_index + 1)))
        return scored_pages

    @staticmethod
    def _safe_page_text(page: Any) -> str:
        """Return bounded page text used only for scoring and short captions."""

        try:
            return re.sub(r"\s+", " ", page.get_text("text") or "").strip()[:4000]
        except Exception:
            return ""

    @staticmethod
    def _caption_hint(text: str, page_number: int) -> str:
        """Extract a short display caption without exposing whole page text."""

        if not text:
            return f"上傳 PDF 第 {page_number} 頁"
        match = re.search(
            r"((?:Fig(?:ure)?\.?|圖|表)\s*\d+[A-Za-z]?[^\n。.!?]{0,180})",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()[:220]
        return f"上傳 PDF 第 {page_number} 頁的圖表或版面截圖"

    def _render_candidate(
        self,
        *,
        document: Any,
        page_index: int,
        visual_score: int,
        caption_hint: str,
        filename: str,
        candidate_index: int,
        conversation_id: str,
        plan_item: Any = None,
        selection_source: str = "heuristic",
    ) -> PdfVisualCandidate | None:
        """Render one selected PDF page or figure crop to a bounded PNG data URI.

        Args:
            document: Open PyMuPDF document.
            page_index: Zero-based page index selected by the cheap visual
                scorer.
            visual_score: Page-level visual score used for candidate ranking.
            caption_hint: Safe short display caption derived from page text.
            filename: Sanitized upload filename for display metadata.
            candidate_index: Stable one-based visual candidate index.
            conversation_id: Correlation id for privacy-safe structured logs.
            plan_item: Optional sanitized planner item. Its text metadata is
                bounded before it reaches the candidate.
            selection_source: Safe source label for candidate provenance.

        Returns:
            A request-scoped visual candidate. When caption-adjacent visual
            geometry is detected, the PNG is clipped to the figure plus caption;
            otherwise it preserves the previous full-page thumbnail behavior.

        Side Effects:
            Emits ``pdf_visual.crop_selected`` with correlation-safe page,
            dimensions, and reason-code metadata. It never logs raw PDF text,
            rendered bytes, prompts, credentials, or user content.
        """

        import fitz  # type: ignore[import-not-found]

        page = document.load_page(page_index)
        target_caption = self._bounded_plan_text(getattr(plan_item, "target_caption", ""), 220)
        crop_rect, crop_reason = self._find_figure_crop_rect(page, target_caption=target_caption)
        crop_choice = self._select_crop_choice(
            crop_rect=crop_rect,
            crop_reason=crop_reason,
            page_rect=fitz.Rect(page.rect),
            target_caption=target_caption,
        )
        # Bound the native RGB allocation before rendering oversized page boxes.
        render_rect = crop_choice.clip if crop_choice.clip is not None else page.rect
        longest_edge = max(render_rect.width, render_rect.height)
        if longest_edge <= 0:
            return None
        zoom = min(self.render_zoom, (PDF_VISUAL_MAX_RENDER_EDGE - 1) / longest_edge)
        png_bytes = page.get_pixmap(
            matrix=fitz.Matrix(zoom, zoom),
            clip=crop_choice.clip,
            alpha=False,
        ).tobytes("png")
        if not self._is_valid_png(png_bytes):
            return None
        if len(png_bytes) > PDF_VISUAL_MAX_DATA_URI_BYTES:
            png_bytes = self._downscale_png(png_bytes)
        if len(png_bytes) > PDF_VISUAL_MAX_DATA_URI_BYTES:
            return None

        width, height = self._png_dimensions(png_bytes)
        logger.info(
            "pdf_visual.crop_selected conversation_id=%s page_number=%s crop_applied=%s reason=%s width=%s height=%s quality_score=%.2f quality_reason=%s",
            conversation_id,
            page_index + 1,
            crop_choice.crop_applied,
            crop_choice.crop_reason,
            width,
            height,
            crop_choice.quality_score,
            crop_choice.quality_reason,
        )
        encoded = base64.b64encode(png_bytes).decode("ascii")
        digest = hashlib.sha256(png_bytes).hexdigest()
        page_number = page_index + 1
        answer_section = self._bounded_plan_text(getattr(plan_item, "answer_section", ""), 100)
        planner_rationale = self._bounded_plan_text(getattr(plan_item, "rationale", ""), 180)
        visual_type = self._bounded_visual_type(getattr(plan_item, "visual_type", "chart"))
        teaching_caption = self._bounded_plan_text(getattr(plan_item, "teaching_caption", ""), 220)
        return PdfVisualCandidate(
            slot_id=f"pdf_img_{candidate_index}",
            filename=filename,
            page_number=page_number,
            image_data_uri=f"data:image/png;base64,{encoded}",
            width=width,
            height=height,
            caption_hint=caption_hint,
            visual_score=visual_score,
            sha256=digest,
            crop_applied=crop_choice.crop_applied,
            crop_reason=crop_choice.crop_reason,
            answer_section=answer_section,
            visual_type=visual_type,
            target_caption=target_caption,
            teaching_caption=teaching_caption,
            planner_rationale=planner_rationale,
            selection_source=selection_source,
            visual_quality_score=crop_choice.quality_score,
            visual_quality_reason=crop_choice.quality_reason,
        )

    @staticmethod
    def _bounded_plan_text(value: Any, max_length: int) -> str:
        """Return bounded planner text safe for captions and prompt inventory."""

        return re.sub(r"\s+", " ", str(value or "")).strip()[:max_length]

    @staticmethod
    def _bounded_visual_type(value: Any) -> str:
        """Return a display-safe visual type from planner metadata."""

        visual_type = re.sub(r"[^a-zA-Z0-9_-]", "", str(value or "").strip().lower())[:40]
        return visual_type or "chart"


    @staticmethod
    def _log_completed(
        conversation_id: str,
        filename: str,
        page_count: int,
        selected_count: int,
        reason: str,
    ) -> None:
        """Emit the stable completion log for PDF visual extraction."""

        logger.info(
            "pdf_visual.extraction_completed conversation_id=%s filename=%s page_count=%s selected_count=%s reason=%s",
            conversation_id,
            filename,
            page_count,
            selected_count,
            reason,
        )


# Moved geometry helpers still reference the historical facade name in their
# globals. Binding it here preserves private-helper compatibility after the
# mechanical split.
_pdf_visual_geometry_module.PdfVisualExtractionService = PdfVisualExtractionService
