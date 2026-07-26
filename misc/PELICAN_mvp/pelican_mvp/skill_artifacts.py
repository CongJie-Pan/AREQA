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


class SkillArtifactError(ValueError):
    """Raised when a runtime skill artifact cannot be loaded safely."""


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


def load_validated_skill_artifact(
    *,
    topic: str,
    root: Path | None = None,
) -> DomainSkill:
    """Load a previously validated runtime skill artifact for a topic.

    Args:
        topic: Normalized learner topic used to derive the artifact filename.
        root: Optional test/deployment override for generated skill artifacts.

    Returns:
        The persisted ``DomainSkill`` payload. The caller must still run the
        current validator before use because validation rules can become stricter
        after an artifact was written.

    Raises:
        SkillArtifactError: If the artifact is missing, malformed, or not a
            validated runtime skill artifact.

    Compatibility:
        Runtime artifacts are local cache entries, not reviewed catalog assets.
        They are intentionally loaded from ``data/generated_skills/validated``
        instead of ``domain_skills`` so promotion remains a human review step.
    """
    artifact_root = root or ARTIFACT_ROOT
    path = artifact_root / "validated" / f"{_slug(topic)}.validated.json"
    if not path.exists():
        raise SkillArtifactError("validated skill artifact not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillArtifactError("validated skill artifact is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("artifact_type") != "validated_runtime_skill":
        raise SkillArtifactError("validated skill artifact has unexpected type")
    skill_payload = payload.get("skill")
    if not isinstance(skill_payload, dict):
        raise SkillArtifactError("validated skill artifact is missing skill payload")
    try:
        return DomainSkill.from_dict(skill_payload)
    except Exception as exc:
        raise SkillArtifactError("validated skill artifact contains invalid skill payload") from exc


def find_relevant_validated_skill_artifact(
    *,
    topic: str,
    category: DomainCategory,
    root: Path | None = None,
    threshold: float = 0.62,
) -> DomainSkill:
    """Find a highly relevant validated runtime skill for a related topic.

    Args:
        topic: Normalized learner topic.
        category: Resolved domain category; artifacts from other domains are
            ignored.
        root: Optional test/deployment override for generated skill artifacts.
        threshold: Minimum conservative similarity score required for reuse.

    Returns:
        The most relevant persisted ``DomainSkill``.

    Raises:
        SkillArtifactError: If no same-domain validated artifact is relevant
            enough or all candidate artifacts are malformed.

    Rationale:
        Exact filename cache hits are too narrow for natural learner phrasing.
        A learner may add intent words around a topic that already has a
        validated runtime skill. This scanner reuses only strong same-domain
        matches based on skill metadata, avoiding unnecessary model generation
        while still failing closed for weak or invalid matches.
    """
    artifact_root = root or ARTIFACT_ROOT
    directory = artifact_root / "validated"
    if not directory.exists():
        raise SkillArtifactError("validated skill artifact directory not found")

    best_skill: DomainSkill | None = None
    best_score = 0.0
    saw_candidate = False
    for path in sorted(directory.glob("*.validated.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("artifact_type") != "validated_runtime_skill":
                continue
            if payload.get("domain_category") != category.value:
                continue
            skill_payload = payload.get("skill")
            if not isinstance(skill_payload, dict):
                continue
            skill = DomainSkill.from_dict(skill_payload)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            continue
        saw_candidate = True
        score = _skill_relevance_score(topic, skill)
        if score > best_score:
            best_score = score
            best_skill = skill

    if best_skill is None or best_score < threshold:
        if saw_candidate:
            raise SkillArtifactError("validated skill artifact relevance below threshold")
        raise SkillArtifactError("validated skill artifact not found")
    return best_skill


def find_relevant_validated_skill_artifact_any_category(
    *,
    topic: str,
    root: Path | None = None,
    threshold: float = 0.62,
) -> DomainSkill:
    """Find a highly relevant validated runtime skill without a known category.

    Args:
        topic: Normalized learner topic.
        root: Optional test/deployment override for generated skill artifacts.
        threshold: Minimum conservative similarity score required for reuse.

    Returns:
        The most relevant persisted ``DomainSkill`` across all domain
        categories.

    Raises:
        SkillArtifactError: If no validated artifact is relevant enough or all
            candidate artifacts are malformed.

    Compatibility:
        This is used only as an intake routing fallback after deterministic
        domain aliases fail. It does not load raw learner text into logs and it
        does not promote runtime skills into reviewed catalog assets.
    """
    artifact_root = root or ARTIFACT_ROOT
    directory = artifact_root / "validated"
    if not directory.exists():
        raise SkillArtifactError("validated skill artifact directory not found")

    best_skill: DomainSkill | None = None
    best_score = 0.0
    saw_candidate = False
    for path in sorted(directory.glob("*.validated.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("artifact_type") != "validated_runtime_skill":
                continue
            skill_payload = payload.get("skill")
            if not isinstance(skill_payload, dict):
                continue
            skill = DomainSkill.from_dict(skill_payload)
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            continue
        saw_candidate = True
        score = _skill_relevance_score(topic, skill)
        if score > best_score:
            best_score = score
            best_skill = skill

    if best_skill is None or best_score < threshold:
        if saw_candidate:
            raise SkillArtifactError("validated skill artifact relevance below threshold")
        raise SkillArtifactError("validated skill artifact not found")
    return best_skill


def save_failed_skill_artifact(
    *,
    topic: str,
    category: DomainCategory,
    route: str,
    reason_codes: tuple[str, ...],
    payload: dict[str, Any] | None = None,
    attempts: tuple[dict[str, Any], ...] = (),
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
        attempts: Safe per-attempt metadata. Each item may contain the bounded
            attempt number, stage, event name, reason codes, HTTP status code,
            and safe provider error type. Raw payload, prompt, response, and
            exception text must not be included.
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
        "attempts": [_safe_attempt(item) for item in attempts],
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


def _safe_attempt(payload: dict[str, Any]) -> dict[str, Any]:
    """Return bounded per-attempt failure metadata for local RCA artifacts."""
    reasons = payload.get("reason_codes", ())
    if not isinstance(reasons, (list, tuple)):
        reasons = ()
    return {
        "attempt": int(payload.get("attempt", 0)),
        "stage": str(payload.get("stage", "unknown"))[:40],
        "event": str(payload.get("event", "unknown"))[:80],
        "reason_codes": [str(item)[:80] for item in reasons[:8]],
        "api_status_code": _safe_int(payload.get("api_status_code")),
        "api_error_type": str(payload.get("api_error_type") or "")[:80] or None,
    }


def _safe_int(value: Any) -> int | None:
    """Return an integer metadata value when already type-safe."""
    return value if isinstance(value, int) else None


def _skill_relevance_score(topic: str, skill: DomainSkill) -> float:
    """Return a conservative metadata-only relevance score."""
    query = _normalize_relevance_text(topic)
    if not query:
        return 0.0
    metadata_items = [
        skill.title,
        *skill.supported_topics,
        *(item.label for item in skill.prerequisites),
        *(item.description for item in skill.prerequisites),
    ]
    return max((_text_relevance_score(query, item) for item in metadata_items), default=0.0)


def _text_relevance_score(normalized_query: str, candidate: str) -> float:
    """Score one normalized topic against one skill metadata string."""
    normalized_candidate = _normalize_relevance_text(candidate)
    if not normalized_candidate:
        return 0.0
    if normalized_query == normalized_candidate:
        return 1.0
    shorter, longer = sorted((normalized_query, normalized_candidate), key=len)
    if len(shorter) >= 4 and shorter in longer:
        return 0.94
    query_tokens = _relevance_tokens(normalized_query)
    candidate_tokens = _relevance_tokens(normalized_candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = len(query_tokens & candidate_tokens)
    union = len(query_tokens | candidate_tokens)
    return overlap / union if union else 0.0


def _normalize_relevance_text(value: str) -> str:
    """Normalize bounded text for relevance matching."""
    text = re.sub(r"\s+", "", str(value or "")).lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def _relevance_tokens(text: str) -> set[str]:
    """Return character n-grams for short mixed CJK/ASCII topic matching."""
    if len(text) <= 2:
        return {text} if text else set()
    bigrams = {text[index : index + 2] for index in range(len(text) - 1)}
    trigrams = {text[index : index + 3] for index in range(len(text) - 2)}
    return bigrams | trigrams


def _slug(value: str) -> str:
    """Create a bounded artifact filename slug that preserves CJK topic text."""
    normalized = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", value).strip("_").lower()
    return normalized[:60] or "topic"


def _now() -> str:
    """Return an ISO-8601 UTC timestamp for artifact metadata."""
    return datetime.now(timezone.utc).isoformat()
