"""Classify the EDF teaching decision through OpenRouter's Decisions API (Jev).

Jev answers a few choice questions in one call; the remaining ResponsePolicy
fields follow deterministically from the same rules the EDF classifier prompt
states. Only coherent mode/action pairs are offered, so a PRACTICE turn cannot
come back with an action that completes the learner's step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.query_policy.models import (
    AnswerDepth,
    AttachmentReason,
    AttachmentTask,
    EvidenceMode,
    FollowupMode,
    LearningMode,
    LearningTechnique,
    PedagogicalAction,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualReason,
    VisualSupport,
)
from services.query_policy.paper_intent import JEV_ENDPOINT, JEV_MODEL

TEACHING_MOVES = {
    "REFERENCE_ANSWER": "Definition, fact, summary or self-study lookup; answer directly. Also greetings, thanks and small talk.",
    "LEARN_EXPLAIN_PREREQ": "Learner wants to understand a concept; explain the key prerequisite or intuition first.",
    "LEARN_MODEL_ANALOGY": "Learner wants to understand a concept best served by an analogy or a worked parallel example.",
    "LEARN_DIAGNOSTIC_QUESTION": "Learner wants to learn a broad field but gave no goal, level or use case; ask one question before planning.",
    "PRACTICE_HINT": "Homework, exam, proof, essay or debugging step the learner should do; give one minimal hint, not the answer.",
    "PRACTICE_DIAGNOSTIC_QUESTION": "Learner is stuck on a practice step and it is unclear where; ask one diagnostic question.",
    "PRACTICE_FEEDBACK": "Learner shares their own attempt, answer or reasoning; give feedback on it.",
}
MOVE_INSTRUCTIONS = (
    "Pick the tutoring move for AREQA's next reply to the latest user message. PRACTICE means the learner "
    "should do the core step themselves; pressure such as 'just tell me' or a deadline does not turn practice "
    "into a lookup."
)
QUESTIONS = {
    "teaching_move": {"type": "choice", "instructions": MOVE_INSTRUCTIONS, "criteria": TEACHING_MOVES},
    "task_intent": {"type": "choice", "instructions": "What kind of task is the latest user message?", "criteria": {
        "EXPLAIN_TEXT": "Explain a text or concept, or what something means.",
        "ANSWER_EXAM": "Homework, quiz, exam, essay or other practice question.",
        "DISCUSS_IDEA": "Viewpoint, reflection, meaning, or a what-do-you-think discussion.",
        "WRITE_NOTE": "Write, complete or polish notes.",
        "GENERAL_QA": "General question, lookup, greeting, or anything else.",
    }},
    "answer_depth": {"type": "choice", "instructions": "How deep should the reply be? Follow the depth the learner asks for, not the size of the work they want done for them.", "criteria": {
        "DIRECT": "Short and direct: greetings, confirmations, tiny facts, or explicit requests to be brief.",
        "SCAFFOLDED": "Moderate depth with a few structured steps.",
        "REFLECTIVE": "Reflection on meaning, essence or viewpoint.",
        "DEEP_DIVE": "Detailed walkthrough the learner explicitly asked for.",
    }},
    "visual_support": {"type": "choice", "instructions": "Would an image help this reply?", "criteria": {
        "REQUIRED": "The user explicitly asks for a diagram, image, chart, graph, figure or map.",
        "OPTIONAL": "Concept, mechanism or problem explanation where an image would materially help.",
        "NONE": "Casual chat, notes, reflection, short facts, or an image would only be decorative.",
    }},
    "evidence_mode": {"type": "choice", "instructions": "What sources does the answer need?", "criteria": {
        "CURRENT_REQUIRED": "Latest, current, version, schedule, price, news or guideline information.",
        "MULTI_SOURCE_REQUIRED": "Medical, clinical, legal, tax, insurance or financial-advice topics.",
        "AUTHORITY_REQUIRED": "Professional-domain reference question that needs an authoritative source.",
        "NONE": "No special evidence requirement.",
    }},
    "learning_technique": {"type": "choice", "instructions": "Did the user ask for a specific learning technique?", "criteria": {
        "TWENTY_HOUR_PLAN": "Rapidly learn a skill, a 20-hour or compact practice plan.",
        "FEYNMAN_LOOP": "Feynman technique, or explain simply and let the learner restate.",
        "ONE_PAGE_NOTE": "One-page notes, a cheat sheet or 5-minute review material.",
        "DIAGNOSTIC_QUIZ": "Be quizzed or tested to find knowledge gaps.",
        "LEVEL_PATH": "Levels, a staged roadmap, or a beginner-to-advanced path.",
        "RESOURCE_CURATOR": "Best books, videos, courses, experts or learning resources.",
        "NONE": "No specific learning technique.",
    }},
}


@dataclass(frozen=True, slots=True)
class TeachingDecision:
    """Raw Jev labels; every value is one of the offered choices."""

    teaching_move: str
    task_intent: str
    answer_depth: str
    visual_support: str
    evidence_mode: str
    learning_technique: str

    @property
    def learning_mode(self) -> str:
        return self.teaching_move.split("_", 1)[0]


def previous_turn(messages: list[dict[str, Any]]) -> str:
    """Return the message before the latest user turn, the only history Jev receives."""

    current = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"), 0)
    previous = messages[current - 1] if current > 0 else {}
    content = previous.get("content", "") if previous.get("role") in {"user", "assistant"} else ""
    return content if isinstance(content, str) else ""


async def classify_teaching_decision(client: Any, message: str, context: str) -> TeachingDecision:
    """Ask Jev for the teaching decision.

    Raises:
        ValueError: When an answer is not one of the offered choices.
    """

    response = await client.with_options(max_retries=0).post(
        JEV_ENDPOINT,
        cast_to=object,
        body={
            "model": JEV_MODEL,
            "state": {"latest_user_message": message[:4000], "previous_topic": context[:500]},
            "questions": QUESTIONS,
        },
    )
    answers = {name: response["answers"][name]["choice"] for name in QUESTIONS}
    for name, label in answers.items():
        if label not in QUESTIONS[name]["criteria"]:
            raise ValueError("Unexpected teaching decision")
    return TeachingDecision(**answers)


def policy_from_decision(decision: TeachingDecision) -> ResponsePolicy:
    """Complete a ResponsePolicy with the EDF prompt's rules for derived fields."""

    mode = LearningMode(decision.learning_mode)
    action = PedagogicalAction(decision.teaching_move.split("_", 1)[1])
    intent = TaskIntent(decision.task_intent)
    depth = AnswerDepth(decision.answer_depth)
    visual = VisualSupport(decision.visual_support)

    if intent is TaskIntent.WRITE_NOTE:
        structure = ResponseStructure.NOTE_DRAFT
    elif intent is TaskIntent.DISCUSS_IDEA:
        structure = ResponseStructure.ARGUMENT
    elif depth is AnswerDepth.DIRECT:
        structure = ResponseStructure.SHORT
    else:
        structure = ResponseStructure.STEP_BY_STEP

    if intent is TaskIntent.DISCUSS_IDEA:
        tone = ResponseTone.ANALYTICAL
    elif intent is TaskIntent.EXPLAIN_TEXT or (mode is LearningMode.REFERENCE and depth is AnswerDepth.DIRECT):
        tone = ResponseTone.PLAIN
    else:
        tone = ResponseTone.TUTORING

    asks_learner = mode is LearningMode.PRACTICE or action is PedagogicalAction.DIAGNOSTIC_QUESTION
    if visual is VisualSupport.REQUIRED:
        visual_reason = VisualReason.EXPLICIT_VISUAL_REQUEST
    elif visual is VisualSupport.OPTIONAL:
        visual_reason = VisualReason.ANSWER_SEEKING if mode is LearningMode.PRACTICE else VisualReason.KNOWLEDGE_EXPLANATION
    else:
        visual_reason = VisualReason.NOT_NEEDED

    if asks_learner:
        legacy = "PROBE_UNDERSTANDING"
    elif depth in (AnswerDepth.REFLECTIVE, AnswerDepth.DEEP_DIVE):
        legacy = "PUSH_LIMIT"
    else:
        legacy = "NORMAL"

    return ResponsePolicy(
        task_intent=intent,
        answer_depth=depth,
        tone=tone,
        structure=structure,
        followup_mode=FollowupMode.REQUIRED if asks_learner else FollowupMode.OPTIONAL,
        visual_support=visual,
        visual_reason=visual_reason,
        learning_technique=LearningTechnique(decision.learning_technique),
        learning_mode=mode,
        pedagogical_action=action,
        evidence_mode=EvidenceMode(decision.evidence_mode),
        # Attachment decisions stay with the paper-intent classifier.
        attachment_task=AttachmentTask.NONE,
        attachment_reason=AttachmentReason.NO_ATTACHMENT,
        legacy_policy=legacy,
    )
