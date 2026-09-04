"""Constants for request-scoped PDF visual extraction.

These values bound PDF rendering, crop quality, and attachment image metadata.
They are implementation policy and must remain free of user-provided text.
"""

from __future__ import annotations

import re

from services.attachment_service import MAX_ATTACHMENT_BYTES

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
PDF_VISUAL_MAX_TARGET_CROP_ASPECT_RATIO = 5.5
PDF_VISUAL_MIN_TARGET_QUALITY_SCORE = 0.72

_PDF_FIGURE_CAPTION_PATTERN = re.compile(
    r"\b(?:fig(?:ure)?\.?|table)\s*\d+[A-Za-z]?\b|(?:圖|表)\s*\d+",
    re.IGNORECASE,
)
