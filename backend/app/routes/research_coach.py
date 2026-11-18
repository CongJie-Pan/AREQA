"""Topic Finder (選題) topic-card API: read the card and confirm the current stage."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from services.conversation.topic_card import TopicCardState, TopicCardUnavailable, topic_card_store

router = APIRouter()
logger = logging.getLogger(__name__)


class ConfirmStageRequest(BaseModel):
    """The card version the learner saw when confirming; stale versions never advance."""

    version: int = Field(ge=0, le=10_000)


class ConfirmStageResponse(BaseModel):
    state: TopicCardState
    advanced: bool


@router.get("/api/v1/research-coach/{conversation_id}/card")
async def get_topic_card(conversation_id: str, current_user_id: str = Depends(get_current_user)) -> TopicCardState:
    """Return the owner's topic card; 404 when the conversation is not theirs (or not synced yet)."""

    try:
        state = await topic_card_store.load(current_user_id, conversation_id)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return state


@router.post("/api/v1/research-coach/{conversation_id}/confirm")
async def confirm_topic_stage(
    conversation_id: str, payload: ConfirmStageRequest, current_user_id: str = Depends(get_current_user),
) -> ConfirmStageResponse:
    """Learner confirms the current stage; adopts the pending draft and advances one stage."""

    try:
        result = await topic_card_store.confirm(current_user_id, conversation_id, payload.version)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    state, advanced = result
    logger.info("topic_card.stage_confirmed conversation_id=%s advanced=%s stage=%s version=%s",
                conversation_id, advanced, state.stage, state.version)
    return ConfirmStageResponse(state=state, advanced=advanced)
