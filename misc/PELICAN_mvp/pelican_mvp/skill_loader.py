"""Validated loading for executable PELICAN domain skills."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .domain_catalog import resolve_domain_category
from .domain_skill import DomainCategory, DomainSkill
from .observability import log_event
from .skill_validator import SkillValidationError, validate_domain_skill


class SkillLoadError(RuntimeError):
    """Raised when a skill asset cannot be safely loaded or validated."""


MAX_SKILL_FILE_BYTES = 128_000
SKILLS_DIR = Path(__file__).resolve().parents[1] / "domain_skills"
CATALOG_SKILLS = {
    "深度學習": "deep_learning",
    "deep learning": "deep_learning",
}


def load_skill(path: Path | str) -> DomainSkill:
    """Load and validate one local skill file.

    The MVP seed asset is JSON-compatible YAML so the standard library can parse
    it. If PyYAML is installed, ordinary YAML is also accepted. Topic-controlled
    input must not call this function directly; use ``load_catalog_skill``.
    """
    skill_path = Path(path).resolve()
    if not skill_path.is_file():
        log_event("pelican_skill_rejected", reason_code="skill_file_missing")
        raise SkillLoadError("skill file missing")
    if skill_path.stat().st_size > MAX_SKILL_FILE_BYTES:
        log_event("pelican_skill_rejected", reason_code="skill_file_too_large")
        raise SkillLoadError("skill file too large")

    try:
        payload = _parse_skill_payload(skill_path.read_text(encoding="utf-8"))
        skill = DomainSkill.from_dict(payload)
        validate_domain_skill(skill)
    except (OSError, ValueError, TypeError, SkillValidationError) as exc:
        log_event("pelican_skill_rejected", level=logging.WARNING, reason_code=type(exc).__name__)
        raise SkillLoadError(f"invalid skill: {type(exc).__name__}") from exc

    log_event(
        "pelican_skill_loaded",
        skill_id=skill.skill_id,
        skill_version=skill.version,
        domain_category=skill.domain_category.value,
        skill_lifecycle=skill.lifecycle.value,
        reason_code="validated",
    )
    return skill


def load_catalog_skill(topic: str) -> DomainSkill:
    """Resolve a topic to a known skill asset and load it without path traversal."""
    normalized_topic = topic.strip().lower()
    skill_slug = CATALOG_SKILLS.get(normalized_topic)
    if skill_slug is None:
        resolution = resolve_domain_category(topic)
        if resolution.category is DomainCategory.STEM and "深度學習" in topic:
            skill_slug = "deep_learning"
        else:
            log_event(
                "pelican_skill_rejected",
                domain_category=resolution.category.value,
                route=resolution.route_slug,
                reason_code=resolution.reason_code,
            )
            raise SkillLoadError("no catalog skill for topic")

    # Catalog slugs are controlled constants; still keep a final traversal guard.
    skill_path = (SKILLS_DIR / f"{skill_slug}.yaml").resolve()
    if SKILLS_DIR.resolve() not in skill_path.parents:
        log_event("pelican_skill_rejected", reason_code="skill_path_escape")
        raise SkillLoadError("invalid skill path")
    return load_skill(skill_path)


def _parse_skill_payload(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise SkillLoadError("yaml parser unavailable") from exc
        parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise SkillLoadError("skill payload must be an object")
    return parsed
