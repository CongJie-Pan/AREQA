"""Persist safe runtime skill generation artifacts for local inspection.

Runtime-generated skills are session-time model outputs, not reviewed catalog
assets. This module stores only two artifact classes: validated skills that have
already passed the DomainSkill validator, and failed-generation metadata with a
payload hash plus safe reason codes. Failed artifacts intentionally omit raw
prompts, learner answers, model reasoning, and full invalid model output.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain_skill import DomainCategory, DomainSkill


ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "data" / "generated_skills"


def save_validated_skill_artifact(
    skill: DomainSkill,
    *,
    topic: str,
    route: str,
    root: Path | None = None,
) -> Path:
    """Save a validated runtime skill JSON artifact under ``data/generated_skills``.

    Args:
        skill: Validator-approved domain skill to persist for inspection.
        topic: Normalized topic used only to derive the artifact filename.
        route: Safe model route or source label used for provenance.
        root: Optional test override for the artifact root directory.

    Returns:
        Path to the written JSON artifact.

    Side Effects:
        Creates the ``validated`` artifact directory and writes a formatted JSON
        file containing the approved skill contract. The write is local MVP
        state only and does not promote the skill to catalog/approved status.
    """
    artifact_root = root or ARTIFACT_ROOT
    directory = artifact_root / "validated"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_slug(topic)}.validated.json"
    payload = {
        "artifact_type": "validated_runtime_skill",
        "topic_slug": _slug(topic),
        "domain_category": skill.domain_category.value,
        "skill_id": skill.skill_id,
        "skill_version": skill.version,
        "route": route,
        "created_at": _now(),
        "skill": skill.to_dict(),
    }
    _write_json(path, payload)
    return path


def save_failed_skill_artifact(
    *,
    topic: str,
    category: DomainCategory,
    route: str,
    reason_codes: tuple[str, ...],
    payload: dict[str, Any] | None = None,
    root: Path | None = None,
) -> Path:
    """Save safe failure metadata without raw learner answers or model reasoning.

    Args:
        topic: Normalized topic used only to derive the artifact filename.
        category: Resolved domain category for routing/debugging.
        route: Safe model route attempted during generation.
        reason_codes: Validator or transport reason codes from the final failed
            attempt. These are stable debugging handles, not raw model text.
        payload: Optional invalid JSON object used only to compute a short hash.
        root: Optional test override for the artifact root directory.

    Returns:
        Path to the written failure artifact.

    Side Effects:
        Creates the ``failed`` artifact directory and writes JSON metadata. The
        payload hash lets developers correlate repeated failures without storing
        potentially unsafe or noisy model output.
    """
    artifact_root = root or ARTIFACT_ROOT
    directory = artifact_root / "failed"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_slug(topic)}.failed.json"
    safe_payload = {
        "artifact_type": "failed_runtime_skill",
        "topic_slug": _slug(topic),
        "domain_category": category.value,
        "route": route,
        "reason_codes": list(reason_codes),
        "payload_hash": _payload_hash(payload) if payload is not None else None,
        "created_at": _now(),
    }
    _write_json(path, safe_payload)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one deterministic UTF-8 JSON artifact."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _payload_hash(payload: dict[str, Any]) -> str:
    """Return a short stable hash for invalid payload correlation."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _slug(value: str) -> str:
    """Create a bounded artifact filename slug that preserves CJK topic text."""
    normalized = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", value).strip("_").lower()
    return normalized[:60] or "topic"


def _now() -> str:
    """Return an ISO-8601 UTC timestamp for artifact metadata."""
    return datetime.now(timezone.utc).isoformat()
