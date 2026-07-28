"""Manifest-derived repair for capability-policy orchestration mismatches.

This module repairs only the policy field of an already parsed Learning Manager
decision. It intentionally does not inspect raw learner text or reinterpret
turn semantics, preserving the orchestrator as the single owner of user-turn
interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CapabilityPolicyRepairResult:
    """Result of a manifest-derived capability-policy repair attempt.

    Args:
        repaired: Whether the requested policy was changed.
        accepted: Whether the effective policy is allowed by the manifest after
            validation or repair.
        capability: Normalized capability name.
        requested_policy: Original requested policy.
        effective_policy: Policy that should be validated/executed downstream.
        reason_code: Stable safe reason explaining the repair outcome.
        allowed_policy_count: Number of policies listed by the manifest for
            this capability. This is safe observability metadata.

    Compatibility:
        Repair is intentionally field-scoped. Callers must preserve all other
        orchestrator fields, especially ``turn_interpretation``.
    """

    repaired: bool
    accepted: bool
    capability: str
    requested_policy: CapabilityPolicy
    effective_policy: CapabilityPolicy
    reason_code: str
    allowed_policy_count: int = 0


def repair_capability_policy(
    capability: str,
    requested_policy: CapabilityPolicy,
    policy_manifest: Mapping[str, Iterable[str]],
) -> CapabilityPolicyRepairResult:
    """Repair one invalid policy using only the capability manifest.

    Args:
        capability: Capability selected by the Learning Manager.
        requested_policy: Policy selected by the Learning Manager.
        policy_manifest: Safe capability-to-policy manifest. Values may be enum
            labels or strings; invalid policy labels are ignored.

    Returns:
        A repair result. ``accepted`` means the returned ``effective_policy`` can
        be passed to normal registry validation. ``repaired`` distinguishes
        unchanged valid pairs from manifest-corrected pairs.

    Safety:
        The repair is deterministic and never upgrades an ambiguous policy. If
        the manifest lists multiple allowed policies and the requested policy is
        not already allowed, the result is rejected with
        ``ambiguous_policy_repair`` so the caller can fallback or run a bounded
        LLM repair later.
    """
    normalized_capability = _normalize_capability_name(capability)
    allowed = _allowed_policies(policy_manifest.get(normalized_capability, ()))
    if not normalized_capability or not allowed:
        return CapabilityPolicyRepairResult(
            repaired=False,
            accepted=False,
            capability=normalized_capability,
            requested_policy=requested_policy,
            effective_policy=requested_policy,
            reason_code="missing_policy_manifest",
            allowed_policy_count=0,
        )
    if requested_policy in allowed:
        return CapabilityPolicyRepairResult(
            repaired=False,
            accepted=True,
            capability=normalized_capability,
            requested_policy=requested_policy,
            effective_policy=requested_policy,
            reason_code="policy_already_allowed",
            allowed_policy_count=len(allowed),
        )
    if len(allowed) == 1:
        repaired_policy = next(iter(allowed))
        return CapabilityPolicyRepairResult(
            repaired=True,
            accepted=True,
            capability=normalized_capability,
            requested_policy=requested_policy,
            effective_policy=repaired_policy,
            reason_code="policy_repaired_from_manifest",
            allowed_policy_count=1,
        )
    return CapabilityPolicyRepairResult(
        repaired=False,
        accepted=False,
        capability=normalized_capability,
        requested_policy=requested_policy,
        effective_policy=requested_policy,
        reason_code="ambiguous_policy_repair",
        allowed_policy_count=len(allowed),
    )


def _allowed_policies(values: Iterable[str]) -> frozenset[CapabilityPolicy]:
    """Return valid policy enum values from a safe manifest iterable."""
    from .learning_manager_orchestrator import CapabilityPolicy

    policies: set[CapabilityPolicy] = set()
    for value in values:
        try:
            policies.add(CapabilityPolicy(str(value)))
        except ValueError:
            continue
    return frozenset(policies)


def _normalize_capability_name(value: str) -> str:
    """Normalize capability labels into bounded snake-case identifiers."""
    import re

    return re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_")[:80]
