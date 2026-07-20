"""Serializable domain models for the PELICAN MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class KnowledgeStatus(str, Enum):
    """Knowledge tracing status for each concept node."""

    UNDIAGNOSED = "undiagnosed"
    MASTERED = "mastered"
    NOT_MASTERED = "not_mastered"


class ResponseCategory(str, Enum):
    """Rule/LLM response labels used by diagnosis and tutoring."""

    INABILITY = "inability_to_respond"
    DIFFICULTY = "difficulty_in_understanding"
    CORRECT = "correct"
    INCORRECT = "incorrect"
    OTHER = "other"


class TutoringStrategy(str, Enum):
    """Supported tutoring moves for the MVP strategy selector."""

    EXPLANATION = "explanation"
    CORRECTION = "correction"
    CONFIRMATION = "confirmation"
    OPEN_QUESTION = "open_question"
    CLOSED_QUESTION = "closed_question"
    SIMPLIFICATION = "simplification"
    DECOMPOSITION = "decomposition"
    ANALOGY = "analogy"


class PlanSource(str, Enum):
    """Identify whether a session resolves a fixture or generated learning plan."""

    FIXTURE = "fixture"
    GENERATED = "generated"


class LearningIntent(str, Enum):
    """Learner intent captured during intake before a skill is compiled."""

    UNKNOWN = "unknown"
    CONCEPTUAL = "conceptual"
    PROCEDURAL = "procedural"
    IMPLEMENTATION = "implementation"
    PROJECT = "project"
    ASSESSMENT = "assessment"
    EXPLANATORY = "explanatory"
    BUSINESS_DECISION = "business_decision"
    LANGUAGE_PRACTICE = "language_practice"


@dataclass(frozen=True)
class LearnerIntakeProfile:
    """Prompt-safe intake metadata used to choose a skill and route.

    The profile may summarize a learner's stated goal, but it does not assert
    mastery. Detailed evidence still belongs in direct-evidence records.
    """

    topic: str = ""
    goal_summary: str = ""
    intent: LearningIntent = LearningIntent.UNKNOWN
    level_hint: str = "unknown"
    domain_category: str = "unknown"
    skill_id: str | None = None
    skill_version: str | None = None
    skill_lifecycle: str | None = None
    model_route: str | None = None
    intake_turns: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe intake profile."""
        return {
            "topic": self.topic,
            "goal_summary": self.goal_summary,
            "intent": self.intent.value,
            "level_hint": self.level_hint,
            "domain_category": self.domain_category,
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "skill_lifecycle": self.skill_lifecycle,
            "model_route": self.model_route,
            "intake_turns": self.intake_turns,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerIntakeProfile":
        """Deserialize intake metadata with schema-compatible defaults."""
        return cls(
            topic=payload.get("topic", ""),
            goal_summary=payload.get("goal_summary", ""),
            intent=LearningIntent(payload.get("intent", LearningIntent.UNKNOWN.value)),
            level_hint=payload.get("level_hint", "unknown"),
            domain_category=payload.get("domain_category", "unknown"),
            skill_id=payload.get("skill_id"),
            skill_version=payload.get("skill_version"),
            skill_lifecycle=payload.get("skill_lifecycle"),
            model_route=payload.get("model_route"),
            intake_turns=int(payload.get("intake_turns", 0)),
        )


@dataclass(frozen=True)
class MemoryEvidenceRecord:
    """Session-local direct evidence record following AREQA's memory boundary."""

    source: str
    kind: str
    text: str
    prompt_safe: bool = True
    cold_export_eligible: bool = False
    confidence: float = 1.0
    topic: str | None = None
    node_id: str | None = None
    signal: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe direct evidence record."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryEvidenceRecord":
        """Deserialize a direct evidence record without promoting model inference."""
        return cls(
            source=payload.get("source", "user_message"),
            kind=payload.get("kind", "USER_EVIDENCE"),
            text=payload.get("text", ""),
            prompt_safe=bool(payload.get("prompt_safe", True)),
            cold_export_eligible=bool(payload.get("cold_export_eligible", False)),
            confidence=float(payload.get("confidence", 1.0)),
            topic=payload.get("topic"),
            node_id=payload.get("node_id"),
            signal=payload.get("signal"),
            timestamp=payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass(frozen=True)
class KnowledgeNode:
    """One node in a fixture or compiled PELICAN knowledge tree."""

    node_id: str
    label: str
    prerequisites: tuple[str, ...] = ()
    priority: int = 0


@dataclass(frozen=True)
class DiagnosticQuestion:
    """One diagnostic prompt with answer kept separate from learner-facing text."""

    node_id: str
    prompt: str
    expected_answer: str
    source: str = "rule"


@dataclass(frozen=True)
class LearningPlanSnapshot:
    """Persist a validated generated learning plan inside one learner session.

    The snapshot belongs to the session rather than the global fixture registry so a
    future planner can safely regenerate or inspect it without mutating other users.
    """

    plan_id: str
    topic: str
    goal_summary: str
    nodes: tuple[KnowledgeNode, ...]
    diagnostics: tuple[DiagnosticQuestion, ...] = ()
    task_steps: tuple[dict[str, str], ...] = ()
    skill_id: str | None = None
    skill_version: str | None = None
    skill_lifecycle: str | None = None
    domain_category: str | None = None
    model_route: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of this immutable plan snapshot."""
        return {
            "plan_id": self.plan_id,
            "topic": self.topic,
            "goal_summary": self.goal_summary,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "label": node.label,
                    "prerequisites": list(node.prerequisites),
                    "priority": node.priority,
                }
                for node in self.nodes
            ],
            "diagnostics": [
                {
                    "node_id": diagnostic.node_id,
                    "prompt": diagnostic.prompt,
                    "expected_answer": diagnostic.expected_answer,
                    "source": diagnostic.source,
                }
                for diagnostic in self.diagnostics
            ],
            "task_steps": [dict(step) for step in self.task_steps],
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "skill_lifecycle": self.skill_lifecycle,
            "domain_category": self.domain_category,
            "model_route": self.model_route,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearningPlanSnapshot":
        """Build a plan snapshot from persisted JSON before store-level validation."""
        nodes = tuple(
            KnowledgeNode(
                node_id=item["node_id"],
                label=item["label"],
                prerequisites=tuple(item.get("prerequisites", ())),
                priority=int(item.get("priority", 0)),
            )
            for item in payload.get("nodes", ())
        )
        diagnostics = tuple(
            DiagnosticQuestion(
                node_id=item["node_id"],
                prompt=item["prompt"],
                expected_answer=item["expected_answer"],
                source=item.get("source", "rule"),
            )
            for item in payload.get("diagnostics", ())
        )
        task_steps = tuple(dict(item) for item in payload.get("task_steps", ()))
        return cls(
            plan_id=payload["plan_id"],
            topic=payload["topic"],
            goal_summary=payload["goal_summary"],
            nodes=nodes,
            diagnostics=diagnostics,
            task_steps=task_steps,
            skill_id=payload.get("skill_id"),
            skill_version=payload.get("skill_version"),
            skill_lifecycle=payload.get("skill_lifecycle"),
            domain_category=payload.get("domain_category"),
            model_route=payload.get("model_route"),
            created_at=payload.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


@dataclass(frozen=True)
class EdfSnapshot:
    """Store a teaching-decision snapshot without asserting a learner memory fact."""

    learner_state: str = "STARTING"
    pedagogical_strategy: str = "probe_understanding"
    trigger_proactive: bool = False
    confidence: float = 0.0
    evidence_count: int = 0
    reason_code: str = "not_evaluated"
    updated_at: str | None = None


@dataclass(frozen=True)
class LearningMemorySnapshot:
    """Track local memory counters while retaining direct evidence as the source of truth."""

    evidence_count: int = 0
    working_context_count: int = 0
    updated_at: str | None = None


@dataclass
class Evidence:
    """Evidence attached to a node-state update."""

    response: str
    category: str
    direct: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class NodeState:
    """Mutable knowledge-state record for one node in a learner session."""

    status: KnowledgeStatus = KnowledgeStatus.UNDIAGNOSED
    evidence: list[Evidence] = field(default_factory=list)
    updated_at: str | None = None

    def update(self, status: KnowledgeStatus, evidence: Evidence) -> None:
        """Apply a status change and append its supporting evidence."""
        self.status = status
        self.evidence.append(evidence)
        self.updated_at = evidence.timestamp


@dataclass
class TurnRecord:
    """Persist one local turn for MVP auditability and tests."""

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
    """Serialize the complete local state for one PELICAN learning session."""

    learner_id: str
    schema_version: int = 2
    plan_source: PlanSource = PlanSource.GENERATED
    curriculum_id: str | None = None
    learning_plan: LearningPlanSnapshot | None = None
    mode: str = "rule"
    phase: str = "onboarding"
    current_node_id: str | None = None
    current_step_id: str | None = None
    current_prompt: str = ""
    current_expected_answer: str = ""
    current_prompt_source: str = "rule"
    step_rounds: dict[str, int] = field(default_factory=dict)
    nodes: dict[str, NodeState] = field(default_factory=dict)
    history: list[TurnRecord] = field(default_factory=list)
    edf_snapshot: EdfSnapshot = field(default_factory=EdfSnapshot)
    memory_snapshot: LearningMemorySnapshot = field(default_factory=LearningMemorySnapshot)
    intake_profile: LearnerIntakeProfile = field(default_factory=LearnerIntakeProfile)
    direct_evidence: list[MemoryEvidenceRecord] = field(default_factory=list)
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full local session without dropping compatibility fields."""
        return {
            "learner_id": self.learner_id,
            "schema_version": self.schema_version,
            "plan_source": self.plan_source.value,
            "curriculum_id": self.curriculum_id,
            "learning_plan": self.learning_plan.to_dict() if self.learning_plan else None,
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
            "edf_snapshot": asdict(self.edf_snapshot),
            "memory_snapshot": asdict(self.memory_snapshot),
            "intake_profile": self.intake_profile.to_dict(),
            "direct_evidence": [item.to_dict() for item in self.direct_evidence],
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionState":
        """Deserialize legacy fixture sessions and versioned generated-plan sessions."""
        nodes = {
            node_id: NodeState(
                status=KnowledgeStatus(value.get("status", KnowledgeStatus.UNDIAGNOSED.value)),
                evidence=[Evidence(**item) for item in value.get("evidence", [])],
                updated_at=value.get("updated_at"),
            )
            for node_id, value in payload.get("nodes", {}).items()
        }
        history = [TurnRecord(**item) for item in payload.get("history", [])]
        curriculum_id = payload.get("curriculum_id")
        plan_source = PlanSource(payload.get(
            "plan_source",
            PlanSource.FIXTURE.value if curriculum_id else PlanSource.GENERATED.value,
        ))
        learning_plan_payload = payload.get("learning_plan")
        return cls(
            learner_id=payload["learner_id"],
            schema_version=int(payload.get("schema_version", 1)),
            plan_source=plan_source,
            curriculum_id=curriculum_id,
            learning_plan=(
                LearningPlanSnapshot.from_dict(learning_plan_payload)
                if learning_plan_payload is not None
                else None
            ),
            mode=payload.get("mode", "rule"),
            phase=payload.get("phase", "diagnosis" if curriculum_id else "onboarding"),
            current_node_id=payload.get("current_node_id"),
            current_step_id=payload.get("current_step_id"),
            current_prompt=payload.get("current_prompt", ""),
            current_expected_answer=payload.get("current_expected_answer", ""),
            current_prompt_source=payload.get("current_prompt_source", "rule"),
            step_rounds=dict(payload.get("step_rounds", {})),
            nodes=nodes,
            history=history,
            edf_snapshot=EdfSnapshot(**payload.get("edf_snapshot", {})),
            memory_snapshot=LearningMemorySnapshot(**payload.get("memory_snapshot", {})),
            intake_profile=LearnerIntakeProfile.from_dict(payload.get("intake_profile", {})),
            direct_evidence=[
                MemoryEvidenceRecord.from_dict(item)
                for item in payload.get("direct_evidence", [])
            ],
            completed=bool(payload.get("completed", False)),
        )


@dataclass(frozen=True)
class TurnOutcome:
    """Engine response returned to CLI/API callers after one state transition."""

    message: str
    node_id: str | None
    category: ResponseCategory | None
    strategy: TutoringStrategy | None
    state_changes: tuple[str, ...]
    next_reason: str
