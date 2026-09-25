"""Short-lived, conversation-scoped source material for English voice practice."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from redis_client import get_redis

logger = logging.getLogger(__name__)
MATERIAL_TTL_SECONDS = 48 * 60 * 60
MAX_MATERIAL_CHARS = 40_000
MAX_VOICE_EXCERPT_CHARS = 12_000


def _key(user_id: str | None, conversation_id: str) -> str:
    scope = f"{user_id or 'guest'}:{conversation_id}"
    return "speaking_material:" + hashlib.sha256(scope.encode()).hexdigest()


def extract_material(attachments: list[Any]) -> dict[str, Any] | None:
    """Extract text from validated text/PDF uploads, with no image guessing."""

    sections: list[str] = []
    names: list[str] = []
    for attachment in attachments:
        text = ""
        if attachment.media_type in {"text/plain", "text/markdown"}:
            text = str(getattr(attachment, "plain_text", "") or "")
        elif attachment.media_type == "application/pdf" and attachment.pdf_bytes:
            try:
                import fitz

                with fitz.open(stream=attachment.pdf_bytes, filetype="pdf") as document:
                    pages: list[str] = []
                    remaining = MAX_MATERIAL_CHARS + 1
                    for page in document:
                        page_text = page.get_text()[:remaining]
                        pages.append(page_text)
                        remaining -= len(page_text)
                        if remaining <= 0:
                            break
                    text = "\n".join(pages)
            except Exception as exc:
                logger.warning("speaking_material.pdf_extraction_failed reason=%s", type(exc).__name__)
        if text.strip():
            names.append(attachment.filename)
            sections.append(text.strip())
    if not sections:
        return None
    full_text = "\n\n".join(sections)
    return {"title": ", ".join(names)[:300], "text": full_text[:MAX_MATERIAL_CHARS], "truncated": len(full_text) > MAX_MATERIAL_CHARS}


def extract_pasted_material(message: str) -> dict[str, Any] | None:
    """Recognize an actual pasted dialogue, excluding ordinary requests about one."""

    text = message.strip()
    if len(text) < 10:
        return None
    speaker_lines = re.findall(
        r"(?im)^\s*(?:speaker\s*\d*|student|professor|interviewer|teacher|[ab]|學生|教授|老師|甲|乙)\s*[:：]",
        text,
    )
    labeled_long_text = len(text) >= 250 and bool(re.search(r"逐字稿|对话稿|transcript|dialogue", text[:250], re.I))
    if len(speaker_lines) < 2 and not labeled_long_text:
        return None
    return {"title": "Pasted dialogue", "text": text[:MAX_MATERIAL_CHARS], "truncated": len(text) > MAX_MATERIAL_CHARS}


async def save_material(user_id: str | None, conversation_id: str, material: dict[str, Any]) -> bool:
    """Keep one latest source per conversation; Redis errors leave chat usable."""

    if not conversation_id or not material.get("text"):
        return False
    try:
        await get_redis().set(_key(user_id, conversation_id), json.dumps(material), ex=MATERIAL_TTL_SECONDS)
        logger.info("speaking_material.saved chars=%s", len(material["text"]))
        return True
    except Exception as exc:
        logger.warning("speaking_material.save_failed reason=%s", type(exc).__name__)
        return False


async def load_material(user_id: str | None, conversation_id: str) -> dict[str, Any] | None:
    if not conversation_id:
        return None
    try:
        raw = await get_redis().get(_key(user_id, conversation_id))
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("speaking_material.load_failed reason=%s", type(exc).__name__)
        return None


def voice_excerpt(material: dict[str, Any] | None) -> dict[str, Any] | None:
    if not material:
        return None
    text = str(material.get("text") or "")
    return {
        "title": str(material.get("title") or "")[:300],
        "text": text[:MAX_VOICE_EXCERPT_CHARS],
        "truncated": bool(material.get("truncated")) or len(text) > MAX_VOICE_EXCERPT_CHARS,
    }
