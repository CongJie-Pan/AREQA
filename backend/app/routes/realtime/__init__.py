"""Realtime HTTP router and compatibility exports for existing callers.

Services own provider calls; this package only composes route registration.
"""

import httpx as httpx
from config import settings as settings
from fastapi import APIRouter
from services.realtime.diagnostics import (
    _live_tutor_debug_logs_enabled as _live_tutor_debug_logs_enabled,
)
from services.realtime.diagnostics import (
    _realtime_debug_logs_enabled as _realtime_debug_logs_enabled,
)
from services.realtime.diagnostics import (
    _realtime_upstream_error as _realtime_upstream_error,
)
from services.realtime.diagnostics import (
    _safe_realtime_user_identifier as _safe_realtime_user_identifier,
)
from services.realtime.livekit_metadata import (
    _livekit_avatar_agent_metadata as _livekit_avatar_agent_metadata,
)
from services.realtime.livekit_metadata import (
    _livekit_avatar_memory_items as _livekit_avatar_memory_items,
)
from services.realtime.livekit_metadata import (
    _livekit_avatar_room_name as _livekit_avatar_room_name,
)
from services.realtime.livekit_metadata import (
    _livekit_avatar_session_id as _livekit_avatar_session_id,
)
from services.realtime.livekit_metadata import (
    _livekit_participant_identity as _livekit_participant_identity,
)
from services.realtime.livekit_metadata import (
    _safe_livekit_fragment as _safe_livekit_fragment,
)
from services.realtime.models import (
    LiveKitAvatarSessionRequest as LiveKitAvatarSessionRequest,
)
from services.realtime.models import (
    LiveKitAvatarSessionResponse as LiveKitAvatarSessionResponse,
)
from services.realtime.models import RealtimeContextMessage as RealtimeContextMessage
from services.realtime.models import RealtimeContextRequest as RealtimeContextRequest
from services.realtime.models import RealtimeSessionRequest as RealtimeSessionRequest
from services.realtime.models import SpeechReadRequest as SpeechReadRequest
from services.realtime.openai_session import (
    _client_secret_from_response as _client_secret_from_response,
)
from services.realtime.session_config import (
    _build_realtime_instructions as _build_realtime_instructions,
)
from services.realtime.session_config import (
    _build_realtime_parts_context as _build_realtime_parts_context,
)
from services.realtime.session_config import (
    _build_realtime_session_config as _build_realtime_session_config,
)
from services.realtime.session_config import (
    _build_realtime_transcription_config as _build_realtime_transcription_config,
)
from services.realtime.session_config import (
    _build_speech_transcription_prompt as _build_speech_transcription_prompt,
)
from services.realtime.session_config import _normalize_model as _normalize_model
from services.realtime.session_config import _normalize_voice as _normalize_voice
from services.realtime.speech import _read_bounded_upload as _read_bounded_upload

from . import attachments, context, sessions, speech

router = APIRouter()
router.include_router(sessions.router)
create_livekit_avatar_session = sessions.create_livekit_avatar_session
create_realtime_session = sessions.create_realtime_session
router.include_router(speech.router)
transcribe_speech = speech.transcribe_speech
read_speech = speech.read_speech
router.include_router(context.router)
get_realtime_context = context.get_realtime_context
router.include_router(attachments.router)
upload_realtime_attachments = attachments.upload_realtime_attachments
