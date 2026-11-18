"""Topic Finder (選題) topic-card API: read the card, adopt the AI draft, and pick a stage."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from services.conversation.topic_card import (
    COMPLETED_STAGE,
    FIRST_STAGE,
    TopicCardState,
    TopicCardUnavailable,
    topic_card_store,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class AdoptDraftRequest(BaseModel):
    """The card version the learner saw when adopting; stale versions are not adopted."""

    version: int = Field(ge=0, le=10_000)


class AdoptDraftResponse(BaseModel):
    state: TopicCardState
    adopted: bool


class SetStageRequest(BaseModel):
    """Stage 1-5, or 6 for done. The learner may jump to any stage."""

    stage: int = Field(ge=FIRST_STAGE, le=COMPLETED_STAGE)


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
async def adopt_topic_draft(
    conversation_id: str, payload: AdoptDraftRequest, current_user_id: str = Depends(get_current_user),
) -> AdoptDraftResponse:
    """Learner adopts the AI draft they are looking at; adds a version, keeps the stage."""

    try:
        result = await topic_card_store.adopt(current_user_id, conversation_id, payload.version)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    state, adopted = result
    logger.info("topic_card.draft_adopted conversation_id=%s adopted=%s stage=%s version=%s",
                conversation_id, adopted, state.stage, state.version)
    return AdoptDraftResponse(state=state, adopted=adopted)


@router.post("/api/v1/research-coach/{conversation_id}/stage")
async def set_topic_stage(
    conversation_id: str, payload: SetStageRequest, current_user_id: str = Depends(get_current_user),
) -> TopicCardState:
    """Learner picks a stage (forward or back); the AI never moves it."""

    try:
        state = await topic_card_store.set_stage(current_user_id, conversation_id, payload.stage)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    logger.info("topic_card.stage_set conversation_id=%s stage=%s version=%s",
                conversation_id, state.stage, state.version)
    return state
