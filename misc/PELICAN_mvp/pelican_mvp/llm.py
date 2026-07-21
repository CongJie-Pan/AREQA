"""Optional OpenAI-compatible LLM support with safe rule-mode fallback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .domain_skill import DomainCategory, DomainSkill, SkillLifecycle
from .models import DiagnosticQuestion, KnowledgeNode, LearningPlanSnapshot, ResponseCategory, TutoringStrategy


class LlmUnavailable(RuntimeError):
    """Raised when optional LLM capabilities are unavailable or invalid."""


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

MODEL_ROUTE_ENV = {
    DomainCategory.STEM: "PELICAN_STEM_MODEL",
    DomainCategory.HUMANITIES: "PELICAN_HUMANITIES_MODEL",
    DomainCategory.BUSINESS: "PELICAN_BUSINESS_MODEL",
    DomainCategory.LANGUAGE: "PELICAN_LANGUAGE_MODEL",
}


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
        global_override = os.getenv("PELICAN_LLM_MODEL", "").strip()
        if global_override:
            return global_override
        return DEFAULT_SKILL_MODEL_ROUTES.get(category, self.config.model if self.config else "unknown")

    def verified_diagnostic(self, node_label: str) -> DiagnosticQuestion | None:
        """Generate a diagnostic only if an independent verifier accepts it."""
        if not self.available:
            return None
        teacher = self._json(
            "你是教師。只產生一題繁體中文的單一概念診斷題，並附簡短標準答案。\n"
            "警告：千萬不能把答案洩漏在 prompt 欄位中，prompt 欄位只能有純題目。",
            f"目標知識點：{node_label}\n輸出 JSON：{{\"prompt\": str, \"expected_answer\": str}}",
        )
        prompt = str(teacher.get("prompt", "")).strip()
        expected = str(teacher.get("expected_answer", "")).strip()
        if not prompt or not expected:
            return None
        assistant = self._json(
            "你是獨立解題者。只回答題目的最終答案。",
            f"題目：{prompt}\n輸出 JSON：{{\"answer\": str}}",
        )
        verifier = self._json(
            "你是嚴格驗證器。比較教師標準答案與獨立答案，只在可判定兩者一致時接受。",
            f"教師答案：{expected}\n獨立答案：{assistant.get('answer', '')}\n輸出 JSON：{{\"accepted\": bool}}",
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
            "若學生明確表達不知道，為 inability_to_respond；表達困惑則為 difficulty_in_understanding。",
            "題目：%s\n標準答案：%s\n學生回答：%s\n"
            "輸出 {\"category\": \"inability_to_respond|difficulty_in_understanding|correct|incorrect|other\"}"
            % (prompt, expected, answer),
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
        )
        response = str(payload.get("response", "")).strip()
        return response or None

    def intake_question(
        self,
        *,
        topic: str,
        domain_category: DomainCategory,
        stage: str,
        model_route: str | None = None,
    ) -> str | None:
        """Generate one domain-aware onboarding question without persisting reasoning."""
        if not self.available:
            return None
        route = model_route or self.model_route_for_category(domain_category)
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
    ) -> DomainSkill | None:
        """Generate a structured domain skill without persisting model reasoning."""
        if not self.available:
            return None
        route = model_route or self.model_route_for_category(category)
        payload = self._json(
            "你是領域教學設計師。只輸出 JSON，不要輸出推理過程、Markdown 或學生可見課程內容。\n"
            "你的任務是產生一份可驗證的 DomainSkill schema，供教學引擎稍後編譯知識樹。\n"
            "必須包含 intake calibration、prerequisite map、canonical_path、single-concept diagnostics、"
            "teaching_moves、unknown/too_detailed/too_easy/project_goal/assessment_goal remediation、"
            "teaching_methodology、remediation_templates，以及 assessment_policy。\n"
            "診斷題 prompt 絕對不能包含 expected_answer。法律知識只能作教育用途，不可提供法律諮詢。",
            f"topic: {topic}\ncategory: {category.value}\n"
            "輸出 JSON 欄位：skill_id, version, title, domain_category, lifecycle, supported_topics, intent_types, "
            "prerequisites, calibration_questions, canonical_path, diagnostic_rules, teaching_moves, remediation_paths, "
            "assessment_policy, teaching_methodology, remediation_templates, safety_notes。lifecycle 請用 runtime_generated。",
            model=route,
        )
        payload["domain_category"] = category.value
        payload["lifecycle"] = payload.get("lifecycle") or SkillLifecycle.RUNTIME_GENERATED.value
        return DomainSkill.from_dict(payload)

    def _json(self, system: str, user: str, *, model: str | None = None) -> dict[str, Any]:
        """Call the configured model and require a JSON object response."""
        if not self.config:
            raise LlmUnavailable("OPENROUTER_API_KEY is not configured")
        try:
            from openai import OpenAI

            if self._client is None:
                self._client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url, timeout=15.0)
            response = self._client.chat.completions.create(
                model=model or self.config.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("response is not a JSON object")
            return parsed
        except Exception as exc:
            raise LlmUnavailable(f"LLM request failed: {type(exc).__name__}") from exc
