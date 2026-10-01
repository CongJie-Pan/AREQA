"""Validated transport contracts shared by realtime routes and services."""

from typing import List, Literal

from pydantic import BaseModel, Field
from services.realtime.constants import (
    MAX_CONTEXT_MESSAGE_CHARS,
    MAX_CONTEXT_MESSAGES,
    MAX_SPEECH_READ_CHARS,
    REALTIME_DEFAULT_MODEL,
)


class RealtimeSessionRequest(BaseModel):
    """Client request for a short-lived OpenAI Realtime client secret.

    Args:
        model: Allowed Realtime model for this voice session.
        voice: Allowed output voice name.
        conversation_id: Safe correlation identifier used only in logs.
        interface_language: UI language used to localize session instructions.
        tutor_profile: Selected subject overlay; unknown values use general.
    """

    model: str = REALTIME_DEFAULT_MODEL
    voice: str = "marin"
    conversation_id: str = ""
    interface_language: Literal["zh-TW", "zh-CN", "en"] = "zh-TW"
    tutor_profile: str = "general"


class RealtimeContextMessage(BaseModel):
    """Sanitized recent message supplied by the browser-side tool bridge."""

    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=MAX_CONTEXT_MESSAGE_CHARS)


class RealtimeContextRequest(BaseModel):
    """Request body for the Realtime AREQA context tool endpoint."""

    conversation_id: str = ""
    messages: List[RealtimeContextMessage] = Field(default_factory=list, max_length=MAX_CONTEXT_MESSAGES)
    interface_language: Literal["zh-TW", "zh-CN", "en"] = "zh-TW"
    tutor_profile: str = "general"


class SpeechReadRequest(BaseModel):
    """Assistant text to render as spoken audio.

    Args:
        text: Already-normalized readback text from the browser. The backend
            bounds it before sending to OpenAI and never logs the raw content.
    """

    text: str = Field(default="", max_length=MAX_SPEECH_READ_CHARS)


class LiveKitAvatarSessionRequest(BaseModel):
    """Client request for an optional LiveKit-backed avatar voice session.

    Args:
        conversation_id: Safe correlation identifier used only to derive an
            opaque room name and structured logs.
        interface_language: UI language carried in dispatch metadata for the
            LiveKit agent.
        tutor_profile: Selected subject overlay sent to the LiveKit agent.
        messages: Bounded recent chat snapshot used by the LiveKit agent's
            AREQA context tool.
    """

    conversation_id: str = ""
    interface_language: Literal["zh-TW", "zh-CN", "en"] = "zh-TW"
    tutor_profile: str = "general"
    messages: List[RealtimeContextMessage] = Field(default_factory=list, max_length=MAX_CONTEXT_MESSAGES)


class LiveKitAvatarSessionResponse(BaseModel):
    """Browser-safe LiveKit connection metadata for avatar mode."""

    livekit_url: str
    token: str
    room_name: str
    participant_identity: str
    agent_name: str
    session_id: str
    expires_in: int
