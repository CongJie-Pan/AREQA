"""Serializable domain models for the PELICAN MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class KnowledgeStatus(str, Enum):
    UNDIAGNOSED = "undiagnosed"
    MASTERED = "mastered"
    NOT_MASTERED = "not_mastered"


class ResponseCategory(str, Enum):
    INABILITY = "inability_to_respond"
    DIFFICULTY = "difficulty_in_understanding"
    CORRECT = "correct"
    INCORRECT = "incorrect"
    OTHER = "other"


class TutoringStrategy(str, Enum):
    EXPLANATION = "explanation"
    CORRECTION = "correction"
    CONFIRMATION = "confirmation"
    OPEN_QUESTION = "open_question"
    CLOSED_QUESTION = "closed_question"
    SIMPLIFICATION = "simplification"
    DECOMPOSITION = "decomposition"
    ANALOGY = "analogy"


@dataclass(frozen=True)
class KnowledgeNode:
    node_id: str
    label: str
    prerequisites: tuple[str, ...] = ()
    priority: int = 0


@dataclass(frozen=True)
class DiagnosticQuestion:
    node_id: str
    prompt: str
    expected_answer: str
    source: str = "rule"


@dataclass
class Evidence:
    response: str
    category: str
    direct: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NodeState:
    status: KnowledgeStatus = KnowledgeStatus.UNDIAGNOSED
    evidence: list[Evidence] = field(default_factory=list)
    updated_at: str | None = None

    def update(self, status: KnowledgeStatus, evidence: Evidence) -> None:
        self.status = status
        self.evidence.append(evidence)
        self.updated_at = evidence.timestamp


@dataclass
class TurnRecord:
    prompt: str
    response: str
    phase: str
    node_id: str
    category: str
    strategy: str | None
    state_changes: list[str]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SessionState:
    learner_id: str
    mode: str = "rule"
    phase: str = "diagnosis"
    current_node_id: str | None = None
    current_step_id: str | None = None
    current_prompt: str = ""
    current_expected_answer: str = ""
    current_prompt_source: str = "rule"
    step_rounds: dict[str, int] = field(default_factory=dict)
    nodes: dict[str, NodeState] = field(default_factory=dict)
    history: list[TurnRecord] = field(default_factory=list)
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "learner_id": self.learner_id,
            "mode": self.mode,
            "phase": self.phase,
            "current_node_id": self.current_node_id,
            "current_step_id": self.current_step_id,
            "current_prompt": self.current_prompt,
            "current_expected_answer": self.current_expected_answer,
            "current_prompt_source": self.current_prompt_source,
            "step_rounds": self.step_rounds,
            "nodes": {
                node_id: {
                    "status": node_state.status.value,
                    "evidence": [asdict(item) for item in node_state.evidence],
                    "updated_at": node_state.updated_at,
                }
                for node_id, node_state in self.nodes.items()
            },
            "history": [asdict(item) for item in self.history],
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionState":
        nodes = {
            node_id: NodeState(
                status=KnowledgeStatus(value.get("status", KnowledgeStatus.UNDIAGNOSED.value)),
                evidence=[Evidence(**item) for item in value.get("evidence", [])],
                updated_at=value.get("updated_at"),
            )
            for node_id, value in payload.get("nodes", {}).items()
        }
        history = [TurnRecord(**item) for item in payload.get("history", [])]
        return cls(
            learner_id=payload["learner_id"],
            mode=payload.get("mode", "rule"),
            phase=payload.get("phase", "diagnosis"),
            current_node_id=payload.get("current_node_id"),
            current_step_id=payload.get("current_step_id"),
            current_prompt=payload.get("current_prompt", ""),
            current_expected_answer=payload.get("current_expected_answer", ""),
            current_prompt_source=payload.get("current_prompt_source", "rule"),
            step_rounds=dict(payload.get("step_rounds", {})),
            nodes=nodes,
            history=history,
            completed=bool(payload.get("completed", False)),
        )


@dataclass(frozen=True)
class TurnOutcome:
    message: str
    node_id: str | None
    category: ResponseCategory | None
    strategy: TutoringStrategy | None
    state_changes: tuple[str, ...]
    next_reason: str

