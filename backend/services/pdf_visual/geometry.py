"""Geometry helpers for deterministic PDF figure and table crops.

The mixin owns PyMuPDF rectangle selection, caption matching, and crop quality
estimation. It logs nothing because callers emit one correlated crop decision
after rendering dimensions are known.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from services.pdf_visual.constants import (
    PDF_VISUAL_CROP_PADDING_POINTS,
    PDF_VISUAL_MAX_CAPTION_GAP_POINTS,
    PDF_VISUAL_MAX_CROP_AREA_RATIO,
    PDF_VISUAL_MAX_TARGET_CROP_ASPECT_RATIO,
    PDF_VISUAL_MIN_CROP_AREA_RATIO,
    PDF_VISUAL_MIN_TARGET_QUALITY_SCORE,
    PDF_VISUAL_MIN_THIN_RECT_POINTS,
    PDF_VISUAL_MIN_VISUAL_RECT_AREA,
    _PDF_FIGURE_CAPTION_PATTERN,
)
from services.pdf_visual.models import _PdfCropChoice


class PdfVisualGeometryMixin:
    """Find caption-adjacent PDF crop rectangles and score crop quality."""

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
                nearby = (
                    self._table_caption_visuals(nearby, caption_rect, page_rect)
                    if self._is_table_caption(_caption_text)
                    else self._nearest_caption_visuals(nearby, caption_rect)
                )
            crop_rect = self._union_rects([*nearby, caption_rect])
            crop_rect = self._pad_rect(crop_rect, page_rect, PDF_VISUAL_CROP_PADDING_POINTS)
            if self._is_usable_crop_rect(crop_rect, page_rect):
                if matched_target and _caption_text == matched_target:
                    return crop_rect, "target_caption_visual_cluster"
                return crop_rect, "caption_visual_cluster"

        return None, "no_caption_visual_cluster"

    def _select_crop_choice(
        self,
        *,
        crop_rect: Any | None,
        crop_reason: str,
        page_rect: Any,
        target_caption: str,
    ) -> _PdfCropChoice:
        """Choose the best deterministic crop variant for a PDF visual.

        Args:
            crop_rect: Caption-adjacent crop returned by the geometry matcher.
            crop_reason: Stable matcher reason code.
            page_rect: Full PDF page rectangle.
            target_caption: Planner-selected caption, if any.

        Returns:
            A crop choice. The choice may use the original crop, an expanded
            crop, or the full page when crop quality is too weak.

        Side Effects:
            None. Callers emit the single structured crop log after rendering
            so dimensions and quality metadata stay correlated.
        """

        if crop_rect is None:
            return _PdfCropChoice(
                clip=None,
                crop_applied=False,
                crop_reason=crop_reason,
                quality_score=0.62,
                quality_reason="full_page_no_crop",
            )

        original_score = self._crop_quality_score(crop_rect, page_rect, crop_reason=crop_reason)
        if not target_caption or original_score >= PDF_VISUAL_MIN_TARGET_QUALITY_SCORE:
            return _PdfCropChoice(
                clip=crop_rect,
                crop_applied=True,
                crop_reason=crop_reason,
                quality_score=original_score,
                quality_reason="crop_quality_pass",
            )

        expanded_rect = self._expanded_crop_rect(crop_rect, page_rect)
        expanded_score = (
            self._crop_quality_score(expanded_rect, page_rect, crop_reason=f"{crop_reason}_expanded")
            if expanded_rect is not None
            else 0.0
        )
        if expanded_rect is not None and expanded_score > original_score:
            return _PdfCropChoice(
                clip=expanded_rect,
                crop_applied=True,
                crop_reason=f"{crop_reason}_expanded",
                quality_score=expanded_score,
                quality_reason="expanded_crop_quality_pass",
            )

        return _PdfCropChoice(
            clip=None,
            crop_applied=False,
            crop_reason=f"{crop_reason}_full_page_quality_fallback",
            quality_score=0.62,
            quality_reason="full_page_quality_fallback",
        )

    @staticmethod
    def _crop_quality_score(crop_rect: Any, page_rect: Any, *, crop_reason: str) -> float:
        """Return a conservative geometry-only visual completeness score."""

        page_area = max(float(page_rect.get_area()), 1.0)
        area_ratio = float(crop_rect.get_area()) / page_area
        aspect_ratio = float(crop_rect.width) / max(float(crop_rect.height), 1.0)
        height_ratio = float(crop_rect.height) / max(float(page_rect.height), 1.0)

        score = 0.82 if "target_caption" in crop_reason else 0.74
        if 0.08 <= area_ratio <= 0.45:
            score += 0.08
        elif area_ratio < 0.05:
            score -= 0.18
        if height_ratio < 0.16:
            score -= 0.16
        if aspect_ratio > PDF_VISUAL_MAX_TARGET_CROP_ASPECT_RATIO:
            score -= 0.18
        if area_ratio > PDF_VISUAL_MAX_CROP_AREA_RATIO:
            score -= 0.12
        return max(0.0, min(1.0, score))

    @staticmethod
    def _expanded_crop_rect(crop_rect: Any, page_rect: Any) -> Any | None:
        """Return a larger crop around a weak target crop when still bounded."""

        import fitz  # type: ignore[import-not-found]

        expanded = fitz.Rect(crop_rect)
        vertical_growth = max(36.0, crop_rect.height * 0.8)
        horizontal_growth = max(24.0, crop_rect.width * 0.12)
        expanded.x0 -= horizontal_growth
        expanded.x1 += horizontal_growth
        expanded.y0 -= vertical_growth
        expanded.y1 += vertical_growth
        expanded = expanded & fitz.Rect(page_rect)
        if expanded.is_empty:
            return None
        if not PdfVisualExtractionService._is_usable_crop_rect(expanded, page_rect):
            return None
        return expanded

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

    @staticmethod
    def _table_caption_visuals(
        visual_rects: list[Any],
        caption_rect: Any,
        page_rect: Any | None = None,
    ) -> list[Any]:
        """Return visual rectangles that plausibly belong to one captioned table.

        PDF tables are often represented as many independent line rectangles.
        Using only the nearest rectangle can crop the final row plus caption
        while dropping the header and most rows. Dense tables still expand from
        the nearest same-column rectangle until a large vertical gap appears.
        Sparse table-rule crops prefer all same-column horizontal ruling lines
        above the caption when the resulting crop remains bounded.
        """

        same_column: list[Any] = []
        for rect in visual_rects:
            horizontal_overlap = max(
                0.0,
                min(rect.x1, caption_rect.x1) - max(rect.x0, caption_rect.x0),
            )
            min_width = max(1.0, min(rect.width, caption_rect.width))
            if horizontal_overlap / min_width >= 0.25:
                same_column.append(rect)
        if not same_column:
            return PdfVisualExtractionService._nearest_caption_visuals(visual_rects, caption_rect)

        above = [rect for rect in same_column if rect.y1 <= caption_rect.y0 + 8]
        below = [rect for rect in same_column if rect.y0 >= caption_rect.y1 - 8]
        if above:
            sparse_table_rules = PdfVisualExtractionService._sparse_table_rules_above_caption(
                above,
                caption_rect,
                page_rect,
            )
            if sparse_table_rules:
                return sparse_table_rules
            ordered = sorted(above, key=lambda rect: rect.y1, reverse=True)
            cluster = [ordered[0]]
            for rect in ordered[1:]:
                previous = cluster[-1]
                gap = previous.y0 - rect.y1
                if gap > 48.0:
                    break
                cluster.append(rect)
            return cluster
        if below:
            ordered = sorted(below, key=lambda rect: rect.y0)
            cluster = [ordered[0]]
            for rect in ordered[1:]:
                previous = cluster[-1]
                gap = rect.y0 - previous.y1
                if gap > 48.0:
                    break
                cluster.append(rect)
            return cluster
        return PdfVisualExtractionService._nearest_caption_visuals(same_column, caption_rect)

    @staticmethod
    def _sparse_table_rules_above_caption(
        above_rects: list[Any],
        caption_rect: Any,
        page_rect: Any | None,
    ) -> list[Any]:
        """Return full sparse table ruling lines above a table caption.

        Args:
            above_rects: Same-column visual rectangles located above the caption.
            caption_rect: Caption rectangle used as the table anchor.
            page_rect: Optional page bounds used to reject oversized table crops.

        Returns:
            Ordered horizontal rule rectangles when they form one bounded sparse
            table; otherwise an empty list so the dense-cluster fallback applies.

        Side Effects:
            None.
        """

        min_rule_width = max(80.0, caption_rect.width * 0.5)
        rules = [
            rect
            for rect in above_rects
            if rect.width >= min_rule_width and rect.height <= max(4.5, rect.width * 0.035)
        ]
        if len(rules) < 2:
            return []

        ordered = sorted(rules, key=lambda rect: rect.y0)
        crop_rect = PdfVisualExtractionService._union_rects([*ordered, caption_rect])
        if page_rect is not None and not PdfVisualExtractionService._is_usable_crop_rect(
            crop_rect,
            page_rect,
        ):
            return []

        crop_height = max(1.0, crop_rect.height)
        caption_gap = max(0.0, caption_rect.y0 - ordered[-1].y1)
        if caption_gap > max(72.0, crop_height * 0.35):
            return []

        table_width = max(rect.width for rect in ordered)
        horizontal_spread = max(rect.x1 for rect in ordered) - min(rect.x0 for rect in ordered)
        if horizontal_spread > table_width * 1.25:
            return []

        return ordered

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

    @staticmethod
    def _is_table_caption(caption_text: str) -> bool:
        """Return whether caption text identifies a table."""

        return bool(re.search(r"\btable\s*\d+|表\s*\d+", str(caption_text or ""), re.IGNORECASE))

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
