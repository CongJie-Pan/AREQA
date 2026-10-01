"""Provider endpoints and bounded voice input limits."""

import os

REALTIME_CLIENT_SECRET_URL = "https://api.openai.com/v1/realtime/client_secrets"
OPENAI_AUDIO_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_AUDIO_SPEECH_URL = "https://api.openai.com/v1/audio/speech"
REALTIME_DEFAULT_MODEL = "gpt-realtime-2.1-mini"
SPEECH_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
SPEECH_READ_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
SPEECH_READ_VOICE = os.environ.get("OPENAI_TTS_VOICE", "cedar")
MAX_SPEECH_READ_CHARS = 4096
REALTIME_ALLOWED_MODELS = frozenset({"gpt-realtime-2.1-mini", "gpt-realtime-2.1"})
REALTIME_ALLOWED_VOICES = frozenset({
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "marin",
    "sage",
    "shimmer",
    "verse",
})
MAX_CONTEXT_MESSAGES = 24
MAX_CONTEXT_MESSAGE_CHARS = 6000
MAX_LIVEKIT_CONTEXT_MESSAGES = 8
MAX_LIVEKIT_CONTEXT_MESSAGE_CHARS = 1000
MAX_LIVEKIT_CONTEXT_TOTAL_CHARS = 6000
MAX_LIVEKIT_MEMORY_ITEMS = 4
MAX_LIVEKIT_MEMORY_ITEM_CHARS = 500
MAX_LIVEKIT_TUTOR_PROMPT_CHARS = 6000
MAX_SPEECH_AUDIO_BYTES = 25 * 1024 * 1024
