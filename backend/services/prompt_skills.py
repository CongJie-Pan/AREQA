"""Load allowlisted prompt payloads without injecting skill maintenance prose."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

logger = logging.getLogger(__name__)

_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "prompts" / "skills"
_MAX_SKILL_BYTES = 64 * 1024
_BEGIN = "<!-- AREQA_RUNTIME_PROMPT_BEGIN -->"
_END = "<!-- AREQA_RUNTIME_PROMPT_END -->"
_SCHEMAS = {
    "pedagogy-tutor": (
        "pedagogy_tutor_skill.md",
        {
            "identity": str,
            "opening_rule": str,
            "task_fit_rule": str,
            "escalation_rule": str,
            "explanation_order_rule": str,
            "cognitive_load_rule": str,
            "followup_rule": str,
            "expression_rule": str,
            "learnlm_rules": list,
            "visual_rule": str,
        },
    ),
    "english-tutor": ("english_tutor_skill.md", {"rules": list}),
    "paper-auto-explain": ("paper_auto_explain_skill.md", {"instruction": str}),
}

PromptPayload = Mapping[str, str | tuple[str, ...]]


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys rather than silently overriding a rule."""

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


@lru_cache(maxsize=3)
def load_prompt_skill(skill_id: str) -> PromptPayload | None:
    """Return an immutable validated payload, or cache a fail-soft result.

    Only fixed application-owned skill IDs are accepted; callers cannot select
    arbitrary files. Both successful and failed loads remain cached until the
    process restarts. Logs include only the skill ID and a bounded reason, never
    file content, JSON parser diagnostics, user text, or credentials.
    """

    if skill_id not in _SCHEMAS:
        raise ValueError("Unsupported prompt skill")
    filename, schema = _SCHEMAS[skill_id]
    try:
        with (_SKILLS_ROOT / filename).open("rb") as source:
            raw = source.read(_MAX_SKILL_BYTES + 1)
        if len(raw) > _MAX_SKILL_BYTES:
            raise ValueError("oversized")
        document = raw.decode("utf-8")
        if document.count(_BEGIN) != 1 or document.count(_END) != 1:
            raise ValueError("invalid_markers")
        payload_text = document.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()
        match = re.fullmatch(r"```json\s*\n(.*?)\n```", payload_text, re.DOTALL)
        if not match:
            raise ValueError("invalid_payload_block")
        payload = json.loads(match[1], object_pairs_hook=_unique_object)
        if not isinstance(payload, dict) or payload.keys() != schema.keys():
            raise ValueError("invalid_fields")
        validated: dict[str, str | tuple[str, ...]] = {}
        for key, expected_type in schema.items():
            value = payload[key]
            if expected_type is str:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("invalid_string")
                validated[key] = value
            else:
                if (
                    not isinstance(value, list)
                    or not 1 <= len(value) <= 32
                    or any(not isinstance(item, str) or not item.strip() for item in value)
                ):
                    raise ValueError("invalid_rules")
                validated[key] = tuple(value)
    except (OSError, UnicodeError, ValueError):
        logger.warning("prompt_skill.fallback skill_id=%s reason=unreadable_or_invalid", skill_id)
        return None

    logger.info("prompt_skill.loaded skill_id=%s", skill_id)
    return MappingProxyType(validated)


def preload_prompt_skills() -> None:
    """Warm the three prompt payloads before serving application requests."""

    for skill_id in _SCHEMAS:
        load_prompt_skill(skill_id)
