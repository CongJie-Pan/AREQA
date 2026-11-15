"""Separate validated attachment transport from estimated provider reading cost."""
from __future__ import annotations

import base64
import io
import logging
import math
from typing import Any
from weakref import WeakKeyDictionary

_NATIVE_SLOTS = WeakKeyDictionary()

logger = logging.getLogger(__name__)


class AttachmentPart(dict):
    """Server-owned marker for uploaded text; JSON serialization stays unchanged.

    Only attachment injection creates this type. User-authored text cannot claim
    exemption by embedding marker-looking JSON. No metadata is sent to providers.
    """


class PdfTextPart(AttachmentPart):
    """A validated PDF represented by extracted text in the provider payload."""


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


def attachment_transport_size(value: Any) -> tuple[int, int]:
    """Count attachment parts and their serialized payload size without parsing them.

    Args:
        value: Assembled provider messages (any JSON-compatible nesting).

    Returns:
        Attachment part count and the summed length of inline data/text strings.
        Constant memory: nothing is decoded, copied or handed to a subprocess.
    """
    if is_attachment(value):
        if value.get('type') == 'file':
            data = value.get('file', {}).get('file_data', '')
        elif value.get('type') == 'image_url':
            data = value.get('image_url', {}).get('url', '')
        else:
            data = value.get('text', '')
        return 1, len(data) if isinstance(data, str) else 0
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    count, size = 0, 0
    for child in children:
        parts, length = attachment_transport_size(child)
        count += parts
        size += length
    return count, size


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


class AttachmentInspectionError(Exception):
    """Expose only a stable failure reason to the public context boundary."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


async def bounded_attachment_cost(value: Any, *, timeout_seconds: float) -> tuple[int, int]:
    """Inspect native media in a killable, resource-limited subprocess.

    Text remains in-process; file/image parsing has a wall-clock deadline covering
    startup and IPC. Timeout or caller cancellation kills and reaps the child.
    Only numeric estimates cross back to the parent; parser stderr is discarded.
    Uses wait_for for Python 3.10 compatibility; cancellation still reaps the child.
    """
    import asyncio
    import json
    from pathlib import Path
    import sys

    parts = []

    def collect(item):
        if is_attachment(item):
            parts.append(item)
        elif isinstance(item, dict):
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    text_units = sum(reading_cost(p) for p in parts if p.get('type') == 'text')
    native = [p for p in parts if p.get('type') != 'text']
    if not native:
        return text_units, len(parts)
    process = None

    async def inspect_native():
        nonlocal process
        loop = asyncio.get_running_loop()
        gate = _NATIVE_SLOTS.setdefault(loop, asyncio.Semaphore(2))
        async with gate:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).resolve()),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            output, _ = await process.communicate(json.dumps(native).encode())
            if process.returncode != 0:
                raise AttachmentInspectionError('attachment_parse_failed')
            units = json.loads(output)
            if not isinstance(units, int) or units < 0:
                raise AttachmentInspectionError('attachment_parse_failed')
            logger.info('attachment.inspection_completed native_parts=%d estimated_reading_units=%d', len(native), text_units + units)
            return text_units + units, len(parts)

    try:
        # wait_for supports Python 3.10 and covers queueing, startup and IPC.
        return await asyncio.wait_for(inspect_native(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning('attachment.inspection_failed reason=attachment_parse_timeout')
        raise AttachmentInspectionError('attachment_parse_timeout') from None
    except (ValueError, OSError):
        raise AttachmentInspectionError('attachment_parse_failed') from None
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            # Drain pipes after killing; wait alone can stall on a full stdout pipe.
            await process.communicate()
            await process.wait()


def _inspection_worker():
    """Read bounded native payloads; constrain parser CPU and address space on Unix."""
    import json
    import sys
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    except ImportError:
        pass
    parts = json.loads(sys.stdin.buffer.read(32 * 1024 * 1024))
    print(json.dumps(sum(reading_cost(part) for part in parts)))


if __name__ == '__main__':
    _inspection_worker()
