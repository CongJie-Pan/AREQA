"""Mailbox API routes for the AREQA backend.

The mailbox product surface is feature-gated and archived by default. This
router preserves the existing endpoint paths while `backend.main` re-exports
request models and helpers for legacy tests and patch points.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
import sys
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user

router = APIRouter()
logger = logging.getLogger("backend.main")


def _main_module():
    return (
        sys.modules.get("backend.main")
        or sys.modules.get("main")
        or importlib.import_module("main")
    )


def _get_mailbox_store():
    return _main_module().get_mailbox_store()

def _ensure_mailbox_feature_enabled(current_user_id: str) -> None:
    """Fail closed when the archived mailbox product surface is disabled.

    Args:
        current_user_id: Authenticated user identifier used only as safe
            operational metadata for the structured log.

    Raises:
        HTTPException: 404 when the mailbox feature is archived for this
            deployment. The 404 preserves the public API boundary by making the
            disabled product surface behave as unavailable rather than merely
            empty.

    Side Effects:
        Emits the stable `mailbox.feature_disabled` info log with user_id as the
        only metadata. The log deliberately excludes mail content, prompts,
        tokens, and mailbox identifiers.
    """

    from config import settings

    if settings.enable_mailbox_feature:
        return
    logger.info("mailbox.feature_disabled user_id=%s", current_user_id)
    raise HTTPException(status_code=404, detail="Mailbox feature is disabled")

@router.get("/api/v1/mailbox")
async def fetch_mailbox(current_user_id: str = Depends(get_current_user)):
    _ensure_mailbox_feature_enabled(current_user_id)
    store = _get_mailbox_store()
    return {
        "mails": await store.get_all_mails(current_user_id),
        "unread_count": await store.get_unread_count(current_user_id)
    }

class SendMailRequest(BaseModel):
    content: str
    recipient: str = "AREQA"
    conversation_id: Optional[str] = None

def _mailbox_reply_task_id(user_id: str, recipient: str, content: str, conversation_id: Optional[str]) -> str:
    window = int(time.time() // 600)
    normalized = " ".join(content.split())
    source = f"{user_id}|{recipient}|{conversation_id or ''}|{normalized}|{window}"
    return f"reply-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:32]}"

@router.post("/api/v1/mailbox/send")
async def send_mail_endpoint(req: SendMailRequest, current_user_id: str = Depends(get_current_user)):
    from config import settings

    _ensure_mailbox_feature_enabled(current_user_id)

    if not settings.enable_mailbox_sending:
        logger.info("mailbox.send_disabled user_id=%s", current_user_id)
        raise HTTPException(status_code=503, detail="Mailbox sending is disabled")

    store = _get_mailbox_store()
    # The original mailbox reply flow is preserved behind ENABLE_MAILBOX_SENDING
    # so it can be re-enabled without rebuilding the feature.
    mail_id = await store.add_mail(user_id=current_user_id, sender="User", content=req.content, recipient=req.recipient, conversation_id=req.conversation_id)
    await store.mark_as_read(user_id=current_user_id, mail_id=mail_id)
    await store.schedule_delayed_mail(
        user_id=current_user_id,
        mail_data={
            "reply_to_mail_id": mail_id,
            "reply_content": req.content,
            "active_avatar": req.recipient,
            "conversation_id": req.conversation_id or mail_id,
            "task_id": _mailbox_reply_task_id(current_user_id, req.recipient, req.content, req.conversation_id),
        },
        delay_seconds=300,
    )
    return {"status": "success", "mail_id": mail_id}

@router.post("/api/v1/mailbox/read/{mail_id}")
async def read_mail_endpoint(mail_id: str, current_user_id: str = Depends(get_current_user)):
    _ensure_mailbox_feature_enabled(current_user_id)
    store = _get_mailbox_store()
    success = await store.mark_as_read(user_id=current_user_id, mail_id=mail_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mail not found")
    return {"status": "success"}
