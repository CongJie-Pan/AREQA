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
    PARTIALLY_MASTERED = "partially_mastered"
    FRAGILE = "fragile"
    INFERRED_MASTERED = "inferred_mastered"


class ResponseCategory(str, Enum):
    """Rule/LLM response labels used by diagnosis and tutoring."""

    INABILITY = "inability_to_respond"
    DIFFICULTY = "difficulty_in_understanding"
    CORRECT = "correct"
    PARTIAL_CORRECT = "partial_correct"
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
    CLARIFY_TERM = "clarify_term"
    GIVE_CHOICES = "give_choices"
    SHORT_REFRAME = "short_reframe"
    MINI_LESSON = "mini_lesson"
    MICRO_CHECK = "micro_check"
    CONFIRM_ADVANCE = "confirm_advance"


class LearnerDialogueAct(str, Enum):
    """Bounded learner utterance roles before knowledge diagnosis.

    These labels separate conversational control from mastery evidence. Only
    ``ANSWER_ATTEMPT`` should flow directly into cognitive diagnosis; the other
    acts are routed as tutor-facing clarification or control moves without
    asserting mastery or failure.
    """

    ANSWER_ATTEMPT = "answer_attempt"
    CLARIFICATION_QUESTION = "clarification_question"
    TERM_DEFINITION_REQUEST = "term_definition_request"
    MICRO_CHECK_CONFUSION = "micro_check_confusion"
    TOO_HARD = "too_hard"
    TOO_EASY = "too_easy"
    READY_TO_CONTINUE = "ready_to_continue"
    TOPIC_SHIFT = "topic_shift"
    OTHER = "other"


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


class MethodologyStage(str, Enum):
    """Six core methodology stages from the Agentic PELICAN blueprint."""

    GOAL_FRAMING = "goal_framing"
    SKILL_CONSTRUCTION = "skill_construction"
    COGNITIVE_DIAGNOSIS = "cognitive_diagnosis"
    KNOWLEDGE_STATE_UPDATE = "knowledge_state_update"
    EDF_STRATEGY_SELECTION = "edf_strategy_selection"
    TUTOR_RESPONSE = "tutor_response"


class MethodologyEventType(str, Enum):
    """Event categories linked to a tutoring cycle."""

    PIPELINE_STAGE = "pipeline_stage"
    GUM_SUBSYSTEM = "gum_subsystem"
    LEARNER_INTERACTION = "learner_interaction"
    AGENT_PROPOSAL = "agent_proposal"


class MethodologyStatus(str, Enum):
    """Lifecycle status for methodology events and records."""

    STARTED = "started"
    COMPLETED = "completed"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    FAILED = "failed"


