"""Own model-assisted query decomposition and EDF response-policy selection."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace

from services.query_policy.models import (
    AnswerDepth,
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

logger = logging.getLogger(__name__)



_LEARNING_TECHNIQUE_PATTERNS: tuple[tuple[LearningTechnique, tuple[re.Pattern[str], ...]], ...] = (
    (
        LearningTechnique.TWENTY_HOUR_PLAN,
        tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
            r"20\s*小時|二十\s*小時|快速學會|快速掌握|rapidly learn|20-hour",
        )),
    ),
    (
        LearningTechnique.FEYNMAN_LOOP,
        tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
            r"費曼|feynman|用自己的話|重新說明|復述|teach me then quiz",
        )),
    ),
    (
        LearningTechnique.ONE_PAGE_NOTE,
        tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
            r"一頁|5\s*分鐘.*複習|重點筆記|cheat\s*sheet|one[- ]page",
        )),
    ),
    (
        LearningTechnique.DIAGNOSTIC_QUIZ,
        tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
            r"測驗|考我|出.*題|quiz me|test my understanding|knowledge gap",
        )),
    ),
    (
        LearningTechnique.LEVEL_PATH,
        tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
            r"五.*階段|5.*層級|level\s*1|學習路線|路線圖|roadmap",
        )),
    ),
    (
        LearningTechnique.RESOURCE_CURATOR,
        tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
            r"學習資源|推薦.*(書|影片|課程|專家|資源)|best resources|recommend.*(book|course|video|expert)",
        )),
    ),
)

_CURRENT_EVIDENCE_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(today|latest|current|recent|news|price|weather|schedule|version|guideline)\b",
    r"今天|目前|最新|近期|新聞|價格|天氣|時程|版本|現任|現在|指引|指南",
    r"20\d{2}",
))
_AUTHORITY_EVIDENCE_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"醫學|醫療|臨床|疾病|症狀|診斷|治療|藥物|副作用|疫苗|手術|癌症|感染",
    r"\b(medical|medicine|clinical|diagnosis|treatment|drug|medication|dose|vaccine|surgery|cancer|infection|guideline)\b",
    r"法律|法規|判例|合約|稅務|投資|保險|退休金|理財建議",
    r"\b(legal|law|regulation|contract|tax|investment|insurance|financial advice)\b",
))
_DOMAIN_ORIENTATION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"學\s*(什麼|哪些|甚麼)",
    r"(主要|通常|大概)?.{0,12}(學|包含|涵蓋|包括).{0,8}(哪些|什麼|甚麼|內容|面向)",
    r"\bwhat\s+(do|does|is)\b.{0,80}\b(study|learn|cover|include)\b",
    r"\bwhat\s+is\b.{0,80}\babout\b",
))
_BROAD_LEARNING_START_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"(我想|想要|準備|打算|要).{0,8}(學|開始學|入門).{0,30}(從哪|怎麼開始|如何開始|先學)",
    r"\b(i want to|i'd like to|where should i start|how should i start)\b.{0,80}\b(learn|study)\b",
))


def _detect_learning_technique(user_msg: str) -> LearningTechnique:
    """Return the strongest deterministic learning move implied by the user text."""

    normalized = str(user_msg or "")
    for technique, patterns in _LEARNING_TECHNIQUE_PATTERNS:
        if any(pattern.search(normalized) for pattern in patterns):
            return technique
    return LearningTechnique.NONE


def _detect_evidence_mode(user_msg: str) -> EvidenceMode:
    """Return the minimum external-grounding level for the user text.

    Args:
        user_msg: Current user message. It is inspected locally and must not be
            logged by callers.

    Returns:
        A conservative evidence mode. Professional domains outrank recency so
        medical, legal, and financial topics can require multiple authoritative
        sources even when the wording does not mention "latest".

    Side Effects:
        None.
    """

    normalized = str(user_msg or "")
    if any(pattern.search(normalized) for pattern in _AUTHORITY_EVIDENCE_PATTERNS):
        return EvidenceMode.MULTI_SOURCE_REQUIRED
    if any(pattern.search(normalized) for pattern in _CURRENT_EVIDENCE_PATTERNS):
        return EvidenceMode.CURRENT_REQUIRED
    return EvidenceMode.NONE


def _is_domain_orientation_request(user_msg: str) -> bool:
    """Return whether the user asks for a compact field-scope orientation."""

    normalized = str(user_msg or "").strip()
    return bool(normalized) and any(pattern.search(normalized) for pattern in _DOMAIN_ORIENTATION_PATTERNS)


def _is_broad_learning_start_request(user_msg: str) -> bool:
    """Return whether the user needs goal clarification before a study plan."""

    normalized = str(user_msg or "").strip()
    return bool(normalized) and any(pattern.search(normalized) for pattern in _BROAD_LEARNING_START_PATTERNS)


def _normalize_learning_ownership(policy: ResponsePolicy) -> ResponsePolicy:
    """Resolve internally inconsistent EDF ownership choices without reading text."""

    if policy.task_intent is not TaskIntent.ANSWER_EXAM:
        return policy
    if (
        policy.learning_mode is LearningMode.PRACTICE
        and policy.pedagogical_action is not PedagogicalAction.ANSWER
        and policy.answer_depth is not AnswerDepth.DIRECT
    ):
        return policy
    return replace(
        policy,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.REQUIRED,
        learning_mode=LearningMode.PRACTICE,
        pedagogical_action=PedagogicalAction.HINT,
        legacy_policy="PROBE_UNDERSTANDING",
    )


def _apply_learning_and_evidence_guardrails(
    policy: ResponsePolicy,
    *,
    user_msg: str,
) -> ResponsePolicy:
    """Apply deterministic tutoring-technique and evidence-mode guardrails.

    Args:
        policy: Sanitized classifier output.
        user_msg: Current user message. It is never logged.

    Returns:
        A policy with local deterministic upgrades when the classifier misses an
        explicit learning technique or high-authority domain.

    Side Effects:
        Emits ``orchestration.response_policy_learning_guardrail_applied`` with
        safe enum metadata only when the guardrail changes the policy.
    """

    detected_technique = _detect_learning_technique(user_msg)
    detected_evidence = _detect_evidence_mode(user_msg)
    learning_technique = (
        detected_technique
        if policy.learning_technique is LearningTechnique.NONE
        else policy.learning_technique
    )
    evidence_rank = {
        EvidenceMode.NONE: 0,
        EvidenceMode.CURRENT_REQUIRED: 1,
        EvidenceMode.AUTHORITY_REQUIRED: 2,
        EvidenceMode.MULTI_SOURCE_REQUIRED: 3,
    }
    evidence_mode = policy.evidence_mode
    if evidence_rank[detected_evidence] > evidence_rank[evidence_mode]:
        evidence_mode = detected_evidence
    guarded = replace(
        policy,
        learning_technique=learning_technique,
        evidence_mode=evidence_mode,
    )
    guarded = _normalize_learning_ownership(guarded)
    if _is_domain_orientation_request(user_msg):
        guarded = replace(
            guarded,
            task_intent=TaskIntent.GENERAL_QA,
            answer_depth=AnswerDepth.DIRECT,
            tone=ResponseTone.PLAIN,
            structure=ResponseStructure.SHORT,
            followup_mode=FollowupMode.OPTIONAL,
            learning_technique=LearningTechnique.NONE,
            learning_mode=LearningMode.REFERENCE,
            pedagogical_action=PedagogicalAction.ANSWER,
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            legacy_policy="NORMAL",
        )
    elif _is_broad_learning_start_request(user_msg):
        guarded = replace(
            guarded,
            task_intent=TaskIntent.GENERAL_QA,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.SHORT,
            followup_mode=FollowupMode.REQUIRED,
            learning_technique=LearningTechnique.NONE,
            learning_mode=LearningMode.LEARN,
            pedagogical_action=PedagogicalAction.DIAGNOSTIC_QUESTION,
            visual_support=VisualSupport.NONE,
            visual_reason=VisualReason.NOT_NEEDED,
            legacy_policy="PROBE_UNDERSTANDING",
        )
    if guarded != policy:
        logger.info(
            "orchestration.response_policy_learning_guardrail_applied metadata=%s",
            json.dumps(guarded.safe_log_metadata(), ensure_ascii=False, sort_keys=True),
        )
    return guarded
