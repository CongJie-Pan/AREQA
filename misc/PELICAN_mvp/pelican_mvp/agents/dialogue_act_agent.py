"""Dialogue-act agent for pre-diagnosis learner utterance routing."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import (
    AgentRole,
    DialogueActSignal,
    LearnerDialogueAct,
    MethodologyRef,
    MethodologyStage,
    ProposalValidationStatus,
)
from .artifacts import bound_agent_text, safe_artifact_ref
from .base import AgentExecutionContext, AgentExecutionResult


_MICRO_CHECK_TERMS = ("轉折點", "原因", "影響", "關鍵", "重點", "選哪個", "怎麼選")
_TERM_QUESTION_PATTERNS = (
    re.compile(r"^(?P<target>[\w\u4e00-\u9fff]{1,24})是什麼意思?[？?]?$"),
    re.compile(r"^(?P<target>[\w\u4e00-\u9fff]{1,24})是什麼[？?]?$"),
    re.compile(r"^什麼是(?P<target>[\w\u4e00-\u9fff]{1,24})[？?]?$"),
    re.compile(r"^什麼(?P<target>[\w\u4e00-\u9fff]{1,24})[？?]?$"),
)


@dataclass(frozen=True)
class DialogueActInterpretation:
    """Safe dialogue-act interpretation returned before engine mutation.

    Args:
        result: Bounded proposal metadata for the methodology trace.
        signal: Detected conversational role. Only ``ANSWER_ATTEMPT`` should be
            forwarded to cognitive diagnosis without a router intervention.
    """

    result: AgentExecutionResult
    signal: DialogueActSignal


class DialogueActAgent:
    """Classify learner utterances before mastery diagnosis.

    The agent is intentionally rule-first and conservative. It catches obvious
    conversational control turns, such as "什麼轉折點？", so the engine can
    clarify the tutor's own question instead of treating the turn as wrong
    knowledge evidence. Ambiguous content remains an ``ANSWER_ATTEMPT`` for the
    existing diagnosis path.
    """

    role = AgentRole.DIALOGUE_ACT_AGENT

    def classify(
        self,
        answer: str,
        *,
        current_prompt: str = "",
        previous_tutor_message: str = "",
        node_label: str = "",
        context: AgentExecutionContext | None = None,
    ) -> DialogueActInterpretation:
        """Classify one learner utterance into a bounded dialogue act.

        Args:
            answer: Latest learner utterance. It is inspected locally but never
                copied into structured trace metadata.
            current_prompt: Current diagnostic or tutoring prompt used only to
                infer whether a short question targets the active micro-check.
            previous_tutor_message: Previous tutor message used only for bounded
                term matching; raw content is not emitted.
            node_label: Current concept label used as a weak grounding hint.
            context: Optional execution correlation IDs.

        Returns:
            A dialogue-act interpretation with safe proposal metadata.
        """
        signal = _classify_rule(
            answer,
            current_prompt=current_prompt,
            previous_tutor_message=previous_tutor_message,
            node_label=node_label,
        )
        result = self._result(signal, context=context)
        return DialogueActInterpretation(result=result, signal=signal)

    def _result(
        self,
        signal: DialogueActSignal,
        *,
        context: AgentExecutionContext | None,
    ) -> AgentExecutionResult:
        """Build one bounded accepted dialogue-act proposal."""
        ref: MethodologyRef = safe_artifact_ref(
            "learner_turn",
            (context.turn_id if context else None) or "turn",
            "dialogue act signal",
        )
        return AgentExecutionResult(
            role=self.role,
            stage=MethodologyStage.COGNITIVE_DIAGNOSIS,
            artifact_type="dialogue_act_signal",
            artifact_ref=ref,
            validation_status=ProposalValidationStatus.ACCEPTED,
            reason_code=signal.reason_code,
            display_summary=bound_agent_text(f"{signal.act.value}:{signal.target_text}", 120),
            proposal_source="rule",
        )


def _classify_rule(
    answer: str,
    *,
    current_prompt: str,
    previous_tutor_message: str,
    node_label: str,
) -> DialogueActSignal:
    """Return a conservative deterministic dialogue-act signal."""
    text = re.sub(r"\s+", "", str(answer or "")).strip()
    if not text:
        return DialogueActSignal(LearnerDialogueAct.OTHER, 0.4, reason_code="empty_utterance")

    if _contains_any(text, ("太難", "看不懂", "不懂", "聽不懂", "更簡單")):
        return DialogueActSignal(LearnerDialogueAct.TOO_HARD, 0.82, reason_code="explicit_too_hard")
    if _contains_any(text, ("太簡單", "太容易", "已經會", "跳過")):
        return DialogueActSignal(LearnerDialogueAct.TOO_EASY, 0.82, reason_code="explicit_too_easy")
    if _contains_any(text, ("繼續", "下一個", "懂了", "可以了")) and len(text) <= 12:
        return DialogueActSignal(
            LearnerDialogueAct.READY_TO_CONTINUE,
            0.74,
            reason_code="explicit_continue",
        )
    if _contains_any(text, ("我想改學", "換成", "不是這個主題")):
        return DialogueActSignal(LearnerDialogueAct.TOPIC_SHIFT, 0.78, reason_code="topic_shift_phrase")

    target = _term_question_target(text)
    if target:
        act = (
            LearnerDialogueAct.MICRO_CHECK_CONFUSION
            if _is_micro_check_target(target, current_prompt, previous_tutor_message, node_label)
            else LearnerDialogueAct.TERM_DEFINITION_REQUEST
        )
        return DialogueActSignal(act, 0.88, target_text=target, reason_code="short_term_question")

    if _contains_any(text, ("不知道選哪個", "不知選哪個", "怎麼選", "選哪個", "哪一個")):
        return DialogueActSignal(
            LearnerDialogueAct.MICRO_CHECK_CONFUSION,
            0.84,
            target_text=_first_micro_check_term(current_prompt, previous_tutor_message),
            reason_code="micro_check_choice_confusion",
        )
    inline_micro_term = _inline_micro_check_term(text)
    if inline_micro_term and text.endswith(("?", "？")):
        return DialogueActSignal(
            LearnerDialogueAct.MICRO_CHECK_CONFUSION,
            0.84,
            target_text=inline_micro_term,
            reason_code="inline_micro_check_term_question",
        )
    if text.endswith(("?", "？")) and len(text) <= 28:
        return DialogueActSignal(
            LearnerDialogueAct.CLARIFICATION_QUESTION,
            0.68,
            target_text=_bounded_question_target(text),
            reason_code="short_clarification_question",
        )

    return DialogueActSignal(LearnerDialogueAct.ANSWER_ATTEMPT, 0.7, reason_code="default_answer_attempt")


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    """Return whether any compact token appears in normalized text."""
    return any(token in text for token in tokens)


def _term_question_target(text: str) -> str:
    """Extract a bounded term from a short definition-style question."""
    for pattern in _TERM_QUESTION_PATTERNS:
        match = pattern.match(text)
        if match:
            target = match.group("target").strip("？?")
            return bound_agent_text(target, 24)
    return ""


def _is_micro_check_target(target: str, current_prompt: str, previous_tutor_message: str, node_label: str) -> bool:
    """Return whether a short term likely references the active micro-check."""
    haystack = f"{current_prompt} {previous_tutor_message} {node_label}"
    return target in haystack or target in _MICRO_CHECK_TERMS


def _first_micro_check_term(current_prompt: str, previous_tutor_message: str) -> str:
    """Return the first known micro-check term seen in recent tutor context."""
    haystack = f"{current_prompt} {previous_tutor_message}"
    for term in _MICRO_CHECK_TERMS:
        if term in haystack:
            return term
    return ""


def _inline_micro_check_term(text: str) -> str:
    """Return a known micro-check term mentioned inside a short question."""
    for term in _MICRO_CHECK_TERMS:
        if term in text:
            return term
    return ""


def _bounded_question_target(text: str) -> str:
    """Return a short safe summary of a clarification question target."""
    cleaned = text.strip("？?")
    for prefix in ("什麼", "為什麼", "怎麼"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return bound_agent_text(cleaned, 32)
