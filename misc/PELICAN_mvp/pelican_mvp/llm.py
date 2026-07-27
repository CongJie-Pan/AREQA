"""Optional OpenAI-compatible LLM support with safe rule-mode fallback."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from .domain_skill import DomainCategory, DomainSkill, IntentType, SkillLifecycle, REQUIRED_REMEDIATION_SIGNALS
from .models import (
    BoundedTutorProposal,
    DiagnosticQuestion,
    KnowledgeNode,
    LearningPlanSnapshot,
    ResponseCategory,
    TutoringStrategy,
)
from .observability import log_event


class LlmUnavailable(RuntimeError):
    """Raised when optional LLM capabilities are unavailable or invalid.

    Args:
        message: Human-readable internal failure summary. This string is never
            emitted directly through structured logs.
        reason_codes: Stable safe reason codes suitable for logs/artifacts.
        api_status_code: Optional HTTP status code from the OpenAI-compatible
            provider. Response bodies and credentials are intentionally excluded.
        api_error_type: Optional provider/openai exception class or safe error
            type for debugging route availability.
    """

    def __init__(
        self,
        message: str,
        *,
        reason_codes: tuple[str, ...] = (),
        api_status_code: int | None = None,
        api_error_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_codes = reason_codes
        self.api_status_code = api_status_code
        self.api_error_type = api_error_type


@dataclass(frozen=True)
class LlmHealth:
    """Safe health result for one configured model route."""

    available: bool
    reason_codes: tuple[str, ...]
    api_status_code: int | None = None
    api_error_type: str | None = None


@dataclass(frozen=True)
class IntakeSemanticSignal:
    """Structured semantic signal for onboarding state transitions.

    The language model is allowed to classify and extract bounded fields, but it
    is not allowed to perform the state transition itself. ``PelicanEngine``
    remains the owner of topic changes, intake reset, domain routing, and
    follow-up question selection.
    """

    intent: str
    confidence: float
    reason_code: str
    new_topic: str = ""


@dataclass(frozen=True)
class LlmConfig:
    """OpenAI-compatible transport configuration for optional OpenRouter calls."""

    api_key: str
    model: str
    base_url: str

    @classmethod
    def from_environment(cls) -> "LlmConfig | None":
        """Load optional LLM settings without making credentials mandatory."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            model=os.getenv("PELICAN_LLM_MODEL", "qwen/qwen-2.5-7b-instruct"),
            base_url=os.getenv("PELICAN_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        )


DEFAULT_SKILL_MODEL_ROUTES = {
    DomainCategory.STEM: "openai/gpt-5.5",
    DomainCategory.HUMANITIES: "~google/gemini-pro-latest",
    DomainCategory.BUSINESS: "~google/gemini-pro-latest",
    DomainCategory.LANGUAGE: "~google/gemini-pro-latest",
}
DEFAULT_TUTOR_MODEL = "google/gemini-3.1-flash-lite"
SKILL_SCHEMA_MODE_ENV = "PELICAN_SKILL_SCHEMA_MODE"
SKILL_SCHEMA_MODELS_ENV = "PELICAN_SKILL_SCHEMA_MODELS"
STRUCTURED_OUTPUT_COMPATIBILITY_ERRORS = {
    "bad_request",
    "invalid_request",
    "invalid_request_error",
    "unsupported_parameter",
    "unknown_parameter",
    "not_supported",
}

MODEL_ROUTE_ENV = {
    DomainCategory.STEM: "PELICAN_STEM_MODEL",
    DomainCategory.HUMANITIES: "PELICAN_HUMANITIES_MODEL",
    DomainCategory.BUSINESS: "PELICAN_BUSINESS_MODEL",
    DomainCategory.LANGUAGE: "PELICAN_LANGUAGE_MODEL",
}


def _domain_skill_json_contract(topic: str, category: DomainCategory) -> str:
    """Return a compact valid DomainSkill example for schema-constrained prompting."""
    slug = _slugify_identifier(topic) or "runtime_topic"
    example = {
        "skill_id": slug[:60],
        "version": "0.1.0",
        "title": f"{topic} Learning Skill",
        "domain_category": category.value,
        "lifecycle": SkillLifecycle.RUNTIME_GENERATED.value,
        "supported_topics": [topic, f"{topic} overview"],
        "intent_types": ["conceptual", "explanatory", "assessment"],
        "prerequisites": [
            {
                "concept_id": "context_foundation",
                "label": "Context foundation",
                "prerequisites": [],
                "description": "Core background needed before detailed study.",
            },
            {
                "concept_id": "key_timeline",
                "label": "Key timeline",
                "prerequisites": ["context_foundation"],
                "description": "Major sequence, actors, and turning points.",
            },
            {
                "concept_id": "cause_effect_reasoning",
                "label": "Cause-effect reasoning",
                "prerequisites": ["context_foundation", "key_timeline"],
                "description": "Use evidence to connect causes, events, and consequences.",
            },
        ],
        "calibration_questions": [
            {
                "question_id": "goal",
                "prompt": "你想先建立脈絡、理解關鍵事件，還是準備考試式整理？",
                "intent_targets": ["conceptual", "explanatory", "assessment"],
                "level_targets": ["beginner", "intermediate"],
            }
        ],
        "canonical_path": {
            "conceptual": ["context_foundation", "key_timeline", "cause_effect_reasoning"],
            "explanatory": ["context_foundation", "key_timeline", "cause_effect_reasoning"],
            "assessment": ["context_foundation", "key_timeline", "cause_effect_reasoning"],
        },
        "diagnostic_rules": [
            {
                "rule_id": "diag_context_foundation",
                "concept_id": "context_foundation",
                "prompt": "請用自己的話說明這個主題的基本背景是什麼。",
                "expected_answer": "Learner should mention the central background and setting.",
                "tests_single_concept": True,
            },
            {
                "rule_id": "diag_key_timeline",
                "concept_id": "key_timeline",
                "prompt": "請列出一個關鍵事件，並說明它在整體脈絡中的位置。",
                "expected_answer": "Learner should identify an event and place it in sequence.",
                "tests_single_concept": True,
            },
            {
                "rule_id": "diag_cause_effect_reasoning",
                "concept_id": "cause_effect_reasoning",
                "prompt": "請說明一個原因如何導致後續結果。",
                "expected_answer": "Learner should connect cause and consequence with evidence.",
                "tests_single_concept": True,
            },
        ],
        "teaching_moves": [
            {
                "move_id": "focused_mini_lesson",
                "strategy": "focused_mini_lesson",
                "description": "Explain one concept briefly before asking a check question.",
            },
            {
                "move_id": "guided_example",
                "strategy": "guided_example",
                "description": "Walk through one concrete example step by step.",
            },
            {
                "move_id": "socratic_question",
                "strategy": "socratic_question",
                "description": "Ask a targeted question to reveal learner reasoning.",
            },
        ],
        "remediation_paths": [
            {"signal": "unknown", "action": "scaffold_prerequisite", "target": "context_foundation"},
            {"signal": "too_detailed", "action": "recalibrate_level", "target": "goal"},
            {"signal": "too_easy", "action": "accelerate", "target": "cause_effect_reasoning"},
            {"signal": "project_goal", "action": "switch_path", "target": "explanatory"},
            {"signal": "assessment_goal", "action": "switch_path", "target": "assessment"},
        ],
        "assessment_policy": {
            "mode": "formative",
            "education_only": True,
            "notes": "Use low-stakes checks and avoid professional advice.",
        },
        "teaching_methodology": {
            "diagnosis": "Start with one concept at a time.",
            "sequencing": "Move from context to sequence to causal reasoning.",
        },
        "remediation_templates": {
            "context_foundation": "Let us rebuild the background with one simple anchor.",
            "key_timeline": "Let us place this event before and after two nearby events.",
            "cause_effect_reasoning": "Let us connect one cause to one consequence using evidence.",
        },
        "safety_notes": ["Educational use only."],
    }
    return json.dumps(example, ensure_ascii=False, indent=2)


def _domain_skill_json_schema(category: DomainCategory) -> dict[str, Any]:
    """Build the provider-native JSON schema for DomainSkill generation.

    Returns:
        A JSON Schema object used inside OpenAI/OpenRouter
        ``response_format={"type": "json_schema"}`` requests.

    Compatibility:
        OpenRouter exposes an OpenAI-compatible ``json_schema`` response format,
        while Gemini's direct API uses a different ``responseSchema`` field.
        This schema intentionally uses common JSON Schema keywords only and is
        still followed by local ``DomainSkill`` parsing and validation.
    """
    string_array = {"type": "array", "items": {"type": "string"}, "minItems": 1}
    min_concepts = 6 if category is DomainCategory.HUMANITIES else 1
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "skill_id",
            "version",
            "title",
            "domain_category",
            "lifecycle",
            "supported_topics",
            "intent_types",
            "prerequisites",
            "calibration_questions",
            "canonical_path",
            "diagnostic_rules",
            "teaching_moves",
            "remediation_paths",
            "assessment_policy",
            "teaching_methodology",
            "remediation_templates",
            "safety_notes",
        ],
        "properties": {
            "skill_id": {"type": "string", "description": "Stable bounded identifier without whitespace."},
            "version": {"type": "string"},
            "title": {"type": "string"},
            "domain_category": {"type": "string", "enum": [category.value]},
            "lifecycle": {"type": "string", "enum": [SkillLifecycle.RUNTIME_GENERATED.value]},
            "supported_topics": string_array,
            "intent_types": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "enum": [item.value for item in IntentType]},
            },
            "prerequisites": {
                "type": "array",
                "minItems": min_concepts,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["concept_id", "label", "prerequisites", "description"],
                    "properties": {
                        "concept_id": {"type": "string"},
                        "label": {"type": "string"},
                        "prerequisites": {"type": "array", "items": {"type": "string"}},
                        "description": {"type": "string"},
                    },
                },
            },
            "calibration_questions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["question_id", "prompt", "intent_targets", "level_targets"],
                    "properties": {
                        "question_id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "intent_targets": string_array,
                        "level_targets": string_array,
                    },
                },
            },
            "canonical_path": {
                "type": "object",
                "description": "Keys are intent types. Values are concept_id arrays from prerequisites.",
                "additionalProperties": string_array,
            },
            "diagnostic_rules": {
                "type": "array",
                "minItems": min_concepts,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["rule_id", "concept_id", "prompt", "expected_answer", "tests_single_concept"],
                    "properties": {
                        "rule_id": {"type": "string"},
                        "concept_id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "expected_answer": {"type": "string"},
                        "tests_single_concept": {"type": "boolean"},
                    },
                },
            },
            "teaching_moves": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["move_id", "strategy", "description"],
                    "properties": {
                        "move_id": {"type": "string"},
                        "strategy": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "remediation_paths": {
                "type": "array",
                "minItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["signal", "action", "target"],
                    "properties": {
                        "signal": {"type": "string", "enum": sorted(REQUIRED_REMEDIATION_SIGNALS)},
                        "action": {"type": "string"},
                        "target": {"type": "string"},
                    },
                },
            },
            "assessment_policy": {
                "type": "object",
                "additionalProperties": False,
                "required": ["mode", "education_only", "notes"],
                "properties": {
                    "mode": {"type": "string"},
                    "education_only": {"type": "boolean"},
                    "notes": {"type": "string"},
                },
            },
            "teaching_methodology": {"type": "object", "additionalProperties": {"type": "string"}},
            "remediation_templates": {"type": "object", "additionalProperties": {"type": "string"}},
            "safety_notes": {"type": "array", "items": {"type": "string"}},
        },
    }


