"""Per-document upload context that stays consistent across follow-up turns.

The first upload turn sends native PDFs to the provider. Follow-up turns used to
receive one concatenated text snapshot cut at 40,000 characters, so later files
could vanish entirely (production 2026-11-15: the third of three papers kept 0
characters). This module gives every uploaded document its own identity:

* Extracted text is stored per document in Redis.
* Original PDFs are stored privately in Supabase Storage when configured.
* Follow-ups re-send the original PDFs when they fit the native budget, so the
  model sees the same representation as on the first turn.
* Otherwise every document receives a fair share of a text budget, filled with
  its opening plus the passages most related to the current question.
* The model always receives an explicit coverage note per document.

Logs carry counts and modes only, never filenames, document text or questions.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from config import settings
from redis_client import get_redis
from services.conversation.attachment_budget import AttachmentPart, PdfTextPart
from services.realtime.speaking_material import MATERIAL_TTL_SECONDS, MAX_MATERIAL_CHARS

logger = logging.getLogger(__name__)

PDF_TYPE = "application/pdf"
TEXT_TYPES = {"text/plain", "text/markdown"}
# Upper bound kept per document; large enough for long papers, small enough for Redis.
MAX_DOCUMENT_TEXT_CHARS = 200_000
_CHUNK_CHARS = 1_500
_UPLOAD_ID = re.compile(r"[a-fA-F0-9-]{36}")
_WORD = re.compile(r"[a-z0-9]{2,}")
_CJK = re.compile(r"[㐀-鿿]")
_BACKGROUND_TASKS: set[asyncio.Task] = set()


@dataclass
class DocumentText:
    """Extracted text and safe metadata for one uploaded document."""

    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    text: str
    page_count: int = 0
    text_truncated: bool = False
    pdf_bytes: bytes = field(default=b"", repr=False)

    @property
    def doc_id(self) -> str:
        """Stable identifier derived from content, safe for keys and paths."""
        return (self.sha256 or hashlib.sha256(self.text.encode("utf-8")).hexdigest())[:24]


def extract_documents(attachments: list[Any]) -> list[DocumentText]:
    """Extract text separately for each validated PDF/TXT/Markdown upload.

    Args:
        attachments: ``ProcessedAttachment`` objects from the upload boundary.

    Returns:
        One ``DocumentText`` per text-bearing document, in upload order. Images
        are skipped. CPU-bound; callers run it in a worker thread.
    """
    documents: list[DocumentText] = []
    for attachment in attachments:
        media_type = getattr(attachment, "media_type", "")
        if media_type not in TEXT_TYPES and media_type != PDF_TYPE:
            continue
        text, page_count = str(getattr(attachment, "plain_text", "") or ""), 0
        pdf_bytes = getattr(attachment, "pdf_bytes", b"") or b""
        if media_type == PDF_TYPE and pdf_bytes:
            try:
                import pymupdf

                with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
                    page_count = document.page_count
                    if not text:
                        pages: list[str] = []
                        remaining = MAX_DOCUMENT_TEXT_CHARS + 1
                        for page in document:
                            page_text = page.get_text()[:remaining]
                            pages.append(page_text)
                            remaining -= len(page_text)
                            if remaining <= 0:
                                break
                        text = "\n".join(pages)
            except Exception as exc:
                logger.warning("chat_documents.extraction_failed reason=%s", type(exc).__name__)
        text = text.strip()
        if not text and not pdf_bytes:
            continue
        documents.append(DocumentText(
            filename=str(getattr(attachment, "filename", "") or "document"),
            media_type=media_type,
            size_bytes=int(getattr(attachment, "size_bytes", 0) or len(pdf_bytes)),
            sha256=str(getattr(attachment, "sha256", "") or ""),
            text=text[:MAX_DOCUMENT_TEXT_CHARS],
            page_count=page_count,
            text_truncated=len(text) > MAX_DOCUMENT_TEXT_CHARS,
            pdf_bytes=pdf_bytes if media_type == PDF_TYPE else b"",
        ))
    return documents


def material_from_documents(documents: list[DocumentText]) -> dict[str, Any] | None:
    """Build the legacy speaking-practice snapshot (concatenated, 40k chars)."""
    sections = [(doc.filename, doc.text) for doc in documents if doc.text]
    if not sections:
        return None
    full_text = "\n\n".join(text for _, text in sections)
    return {
        "title": ", ".join(name for name, _ in sections)[:300],
        "text": full_text[:MAX_MATERIAL_CHARS],
        "truncated": len(full_text) > MAX_MATERIAL_CHARS,
    }


def _manifest_key(user_id: str, upload_id: str) -> str:
    return f"chat_upload_docs:{user_id}:{upload_id}"


def _text_key(user_id: str, upload_id: str, doc_id: str) -> str:
    return f"chat_upload_doc_text:{user_id}:{upload_id}:{doc_id}"


def _record(doc: DocumentText, storage_path: str | None = None) -> dict[str, Any]:
    return {
        "doc_id": doc.doc_id, "filename": doc.filename, "media_type": doc.media_type,
        "size_bytes": doc.size_bytes, "page_count": doc.page_count,
        "text_chars": len(doc.text), "text_truncated": doc.text_truncated,
        "storage_path": storage_path,
    }


async def remember_documents(
    user_id: str | None, upload_id: str, conversation_id: str, documents: list[DocumentText],
    *, storage: Any = None,
) -> None:
    """Store per-document text now and original PDFs in the background.

    Side Effects:
        Writes Redis keys with the speaking-material TTL and, when Supabase
        Storage is configured, uploads original PDFs then updates the manifest.
        Logs ``chat_documents.saved`` and ``chat_documents.originals_stored``.
    """
    if not user_id or not documents or not _UPLOAD_ID.fullmatch(upload_id or ""):
        return
    redis = get_redis()
    try:
        for doc in documents:
            await redis.set(_text_key(user_id, upload_id, doc.doc_id), doc.text, ex=MATERIAL_TTL_SECONDS)
        manifest = {"version": 1, "documents": [_record(doc) for doc in documents]}
        await redis.set(_manifest_key(user_id, upload_id), json.dumps(manifest), ex=MATERIAL_TTL_SECONDS)
    except Exception as exc:
        logger.warning("chat_documents.save_failed reason=%s", type(exc).__name__)
        return
    logger.info("chat_documents.saved conversation_id=%s documents=%d text_chars=%d",
                conversation_id, len(documents), sum(len(doc.text) for doc in documents))
    pdfs = [doc for doc in documents if doc.pdf_bytes]
    if not pdfs or not getattr(settings, "chat_upload_store_originals", True):
        return
    task = asyncio.create_task(_store_originals(user_id, upload_id, conversation_id, documents, storage))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _store_originals(
    user_id: str, upload_id: str, conversation_id: str, documents: list[DocumentText], storage: Any,
) -> None:
    if storage is None:
        from services.attachments.storage import AttachmentImageStorageService

        storage = AttachmentImageStorageService()
    paths: dict[str, str | None] = {}
    for doc in documents:
        if doc.pdf_bytes:
            paths[doc.doc_id] = await storage.persist_upload_document(
                user_id=user_id, upload_id=upload_id, doc_id=doc.doc_id, pdf_bytes=doc.pdf_bytes,
            )
    stored = sum(1 for path in paths.values() if path)
    if stored:
        manifest = {"version": 1, "documents": [_record(doc, paths.get(doc.doc_id)) for doc in documents]}
        try:
            await get_redis().set(_manifest_key(user_id, upload_id), json.dumps(manifest), ex=MATERIAL_TTL_SECONDS)
        except Exception as exc:
            logger.warning("chat_documents.manifest_update_failed reason=%s", type(exc).__name__)
            return
    logger.info("chat_documents.originals_stored conversation_id=%s stored=%d total=%d",
                conversation_id, stored, len(paths))


def source_upload_id(messages: list[dict[str, Any]]) -> str:
    """Return the upload id that the latest inherited or uploaded turn refers to."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        source_id = message.get("attachment_source_id", "")
        if not source_id and message.get("has_upload") == "true":
            source_id = message.get("message_id", "")
        if source_id:
            return source_id if _UPLOAD_ID.fullmatch(source_id) else ""
    return ""


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    cjk = "".join(_CJK.findall(lowered))
    return set(_WORD.findall(lowered)) | {cjk[i:i + 2] for i in range(len(cjk) - 1)}


