"""Separate validated attachment transport from estimated provider reading cost."""
from __future__ import annotations

import base64
import io
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


class AttachmentPart(dict):
    """Server-owned marker for uploaded text; JSON serialization stays unchanged.

    Only attachment injection creates this type. User-authored text cannot claim
    exemption by embedding marker-looking JSON. No metadata is sent to providers.
    """


def is_attachment(value: Any) -> bool:
    """Identify upload markers and native provider file/image content parts."""
    return isinstance(value, dict) and (
        isinstance(value, AttachmentPart) or value.get('type') in ('file', 'image_url')
    )


def conversation_view(value: Any) -> Any:
    """Return a counting-only view without mutating or truncating provider data."""
    if is_attachment(value):
        return {'type': 'attachment_reference'}
    if isinstance(value, dict):
        return {k: conversation_view(v) for k, v in value.items()}
    if isinstance(value, list):
        return [conversation_view(v) for v in value]
    return value


def reading_cost(part: dict) -> int:
    """Estimate reading units independently of Base64 size.

    Text uses conservative UTF-8 bytes. PDF pages reserve 1024 image units plus
    extracted text bytes; images reserve 1024 units per 512-pixel tile. These are
    deployment allowances, not provider token measurements. Unknown/corrupt
    native data reserves 65536 units rather than silently costing zero.
    """
    kind = part.get('type')
    if kind == 'text':
        return len(str(part.get('text', '')).encode('utf-8')) + 32
    try:
        if kind == 'file':
            data = part.get('file', {}).get('file_data', '')
        else:
            data = part.get('image_url', {}).get('url', '')
        if not isinstance(data, str) or ';base64,' not in data:
            raise ValueError('unavailable_inline_data')
        raw = base64.b64decode(data.split(';base64,', 1)[1], validate=True)
        if kind == 'file' and data.startswith('data:application/pdf;'):
            import pymupdf
            with pymupdf.open(stream=raw, filetype='pdf') as doc:
                if doc.needs_pass or not doc.page_count:
                    raise ValueError('unreadable_pdf')
                # Bound parsing work: a very large document already exceeds allowance.
                if doc.page_count > 256:
                    return 1_000_000
                units = sum(1024 + len(page.get_text().encode('utf-8')) for page in doc)
                logger.info('attachment.pdf_budget pages=%d transport_bytes=%d estimated_reading_units=%d', doc.page_count, len(raw), units)
                return units
        if kind == 'image_url':
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as image:
                return 1024 * max(1, math.ceil(image.width / 512) * math.ceil(image.height / 512))
    except Exception as error:
        logger.info('attachment.budget_estimate_fallback kind=%s error_type=%s', kind, type(error).__name__)
    return 65_536


def attachment_cost(value: Any) -> tuple[int, int]:
    """Return total estimated reading units and part count for assembled messages."""
    if is_attachment(value):
        return reading_cost(value), 1
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    cost, count = 0, 0
    for child in children:
        units, parts = attachment_cost(child)
        cost += units
        count += parts
    return cost, count
