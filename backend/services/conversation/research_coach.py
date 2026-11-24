"""Topic Finder (選題) conversation kind and its prompt overlay.

A conversation's kind is fixed when it is created. ``research_coach``
conversations get the research-topic coach skill on top of the general pedagogy
skill, and never combine it with subject tutor overlays or image generation.
The client sends the kind; the backend normalizes it against an allowlist so an
unknown value can only fall back to ordinary chat.
"""

from __future__ import annotations

import logging
from typing import Literal

from services.conversation.tutor_profile import TutorProfileId, render_tutor_profile_prompt
from services.prompt_skills import load_prompt_skill

logger = logging.getLogger(__name__)

ConversationKind = Literal["chat", "research_coach"]
PromptProfileId = Literal["general", "english", "research_coach"]

RESEARCH_COACH_KIND: ConversationKind = "research_coach"
RESEARCH_COACH_SKILL_ID = "RESEARCH_TOPIC_COACH_SKILL_V5"
RESEARCH_COACH_SKILL_PATH = "backend/prompts/skills/research_topic_coach_skill.md"
# Answer token cap for coach turns (not applied when the learner forces thinking).
TOPIC_FINDER_MAX_TOKENS = 1200


def normalize_conversation_kind(value: object) -> ConversationKind:
    """Return a supported conversation kind.

    Args:
        value: Raw client-provided kind.

    Returns:
        ``"research_coach"`` only for that exact value (case-insensitive,
        trimmed); anything else, including non-strings, is ``"chat"``.
    """

    if isinstance(value, str) and value.strip().lower() == RESEARCH_COACH_KIND:
        return RESEARCH_COACH_KIND
    return "chat"


def resolve_prompt_profile(tutor_profile: TutorProfileId, conversation_kind: ConversationKind) -> PromptProfileId:
    """Pick the single prompt overlay for this turn.

    Topic Finder conversations always use the coach overlay, so a stale
    English Tutor selection cannot leak into them.
    """

    return RESEARCH_COACH_KIND if conversation_kind == RESEARCH_COACH_KIND else tutor_profile


def is_research_coach(prompt_profile: object) -> bool:
    """Return whether an internal prompt profile is the Topic Finder coach."""

    return prompt_profile == RESEARCH_COACH_KIND


def render_research_coach_prompt() -> str:
    """Render the coach skill as a bounded prompt block.

    Returns:
        The coach block, or an empty string when the skill cannot be loaded.
        The empty fallback keeps the conversation usable with the general
        pedagogy skill; the loader already logged the safe failure reason.
    """

    payload = load_prompt_skill("research-topic-coach")
    if payload is None:
        logger.warning("research_coach.skill_fallback skill_id=%s fallback=general", RESEARCH_COACH_SKILL_ID)
        return ""
    rules = "\n".join(f"- {rule}" for rule in payload["rules"])
    return (
        "\n\n【Workspace：Topic Finder／選題（最後且優先的回答規則）】"
        "\n本區塊決定本回合的回答長度、格式與引導方式，優先於上方任何回答深度、格式或風格設定；"
        "但不得覆蓋回答語言、RAG/引用真實性、附件根據、記憶、安全或工具規則。"
        f"\n{rules}"
    )


def render_prompt_profile(prompt_profile: object) -> str:
    """Render the overlay for an internal prompt profile.

    Client-facing callers (for example realtime voice) keep using
    ``render_tutor_profile_prompt``, which never selects the coach overlay.
    """

    if is_research_coach(prompt_profile):
        return render_research_coach_prompt()
    return render_tutor_profile_prompt(prompt_profile)
