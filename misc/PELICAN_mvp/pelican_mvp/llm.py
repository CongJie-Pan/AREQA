"""Optional OpenAI-compatible LLM support with safe rule-mode fallback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .models import DiagnosticQuestion, ResponseCategory, TutoringStrategy


class LlmUnavailable(RuntimeError):
    """Raised when optional LLM capabilities are unavailable or invalid."""


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    model: str
    base_url: str

    @classmethod
    def from_environment(cls) -> "LlmConfig | None":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            model=os.getenv("PELICAN_LLM_MODEL", "qwen/qwen-2.5-7b-instruct"),
            base_url=os.getenv("PELICAN_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        )


class LlmAdapter:
    def __init__(self, config: LlmConfig | None = None):
        self.config = config or LlmConfig.from_environment()
        self._client: Any | None = None

    @property
    def available(self) -> bool:
        return self.config is not None

    def verified_diagnostic(self, node_label: str) -> DiagnosticQuestion | None:
        if not self.available:
            return None
        teacher = self._json(
            "你是教師。只產生一題繁體中文的單一概念診斷題，並附簡短標準答案。",
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
        if not self.available:
            return None
        payload = self._json(
            "將學生回答分類成指定五類之一。只輸出 JSON。",
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
        if not self.available:
            return None
        payload = self._json(
            "你是繁體中文家教。一次只處理一個概念、只問一個問題，不能直接給原題最終答案。",
            f"策略：{strategy.value}\n知識點：{node_label}\n目前題目：{prompt}\n輸出 {{\"response\": str}}",
        )
        response = str(payload.get("response", "")).strip()
        return response or None

    def _json(self, system: str, user: str) -> dict[str, Any]:
        if not self.config:
            raise LlmUnavailable("OPENROUTER_API_KEY is not configured")
        try:
            from openai import OpenAI

            if self._client is None:
                self._client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url, timeout=15.0)
            response = self._client.chat.completions.create(
                model=self.config.model,
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

