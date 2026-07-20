"""Safe JSON persistence for a single learner's PELICAN state."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path

from .curriculum import CURRICULUMS
from .models import KnowledgeNode, LearningPlanSnapshot, NodeState, PlanSource, SessionState
from .observability import log_event


class StateStoreError(RuntimeError):
    """Raised when a persisted learning state cannot be safely used."""


SUPPORTED_SCHEMA_VERSION = 2


class StateStore:
    """Persist and validate local PELICAN session state using atomic JSON writes."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_or_create(self, learner_id: str, mode: str = "rule", curriculum_id: str | None = None) -> SessionState:
        """Load one session, preserving fixture compatibility or creating onboarding state."""
        path = self._path_for(learner_id)
        if not path.exists():
            state = self.new_state(learner_id, mode, curriculum_id)
            log_event(
                "pelican_session_created",
                learner_id,
                schema_version=state.schema_version,
                phase=state.phase,
                plan_source=state.plan_source.value,
                node_count=len(state.nodes),
            )
            return state
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            state = SessionState.from_dict(payload)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            log_event(
                "pelican_state_rejected",
                learner_id,
                level=logging.WARNING,
                reason_code="deserialize_failed",
            )
            raise StateStoreError(f"Unable to read learner state {path.name}: {exc}") from exc

        if curriculum_id is not None and state.curriculum_id != curriculum_id:
            state = self.reset(learner_id, mode, curriculum_id)
            return state

        try:
            normalized = self._normalize_state(state)
        except (TypeError, ValueError) as exc:
            log_event(
                "pelican_state_rejected",
                learner_id,
                level=logging.WARNING,
                reason_code="invalid_plan",
            )
            raise StateStoreError(f"Unable to validate learner state {path.name}: {exc}") from exc

        if normalized:
            self.save(state)

        log_event(
            "pelican_state_normalized" if normalized else "pelican_state_loaded",
            learner_id,
            schema_version=state.schema_version,
            phase=state.phase,
            plan_source=state.plan_source.value,
            node_count=len(state.nodes),
        )
        return state

    def new_state(self, learner_id: str, mode: str = "rule", curriculum_id: str | None = None) -> SessionState:
        """Create an onboarding session or an explicit legacy fixture session."""
        self._validate_learner_id(learner_id)
        if curriculum_id is None:
            return SessionState(learner_id=learner_id, mode=mode)
        if curriculum_id not in CURRICULUMS:
            raise ValueError(f"Unknown curriculum_id: {curriculum_id}")
        return SessionState(
            learner_id=learner_id,
            curriculum_id=curriculum_id,
            plan_source=PlanSource.FIXTURE,
            mode=mode,
            phase="diagnosis",
            nodes={node_id: NodeState() for node_id in CURRICULUMS[curriculum_id].nodes},
        )

    def save(self, state: SessionState) -> None:
        """Validate then atomically persist a local session without logging its content."""
        path = self._path_for(state.learner_id)
        temporary_path: Path | None = None
        try:
            self._normalize_state(state)
            serialized = json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.data_dir,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(serialized)
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, path)
        except OSError as exc:
            raise StateStoreError(f"Unable to save learner state {path.name}: {exc}") from exc
        except (TypeError, ValueError) as exc:
            log_event(
                "pelican_state_rejected",
                state.learner_id,
                level=logging.WARNING,
                reason_code="invalid_plan",
            )
            raise StateStoreError(f"Unable to save learner state {path.name}: {exc}") from exc
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def reset(self, learner_id: str, mode: str = "rule", curriculum_id: str | None = None) -> SessionState:
        """Replace one local session with a clean onboarding or explicit fixture state."""
        state = self.new_state(learner_id, mode, curriculum_id)
        self.save(state)
        return state

    def _normalize_state(self, state: SessionState) -> bool:
        """Validate the active plan and reconcile stale or missing node-state records."""
        normalized = False
        if state.schema_version < 1 or state.schema_version > SUPPORTED_SCHEMA_VERSION:
            raise ValueError("unsupported session schema version")
        if state.schema_version < SUPPORTED_SCHEMA_VERSION:
            state.schema_version = SUPPORTED_SCHEMA_VERSION
            normalized = True
        if state.plan_source is PlanSource.FIXTURE:
            if state.learning_plan is not None:
                raise ValueError("fixture sessions cannot contain generated learning plans")
            if not state.curriculum_id or state.curriculum_id not in CURRICULUMS:
                raise ValueError("fixture sessions require a known curriculum_id")
            expected_node_ids = set(CURRICULUMS[state.curriculum_id].nodes)
        elif state.plan_source is PlanSource.GENERATED:
            if state.curriculum_id is not None:
                raise ValueError("generated sessions cannot contain curriculum_id")
            if state.learning_plan is None:
                if state.phase != "onboarding" or state.nodes:
                    raise ValueError("unplanned generated sessions must remain empty onboarding states")
                return normalized
            self._validate_learning_plan(state.learning_plan)
            expected_node_ids = {node.node_id for node in state.learning_plan.nodes}
        else:
            raise ValueError("unknown plan source")

        for node_id in expected_node_ids:
            if node_id not in state.nodes:
                state.nodes[node_id] = NodeState()
                normalized = True
        stale_node_ids = set(state.nodes) - expected_node_ids
        for node_id in stale_node_ids:
            del state.nodes[node_id]
            normalized = True
        return normalized

    @staticmethod
    def _validate_learning_plan(plan: LearningPlanSnapshot) -> None:
        """Validate the generated-plan graph before it becomes persistent session state."""
        if not all(isinstance(value, str) and value.strip() for value in (plan.plan_id, plan.topic, plan.goal_summary)):
            raise ValueError("generated plan requires non-empty identifiers and summaries")
        for field_name in ("skill_id", "skill_version", "skill_lifecycle", "domain_category", "model_route"):
            value = getattr(plan, field_name)
            if value is not None and (not isinstance(value, str) or len(value) > 120):
                raise ValueError(f"generated plan {field_name} must be bounded metadata")
        if not plan.nodes:
            raise ValueError("generated plan requires at least one node")
        node_ids = [node.node_id for node in plan.nodes]
        if any(not node_id.strip() for node_id in node_ids) or len(node_ids) != len(set(node_ids)):
            raise ValueError("generated plan node IDs must be unique and non-empty")
        node_id_set = set(node_ids)
        for node in plan.nodes:
            if not node.label.strip() or node.node_id in node.prerequisites:
                raise ValueError("generated plan nodes require labels and cannot self-reference")
            if any(prerequisite not in node_id_set for prerequisite in node.prerequisites):
                raise ValueError("generated plan prerequisites must reference known nodes")
        StateStore._assert_acyclic(plan.nodes)
        diagnostic_node_ids = [diagnostic.node_id for diagnostic in plan.diagnostics]
        if len(diagnostic_node_ids) != len(set(diagnostic_node_ids)):
            raise ValueError("generated plan diagnostics must not repeat nodes")
        if any(node_id not in node_id_set for node_id in diagnostic_node_ids):
            raise ValueError("generated plan diagnostics must reference known nodes")
        for diagnostic in plan.diagnostics:
            if not diagnostic.prompt.strip() or not diagnostic.expected_answer.strip():
                raise ValueError("generated plan diagnostics require prompt and expected answer")
        step_ids: set[str] = set()
        for step in plan.task_steps:
            step_id = step.get("step_id", "")
            if not isinstance(step_id, str) or not step_id.strip() or step_id in step_ids:
                raise ValueError("generated plan task steps require unique step_id values")
            if step.get("node_id") not in node_id_set:
                raise ValueError("generated plan task steps must reference known nodes")
            if not all(isinstance(step.get(field), str) and step[field].strip() for field in ("prompt", "expected")):
                raise ValueError("generated plan task steps require prompt and expected values")
            step_ids.add(step_id)

    @staticmethod
    def _assert_acyclic(nodes: tuple[KnowledgeNode, ...]) -> None:
        """Reject cyclic prerequisite graphs before successor-first diagnosis uses them."""
        node_map = {node.node_id: node for node in nodes}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("generated plan prerequisites must be acyclic")
            if node_id in visited:
                return
            visiting.add(node_id)
            for prerequisite in node_map[node_id].prerequisites:
                visit(prerequisite)
            visiting.remove(node_id)
            visited.add(node_id)

        for node in nodes:
            visit(node.node_id)

    def _path_for(self, learner_id: str) -> Path:
        self._validate_learner_id(learner_id)
        return self.data_dir / f"{learner_id}.json"

    @staticmethod
    def _validate_learner_id(learner_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", learner_id or ""):
            raise ValueError("learner_id must contain only letters, numbers, underscores, or hyphens")
