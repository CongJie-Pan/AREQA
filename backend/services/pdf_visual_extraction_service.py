"""Extract request-scoped visual candidates from uploaded PDF attachments.

PDF figures in academic papers are often vector drawings rather than embedded
bitmap images. This service therefore renders likely visual pages into bounded
PNG thumbnails instead of relying only on raw image extraction. The rendered
bytes are kept in memory for the current chat request and are never written to
disk by this module.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import io
import logging
import re
from typing import Any

from PIL import Image, UnidentifiedImageError

from config import settings
from services.attachment_service import MAX_ATTACHMENT_BYTES, MAX_IMAGE_PIXELS
from services.visual_answer_service import ImageBlock


logger = logging.getLogger(__name__)

PDF_ATTACHMENT_IMAGE_PROVIDER = "pdf_attachment"
PDF_ATTACHMENT_SOURCE_DOMAIN = "uploaded PDF"
DEFAULT_MAX_PDF_VISUAL_CANDIDATES = 2
DEFAULT_MAX_PDF_VISUAL_PAGES_SCANNED = 8
PDF_VISUAL_RENDER_ZOOM = 1.6
PDF_VISUAL_MIN_PAGE_SCORE = 1
PDF_VISUAL_MAX_DATA_URI_BYTES = min(MAX_ATTACHMENT_BYTES, 2 * 1024 * 1024)


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

    def to_image_block(self) -> ImageBlock:
        """Convert the candidate into the existing frontend image block shape.

        Returns:
            ``ImageBlock`` with a data URI image and PDF attachment attribution.

        Side Effects:
            None.
        """

        topic = f"{self.filename} 第 {self.page_number} 頁"
        caption = self.caption_hint or f"上傳 PDF 第 {self.page_number} 頁的圖像內容"
        return ImageBlock(
            slot_id=self.slot_id,
            topic=topic,
            purpose="chart",
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
            match_confidence=0.92,
            heuristic_score=min(1.0, 0.5 + (self.visual_score / 20)),
            pedagogical_score=min(1.0, 0.55 + (self.visual_score / 20)),
            vision_source="unavailable",
            transient=True,
        )


class PdfVisualExtractionService:
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
        self.max_candidates = max(0, min(int(max_candidates or configured_candidates), 3))
        self.max_pages_scanned = max(1, min(int(max_pages_scanned or configured_pages), 20))
        self.render_zoom = max(0.5, min(float(render_zoom), 2.0))

    def extract_candidates(
        self,
        *,
        pdf_bytes: bytes,
        filename: str,
        conversation_id: str = "unknown",
    ) -> tuple[PdfVisualCandidate, ...]:
        """Return rendered PDF page candidates for inline answer images.

        Args:
            pdf_bytes: Validated PDF bytes from the current upload.
            filename: Sanitized filename for display metadata.
            conversation_id: Correlation id for privacy-safe structured logs.

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
            scored_pages = self._score_pages(document, page_count)
            selected_pages = [
                item
                for item in sorted(scored_pages, key=lambda value: value[1], reverse=True)
                if item[1] >= PDF_VISUAL_MIN_PAGE_SCORE
            ][: self.max_candidates]
            candidates: list[PdfVisualCandidate] = []
            for page_index, score, caption_hint in selected_pages:
                candidate = self._render_candidate(
                    document=document,
                    page_index=page_index,
                    visual_score=score,
                    caption_hint=caption_hint,
                    filename=filename,
                    candidate_index=len(candidates) + 1,
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
    ) -> PdfVisualCandidate | None:
        """Render one selected PDF page to a bounded PNG data URI."""

        import fitz  # type: ignore[import-not-found]

        page = document.load_page(page_index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(self.render_zoom, self.render_zoom), alpha=False)
        png_bytes = pixmap.tobytes("png")
        if not self._is_valid_png(png_bytes):
            return None
        if len(png_bytes) > PDF_VISUAL_MAX_DATA_URI_BYTES:
            png_bytes = self._downscale_png(png_bytes)
        if len(png_bytes) > PDF_VISUAL_MAX_DATA_URI_BYTES:
            return None

        encoded = base64.b64encode(png_bytes).decode("ascii")
        digest = hashlib.sha256(png_bytes).hexdigest()
        page_number = page_index + 1
        return PdfVisualCandidate(
            slot_id=f"pdf_img_{candidate_index}",
            filename=filename,
            page_number=page_number,
            image_data_uri=f"data:image/png;base64,{encoded}",
            width=pixmap.width,
            height=pixmap.height,
            caption_hint=caption_hint,
            visual_score=visual_score,
            sha256=digest,
        )

    @staticmethod
    def _is_valid_png(data: bytes) -> bool:
        """Return whether rendered bytes are a bounded valid PNG."""

        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                return width * height <= MAX_IMAGE_PIXELS
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError):
            return False

    @staticmethod
    def _downscale_png(data: bytes) -> bytes:
        """Downscale large rendered pages while preserving readable layout."""

        with Image.open(io.BytesIO(data)) as image:
            image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()

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
