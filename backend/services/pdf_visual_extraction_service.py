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
from typing import Any, Iterable

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
PDF_VISUAL_CROP_PADDING_POINTS = 12.0
PDF_VISUAL_MAX_CAPTION_GAP_POINTS = 260.0
PDF_VISUAL_MIN_CROP_AREA_RATIO = 0.02
PDF_VISUAL_MAX_CROP_AREA_RATIO = 0.7
PDF_VISUAL_MIN_VISUAL_RECT_AREA = 24.0
PDF_VISUAL_MIN_THIN_RECT_POINTS = 2.0

_PDF_FIGURE_CAPTION_PATTERN = re.compile(
    r"\b(?:fig(?:ure)?\.?|table)\s*\d+[A-Za-z]?\b|(?:圖|表)\s*\d+",
    re.IGNORECASE,
)


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

    def to_image_block(self) -> ImageBlock:
        """Convert the candidate into the existing frontend image block shape.

        Returns:
            ``ImageBlock`` with a data URI image and PDF attachment attribution.

        Side Effects:
            None.
        """

        topic = f"{self.filename} 第 {self.page_number} 頁"
        caption = self.caption_hint or f"上傳 PDF 第 {self.page_number} 頁的圖像內容"
        if self.answer_section and self.teaching_caption:
            explanatory_caption = f"這張圖適合用來說明{self.answer_section}。{self.teaching_caption}"
        else:
            explanatory_caption = self.teaching_caption or ""
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
            explanatory_caption=explanatory_caption,
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
        clip = crop_rect if crop_rect is not None else None
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(self.render_zoom, self.render_zoom),
            clip=clip,
            alpha=False,
        )
        png_bytes = pixmap.tobytes("png")
        if not self._is_valid_png(png_bytes):
            return None
        if len(png_bytes) > PDF_VISUAL_MAX_DATA_URI_BYTES:
            png_bytes = self._downscale_png(png_bytes)
        if len(png_bytes) > PDF_VISUAL_MAX_DATA_URI_BYTES:
            return None

        width, height = self._png_dimensions(png_bytes)
        logger.info(
            "pdf_visual.crop_selected conversation_id=%s page_number=%s crop_applied=%s reason=%s width=%s height=%s",
            conversation_id,
            page_index + 1,
            crop_rect is not None,
            crop_reason,
            width,
            height,
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
            crop_applied=crop_rect is not None,
            crop_reason=crop_reason,
            answer_section=answer_section,
            visual_type=visual_type,
            target_caption=target_caption,
            teaching_caption=teaching_caption,
            planner_rationale=planner_rationale,
            selection_source=selection_source,
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

    def _find_figure_crop_rect(self, page: Any, *, target_caption: str = "") -> tuple[Any | None, str]:
        """Find a caption-adjacent figure crop rectangle for one PDF page.

        Args:
            page: PyMuPDF page object. The type stays ``Any`` because PyMuPDF is
                imported lazily and optional in test environments.
            target_caption: Optional planner-selected caption text. When it
                matches a caption block on the page, only that caption's visual
                cluster is considered first. This preserves deterministic
                renderer ownership of crop geometry.

        Returns:
            ``(rect, reason)`` when the page contains a safe figure crop, or
            ``(None, reason)`` when callers should render the full page.

        Side Effects:
            None. This method reads page geometry only and does not log raw page
            text.
        """

        import fitz  # type: ignore[import-not-found]

        page_rect = fitz.Rect(page.rect)
        visual_rects = self._visual_rects(page)
        if not visual_rects:
            return None, "no_visual_rects"

        caption_blocks = self._caption_blocks(page)
        ordered_caption_blocks, matched_target = self._ordered_caption_blocks(
            caption_blocks,
            target_caption=target_caption,
        )

        for caption_rect, _caption_text in ordered_caption_blocks:
            above = [
                rect
                for rect in visual_rects
                if self._is_caption_adjacent_visual(rect, caption_rect, side="above")
            ]
            below = [
                rect
                for rect in visual_rects
                if self._is_caption_adjacent_visual(rect, caption_rect, side="below")
            ]
            # Figure captions in papers most often sit below the visual. If a
            # caption has a usable visual cluster above it, mixing in lower
            # formulas or later-page diagrams produces oversized crops.
            nearby = above or below
            if not nearby:
                continue
            if matched_target and _caption_text == matched_target:
                nearby = self._nearest_caption_visuals(nearby, caption_rect)
            crop_rect = self._union_rects([*nearby, caption_rect])
            crop_rect = self._pad_rect(crop_rect, page_rect, PDF_VISUAL_CROP_PADDING_POINTS)
            if self._is_usable_crop_rect(crop_rect, page_rect):
                if matched_target and _caption_text == matched_target:
                    return crop_rect, "target_caption_visual_cluster"
                return crop_rect, "caption_visual_cluster"

        return None, "no_caption_visual_cluster"

    @staticmethod
    def _nearest_caption_visuals(visual_rects: list[Any], caption_rect: Any) -> list[Any]:
        """Return the closest visual rectangles for a planner-targeted caption.

        Planner-targeted crops should disambiguate pages with multiple figures
        or tables. The legacy crop path unions every nearby rectangle, but for a
        matched target caption the nearest visual is the safest deterministic
        anchor because including farther rectangles can accidentally merge
        unrelated figures on the same page.
        """

        if len(visual_rects) <= 1:
            return visual_rects

        def vertical_gap(rect: Any) -> float:
            if rect.y1 <= caption_rect.y0:
                return max(0.0, caption_rect.y0 - rect.y1)
            if rect.y0 >= caption_rect.y1:
                return max(0.0, rect.y0 - caption_rect.y1)
            return 0.0

        nearest = min(visual_rects, key=vertical_gap)
        nearest_gap = vertical_gap(nearest)
        same_cluster = [
            rect
            for rect in visual_rects
            if abs(vertical_gap(rect) - nearest_gap) <= 12.0
        ]
        return same_cluster or [nearest]

    @classmethod
    def _ordered_caption_blocks(
        cls,
        caption_blocks: list[tuple[Any, str]],
        *,
        target_caption: str,
    ) -> tuple[list[tuple[Any, str]], str]:
        """Return caption blocks with the target caption first when matched."""

        target = cls._normalize_caption_match_text(target_caption)
        if not target:
            return caption_blocks, ""

        best_index = -1
        best_score = 0.0
        for index, (_rect, caption_text) in enumerate(caption_blocks):
            score = cls._caption_match_score(target, cls._normalize_caption_match_text(caption_text))
            if score > best_score:
                best_index = index
                best_score = score

        if best_index < 0 or best_score < 0.55:
            return caption_blocks, ""

        matched = caption_blocks[best_index]
        reordered = [matched, *caption_blocks[:best_index], *caption_blocks[best_index + 1 :]]
        return reordered, matched[1]

    @staticmethod
    def _caption_match_score(target: str, candidate: str) -> float:
        """Return conservative token-overlap score for caption targeting."""

        if not target or not candidate:
            return 0.0
        if target in candidate or candidate in target:
            return 1.0
        target_tokens = set(target.split())
        candidate_tokens = set(candidate.split())
        if not target_tokens or not candidate_tokens:
            return 0.0
        return len(target_tokens & candidate_tokens) / max(len(target_tokens), len(candidate_tokens))

    @staticmethod
    def _normalize_caption_match_text(value: str) -> str:
        """Normalize caption text for deterministic target matching."""

        return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(value or "").lower()).strip()

    def _caption_blocks(self, page: Any) -> list[tuple[Any, str]]:
        """Return text blocks that look like figure or table captions."""

        import fitz  # type: ignore[import-not-found]

        captions: list[tuple[Any, str]] = []
        try:
            blocks = page.get_text("dict").get("blocks", [])
        except Exception:
            return captions
        for block in blocks:
            if block.get("type") != 0:
                continue
            text = self._block_text(block)
            if not text or not _PDF_FIGURE_CAPTION_PATTERN.search(text):
                continue
            captions.append((fitz.Rect(block.get("bbox")), text[:220]))
        return captions

    @staticmethod
    def _block_text(block: dict[str, Any]) -> str:
        """Collapse one PyMuPDF text block into bounded plain text."""

        return re.sub(
            r"\s+",
            " ",
            " ".join(
                str(span.get("text") or "")
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            ),
        ).strip()[:500]

    def _visual_rects(self, page: Any) -> list[Any]:
        """Return image and vector drawing rectangles suitable for crop search."""

        rects: list[Any] = []
        rects.extend(self._image_rects(page))
        rects.extend(self._drawing_rects(page))
        return self._dedupe_rects(rects)

    @staticmethod
    def _image_rects(page: Any) -> list[Any]:
        """Return visible embedded-image rectangles from a PyMuPDF page."""

        import fitz  # type: ignore[import-not-found]

        rects: list[Any] = []
        try:
            images = page.get_images(full=True)
        except Exception:
            return rects
        for image in images:
            xref = image[0]
            try:
                rects.extend(fitz.Rect(rect) for rect in page.get_image_rects(xref))
            except Exception:
                continue
        return rects

    @staticmethod
    def _drawing_rects(page: Any) -> list[Any]:
        """Return vector drawing rectangles, inflating thin strokes for matching."""

        import fitz  # type: ignore[import-not-found]

        rects: list[Any] = []
        try:
            drawings = page.get_drawings()
        except Exception:
            return rects
        for drawing in drawings:
            rect = drawing.get("rect")
            if rect is None:
                continue
            normalized = PdfVisualExtractionService._normalize_visual_rect(
                fitz.Rect(rect),
                fitz.Rect(page.rect),
            )
            if normalized is not None:
                rects.append(normalized)
        return rects

    @staticmethod
    def _normalize_visual_rect(rect: Any, page_rect: Any) -> Any | None:
        """Inflate usable thin PDF drawing rectangles and reject tiny marks."""

        import fitz  # type: ignore[import-not-found]

        normalized = fitz.Rect(rect)
        if normalized.is_infinite:
            return None
        if normalized.width < PDF_VISUAL_MIN_THIN_RECT_POINTS:
            center = (normalized.x0 + normalized.x1) / 2
            normalized.x0 = center - (PDF_VISUAL_MIN_THIN_RECT_POINTS / 2)
            normalized.x1 = center + (PDF_VISUAL_MIN_THIN_RECT_POINTS / 2)
        if normalized.height < PDF_VISUAL_MIN_THIN_RECT_POINTS:
            center = (normalized.y0 + normalized.y1) / 2
            normalized.y0 = center - (PDF_VISUAL_MIN_THIN_RECT_POINTS / 2)
            normalized.y1 = center + (PDF_VISUAL_MIN_THIN_RECT_POINTS / 2)
        normalized = normalized & page_rect
        if normalized.is_empty:
            return None
        if normalized.get_area() < PDF_VISUAL_MIN_VISUAL_RECT_AREA:
            return None
        return normalized

    @staticmethod
    def _is_caption_adjacent_visual(visual_rect: Any, caption_rect: Any, *, side: str) -> bool:
        """Return whether a visual rectangle plausibly belongs to a caption."""

        horizontal_overlap = max(
            0.0,
            min(visual_rect.x1, caption_rect.x1) - max(visual_rect.x0, caption_rect.x0),
        )
        min_width = max(1.0, min(visual_rect.width, caption_rect.width))
        overlaps_same_column = horizontal_overlap / min_width >= 0.15
        visual_above_caption = side == "above" and visual_rect.y1 <= caption_rect.y0 + 8
        visual_below_caption = side == "below" and visual_rect.y0 >= caption_rect.y1 - 8
        vertical_gap = (
            caption_rect.y0 - visual_rect.y1
            if visual_above_caption
            else visual_rect.y0 - caption_rect.y1
        )
        return (
            overlaps_same_column
            and (visual_above_caption or visual_below_caption)
            and 0 <= vertical_gap <= PDF_VISUAL_MAX_CAPTION_GAP_POINTS
        )

    @staticmethod
    def _union_rects(rects: Iterable[Any]) -> Any:
        """Return the bounding rectangle covering all input rectangles."""

        import fitz  # type: ignore[import-not-found]

        iterator = iter(rects)
        union = fitz.Rect(next(iterator))
        for rect in iterator:
            union |= fitz.Rect(rect)
        return union

    @staticmethod
    def _pad_rect(rect: Any, page_rect: Any, padding: float) -> Any:
        """Pad a rectangle while keeping it inside the PDF page bounds."""

        import fitz  # type: ignore[import-not-found]

        padded = fitz.Rect(rect)
        padded.x0 -= padding
        padded.y0 -= padding
        padded.x1 += padding
        padded.y1 += padding
        return padded & fitz.Rect(page_rect)

    @staticmethod
    def _is_usable_crop_rect(crop_rect: Any, page_rect: Any) -> bool:
        """Return whether a crop is neither too small nor effectively full-page."""

        page_area = max(float(page_rect.get_area()), 1.0)
        area_ratio = float(crop_rect.get_area()) / page_area
        return (
            crop_rect.width >= 80
            and crop_rect.height >= 60
            and PDF_VISUAL_MIN_CROP_AREA_RATIO <= area_ratio <= PDF_VISUAL_MAX_CROP_AREA_RATIO
        )

    @staticmethod
    def _dedupe_rects(rects: list[Any]) -> list[Any]:
        """Remove duplicate rectangles caused by repeated PDF image references."""

        seen: set[tuple[int, int, int, int]] = set()
        unique = []
        for rect in rects:
            key = (
                round(rect.x0),
                round(rect.y0),
                round(rect.x1),
                round(rect.y1),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(rect)
        return unique

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
    def _png_dimensions(data: bytes) -> tuple[int, int]:
        """Return PNG dimensions after any final downscaling step."""

        with Image.open(io.BytesIO(data)) as image:
            return image.size

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
