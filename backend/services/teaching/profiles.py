"""Declarative teaching capabilities per prompt profile.

Prompt wording lives in ``tutor_profile`` and the skill files; this table says
what a profile may do and how its answers are shaped, so callers ask about a
capability instead of checking for a specific profile.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.conversation.research_coach import RESEARCH_COACH_KIND, TOPIC_FINDER_MAX_TOKENS


@dataclass(frozen=True, slots=True)
class ProfileCapabilities:
    """What one prompt profile allows and how it shapes answers.

    Attributes:
        auto_web_search: Whether AUTO search mode may search on the learner's behalf.
        image_slots: Whether answers may carry images; ``False`` also removes the image tool.
        paper_auto_explain: Whether the generic PDF walkthrough may be forced.
        max_answer_tokens: Optional answer cap; not applied when thinking is forced.
        response_policy_overlay: Whether the per-turn response strategy is rendered.
        overlay_last: Render the profile overlay after every other block, so later
            style overlays cannot outweigh it.
    """

    auto_web_search: bool = True
    image_slots: bool = True
    paper_auto_explain: bool = True
    max_answer_tokens: int | None = None
    response_policy_overlay: bool = True
    overlay_last: bool = False


_DEFAULT = ProfileCapabilities()

_CAPABILITIES: dict[str, ProfileCapabilities] = {
    # Topic Finder coaches learners to search and read for themselves in short turns.
    RESEARCH_COACH_KIND: ProfileCapabilities(
        auto_web_search=False,
        image_slots=False,
        paper_auto_explain=False,
        max_answer_tokens=TOPIC_FINDER_MAX_TOKENS,
        response_policy_overlay=False,
        overlay_last=True,
    ),
}


def capabilities_for(prompt_profile: object) -> ProfileCapabilities:
    """Return the capabilities of a prompt profile; unknown profiles get the defaults."""

    return _CAPABILITIES.get(prompt_profile, _DEFAULT) if isinstance(prompt_profile, str) else _DEFAULT
