"""Topic Finder (選題) topic-card API: read the card, adopt or decline the AI draft, pick a stage, and set a focus gap aside."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from services.conversation.topic_card import (
    COMPLETED_STAGE,
    FIRST_STAGE,
    FOCUS_ID_PATTERN,
    TopicCardUnavailable,
    TopicCardView,
    card_view,
    topic_card_store,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class AdoptDraftRequest(BaseModel):
    """The card version the learner saw when adopting or declining; stale versions change nothing."""

    version: int = Field(ge=0, le=10_000)


class AdoptDraftResponse(BaseModel):
    state: TopicCardView
    adopted: bool


class SetStageRequest(BaseModel):
    """Stage 1-5, or 6 for done. The learner may jump to any stage."""

    stage: int = Field(ge=FIRST_STAGE, le=COMPLETED_STAGE)


class SkipFocusRequest(BaseModel):
    """The focus gap id the learner set aside (ids never carry card text)."""

    gap_id: str = Field(pattern=FOCUS_ID_PATTERN.pattern, max_length=81)


@router.get("/api/v1/research-coach/{conversation_id}/card")
async def get_topic_card(conversation_id: str, current_user_id: str = Depends(get_current_user)) -> TopicCardView:
    """Return the owner's topic card; 404 when the conversation is not theirs (or not synced yet)."""

    try:
        state = await topic_card_store.load(current_user_id, conversation_id)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return card_view(state)


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
    review_stages = ",".join(map(str, state.review.stages)) if adopted and state.review else "-"
    logger.info("topic_card.draft_adopted conversation_id=%s adopted=%s stage=%s version=%s review_stages=%s",
                conversation_id, adopted, state.stage, state.version, review_stages)
    return AdoptDraftResponse(state=card_view(state), adopted=adopted)


class RejectDraftResponse(BaseModel):
    state: TopicCardView
    rejected: bool


@router.post("/api/v1/research-coach/{conversation_id}/reject")
async def reject_topic_draft(
    conversation_id: str, payload: AdoptDraftRequest, current_user_id: str = Depends(get_current_user),
) -> RejectDraftResponse:
    """Learner declines the AI draft they are looking at; the adopted card and version stay as they were."""

    try:
        result = await topic_card_store.reject(current_user_id, conversation_id, payload.version)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    state, rejected = result
    logger.info("topic_card.draft_rejected conversation_id=%s rejected=%s stage=%s version=%s",
                conversation_id, rejected, state.stage, state.version)
    return RejectDraftResponse(state=card_view(state), rejected=rejected)


@router.post("/api/v1/research-coach/{conversation_id}/stage")
async def set_topic_stage(
    conversation_id: str, payload: SetStageRequest, current_user_id: str = Depends(get_current_user),
) -> TopicCardView:
    """Learner picks a stage (forward or back); the AI never moves it."""

    try:
        state = await topic_card_store.set_stage(current_user_id, conversation_id, payload.stage)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    logger.info("topic_card.stage_set conversation_id=%s stage=%s version=%s",
                conversation_id, state.stage, state.version)
    return card_view(state)


@router.post("/api/v1/research-coach/{conversation_id}/focus/skip")
async def skip_topic_focus(
    conversation_id: str, payload: SkipFocusRequest, current_user_id: str = Depends(get_current_user),
) -> TopicCardView:
    """Learner sets the current focus gap aside; the coach then moves to the next gap or the stage goal."""

    try:
        state = await topic_card_store.skip_focus(current_user_id, conversation_id, payload.gap_id)
    except TopicCardUnavailable:
        raise HTTPException(status_code=503, detail="Topic card unavailable") from None
    if state is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    logger.info("topic_card.focus_skipped conversation_id=%s stage=%s focus_kind=%s skipped=%s",
                conversation_id, state.stage, payload.gap_id.split(":", 1)[0], len(state.skipped_focus))
    return card_view(state)
