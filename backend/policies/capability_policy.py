from __future__ import annotations

import hashlib


class CapabilityPolicy:
    @staticmethod
    def rollout_enabled(
        *,
        feature_enabled: bool,
        rollout_percentage: float,
        user_id: str,
        conversation_id: str,
    ) -> bool:
        if not feature_enabled or rollout_percentage <= 0:
            return False
        if rollout_percentage >= 100:
            return True
        digest = hashlib.sha256(
            f"{user_id}:{conversation_id}".encode("utf-8")
        ).digest()
        bucket = int.from_bytes(digest[:4], "big") % 10000 / 100
        return bucket < rollout_percentage
