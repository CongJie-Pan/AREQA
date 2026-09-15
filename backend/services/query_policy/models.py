"""Response policy data contracts and coercion helpers.

These enums and dataclasses define AREQA's internal EDF response-shaping
contract. They are re-exported from ``services.query_policy_service`` for
compatibility with orchestration, context assembly, visual services, and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

class TaskIntent(str, Enum):
    """Supported user-task intents for EDF response shaping."""

    EXPLAIN_TEXT = "EXPLAIN_TEXT"
    ANSWER_EXAM = "ANSWER_EXAM"
    DISCUSS_IDEA = "DISCUSS_IDEA"
    WRITE_NOTE = "WRITE_NOTE"
    GENERAL_QA = "GENERAL_QA"


class AnswerDepth(str, Enum):
    """How much conceptual depth the feedback stage should open."""

    DIRECT = "DIRECT"
    SCAFFOLDED = "SCAFFOLDED"
    REFLECTIVE = "REFLECTIVE"
    DEEP_DIVE = "DEEP_DIVE"


class ResponseTone(str, Enum):
    """The voice used by the feedback stage for the current turn."""

    PLAIN = "PLAIN"
    TUTORING = "TUTORING"
    ANALYTICAL = "ANALYTICAL"
    LITERARY = "LITERARY"


class ResponseStructure(str, Enum):
    """The visible answer format selected by the EDF decision stage."""

    SHORT = "SHORT"
    STEP_BY_STEP = "STEP_BY_STEP"
    NOTE_DRAFT = "NOTE_DRAFT"
    ARGUMENT = "ARGUMENT"


class FollowupMode(str, Enum):
    """Whether the final answer should include an invitation to continue."""

    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class LearningTechnique(str, Enum):
    """Structured learning move selected for the current tutoring turn."""

    NONE = "NONE"
    TWENTY_HOUR_PLAN = "TWENTY_HOUR_PLAN"
    FEYNMAN_LOOP = "FEYNMAN_LOOP"
    ONE_PAGE_NOTE = "ONE_PAGE_NOTE"
    DIAGNOSTIC_QUIZ = "DIAGNOSTIC_QUIZ"
    LEVEL_PATH = "LEVEL_PATH"
    RESOURCE_CURATOR = "RESOURCE_CURATOR"


class LearningMode(str, Enum):
    """Who should own the cognitive work in the current learning turn."""

    REFERENCE = "REFERENCE"
    LEARN = "LEARN"
    PRACTICE = "PRACTICE"


class PedagogicalAction(str, Enum):
    """Single feedback move selected by the EDF decision stage."""

    ANSWER = "ANSWER"
    EXPLAIN_PREREQ = "EXPLAIN_PREREQ"
    MODEL_ANALOGY = "MODEL_ANALOGY"
    DIAGNOSTIC_QUESTION = "DIAGNOSTIC_QUESTION"
    HINT = "HINT"
    FEEDBACK = "FEEDBACK"
    TRANSFER = "TRANSFER"


class EvidenceMode(str, Enum):
    """How strictly the answer should rely on external authority."""

    NONE = "NONE"
    CURRENT_REQUIRED = "CURRENT_REQUIRED"
    AUTHORITY_REQUIRED = "AUTHORITY_REQUIRED"
    MULTI_SOURCE_REQUIRED = "MULTI_SOURCE_REQUIRED"


class VisualSupport(str, Enum):
    """Whether the current turn should spend visual enrichment cost."""

    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class VisualReason(str, Enum):
    """Allowlisted reason for the visual enrichment decision."""

    EXPLICIT_VISUAL_REQUEST = "EXPLICIT_VISUAL_REQUEST"
    KNOWLEDGE_EXPLANATION = "KNOWLEDGE_EXPLANATION"
    ANSWER_SEEKING = "ANSWER_SEEKING"
    ATTACHMENT_FIGURE_EXPLANATION = "ATTACHMENT_FIGURE_EXPLANATION"
    NOT_NEEDED = "NOT_NEEDED"


class AttachmentTask(str, Enum):
    """Optional attachment-scoped task selected by the policy classifier."""

    NONE = "NONE"
    PAPER_AUTO_EXPLAIN = "PAPER_AUTO_EXPLAIN"
    PAPER_TARGETED_QA = "PAPER_TARGETED_QA"


class AttachmentReason(str, Enum):
    """Allowlisted reason for attachment task decisions."""

    NO_ATTACHMENT = "NO_ATTACHMENT"
    GENERIC_PAPER_EXPLANATION = "GENERIC_PAPER_EXPLANATION"
    TARGETED_ATTACHMENT_TASK = "TARGETED_ATTACHMENT_TASK"
    NOT_PAPER_TASK = "NOT_PAPER_TASK"


ALLOWED_LEGACY_POLICIES = {
    "PROBE_UNDERSTANDING",
    "SUGGEST_ACTION",
    "PUSH_LIMIT",
    "NORMAL",
}

@dataclass(frozen=True, slots=True)
class ResponsePolicy:
    """Structured EDF decision that constrains final answer generation.

    Args:
        task_intent: The user's immediate task type.
        answer_depth: The maximum depth the feedback stage should use.
        tone: The response voice for this turn.
        structure: The expected answer shape.
        followup_mode: Whether a follow-up question should be omitted, optional,
            or required.
        visual_support: Whether this turn should spend image retrieval or PDF
            rendering cost.
        visual_reason: Sanitized reason for the visual support decision.
        learning_technique: Optional learning move that adapts the answer shape
            without requiring users to paste prompt templates.
        learning_mode: Whether this turn is reference lookup, learning support,
            or learner-owned practice.
        pedagogical_action: The one feedback move the answer model should
            express for this turn.
        evidence_mode: Optional grounding requirement for current or
            high-stakes professional-domain claims.
        attachment_task: Optional PDF-attachment task overlay selected by the
            same model policy call.
        attachment_reason: Sanitized reason for the attachment task decision.
        legacy_policy: Compatibility policy used by older orchestration code for
            token budgeting and tests.

    Compatibility:
        This object is an internal backend contract. It does not change the
        public chat API or SSE payloads. Logs must contain only enum values and
        correlation IDs, never raw user text, prompts, or model output.
    """

    task_intent: TaskIntent
    answer_depth: AnswerDepth
    tone: ResponseTone
    structure: ResponseStructure
    followup_mode: FollowupMode
    visual_support: VisualSupport = VisualSupport.NONE
    visual_reason: VisualReason = VisualReason.NOT_NEEDED
    learning_technique: LearningTechnique = LearningTechnique.NONE
    learning_mode: LearningMode = LearningMode.LEARN
    pedagogical_action: PedagogicalAction = PedagogicalAction.EXPLAIN_PREREQ
    evidence_mode: EvidenceMode = EvidenceMode.NONE
    attachment_task: AttachmentTask = AttachmentTask.NONE
    attachment_reason: AttachmentReason = AttachmentReason.NO_ATTACHMENT
    legacy_policy: str = "NORMAL"

    def safe_log_metadata(self) -> dict[str, str]:
        """Return privacy-safe enum metadata for structured logs."""

        return {
            "task_intent": self.task_intent.value,
            "answer_depth": self.answer_depth.value,
            "tone": self.tone.value,
            "structure": self.structure.value,
            "followup_mode": self.followup_mode.value,
            "visual_support": self.visual_support.value,
            "visual_reason": self.visual_reason.value,
            "learning_technique": self.learning_technique.value,
            "learning_mode": self.learning_mode.value,
            "pedagogical_action": self.pedagogical_action.value,
            "evidence_mode": self.evidence_mode.value,
            "attachment_task": self.attachment_task.value,
            "attachment_reason": self.attachment_reason.value,
            "legacy_policy": self.legacy_policy,
        }


def default_response_policy() -> ResponsePolicy:
    """Return a conservative EDF fallback policy for classifier failures.

    The fallback intentionally favors plain scaffolding over reflective depth so
    malformed model output cannot reopen AREQA's always-on essay style.
    """

    return ResponsePolicy(
        task_intent=TaskIntent.GENERAL_QA,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        visual_support=VisualSupport.NONE,
        visual_reason=VisualReason.NOT_NEEDED,
        learning_technique=LearningTechnique.NONE,
        learning_mode=LearningMode.LEARN,
        pedagogical_action=PedagogicalAction.EXPLAIN_PREREQ,
        evidence_mode=EvidenceMode.NONE,
        attachment_task=AttachmentTask.NONE,
        attachment_reason=AttachmentReason.NO_ATTACHMENT,
        legacy_policy="NORMAL",
    )


def _coerce_enum(enum_type: type[Enum], value: Any, fallback: Enum) -> Enum:
    """Coerce untrusted model output into an allowlisted enum value."""

    try:
        return enum_type(str(value).strip())
    except Exception:
        return fallback


def response_policy_from_dict(payload: Any) -> ResponsePolicy:
    """Build a sanitized ``ResponsePolicy`` from untrusted JSON.

    Args:
        payload: Model-produced JSON decoded into a Python object.

    Returns:
        A fully allowlisted ``ResponsePolicy``. Unknown values are replaced with
        conservative defaults rather than failing open into deep analysis.
    """

    fallback = default_response_policy()
    if not isinstance(payload, dict):
        return fallback
    legacy_policy = str(payload.get("legacy_policy") or fallback.legacy_policy).strip()
    if legacy_policy not in ALLOWED_LEGACY_POLICIES:
        legacy_policy = fallback.legacy_policy
    answer_depth = _coerce_enum(AnswerDepth, payload.get("answer_depth"), fallback.answer_depth)
    learning_mode = _coerce_enum(
        LearningMode,
        payload.get("learning_mode"),
        fallback.learning_mode,
    )
    pedagogical_action = _coerce_enum(
        PedagogicalAction,
        payload.get("pedagogical_action"),
        fallback.pedagogical_action,
    )
    if answer_depth is AnswerDepth.DIRECT:
        if "learning_mode" not in payload:
            learning_mode = LearningMode.REFERENCE
        if "pedagogical_action" not in payload:
            pedagogical_action = PedagogicalAction.ANSWER
    return ResponsePolicy(
        task_intent=_coerce_enum(TaskIntent, payload.get("task_intent"), fallback.task_intent),
        answer_depth=answer_depth,
        tone=_coerce_enum(ResponseTone, payload.get("tone"), fallback.tone),
        structure=_coerce_enum(
            ResponseStructure,
            payload.get("structure"),
            fallback.structure,
        ),
        followup_mode=_coerce_enum(
            FollowupMode,
            payload.get("followup_mode"),
            fallback.followup_mode,
        ),
        visual_support=_coerce_enum(
            VisualSupport,
            payload.get("visual_support"),
            fallback.visual_support,
        ),
        visual_reason=_coerce_enum(
            VisualReason,
            payload.get("visual_reason"),
            fallback.visual_reason,
        ),
        learning_technique=_coerce_enum(
            LearningTechnique,
            payload.get("learning_technique"),
            fallback.learning_technique,
        ),
        learning_mode=learning_mode,
        pedagogical_action=pedagogical_action,
        evidence_mode=_coerce_enum(
            EvidenceMode,
            payload.get("evidence_mode"),
            fallback.evidence_mode,
        ),
        attachment_task=_coerce_enum(
            AttachmentTask,
            payload.get("attachment_task"),
            fallback.attachment_task,
        ),
        attachment_reason=_coerce_enum(
            AttachmentReason,
            payload.get("attachment_reason"),
            fallback.attachment_reason,
        ),
        legacy_policy=legacy_policy,
    )


def response_policy_from_legacy(policy: Any) -> ResponsePolicy:
    """Bridge older string-only policies into a conservative response policy.

    Args:
        policy: A legacy dialogue policy string, often supplied by older tests
            through mocks.

    Returns:
        A structured policy that preserves old token-budget intent without
        enabling deep style unless the legacy policy was explicitly
        ``PUSH_LIMIT``.
    """

    legacy_policy = str(policy or "NORMAL").strip()
    if legacy_policy not in ALLOWED_LEGACY_POLICIES:
        legacy_policy = "NORMAL"
    if legacy_policy == "PUSH_LIMIT":
        return ResponsePolicy(
            task_intent=TaskIntent.DISCUSS_IDEA,
            answer_depth=AnswerDepth.REFLECTIVE,
            tone=ResponseTone.ANALYTICAL,
            structure=ResponseStructure.ARGUMENT,
            followup_mode=FollowupMode.OPTIONAL,
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            learning_technique=LearningTechnique.NONE,
            learning_mode=LearningMode.LEARN,
            pedagogical_action=PedagogicalAction.TRANSFER,
            evidence_mode=EvidenceMode.NONE,
            attachment_task=AttachmentTask.NONE,
            attachment_reason=AttachmentReason.NO_ATTACHMENT,
            legacy_policy=legacy_policy,
        )
    if legacy_policy == "SUGGEST_ACTION":
        return ResponsePolicy(
            task_intent=TaskIntent.GENERAL_QA,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            learning_technique=LearningTechnique.NONE,
            learning_mode=LearningMode.LEARN,
            pedagogical_action=PedagogicalAction.HINT,
            evidence_mode=EvidenceMode.NONE,
            attachment_task=AttachmentTask.NONE,
            attachment_reason=AttachmentReason.NO_ATTACHMENT,
            legacy_policy=legacy_policy,
        )
    if legacy_policy == "PROBE_UNDERSTANDING":
        return ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.REQUIRED,
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            learning_technique=LearningTechnique.NONE,
            learning_mode=LearningMode.PRACTICE,
            pedagogical_action=PedagogicalAction.DIAGNOSTIC_QUESTION,
            evidence_mode=EvidenceMode.NONE,
            attachment_task=AttachmentTask.NONE,
            attachment_reason=AttachmentReason.NO_ATTACHMENT,
            legacy_policy=legacy_policy,
        )
    return default_response_policy()