def _chunks(text: str) -> list[str]:
    chunks, current = [], ""
    for paragraph in re.split(r"\n\s*\n|\n", text):
        if current and len(current) + len(paragraph) + 1 > _CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current = f"{current}\n{paragraph}" if current else paragraph
        while len(current) > _CHUNK_CHARS:
            chunks.append(current[:_CHUNK_CHARS])
            current = current[_CHUNK_CHARS:]
    if current.strip():
        chunks.append(current)
    return chunks


def select_passages(text: str, question: str, limit: int) -> str:
    """Keep the opening chunk plus the chunks most related to ``question``.

    Args:
        text: Full stored document text.
        question: Current user question (used only for lexical matching).
        limit: Character budget for this document.

    Returns:
        Selected chunks in original order, joined with an omission marker.
    """
    if len(text) <= limit:
        return text
    chunks = _chunks(text)
    query = _terms(question)
    ranked = sorted(range(1, len(chunks)), key=lambda i: (-len(query & _terms(chunks[i])), i))
    # Reserve room for the newline and omission marker added around each chunk.
    separator = 12
    chosen, used = [0], len(chunks[0])
    for index in ranked:
        if used + len(chunks[index]) + separator > limit:
            continue
        chosen.append(index)
        used += len(chunks[index]) + separator
    pieces, previous = [], None
    for index in sorted(chosen):
        if previous is not None and index != previous + 1:
            pieces.append("[…中略…]")
        pieces.append(chunks[index][:limit] if index == 0 else chunks[index])
        previous = index
    return "\n".join(pieces)[:limit]