def _domain_skill_response_format(category: DomainCategory) -> dict[str, Any]:
    """Return the OpenAI/OpenRouter strict schema response_format payload."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "domain_skill",
            "strict": True,
            "schema": _domain_skill_json_schema(category),
        },
    }


def _skill_schema_response_format_for_route(model_route: str, category: DomainCategory) -> dict[str, Any] | None:
    """Return strict schema response format when enabled for a model route.

    Args:
        model_route: OpenAI/OpenRouter model route selected for skill generation.
        category: Domain category used to constrain the generated schema.

    Returns:
        ``response_format`` payload for provider-native structured output, or
        ``None`` when the route should use JSON object compatibility mode.

    Environment:
        ``PELICAN_SKILL_SCHEMA_MODE`` supports:
        - ``auto`` (default): enable strict schema for OpenAI routes and
          allowlisted routes only.
        - ``strict``: force strict schema for every route; useful for manual
          compatibility verification.
        - ``json_object``: disable provider-native strict schema.

        ``PELICAN_SKILL_SCHEMA_MODELS`` is a comma-separated allowlist for
        routes verified to support OpenAI/OpenRouter ``json_schema`` format.
    """
    mode = _skill_schema_mode()
    if mode == "json_object":
        return None
    if mode == "strict" or _route_supports_skill_json_schema(model_route):
        return _domain_skill_response_format(category)
    return None


def _skill_schema_mode() -> str:
    """Read the bounded provider-native schema mode from environment."""
    raw_mode = os.getenv(SKILL_SCHEMA_MODE_ENV, "auto").strip().lower()
    return raw_mode if raw_mode in {"auto", "strict", "json_object"} else "auto"


def _route_supports_skill_json_schema(model_route: str) -> bool:
    """Return whether auto mode should attempt strict schema for this route."""
    normalized_route = model_route.strip().lower()
    allowlist = {
        item.strip().lower()
        for item in os.getenv(SKILL_SCHEMA_MODELS_ENV, "").split(",")
        if item.strip()
    }
    if normalized_route in allowlist:
        return True
    # Direct OpenAI-style routes are the safest default for Chat Completions
    # ``response_format=json_schema``. Gemini through OpenRouter is left opt-in
    # because direct Gemini uses a different ``responseSchema`` API surface.
    return normalized_route.startswith("openai/")


def _is_structured_output_compatibility_failure(exc: LlmUnavailable) -> bool:
    """Detect provider errors that likely mean strict schema is unsupported."""
    if exc.api_status_code == 400:
        return True
    if exc.api_error_type in STRUCTURED_OUTPUT_COMPATIBILITY_ERRORS:
        return True
    return any(error_type in code for error_type in STRUCTURED_OUTPUT_COMPATIBILITY_ERRORS for code in exc.reason_codes)


def _slugify_identifier(value: str) -> str:
    """Create a bounded ASCII-ish identifier from a learner topic."""
    slug = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return slug or "runtime_topic"


class LlmAdapter:
    """Small fail-safe wrapper around optional OpenAI-compatible model calls.

    The adapter exposes structured generation and tutoring helpers, but every
    caller must tolerate ``None`` or ``LlmUnavailable`` and keep deterministic
    rule behavior available. Model reasoning is neither requested nor persisted.
    """

    def __init__(self, config: LlmConfig | None = None):
        """Create a lazily initialized client wrapper."""
        self.config = config or LlmConfig.from_environment()
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        """Return whether an API key/config is available."""
        return self.config is not None

    def model_route_for_category(self, category: DomainCategory) -> str:
        """Resolve the model route for structured skill generation.

        Category-specific environment variables take precedence. The existing
        ``PELICAN_LLM_MODEL`` setting remains a compatibility override for
        deployments that only configure one model. Defaults come from the local
        OpenRouter model documents and are treated as deployment-time routes, not
        availability or pricing guarantees.
        """
        env_key = MODEL_ROUTE_ENV.get(category)
        if env_key:
            override = os.getenv(env_key, "").strip()
            if override:
                return override
        skill_override = os.getenv("PELICAN_SKILL_MODEL", "").strip()
        if skill_override:
            return skill_override
        global_override = os.getenv("PELICAN_LLM_MODEL", "").strip()
        if global_override:
            return global_override
        return DEFAULT_SKILL_MODEL_ROUTES.get(category, self.config.model if self.config else "unknown")

    def tutor_model_route(self) -> str:
        """Resolve the default model for learner-facing intake and tutoring.

        Returns:
            OpenRouter model slug for fast learner-facing turns. The precedence
            is ``PELICAN_TUTOR_MODEL``, legacy ``PELICAN_LLM_MODEL``, then the
            Gemini Flash Lite default documented in the local OpenRouter notes.

        Compatibility:
            Skill generation intentionally uses ``model_route_for_category()``
            instead. Keeping these routes separate lets structured skill
            generation stay on a stronger model while chat/intake uses a cheaper
            low-latency model.
        """
        override = os.getenv("PELICAN_TUTOR_MODEL", "").strip()
        if override:
            return override
        legacy_override = os.getenv("PELICAN_LLM_MODEL", "").strip()
        if legacy_override:
            return legacy_override
        return DEFAULT_TUTOR_MODEL

    def check_route_health(self, model_route: str) -> LlmHealth:
        """Probe whether a model route can return a minimal JSON response.

        Args:
            model_route: OpenRouter/OpenAI-compatible model slug to check.

        Returns:
            Safe availability metadata. The probe returns only status, reason
            codes, and optional HTTP status/error class. It never returns or logs
            model content, response bodies, prompts, credentials, or API keys.

        Raises:
            This method never raises for provider failures; callers use the
            returned health object to decide whether to attempt generation or
            fail closed into deterministic fallback.
        """
        if not self.available:
            return LlmHealth(False, ("llm_missing_api_key",))
        try:
            self._json(
                "You are a health check endpoint. Return only JSON.",
                'Return exactly {"ok": true}.',
                model=model_route,
            )
            return LlmHealth(True, ("ok",))
        except LlmUnavailable as exc:
            return LlmHealth(
                False,
                exc.reason_codes or ("llm_unavailable",),
                api_status_code=exc.api_status_code,
                api_error_type=exc.api_error_type,
            )

    def verified_diagnostic(self, node_label: str) -> DiagnosticQuestion | None:
        """Generate a diagnostic only if an independent verifier accepts it."""
        if not self.available:
            return None
        teacher = self._json(
            "你是教師。只產生一題繁體中文的單一概念診斷題，並附簡短標準答案。\n"
            "警告：千萬不能把答案洩漏在 prompt 欄位中，prompt 欄位只能有純題目。",
            f"目標知識點：{node_label}\n輸出 JSON：{{\"prompt\": str, \"expected_answer\": str}}",
            model=self.tutor_model_route(),
        )
        prompt = str(teacher.get("prompt", "")).strip()
        expected = str(teacher.get("expected_answer", "")).strip()
        if not prompt or not expected:
            return None
        assistant = self._json(
            "你是獨立解題者。只回答題目的最終答案。",
            f"題目：{prompt}\n輸出 JSON：{{\"answer\": str}}",
            model=self.tutor_model_route(),
        )
        verifier = self._json(
            "你是嚴格驗證器。比較教師標準答案與獨立答案，只在可判定兩者一致時接受。",
            f"教師答案：{expected}\n獨立答案：{assistant.get('answer', '')}\n輸出 JSON：{{\"accepted\": bool}}",
            model=self.tutor_model_route(),
        )
        if verifier.get("accepted") is not True:
            return None
        return DiagnosticQuestion("", prompt, expected, source="llm")

    def classify(self, prompt: str, expected: str, answer: str) -> ResponseCategory | None:
        """Classify a learner response with the optional LLM path."""
        if not self.available:
            return None
        payload = self._json(
            "將學生回答分類成指定五類之一。只輸出 JSON。\n"
            "注意：若學生的回答包含了正確的概念、部分正確，或意思與標準答案相符（例如選擇題多選了合理選項），請寬容地分類為 correct。\n"
            "若學生有明確線索但缺關鍵人物、步驟、因果鏈或術語，請分類為 partial_correct。"
            "若學生明確表達不知道，為 inability_to_respond；表達困惑則為 difficulty_in_understanding。",
            "題目：%s\n標準答案：%s\n學生回答：%s\n"
            "輸出 {\"category\": \"inability_to_respond|difficulty_in_understanding|correct|partial_correct|incorrect|other\"}"
            % (prompt, expected, answer),
            model=self.tutor_model_route(),
        )
        try:
            return ResponseCategory(payload["category"])
        except (KeyError, ValueError):
            return None

    def tutor_response(
        self, strategy: TutoringStrategy, prompt: str, node_label: str
    ) -> str | None:
        """Generate one tutor response for the selected pedagogical strategy."""
        if not self.available:
            return None
        payload = self._json(
            "你是繁體中文家教。一次只處理一個概念、只問一個問題，必須以循循善誘的口吻引導學生思考。\n"
            "警告：絕對不能直接把定義或標準答案複製貼上，請給予提示或引導式反問。",
            f"策略：{strategy.value}\n知識點：{node_label}\n目前題目：{prompt}\n輸出 {{\"response\": str}}",
            model=self.tutor_model_route(),
        )
        response = str(payload.get("response", "")).strip()
        return response or None

    def edf_policy_decision(
        self,
        *,
        current_learner_state: str,
        current_policy: str,
        current_route: str,
        current_strategy: str,
        current_node_id: str,
        current_node_label: str,
        recent_safe_signals: tuple[str, ...],
        recent_dialogue_acts: tuple[str, ...],
        mastery_summary: str,
    ) -> dict[str, Any] | None:
        """Ask the model to propose one bounded EDF policy decision.

        Args:
            current_learner_state: Deterministic EDF learner-state label used as
                the baseline policy state.
            current_policy: Deterministic EDF policy label used for comparison.
            current_route: Baseline route: ``fast``, ``slow``, or ``dialogue``.
            current_strategy: Baseline tutor strategy enum value.
            current_node_id: Safe current knowledge-node id.
            current_node_label: Safe current knowledge-node label.
            recent_safe_signals: Bounded GUM evidence labels only.
            recent_dialogue_acts: Bounded dialogue-control labels only.
            mastery_summary: Compact status counts, not raw learner text.

        Returns:
            Raw JSON object for local validation, or ``None`` when unavailable.

        Privacy:
            This prompt intentionally sends safe state labels and compact counts,
            not learner answers, transcript text, provider reasoning, or hidden
            chain-of-thought. Callers must validate every enum before adoption.
        """
        if not self.available:
            return None
        allowed_strategies = ", ".join(item.value for item in TutoringStrategy)
        payload = self._json(
            "You are the EDF policy decision agent for Agentic PELICAN. "
            "Return only one JSON object. Do not include reasoning text. "
            "Choose the smallest intervention that fits the bounded learner state.",
            "baseline_learner_state: {learner_state}\n"
            "baseline_policy: {policy}\n"
            "baseline_route: {route}\n"
            "baseline_strategy: {strategy}\n"
            "current_node_id: {node_id}\n"
            "current_node_label: {node_label}\n"
            "recent_safe_signals: {signals}\n"
            "recent_dialogue_acts: {dialogue_acts}\n"
            "mastery_summary: {mastery}\n"
            "allowed_routes: fast, slow, dialogue\n"
            "allowed_strategies: {allowed_strategies}\n"
            "Rules:\n"
            "- Use dialogue route for clarification/control turns that should not update mastery.\n"
            "- Use slow route only when repeated confusion, repeated incorrectness, or high support need is visible.\n"
            "- Keep should_advance false unless sustained mastery is visible.\n"
            "- Keep should_recheck true unless the learner has already demonstrated mastery.\n"
            "Return JSON with exactly these keys: "
            '{{"learner_state": str, "route": str, "selected_strategy": str, '
            '"intervention_strength": number, "should_advance": bool, '
            '"should_recheck": bool, "reason_code": str, "dialogue_act": str}}.'.format(
                learner_state=current_learner_state[:80],
                policy=current_policy[:80],
                route=current_route[:40],
                strategy=current_strategy[:80],
                node_id=current_node_id[:80] or "none",
                node_label=current_node_label[:160] or "none",
                signals=", ".join(recent_safe_signals[-8:]) or "none",
                dialogue_acts=", ".join(recent_dialogue_acts[-8:]) or "none",
                mastery=mastery_summary[:200],
                allowed_strategies=allowed_strategies,
            ),
            model=self.tutor_model_route(),
        )
        if not isinstance(payload, dict):
            return None
        payload["reason_code"] = _slug_reason(str(payload.get("reason_code", "llm_edf_policy")))
        return payload

    def tutor_proposal(
        self,
        *,
        strategy: TutoringStrategy,
        node_id: str,
        node_label: str,
        base_prompt: str,
        learner_state: str,
        edf_policy: str,
        recent_signals: tuple[str, ...],
        evidence_signal: str,
        learner_answer: str = "",
        domain_category: str = "",
        concept_description: str = "",
        expected_answer: str = "",
        remediation_template: str = "",
        teaching_methodology: dict[str, str] | None = None,
        dialogue_act: str = "",
        dialogue_target: str = "",
    ) -> BoundedTutorProposal | None:
        """Generate a bounded tutor proposal constrained by EDF/GUM state.

        Args:
            strategy: Tutoring strategy selected by the local EDF policy.
            node_id: Current knowledge node identifier.
            node_label: Human-readable current concept label.
            base_prompt: Current diagnostic/task prompt. This is sent to the
                model for context but is not logged or persisted by this method.
            learner_state: Safe EDF learner-state label.
            edf_policy: Safe EDF policy label.
            recent_signals: Safe bounded GUM signal labels.
            evidence_signal: Current safe response signal, such as ``unknown``
                or ``too_detailed``.
            learner_answer: Latest learner answer. It is sent only to the tutor
                model so the response can acknowledge what the learner said; it
                must not be logged by callers.
            domain_category: Safe domain label used to select teaching style.
            concept_description: Skill-authored learner-facing concept context.
            expected_answer: Current answer/rubric. The model may use it to
                understand the target, but must not reveal it verbatim.
            remediation_template: Skill-authored remediation guidance for the
                current concept.
            teaching_methodology: Skill-authored pedagogy notes for this domain.
            dialogue_act: Optional bounded conversational role before diagnosis.
            dialogue_target: Optional short term from a clarification turn.

        Returns:
            A bounded proposal candidate, or ``None`` when the optional model is
            unavailable or returns an unusable payload.

        Privacy:
            Only the bounded response, move label, and safe summary are returned
            to the engine for validation. Raw prompts, provider payloads, and
            model reasoning are never logged or persisted here.
        """
        if not self.available:
            return None
        methodology_lines = "\n".join(
            f"- {key}: {value}"
            for key, value in (teaching_methodology or {}).items()
            if str(key).strip() and str(value).strip()
        ) or "none"
        humanities_contract = (
            "domain_style_contract for humanities:\n"
            "- If current_signal is unknown, inability_to_respond, incorrect, partial_correct, or difficulty_in_understanding, do not keep probing first.\n"
            "- Generate a topic-specific explanatory mini-lesson from the provided knowledge_node, concept_description, current_prompt, expected_answer, remediation_template, and teaching_methodology.\n"
            "- The mini-lesson should teach the missing knowledge in Traditional Chinese with narrative context, key actors/concepts, cause-effect links, and where this node sits in the knowledge map.\n"
            "- If current_signal is partial_correct, start by acknowledging the specific useful idea in latest_learner_answer before adding missing details. Do not ignore the learner's sentence.\n"
            "- End with a warm, low-pressure humanities micro-check rather than asking the learner to paraphrase the whole mini-lesson.\n"
            "- Prefer a scaffolded causal/context question. Example: 先不用完整重述。你可以先說說看：在剛剛這段裡，你覺得最關鍵的轉折點或原因是哪一個？如果一開始不好說，也可以只選一個你覺得重要的原因。\n"
            "- If the learner's next explanation is correct, the engine will unlock the next knowledge-map node; if not, the tutor should explain again based on that answer.\n"
            "- Do not output a generic template with headings only; fill it with the actual subject matter from the provided context.\n"
            if domain_category == DomainCategory.HUMANITIES.value
            else ""
        )
        payload = self._json(
            "你是 Agentic PELICAN 的繁體中文家教代理。請只輸出 JSON，不要輸出推理。\n"
            "你必須根據 EDF/GUM 狀態提出一個 bounded tutor proposal：一次只處理一個概念、"
            "只問一個問題、避免固定模板。你可以根據領域調整教學法；若學生不知道或答錯，"
            "應先教會該知識點，再用一個低負荷檢核確認理解。不要逐字洩漏 expected_answer。",
            "node_id: {node_id}\n"
            "knowledge_node: {node_label}\n"
            "domain_category: {domain_category}\n"
            "strategy: {strategy}\n"
            "learner_state: {learner_state}\n"
            "edf_policy: {edf_policy}\n"
            "current_signal: {evidence_signal}\n"
            "dialogue_act: {dialogue_act}\n"
            "dialogue_target: {dialogue_target}\n"
            "recent_safe_signals: {recent_signals}\n"
            "latest_learner_answer: {learner_answer}\n"
            "current_prompt: {base_prompt}\n"
            "concept_description: {concept_description}\n"
            "expected_answer: {expected_answer}\n"
            "remediation_template: {remediation_template}\n"
            "teaching_methodology:\n{teaching_methodology}\n"
            "{humanities_contract}"
            "輸出 JSON：{{\"response\": str, \"pedagogical_move\": str, \"summary\": str}}".format(
                node_id=node_id,
                node_label=node_label,
                domain_category=domain_category or "unknown",
                strategy=strategy.value,
                learner_state=learner_state,
                edf_policy=edf_policy,
                evidence_signal=evidence_signal,
                dialogue_act=dialogue_act[:80] or "none",
                dialogue_target=dialogue_target[:80] or "none",
                recent_signals=", ".join(recent_signals[-5:]) or "none",
                learner_answer=learner_answer[:800] or "none",
                base_prompt=base_prompt,
                concept_description=concept_description[:800] or "none",
                expected_answer=expected_answer[:800] or "none",
                remediation_template=remediation_template[:800] or "none",
                teaching_methodology=methodology_lines[:1200],
                humanities_contract=humanities_contract,
            ),
            model=self.tutor_model_route(),
        )
        response = str(payload.get("response", "")).strip()
        move = str(payload.get("pedagogical_move", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        if not response:
            return None
        return BoundedTutorProposal(
            response=response,
            pedagogical_move=move or strategy.value,
            summary=summary or f"{strategy.value} for {node_label}",
            node_id=node_id,
            strategy=strategy.value,
            evidence_signal=evidence_signal,
            source="llm",
        )

    def intake_question(
        self,
        *,
        topic: str,
        domain_category: DomainCategory,
        stage: str,
        model_route: str | None = None,
    ) -> str | None:
        """Generate one domain-aware onboarding question without persisting reasoning.

        Args:
            topic: Bounded learner topic from the onboarding state.
            domain_category: Resolved teaching domain used to avoid STEM-shaped
                questions for humanities, business, or language topics.
            stage: Intake stage, currently ``goal`` or ``level``.
            model_route: Optional explicit route for tests or deployments.

        Returns:
            A single bounded learner-facing question, or ``None`` when the model
            is unavailable or returns an empty payload.

        Privacy:
            The method returns only the final question string. It does not expose
            or persist model reasoning, and callers log only source/route codes.
        """
        if not self.available:
            return None
        route = model_route or self.tutor_model_route()
        payload = self._json(
            "你是繁體中文學習訪談主持人。請根據領域產生一題前置校準問題，只問一題。\n"
            "不要輸出推理、不要教學、不要診斷細節。問題必須適合該領域，不可把所有領域都問成理科或程式學習。",
            f"topic: {topic}\ndomain_category: {domain_category.value}\nstage: {stage}\n"
            "stage=goal 時請詢問學習目的或角度；stage=level 時請詢問背景、經驗或熟悉度。\n"
            "輸出 JSON：{\"question\": str}",
            model=route,
        )
        question = str(payload.get("question", "")).strip()
        return question[:500] if question else None

    def classify_intake_semantics(
        self,
        *,
        current_topic: str,
        answer: str,
        stage: str,
        domain_category: DomainCategory,
        model_route: str | None = None,
    ) -> IntakeSemanticSignal:
        """Classify one onboarding answer into a bounded semantic control signal.

        Args:
            current_topic: Topic currently stored in the intake profile.
            answer: Learner's latest onboarding reply.
            stage: Current onboarding stage, such as ``goal`` or ``level``.
            domain_category: Resolved current domain category for context.
            model_route: Optional route override for tests/deployments.

        Returns:
            A bounded semantic signal. Supported intents are
            ``topic_revision``, ``goal_revision``, ``level_answer``,
            ``normal_answer``, and ``ambiguous``.

        Raises:
            LlmUnavailable: If the model route cannot return valid JSON.

        Privacy:
            The result contains only classification metadata and an optional
            bounded replacement topic. Callers log the intent, confidence, and
            reason code, not the raw answer or model output.
        """
        if not self.available:
            raise LlmUnavailable(
                "OPENROUTER_API_KEY is not configured",
                reason_codes=("llm_missing_api_key",),
            )
        route = model_route or self.tutor_model_route()
        payload = self._json(
            "你是學習系統的語意分類器。只輸出 JSON，不要教學、不要改寫流程、不要輸出推理。\n"
            "你的任務是判斷使用者在 onboarding 階段的回覆是否要改變系統狀態。\n"
            "intent 只能是 topic_revision, goal_revision, level_answer, normal_answer, ambiguous。\n"
            "若使用者表示先前主題說錯、想改成另一個主題、不是目前主題而是新主題，請用 topic_revision 並抽取 new_topic。\n"
            "若不確定，請用 ambiguous 並給低 confidence。",
            f"current_topic: {current_topic}\nstage: {stage}\ndomain_category: {domain_category.value}\n"
            f"learner_answer: {answer}\n"
            "輸出 JSON：{\"intent\": str, \"new_topic\": str, \"confidence\": number, \"reason_code\": str}",
            model=route,
        )
        intent = _bounded_choice(
            str(payload.get("intent", "normal_answer")),
            {"topic_revision", "goal_revision", "level_answer", "normal_answer", "ambiguous"},
            "normal_answer",
        )
        confidence = _bounded_confidence(payload.get("confidence", 0.0))
        reason_code = _slug_reason(str(payload.get("reason_code", intent)))
        new_topic = str(payload.get("new_topic", "")).strip()[:100]
        return IntakeSemanticSignal(
            intent=intent,
            confidence=confidence,
            reason_code=reason_code,
            new_topic=new_topic,
        )

    def generate_learning_plan(self, topic: str) -> LearningPlanSnapshot | None:
        """Legacy topic-to-plan generation kept as a compatibility fallback."""
        if not self.available:
            return None
        import uuid
        payload = self._json(
            "你是一個課程規劃師。請根據主題產生一份包含知識點、診斷題與任務步驟的 JSON 計畫。\n"
            "警告：所有物件的 prompt 欄位只能包含純題目，千萬不能把答案寫進 prompt 裡，答案只能寫在 expected_answer 或 expected 欄位。",
            f"主題：{topic}\n"
            "輸出 JSON 格式如下：\n"
            "{\n"
            "  \"goal_summary\": \"...\",\n"
            "  \"nodes\": [{\"node_id\": \"n1\", \"label\": \"...\", \"prerequisites\": [], \"priority\": 2}],\n"
            "  \"diagnostics\": [{\"node_id\": \"n1\", \"prompt\": \"...\", \"expected_answer\": \"...\"}],\n"
            "  \"task_steps\": [{\"step_id\": \"s1\", \"node_id\": \"n1\", \"label\": \"...\", \"prompt\": \"...\", \"expected\": \"...\"}]\n"
            "}"
        )

        nodes = tuple(
            KnowledgeNode(
                node_id=n["node_id"],
                label=n["label"],
                prerequisites=tuple(n.get("prerequisites", [])),
                priority=n.get("priority", 0)
            )
            for n in payload.get("nodes", [])
        )
        diagnostics = tuple(
            DiagnosticQuestion(
                node_id=d["node_id"],
                prompt=d["prompt"],
                expected_answer=d["expected_answer"],
                source="llm"
            )
            for d in payload.get("diagnostics", [])
        )
        task_steps = tuple(
            {
                "step_id": s["step_id"],
                "node_id": s["node_id"],
                "label": s.get("label", ""),
                "prompt": s["prompt"],
                "expected": s["expected"]
            }
            for s in payload.get("task_steps", [])
        )

        return LearningPlanSnapshot(
            plan_id=str(uuid.uuid4()),
            topic=topic,
            goal_summary=payload.get("goal_summary", f"學習 {topic}"),
            nodes=nodes,
            diagnostics=diagnostics,
            task_steps=task_steps
        )

    def generate_domain_skill(
        self,
        topic: str,
        category: DomainCategory,
        *,
        model_route: str | None = None,
        repair_issues: tuple[str, ...] = (),
        goal_context: str = "",
    ) -> DomainSkill | None:
        """Generate a structured domain skill without persisting model reasoning.

        Args:
            topic: Topic to turn into a DomainSkill schema.
            category: Resolved domain category; this is enforced back onto the
                payload before parsing so model output cannot silently reroute.
            model_route: Optional skill-generation model route.
            repair_issues: Safe validator reason codes from a previous attempt.
            goal_context: Optional learner goal summary used to scope the skill.

        Returns:
            Parsed ``DomainSkill`` or ``None`` for unavailable model access.

        Raises:
            DomainSkillError: If the returned JSON cannot be represented by the
                strict DomainSkill dataclasses.
            LlmUnavailable: If the OpenAI-compatible request fails.
        """
        if not self.available:
            return None
        payload = self.generate_domain_skill_payload(
            topic,
            category,
            model_route=model_route,
            repair_issues=repair_issues,
            goal_context=goal_context,
        )
        payload["domain_category"] = category.value
        payload["lifecycle"] = payload.get("lifecycle") or SkillLifecycle.RUNTIME_GENERATED.value
        return DomainSkill.from_dict(payload)

    def generate_domain_skill_payload(
        self,
        topic: str,
        category: DomainCategory,
        *,
        model_route: str | None = None,
        repair_issues: tuple[str, ...] = (),
        goal_context: str = "",
    ) -> dict[str, Any]:
        """Generate raw DomainSkill JSON for validation or bounded repair.

        Args:
            topic: Topic to send in the schema-generation prompt.
            category: Resolved domain category.
            model_route: Optional skill model override. ``None`` uses the
                category-aware skill-generation route.
            repair_issues: Validator reason codes from the previous attempt.
                When present, the prompt asks for schema repair rather than a
                brand-new lesson or Markdown response.
            goal_context: Optional bounded learner goal summary. It should steer
                concept-map scope but must not be logged by callers.

        Returns:
            JSON object emitted by the model. The caller owns parsing, validation,
            artifact persistence, and safe fallback selection.

        Raises:
            LlmUnavailable: If credentials are absent or the transport/JSON parse
                fails.

        Privacy:
            The payload is returned for validation only. Callers must not log raw
            model output; failed artifacts store only a short hash and reason
            codes.
        """
        if not self.available:
            raise LlmUnavailable("OPENROUTER_API_KEY is not configured")
        route = model_route or self.model_route_for_category(category)
        repair_instruction = ""
        if repair_issues:
            # Repair prompts carry validator reason codes only. This keeps retry
            # context useful without feeding raw invalid output back through logs.
            repair_instruction = (
                "前一次輸出未通過驗證。請只修正 schema，不要改成課文或 Markdown。\n"
                f"validation_reason_codes: {', '.join(repair_issues)}\n"
            )
        contract = _domain_skill_json_contract(topic, category)
        system_prompt = (
            "你是領域教學設計師。只輸出 JSON，不要輸出推理過程、Markdown 或學生可見課程內容。\n"
            "你的任務是產生一份可驗證的 DomainSkill schema，供教學引擎稍後編譯知識樹。\n"
            "必須包含 intake calibration、prerequisite map、canonical_path、single-concept diagnostics、"
            "teaching_moves、unknown/too_detailed/too_easy/project_goal/assessment_goal remediation、"
            "teaching_methodology、remediation_templates，以及 assessment_policy。\n"
            "硬性規則：canonical_path 只能引用 prerequisites 裡存在的 concept_id；每個 concept 必須有一個 diagnostic_rule；"
            "diagnostic prompt 絕對不能包含 expected_answer；prerequisites 必須無循環；"
            "remediation_templates 的 key 應對應 concept_id。法律知識只能作教育用途，不可提供法律諮詢。\n"
            "你必須輸出單一 JSON object，且 shape 必須符合使用者訊息中的範例。所有 required arrays 都必須是 non-empty。"
        )
        goal_line = f"learner_goal: {goal_context[:300]}\n" if goal_context.strip() else ""
        humanities_quality = (
            "humanities quality rules: learner-facing title, concept labels, descriptions, teaching_methodology, "
            "teaching_moves, and remediation_templates must be Traditional Chinese; build at least 6 focused concepts; "
            "the concept map must target learner_goal rather than a broad survey.\n"
            if category is DomainCategory.HUMANITIES
            else ""
        )
        user_prompt = (
            repair_instruction + f"topic: {topic}\ncategory: {category.value}\n{goal_line}{humanities_quality}"
            "輸出 JSON 欄位：skill_id, version, title, domain_category, lifecycle, supported_topics, intent_types, "
            "prerequisites, calibration_questions, canonical_path, diagnostic_rules, teaching_moves, remediation_paths, "
            "assessment_policy, teaching_methodology, remediation_templates, safety_notes。lifecycle 請用 runtime_generated。\n"
            "enum 限制：domain_category 必須等於上述 category；lifecycle 必須是 runtime_generated；"
            "intent_types 只能使用 conceptual, procedural, implementation, project, assessment, explanatory, "
            "business_decision, language_practice。\n"
            "每個 prerequisite object 必須有 concept_id, label, prerequisites, description。\n"
            "每個 calibration_questions object 必須有 question_id, prompt, intent_targets, level_targets。\n"
            "每個 diagnostic_rules object 必須有 rule_id, concept_id, prompt, expected_answer, tests_single_concept。\n"
            "每個 teaching_moves object 必須有 move_id, strategy, description。\n"
            "每個 remediation_paths object 必須有 signal, action, target，且 signal 必須覆蓋 "
            "unknown, too_detailed, too_easy, project_goal, assessment_goal。\n"
            "assessment_policy 必須是 object 並包含 mode, education_only, notes。\n"
            "最小有效 JSON 範例，請依 topic 改寫內容但保持相同 schema：\n"
            f"{contract}"
        )
        response_format = _skill_schema_response_format_for_route(route, category)
        schema_mode = _skill_schema_mode()
        schema_format = "json_schema" if response_format else "json_object"
        log_event(
            "pelican_skill_schema_mode_selected",
            level=logging.DEBUG,
            domain_category=category.value,
            route=route,
            model_route=route,
            schema_mode=schema_mode,
            schema_format=schema_format,
            schema_strict=response_format is not None,
            schema_fallback=False,
        )
        if response_format is None:
            return self._json(system_prompt, user_prompt, model=route)
        try:
            return self._json(system_prompt, user_prompt, model=route, response_format=response_format)
        except LlmUnavailable as exc:
            if _skill_schema_mode() != "auto" or not _is_structured_output_compatibility_failure(exc):
                raise
            # Some OpenRouter/provider routes accept JSON mode but reject strict
            # schema parameters. In auto mode the generation still proceeds via
            # JSON object mode and is guarded by local schema validation/repair.
            log_event(
                "pelican_skill_schema_provider_fallback",
                level=logging.DEBUG,
                domain_category=category.value,
                route=route,
                model_route=route,
                schema_mode=schema_mode,
                schema_format="json_object",
                schema_strict=False,
                schema_fallback=True,
                reason_code="structured_output_unsupported",
                api_status_code=exc.api_status_code,
                api_error_type=exc.api_error_type,
            )
            return self._json(system_prompt, user_prompt, model=route)

    def _json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call the configured model and require a JSON object response.

        Args:
            system: System instruction sent to the provider.
            user: User/developer payload sent to the provider.
            model: Optional model route override.
            response_format: Optional OpenAI/OpenRouter response format. When
                omitted, JSON object mode is used for compatibility.

        Returns:
            Parsed JSON object.

        Raises:
            LlmUnavailable: If credentials are absent, the provider request
                fails, or the returned content is not a JSON object.
        """
        if not self.config:
            raise LlmUnavailable(
                "OPENROUTER_API_KEY is not configured",
                reason_codes=("llm_missing_api_key",),
            )
        try:
            from openai import OpenAI

            if self._client is None:
                self._client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url, timeout=15.0)
            response = self._client.chat.completions.create(
                model=model or self.config.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                response_format=response_format or {"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("response is not a JSON object")
            return parsed
        except Exception as exc:
            status_code = _safe_status_code(exc)
            error_type = _safe_error_type(exc)
            raise LlmUnavailable(
                f"LLM request failed: {type(exc).__name__}",
                reason_codes=_safe_llm_reason_codes(exc, status_code, error_type),
                api_status_code=status_code,
                api_error_type=error_type,
            ) from exc


def _safe_status_code(exc: Exception) -> int | None:
    """Extract an HTTP status code from provider exceptions without response text."""
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _safe_error_type(exc: Exception) -> str:
    """Return a bounded provider error type for safe logs."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        nested_error = body.get("error")
        if isinstance(nested_error, dict):
            provider_type = nested_error.get("type") or nested_error.get("code")
            if provider_type:
                return _slug_reason(str(provider_type))
        provider_type = body.get("type") or body.get("code")
        if provider_type:
            return _slug_reason(str(provider_type))
    return _slug_reason(type(exc).__name__)


def _safe_llm_reason_codes(exc: Exception, status_code: int | None, error_type: str) -> tuple[str, ...]:
    """Build stable LLM failure reason codes from safe exception metadata."""
    codes = ["llm_request_failed", f"llm_{_slug_reason(type(exc).__name__)}"]
    if status_code is not None:
        codes.append(f"llm_api_status_{status_code}")
    if error_type and error_type != _slug_reason(type(exc).__name__):
        codes.append(f"llm_api_error_{error_type}")
    return tuple(dict.fromkeys(codes))


def _bounded_choice(value: str, allowed: set[str], default: str) -> str:
    """Return a model-selected enum value only when it is explicitly allowed."""
    return value if value in allowed else default


def _bounded_confidence(value: Any) -> float:
    """Clamp a model confidence score to the ``0.0`` to ``1.0`` range."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _slug_reason(value: str) -> str:
    """Normalize provider exception labels into safe reason-code fragments."""
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")[:60] or "unknown"
