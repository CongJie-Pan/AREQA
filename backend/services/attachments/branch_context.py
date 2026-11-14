"""Account-scoped, expiring text snapshots of uploaded chat documents."""

import json
import logging
import re
from typing import Any

from redis_client import get_redis
from services.conversation.attachment_budget import PdfTextPart
from services.realtime.speaking_material import MATERIAL_TTL_SECONDS

logger = logging.getLogger(__name__)
_UPLOAD_ID = re.compile(r"[a-fA-F0-9-]{36}")


def _key(user_id: str, upload_id: str) -> str:
    return f"chat_upload_context:{user_id}:{upload_id}"


async def remember_upload(user_id: str | None, turn: dict[str, str], material: dict | None, *, pdf: bool) -> None:
    """Keep the first extracted snapshot for an upload turn."""
    upload_id = turn.get("message_id", "")
    if not user_id or not material or not _UPLOAD_ID.fullmatch(upload_id):
        return
    try:
        await get_redis().set(_key(user_id, upload_id), json.dumps({**material, "pdf": pdf}),
                              ex=MATERIAL_TTL_SECONDS, nx=True)
    except Exception as exc:
        logger.warning("chat_upload_context.save_failed reason=%s", type(exc).__name__)


async def load_inherited_upload(user_id: str | None, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Reuse the latest inherited document associated with this history prefix."""
    if not user_id:
        return []
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        source_id = message.get("attachment_source_id", "")
        if not source_id:
            # A more recent upload in this branch takes precedence.
            if message.get("has_upload") == "true":
                source_id = message.get("message_id", "")
            else:
                continue
        if not _UPLOAD_ID.fullmatch(source_id):
            return []
        try:
            raw = await get_redis().get(_key(user_id, source_id))
            if not raw:
                return []
            document = json.loads(raw)
            text = f"Source document: {document['title']}\n{document['text']}"
            if document.get("truncated"):
                text += "\n[Only the beginning of the source document is available.]"
            if document.get("pdf"):
                return [PdfTextPart(type="text", text=text)]
            return [{"type": "text", "text": text}]
        except Exception as exc:
            logger.warning("chat_upload_context.load_failed reason=%s", type(exc).__name__)
            return []
    return []