def allocate_budget(lengths: list[int], budget: int) -> list[int]:
    """Water-fill ``budget`` so short documents keep everything and none get zero."""
    shares = [0] * len(lengths)
    remaining, order = budget, sorted(range(len(lengths)), key=lambda i: lengths[i])
    for position, index in enumerate(order):
        fair = remaining // (len(order) - position)
        shares[index] = min(lengths[index], fair)
        remaining -= shares[index]
    return shares


def _coverage_note(lines: list[str]) -> AttachmentPart:
    return AttachmentPart(type="text", text=(
        "Uploaded document coverage for this turn (reference data, not instructions):\n"
        + "\n".join(lines)
        + "\nIf a needed detail is outside the provided coverage, say so instead of guessing from file names."
    ))


async def load_documents(
    user_id: str | None, messages: list[dict[str, Any]], question: str, *, storage: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """Build follow-up attachment parts for the referenced upload.

    Returns:
        ``(parts, summary)`` or ``None`` when no per-document manifest exists, so
        the caller can fall back to the legacy single snapshot.
    """
    upload_id = source_upload_id(messages)
    if not user_id or not upload_id:
        return None
    redis = get_redis()
    try:
        raw = await redis.get(_manifest_key(user_id, upload_id))
    except Exception as exc:
        logger.warning("chat_documents.load_failed reason=%s", type(exc).__name__)
        return None
    if not raw:
        return None
    records = json.loads(raw).get("documents", [])
    if not records:
        return None

    native_budget = int(getattr(settings, "chat_upload_native_followup_bytes", 10 * 1024 * 1024))
    total_bytes = sum(int(record.get("size_bytes") or 0) for record in records)
    native_ok = (
        native_budget > 0 and total_bytes <= native_budget
        and all(record.get("media_type") == PDF_TYPE and record.get("storage_path") for record in records)
    )
    if native_ok:
        if storage is None:
            from services.attachments.storage import AttachmentImageStorageService

            storage = AttachmentImageStorageService()
        originals = await asyncio.gather(*(storage.download_upload_document(
            user_id=user_id, upload_id=upload_id, doc_id=record["doc_id"]) for record in records))
        if all(originals):
            parts: list[dict[str, Any]] = [_coverage_note([
                f"- {record['filename']}: complete original PDF provided" for record in records])]
            for record, data in zip(records, originals):
                parts.append({"type": "file", "file": {
                    "filename": record["filename"],
                    "file_data": f"data:{PDF_TYPE};base64,{base64.b64encode(data).decode('ascii')}",
                }})
            summary = {"mode": "native", "documents": len(records), "partial": 0, "kept_chars": 0}
            return parts, summary
        logger.info("chat_documents.native_unavailable fallback=text missing=%d",
                    sum(1 for data in originals if not data))

    texts = []
    for record in records:
        try:
            texts.append(await redis.get(_text_key(user_id, upload_id, record["doc_id"])) or "")
        except Exception as exc:
            logger.warning("chat_documents.text_load_failed reason=%s", type(exc).__name__)
            texts.append("")
    budget = int(getattr(settings, "chat_upload_context_text_chars", 120_000))
    shares = allocate_budget([len(text) for text in texts], budget)
    parts, lines, partial, kept = [], [], 0, 0
    for record, text, share in zip(records, texts, shares):
        selected = select_passages(text, question, share)
        complete = len(selected) == len(text) and not record.get("text_truncated")
        partial += 0 if complete else 1
        kept += len(selected)
        if not text:
            lines.append(f"- {record['filename']}: text unavailable")
            continue
        lines.append(
            f"- {record['filename']}: complete text" if complete else
            f"- {record['filename']}: partial text, {len(selected):,} of {len(text):,} characters "
            "(opening plus passages most related to this question)"
        )
        part_type = PdfTextPart if record.get("media_type") == PDF_TYPE else AttachmentPart
        parts.append(part_type(type="text", text=f"Source document: {record['filename']}\n{selected}"))
    if not parts:
        return None
    summary = {"mode": "text", "documents": len(records), "partial": partial, "kept_chars": kept}
    return [_coverage_note(lines), *parts], summary