class ProposalValidationStatus(str, Enum):
    """Validation result for bounded agent proposals."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FALLBACK_USED = "fallback_used"


class AgentRole(str, Enum):
    """Functional agent roles used by the proposal layer."""

    DIALOGUE_ACT_AGENT = "dialogue_act_agent"
    INTAKE_AGENT = "intake_agent"
    SKILL_AGENT = "skill_agent"
    DIAGNOSIS_AGENT = "diagnosis_agent"
    STATE_AGENT = "state_agent"
    POLICY_AGENT = "policy_agent"
    FAST_TUTOR_AGENT = "fast_tutor_agent"
    SLOW_SIMULATOR_AGENT = "slow_simulator_agent"


def _bounded_text(value: Any, limit: int = 160) -> str:
    """Return bounded text for public metadata fields."""
    return str(value or "")[:limit]


def _utc_now() -> str:
    """Return a timezone-aware ISO timestamp for serialized session records."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MethodologyRef:
    """Safe reference to an input or output artifact without raw payload content."""

    ref_type: str
    ref_id: str
    label: str

    def to_dict(self) -> dict[str, str]:
        """Serialize the safe reference for API and persistence use."""
        return {
            "ref_type": _bounded_text(self.ref_type, 80),
            "ref_id": _bounded_text(self.ref_id, 120),
            "label": _bounded_text(self.label, 160),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "MethodologyRef":
        """Deserialize a reference, applying fail-closed bounded defaults."""
        payload = payload or {}
        return cls(
            ref_type=_bounded_text(payload.get("ref_type", "unknown"), 80),
            ref_id=_bounded_text(payload.get("ref_id", "unknown"), 120),
            label=_bounded_text(payload.get("label", "unknown"), 160),
        )


@dataclass(frozen=True)
class LearnerProgressNode:
    """Learner-visible progress for one concept without exposing raw evidence."""

    node_id: str
    label: str
    status: KnowledgeStatus
    confidence: float
    evidence_source: str
    direct_evidence_count: int
    inferred_from: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize one progress node for API display."""
        return {
            "node_id": _bounded_text(self.node_id, 120),
            "label": _bounded_text(self.label, 160),
            "status": self.status.value,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "evidence_source": _bounded_text(self.evidence_source, 80),
            "direct_evidence_count": max(0, int(self.direct_evidence_count)),
            "inferred_from": [_bounded_text(item, 120) for item in self.inferred_from[:8]],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LearnerProgressNode":
        """Deserialize progress metadata with enum validation."""
        return cls(
            node_id=_bounded_text(payload.get("node_id"), 120),
            label=_bounded_text(payload.get("label"), 160),
            status=KnowledgeStatus(payload.get("status", KnowledgeStatus.UNDIAGNOSED.value)),
            confidence=max(0.0, min(1.0, float(payload.get("confidence", 0.0)))),
            evidence_source=_bounded_text(payload.get("evidence_source", "none"), 80),
            direct_evidence_count=max(0, int(payload.get("direct_evidence_count", 0))),
            inferred_from=tuple(_bounded_text(item, 120) for item in payload.get("inferred_from", ())[:8]),
        )


@dataclass(frozen=True)
class LearnerProgressSnapshot:
    """Current learner progress snapshot derived from knowledge state."""

    cycle_id: str | None
    current_node_id: str | None
    nodes: tuple[LearnerProgressNode, ...]
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize learner progress for API responses and exports."""
        return {
            "cycle_id": self.cycle_id,
            "current_node_id": self.current_node_id,
            "nodes": [item.to_dict() for item in self.nodes],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LearnerProgressSnapshot":
        """Deserialize learner progress, dropping malformed node entries safely."""
        payload = payload or {}
        nodes: list[LearnerProgressNode] = []
        for item in payload.get("nodes", ())[:64]:
            try:
                nodes.append(LearnerProgressNode.from_dict(item))
            except (TypeError, ValueError):
                continue
        return cls(
            cycle_id=payload.get("cycle_id"),
            current_node_id=payload.get("current_node_id"),
            nodes=tuple(nodes),
            updated_at=payload.get("updated_at", _utc_now()),
        )


@dataclass(frozen=True)
class BoundedTutorProposal:
    """Learner-facing tutor proposal after validation and privacy bounding.

    Args:
        response: Final learner-facing message candidate. This is intentionally
            bounded because it can be shown in chat/export after validation.
        pedagogical_move: Short safe label for the teaching move, such as
            ``scaffold`` or ``scope_recalibration``.
        summary: Safe explanation of why the proposal was selected. It must not
            contain raw learner answers, raw prompts, model output, credentials,
            provider payloads, or chain-of-thought.
        node_id: Current concept node that grounds the response.
        strategy: EDF-selected tutoring strategy that constrained generation.
        evidence_signal: Safe response signal used by EDF/GUM.
        source: ``llm`` for generated proposals or ``rule`` for fallback.

    Compatibility:
        This model is append-only metadata for the MVP proposal layer. Session
        replay remains compatible because persisted ``AgentProposal`` records
        store only bounded summaries, not this full dataclass.
    """

    response: str
    pedagogical_move: str
    summary: str
    node_id: str
    strategy: str
    evidence_signal: str
    source: str = "llm"

    def to_safe_dict(self) -> dict[str, str]:
        """Serialize a bounded tutor proposal for UI metadata and tests."""
        return {
            "response": _bounded_text(self.response, 900),
            "pedagogical_move": _bounded_text(self.pedagogical_move, 80),
            "summary": _bounded_text(self.summary, 260),
            "node_id": _bounded_text(self.node_id, 120),
            "strategy": _bounded_text(self.strategy, 80),
            "evidence_signal": _bounded_text(self.evidence_signal, 80),
            "source": _bounded_text(self.source, 40),
        }


@dataclass(frozen=True)
class AgentProposal:
    """Bounded agent proposal validated by the engine before state mutation."""

    proposal_id: str
    turn_id: str | None
    cycle_id: str | None
    sequence: int
    role: AgentRole
    stage: MethodologyStage
    artifact_type: str
    payload_ref: MethodologyRef
    validation_status: ProposalValidationStatus
    reason_code: str
    node_id: str | None = None
    strategy: str | None = None
    skill_id: str | None = None
    display_summary: str = ""
    pedagogical_move: str = ""
    final_message_preview: str = ""
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize a proposal without raw payloads.

        The optional display fields are safe, bounded summaries for the
        frontend/export trace. They intentionally exclude raw learner answers,
        prompts, provider output bodies, credentials, and chain-of-thought.
        """
        return {
            "proposal_id": _bounded_text(self.proposal_id, 80),
            "turn_id": self.turn_id,
            "cycle_id": self.cycle_id,
            "sequence": int(self.sequence),
            "role": self.role.value,
            "stage": self.stage.value,
            "artifact_type": _bounded_text(self.artifact_type, 80),
            "payload_ref": self.payload_ref.to_dict(),
            "validation_status": self.validation_status.value,
            "reason_code": _bounded_text(self.reason_code, 120),
            "node_id": self.node_id,
            "strategy": self.strategy,
            "skill_id": self.skill_id,
            "display_summary": _bounded_text(self.display_summary, 260),
            "pedagogical_move": _bounded_text(self.pedagogical_move, 80),
            "final_message_preview": _bounded_text(self.final_message_preview, 220),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentProposal":
        """Deserialize one proposal with strict enum validation."""
        return cls(
            proposal_id=_bounded_text(payload.get("proposal_id"), 80),
            turn_id=payload.get("turn_id"),
            cycle_id=payload.get("cycle_id"),
            sequence=int(payload.get("sequence", 0)),
            role=AgentRole(payload.get("role")),
            stage=MethodologyStage(payload.get("stage")),
            artifact_type=_bounded_text(payload.get("artifact_type"), 80),
            payload_ref=MethodologyRef.from_dict(payload.get("payload_ref")),
            validation_status=ProposalValidationStatus(payload.get("validation_status")),
            reason_code=_bounded_text(payload.get("reason_code", "recorded"), 120),
            node_id=payload.get("node_id"),
            strategy=payload.get("strategy"),
            skill_id=payload.get("skill_id"),
            display_summary=_bounded_text(payload.get("display_summary"), 260),
            pedagogical_move=_bounded_text(payload.get("pedagogical_move"), 80),
            final_message_preview=_bounded_text(payload.get("final_message_preview"), 220),
            created_at=payload.get("created_at", _utc_now()),
        )


@dataclass(frozen=True)
class MethodologyEvent:
    """Cycle-grouped event describing the Figure 1 learning pipeline."""

    event_id: str
    turn_id: str | None
    cycle_id: str | None
    sequence: int
    event_type: MethodologyEventType
    stage: MethodologyStage | None
    status: MethodologyStatus
    source: str
    input_ref: MethodologyRef | None
    output_ref: MethodologyRef | None
    node_id: str | None = None
    strategy: str | None = None
    reason_code: str = "recorded"
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize safe methodology event metadata."""
        return {
            "event_id": _bounded_text(self.event_id, 80),
            "turn_id": self.turn_id,
            "cycle_id": self.cycle_id,
            "sequence": int(self.sequence),
            "event_type": self.event_type.value,
            "stage": self.stage.value if self.stage else None,
            "status": self.status.value,
            "source": _bounded_text(self.source, 80),
            "input_ref": self.input_ref.to_dict() if self.input_ref else None,
            "output_ref": self.output_ref.to_dict() if self.output_ref else None,
            "node_id": self.node_id,
            "strategy": self.strategy,
            "reason_code": _bounded_text(self.reason_code, 120),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MethodologyEvent":
        """Deserialize one methodology event with bounded metadata."""
        stage_value = payload.get("stage")
        return cls(
            event_id=_bounded_text(payload.get("event_id"), 80),
            turn_id=payload.get("turn_id"),
            cycle_id=payload.get("cycle_id"),
            sequence=int(payload.get("sequence", 0)),
            event_type=MethodologyEventType(payload.get("event_type")),
            stage=MethodologyStage(stage_value) if stage_value else None,
            status=MethodologyStatus(payload.get("status")),
            source=_bounded_text(payload.get("source"), 80),
            input_ref=MethodologyRef.from_dict(payload.get("input_ref")) if payload.get("input_ref") else None,
            output_ref=MethodologyRef.from_dict(payload.get("output_ref")) if payload.get("output_ref") else None,
            node_id=payload.get("node_id"),
            strategy=payload.get("strategy"),
            reason_code=_bounded_text(payload.get("reason_code", "recorded"), 120),
            created_at=payload.get("created_at", _utc_now()),
        )


@dataclass(frozen=True)
class TutoringContext:
    """Current-turn context used by deterministic tutoring strategy selection."""

    category: ResponseCategory
    rounds: int
    pedagogical_policy: str
    learner_state: str
    node_id: str | None
    node_label: str
    recent_signals: tuple[str, ...] = ()
    plan_source: PlanSource = PlanSource.GENERATED
    skill_id: str | None = None
    dialogue_act: str = ""
    repeated_confusion_count: int = 0


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
class DialogueActSignal:
    """Bounded dialogue-act proposal for one learner turn.

    Args:
        act: Conversational role detected before cognitive diagnosis.
        confidence: Conservative confidence from deterministic or LLM-backed
            classification. The engine may fail closed to diagnosis when this
            is low.
        target_text: Bounded term or phrase the learner appears to ask about.
            This may appear in traces and must not contain full raw prompts.
        reason_code: Stable safe reason code for observability and tests.

    Privacy:
        ``target_text`` is capped and intended for short terms such as
        "轉折點"; callers must not pass full learner answers or prompts here.
    """

    act: LearnerDialogueAct
    confidence: float = 0.0
    target_text: str = ""
    reason_code: str = "unknown"

    def to_safe_dict(self) -> dict[str, str | float]:
        """Serialize bounded dialogue-act metadata for traces and tests."""
        return {
            "act": self.act.value,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "target_text": _bounded_text(self.target_text, 80),
            "reason_code": _bounded_text(self.reason_code, 80),
        }


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
    teaching_methodology: dict[str, str] = field(default_factory=dict)
    remediation_templates: dict[str, str] = field(default_factory=dict)
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
            "teaching_methodology": dict(self.teaching_methodology),
            "remediation_templates": dict(self.remediation_templates),
            "created_at": self.created_at,
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Return a learner/API-safe representation without answer keys.

        ``to_dict`` remains the local persistence format and must keep
        ``expected_answer`` so existing saved sessions can be restored. Public
        surfaces should use this method when exposing plan structure.
        """
        payload = self.to_dict()
        payload["diagnostics"] = [
            {
                "node_id": diagnostic["node_id"],
                "prompt": diagnostic["prompt"],
                "source": diagnostic["source"],
            }
            for diagnostic in payload["diagnostics"]
        ]
        return payload

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
            teaching_methodology={
                str(key)[:80]: str(value)[:800]
                for key, value in payload.get("teaching_methodology", {}).items()
            },
            remediation_templates={
                str(key)[:80]: str(value)[:800]
                for key, value in payload.get("remediation_templates", {}).items()
            },
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
    route: str = "fast"
    selected_strategy: str = ""
    dialogue_act: str = ""
    updated_at: str | None = None


@dataclass(frozen=True)
class LearningMemorySnapshot:
    """Track local memory counters while retaining direct evidence as the source of truth."""

    evidence_count: int = 0
    working_context_count: int = 0
    recent_dialogue_acts: tuple[str, ...] = ()
    recent_tutor_moves: tuple[str, ...] = ()
    repeated_confusion_count: int = 0
    updated_at: str | None = None


@dataclass(frozen=True)
class ActivityEvent:
    """Safe, user-visible system activity entry for observability UI."""

    code: str
    label: str
    status: str = "done"
    detail: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, str]:
        """Return an API-safe activity entry without raw learner/model content."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ActivityEvent":
        """Deserialize an activity entry with bounded compatibility defaults."""
        return cls(
            code=str(payload.get("code", "unknown"))[:80],
            label=str(payload.get("label", "Unknown activity"))[:120],
            status=str(payload.get("status", "done"))[:40],
            detail=str(payload.get("detail", ""))[:160],
            timestamp=payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


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


@dataclass(frozen=True)
class TranscriptEntry:
    """One exportable chat transcript entry for the local MVP session.

    Transcript entries intentionally preserve learner-visible text because the
    export feature is explicitly user-triggered and local to the MVP. They remain
    separate from structured logs, which must never contain raw prompts or user
    answers.
    """

    role: str
    text: str
    phase: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe transcript entry."""
        return {
            "role": self.role,
            "text": self.text,
            "phase": self.phase,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TranscriptEntry":
        """Deserialize a transcript entry with bounded compatibility defaults."""
        return cls(
            role=str(payload.get("role", "assistant"))[:32],
            text=str(payload.get("text", ""))[:4000],
            phase=str(payload.get("phase", "unknown"))[:80],
            timestamp=payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
        )


@dataclass
class SessionState:
    """Serialize the complete local state for one PELICAN learning session."""

    learner_id: str
    schema_version: int = 3
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
    activity_log: list[ActivityEvent] = field(default_factory=list)
    transcript: list[TranscriptEntry] = field(default_factory=list)
    turn_id: str | None = None
    cycle_id: str | None = None
    methodology_sequence: int = 0
    methodology_events: list[MethodologyEvent] = field(default_factory=list)
    agent_proposals: list[AgentProposal] = field(default_factory=list)
    learner_progress: LearnerProgressSnapshot = field(default_factory=lambda: LearnerProgressSnapshot(None, None, ()))
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
            "activity_log": [item.to_dict() for item in self.activity_log],
            "transcript": [item.to_dict() for item in self.transcript],
            "turn_id": self.turn_id,
            "cycle_id": self.cycle_id,
            "methodology_sequence": self.methodology_sequence,
            "methodology_events": [item.to_dict() for item in self.methodology_events[-64:]],
            "agent_proposals": [item.to_dict() for item in self.agent_proposals[-48:]],
            "learner_progress": self.learner_progress.to_dict(),
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
        methodology_events: list[MethodologyEvent] = []
        for item in payload.get("methodology_events", [])[-64:]:
            try:
                methodology_events.append(MethodologyEvent.from_dict(item))
            except (TypeError, ValueError):
                continue
        agent_proposals: list[AgentProposal] = []
        for item in payload.get("agent_proposals", [])[-48:]:
            try:
                agent_proposals.append(AgentProposal.from_dict(item))
            except (TypeError, ValueError):
                continue
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
            activity_log=[
                ActivityEvent.from_dict(item)
                for item in payload.get("activity_log", [])
            ],
            transcript=[
                TranscriptEntry.from_dict(item)
                for item in payload.get("transcript", [])
            ],
            turn_id=payload.get("turn_id"),
            cycle_id=payload.get("cycle_id"),
            methodology_sequence=max(0, int(payload.get("methodology_sequence", 0))),
            methodology_events=methodology_events,
            agent_proposals=agent_proposals,
            learner_progress=LearnerProgressSnapshot.from_dict(payload.get("learner_progress")),
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
