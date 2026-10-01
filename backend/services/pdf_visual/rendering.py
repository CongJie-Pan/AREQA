"""PNG rendering validation helpers for PDF visual extraction.

The mixin validates rendered PNG bytes, bounds image dimensions, and downscales
large page renders in memory. It performs no persistence and emits no logs.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from services.attachments.parsing import MAX_IMAGE_PIXELS


class PdfVisualRenderingMixin:
    """Validate and downscale rendered PDF PNG data."""

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
