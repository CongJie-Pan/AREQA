"""Safe JSON persistence for a single learner's PELICAN state."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .curriculum import CURRICULUMS
from .models import NodeState, SessionState


class StateStoreError(RuntimeError):
    """Raised when a persisted learning state cannot be safely used."""


class StateStore:
    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_or_create(self, learner_id: str, mode: str = "rule", curriculum_id: str | None = None) -> SessionState:
        path = self._path_for(learner_id)
        if not path.exists():
            return self.new_state(learner_id, mode, curriculum_id or "cnn")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            state = SessionState.from_dict(payload)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise StateStoreError(f"Unable to read learner state {path.name}: {exc}") from exc
        
        # If curriculum_id is provided and differs from the stored state, trigger a full reset
        target_curriculum = curriculum_id or state.curriculum_id
        if target_curriculum not in CURRICULUMS:
            target_curriculum = "cnn"
            
        if state.curriculum_id != target_curriculum:
            return self.reset(learner_id, mode, target_curriculum)
            
        # Ensure all nodes for the current curriculum exist
        curriculum = CURRICULUMS[state.curriculum_id]
        for node_id in curriculum.nodes:
            state.nodes.setdefault(node_id, NodeState())
            
        # Optional: remove stale nodes from previous curriculums if any snuck in
        stale_nodes = [nid for nid in state.nodes if nid not in curriculum.nodes]
        for nid in stale_nodes:
            del state.nodes[nid]
            
        return state

    def new_state(self, learner_id: str, mode: str = "rule", curriculum_id: str = "cnn") -> SessionState:
        self._validate_learner_id(learner_id)
        if curriculum_id not in CURRICULUMS:
            raise ValueError(f"Unknown curriculum_id: {curriculum_id}")
        return SessionState(
            learner_id=learner_id,
            curriculum_id=curriculum_id,
            mode=mode,
            nodes={node_id: NodeState() for node_id in CURRICULUMS[curriculum_id].nodes},
        )

    def save(self, state: SessionState) -> None:
        path = self._path_for(state.learner_id)
        serialized = json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        try:
            path.write_text(serialized, encoding="utf-8")
        except OSError as exc:
            raise StateStoreError(f"Unable to save learner state {path.name}: {exc}") from exc

    def reset(self, learner_id: str, mode: str = "rule", curriculum_id: str = "cnn") -> SessionState:
        state = self.new_state(learner_id, mode, curriculum_id)
        self.save(state)
        return state

    def _path_for(self, learner_id: str) -> Path:
        self._validate_learner_id(learner_id)
        return self.data_dir / f"{learner_id}.json"

    @staticmethod
    def _validate_learner_id(learner_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", learner_id or ""):
            raise ValueError("learner_id must contain only letters, numbers, underscores, or hyphens")
