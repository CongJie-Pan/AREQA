"""AREQA LiveKit agent with OpenAI Realtime voice and Anam avatar output.

This worker is intentionally separate from the FastAPI backend. LiveKit Agents
run as long-lived workers that receive room dispatches from LiveKit, while the
main AREQA backend only mints browser-safe room tokens.
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, room_io
from livekit.plugins import anam, openai

logger = logging.getLogger("areqa.livekit_agent")
load_dotenv(".env.local")
load_dotenv("../.env")

AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "areqa-live-tutor")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1-mini")
OPENAI_REALTIME_VOICE = os.getenv("OPENAI_REALTIME_VOICE", "marin")
ANAM_AVATAR_NAME = os.getenv("ANAM_AVATAR_NAME", "Mei")
ANAM_AVATAR_ID = os.getenv("ANAM_AVATAR_ID", "").strip()


def _instructions(interface_language: str) -> str:
    """Build concise spoken instructions for the LiveKit avatar agent.

    Args:
        interface_language: Language code supplied by the room dispatch
            metadata. Unknown values fall back to Traditional Chinese.

    Returns:
        Voice-friendly agent instructions with no markdown requirements.
    """

    answer_language = {
        "zh-CN": "Simplified Chinese",
        "en": "English",
    }.get(interface_language, "Traditional Chinese")
    return " ".join(
        [
            "You are AREQA Live Tutor, the realtime voice mode of AREQA.",
            "This product name is pronounced ah-ray-kah.",
            "When speaking Mandarin, call yourself 阿瑞卡 and continue naturally.",
            f"Respond in {answer_language} unless the learner clearly asks for another language.",
            "Keep replies concise, spoken, and easy to interrupt.",
            "Use one to three short sentences, then ask exactly one short open question when useful.",
            "Do not use markdown, bullets, emojis, asterisks, or visual formatting.",
        ]
    )


def _dispatch_metadata(ctx: agents.JobContext) -> dict[str, str]:
    """Parse bounded metadata from the room dispatch.

    Args:
        ctx: LiveKit job context.

    Returns:
        String metadata with safe defaults. The backend only sends opaque
        correlation values and language, never credentials or raw transcript.
    """

    raw = getattr(ctx.job, "metadata", "") or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("livekit_agent.metadata_invalid")
        return {"interface_language": "zh-TW", "conversation_id": ""}
    return {
        "interface_language": str(payload.get("interface_language") or "zh-TW"),
        "conversation_id": str(payload.get("conversation_id") or ""),
    }


class AreqaLiveTutor(Agent):
    """Voice-first AREQA tutor persona used inside LiveKit rooms."""

    def __init__(self, *, interface_language: str) -> None:
        """Create the LiveKit voice agent.

        Args:
            interface_language: UI language from dispatch metadata.
        """

        super().__init__(instructions=_instructions(interface_language))


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def areqa_live_tutor(ctx: agents.JobContext) -> None:
    """Handle one dispatched LiveKit avatar room.

    Args:
        ctx: LiveKit job context with room and dispatch metadata.

    Side Effects:
        Starts an OpenAI Realtime-backed AgentSession. When `ANAM_AVATAR_ID` is
        configured, starts the Anam avatar before the agent speaks and waits for
        its video track. If Anam is not configured, the voice agent still runs
        so the frontend can fall back to the AREQA logo.
    """

    metadata = _dispatch_metadata(ctx)
    logger.info(
        "livekit_agent.session_starting room=%s agent_name=%s avatar_configured=%s conversation_id=%s",
        ctx.room.name,
        AGENT_NAME,
        bool(ANAM_AVATAR_ID),
        metadata["conversation_id"],
    )
    session = AgentSession(
        llm=openai.realtime.RealtimeModel(
            model=OPENAI_REALTIME_MODEL,
            voice=OPENAI_REALTIME_VOICE,
        )
    )

    if ANAM_AVATAR_ID:
        avatar = anam.AvatarSession(
            persona_config=anam.PersonaConfig(
                name=ANAM_AVATAR_NAME,
                avatarId=ANAM_AVATAR_ID,
            )
        )
        await avatar.start(session, room=ctx.room)
        await avatar.wait_for_join()
        logger.info(
            "livekit_agent.avatar_joined room=%s agent_name=%s avatar_name=%s",
            ctx.room.name,
            AGENT_NAME,
            ANAM_AVATAR_NAME,
        )
    else:
        logger.warning("livekit_agent.avatar_skipped room=%s reason=missing_anam_avatar_id", ctx.room.name)

    await session.start(
        room=ctx.room,
        agent=AreqaLiveTutor(interface_language=metadata["interface_language"]),
        room_options=room_io.RoomOptions(
            audio_output=not bool(ANAM_AVATAR_ID),
        ),
    )
    await session.generate_reply(
        instructions="Greet the learner briefly and ask what they want to work on."
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
