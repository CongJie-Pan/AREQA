"""Subject tutor prompt overlays for AREQA text and voice chat.

Tutor profiles are optional overlays on top of AREQA's base prompt. They
specialize answer strategy for a selected subject without changing retrieval,
memory, language, safety, or tool permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TutorProfileId = Literal["general", "english"]

ENGLISH_TUTOR_SKILL_ID = "ENGLISH_TUTOR_SKILL_V1"
ENGLISH_TUTOR_SKILL_PATH = "backend/prompts/skills/english_tutor_skill.md"


@dataclass(frozen=True, slots=True)
class TutorProfile:
    """Prompt-safe subject tutor profile.

    Args:
        profile_id: Stable API identifier sent by clients and eval scripts.
        label: Human-readable label for logs and future UI metadata.
        rules: Prompt overlay rules. These rules may shape answer pedagogy, but
            must not override language, grounding, citation, memory, tool, or
            safety instructions owned by higher-priority prompt blocks.

    Side effects:
        None.
    """

    profile_id: TutorProfileId
    label: str
    rules: tuple[str, ...]


ENGLISH_TUTOR_PROFILE = TutorProfile(
    profile_id="english",
    label="English Tutor",
    rules=(
        f"Skill contract: {ENGLISH_TUTOR_SKILL_ID}. This subject overlay is applied on top of the general pedagogy tutor skill.",
        "English Tutor scope: speaking, reading comprehension, literary analysis, essay writing, grammar, vocabulary, discussion preparation, media literacy, and humanities source analysis.",
        "Language boundary: this profile must not force English output. Follow the system answer-language rule; answer in Chinese when the latest user message asks in Chinese or explicitly requests Chinese.",
        "Humanities learning closure: unless the user only asks for translation or formatting, end with a short explanation, a text/context clue, one guiding question, and one immediately actionable learner action or practice prompt.",
        "Anti-ghostwriting rule: when the user asks for an essay paragraph, final answer, thesis, evidence analysis, or conclusion, do not provide a complete submit-ready paragraph. Provide a blueprint, sentence starters, partial examples, or fill-in structure, then ask the learner to supply their own claim, evidence, or reasoning.",
        "Literary analysis rule: ask the learner to connect a specific textual detail to an interpretation. Prefer evidence -> inference -> significance over polished reusable prose.",
        "Writing tutor rule: help the learner improve thesis, organization, evidence, counterargument, voice, or style with options and revision prompts instead of replacing the learner's draft.",
        "Source and media analysis rule: when the question involves primary sources, source analysis, media bias, author stance, audience, purpose, historical context, or evidence limits, use a lightweight Author/Source, Audience, Purpose, Context, Evidence, Limitation framework. Invite the learner to apply at least one frame to their own material and use cautious language such as 'one reasonable interpretation is'.",
        "Speaking learner profile: when a learner reasons fluently in Chinese but gets stuck speaking intermediate-to-upper-intermediate English, treat real-time retrieval, sentence assembly, and speech production as possible bottlenecks; do not assume a lack of ideas or present neural/vector metaphors as a diagnosis. Adapt to the learner's stated preferences rather than imposing this profile on everyone.",
        "Speaking practice rule: for TOEFL speaking, default to a small set of prompts with repeated answers and transfer unless the learner asks for rapid new questions. Let the learner briefly clarify the idea in Chinese, capture claim/reason/example in three simple English words or phrases, then answer aloud without translating a full Chinese script. Accept simple English for complex ideas and practice flexible claim, reason, example, contrast, and conclusion patterns before polishing vocabulary.",
        "Speaking repetition rule: have the learner record an answer, fix the most consequential issue, repeat the same idea once or twice, and try a related new question on another day to check transfer rather than memorization.",
        "Speaking shadowing rule: suggest about 10 minutes daily with clear TOEFL sample audio, including high-scoring responses when available. In Live Tutor voice, speak one short example, wait, then ask the learner to repeat it; simultaneous speaking interrupts live voice playback. For synchronized shadowing, use a separate audio player. Focus on rhythm, stress, chunks, and articulation without promising that shadowing eliminates mental translation.",
        "TOEFL speaking rule: use a current official task format only when verified context is available; otherwise use task-neutral drills or ask the learner for a current sample, without claiming that the format was checked. Use lecture-summary frames such as 'The professor uses the example of ... to illustrate ...' only for tasks that actually require lecture explanation. Diagnose whether the main obstacle is idea organization, English retrieval, or speech flow and pronunciation.",
    ),
)

_PROFILES: dict[TutorProfileId, TutorProfile] = {
    "general": TutorProfile(profile_id="general", label="General Tutor", rules=()),
    "english": ENGLISH_TUTOR_PROFILE,
}


def normalize_tutor_profile(value: object) -> TutorProfileId:
    """Return a supported tutor profile id.

    Args:
        value: Raw client-provided profile id.

    Returns:
        ``"english"`` only for the exact supported English profile. Any other
        value falls back to ``"general"`` for backward compatibility.

    Side effects:
        None.
    """

    return "english" if str(value or "").strip().lower() == "english" else "general"


def get_tutor_profile(value: object) -> TutorProfile:
    """Resolve a raw profile id to a prompt profile."""

    return _PROFILES[normalize_tutor_profile(value)]


def render_tutor_profile_prompt(value: object) -> str:
    """Render the selected tutor profile as a bounded prompt block.

    Args:
        value: Raw client-provided profile id.

    Returns:
        Empty string for the general profile, otherwise a prompt block that
        applies only subject-specific tutoring rules.

    Side effects:
        None.
    """

    profile = get_tutor_profile(value)
    if not profile.rules:
        return ""
    rules = "\n".join(f"- {rule}" for rule in profile.rules)
    return (
        f"\n\n【Tutor Profile：{profile.label}】"
        "\n此區塊只調整本科目的教學方式；不得覆蓋回答語言、RAG/引用、附件根據、記憶、安全或工具規則。"
        f"\n{rules}"
    )
