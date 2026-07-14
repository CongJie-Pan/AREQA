"""Safe JSON persistence for a single learner's PELICAN state."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .curriculum import NODES
from .models import NodeState, SessionState


class StateStoreError(RuntimeError):
    """Raised when a persisted learning state cannot be safely used."""


class StateStore:
    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_or_create(self, learner_id: str, mode: str = "rule") -> SessionState:
        path = self._path_for(learner_id)
        if not path.exists():
            return self.new_state(learner_id, mode)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            state = SessionState.from_dict(payload)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise StateStoreError(f"Unable to read learner state {path.name}: {exc}") from exc
        for node_id in NODES:
            state.nodes.setdefault(node_id, NodeState())
        return state

    def new_state(self, learner_id: str, mode: str = "rule") -> SessionState:
        self._validate_learner_id(learner_id)
        return SessionState(
            learner_id=learner_id,
            mode=mode,
            nodes={node_id: NodeState() for node_id in NODES},
        )

    def save(self, state: SessionState) -> None:
        path = self._path_for(state.learner_id)
        serialized = json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.data_dir, delete=False
            ) as temporary:
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            temporary_path.replace(path)
        except OSError as exc:
            raise StateStoreError(f"Unable to save learner state {path.name}: {exc}") from exc

    def reset(self, learner_id: str, mode: str = "rule") -> SessionState:
        state = self.new_state(learner_id, mode)
        self.save(state)
        return state

    def _path_for(self, learner_id: str) -> Path:
        self._validate_learner_id(learner_id)
        return self.data_dir / f"{learner_id}.json"

    @staticmethod
    def _validate_learner_id(learner_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", learner_id or ""):
            raise ValueError("learner_id must contain only letters, numbers, underscores, or hyphens")

