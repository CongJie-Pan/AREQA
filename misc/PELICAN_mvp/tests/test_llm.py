import logging

import pytest
from pelican_mvp.domain_skill import DomainCategory
from pelican_mvp.llm import LlmAdapter, LlmConfig, LlmUnavailable
from pelican_mvp.models import TutoringStrategy
from test_domain_skill import valid_skill_payload

def test_llm_adapter_no_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    adapter = LlmAdapter(config=None)
    assert adapter.available is False
    assert adapter.verified_diagnostic("test") is None
    assert adapter.classify("p", "e", "a") is None
    assert adapter.tutor_response(TutoringStrategy.EXPLANATION, "p", "l") is None
    
    with pytest.raises(LlmUnavailable):
        adapter._json("system", "user")

def test_llm_adapter_import_error_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    original_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("No module named openai")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    
    config = LlmConfig(api_key="test", model="test", base_url="test")
    adapter = LlmAdapter(config=config)
    assert adapter.available is True
    
    with pytest.raises(LlmUnavailable, match="LLM request failed: ImportError"):
        adapter._json("system", "user")


def test_llm_adapter_preserves_safe_api_status_metadata() -> None:
    class MockApiStatusError(Exception):
        status_code = 404
        body = {"error": {"type": "not_found"}}

    class MockCompletions:
        def create(self, *args, **kwargs):
            raise MockApiStatusError()

    class MockChat:
        completions = MockCompletions()

    class MockClient:
        chat = MockChat()

    config = LlmConfig(api_key="test", model="test", base_url="test")
    adapter = LlmAdapter(config=config)
    adapter._client = MockClient()

    with pytest.raises(LlmUnavailable) as exc_info:
        adapter._json("system", "user")

    assert exc_info.value.api_status_code == 404
    assert exc_info.value.api_error_type == "not_found"
    assert exc_info.value.reason_codes == (
        "llm_request_failed",
        "llm_mockapistatuserror",
        "llm_api_status_404",
        "llm_api_error_not_found",
    )


def test_llm_route_health_returns_safe_failure_metadata() -> None:
    class MockApiStatusError(Exception):
        status_code = 402
        body = {"error": {"type": "insufficient_credits"}}

    class MockCompletions:
        def create(self, *args, **kwargs):
            raise MockApiStatusError()

    class MockChat:
        completions = MockCompletions()

    class MockClient:
        chat = MockChat()

    config = LlmConfig(api_key="test", model="test", base_url="test")
    adapter = LlmAdapter(config=config)
    adapter._client = MockClient()

    health = adapter.check_route_health("model")

    assert health.available is False
    assert health.api_status_code == 402
    assert health.api_error_type == "insufficient_credits"
    assert "llm_api_status_402" in health.reason_codes

def test_llm_adapter_valid_json_response() -> None:
    class MockMessage:
        content = '{"response": "this is a mock response"}'
    class MockChoice:
        message = MockMessage()
    class MockCompletion:
        choices = [MockChoice()]
    class MockChat:
        completions = type('Obj', (object,), {'create': lambda *args, **kwargs: MockCompletion()})()
    class MockClient:
        chat = MockChat()
    
    config = LlmConfig(api_key="test", model="test", base_url="test")
    adapter = LlmAdapter(config=config)
    adapter._client = MockClient()
    
    res = adapter.tutor_response(TutoringStrategy.EXPLANATION, "prompt", "label")
    assert res == "this is a mock response"


def test_llm_tutor_proposal_returns_bounded_safe_candidate() -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.user_prompt = ""

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.user_prompt = user
            return {
                "response": "我們先把資料想成機器看得懂的數字。你覺得圖片可以怎麼變成數字？",
                "pedagogical_move": "scaffold",
                "summary": "Use current unknown signal to scaffold the active node.",
            }

    adapter = RecordingAdapter()

    proposal = adapter.tutor_proposal(
        strategy=TutoringStrategy.DECOMPOSITION,
        node_id="vectors_tensors",
        node_label="資料表示與向量直覺",
        base_prompt="圖片如何交給模型？",
        learner_state="needs_support",
        edf_policy="simplify_or_decompose",
        recent_signals=("unknown",),
        evidence_signal="unknown",
    )

    assert proposal is not None
    assert proposal.node_id == "vectors_tensors"
    assert proposal.strategy == "decomposition"
    assert proposal.pedagogical_move == "scaffold"
    assert proposal.source == "llm"


def test_llm_edf_policy_decision_prompt_uses_bounded_state() -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.user_prompt = ""

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.user_prompt = user
            return {
                "learner_state": "CLARIFYING",
                "route": "dialogue",
                "selected_strategy": "give_choices",
                "intervention_strength": 0.5,
                "should_advance": False,
                "should_recheck": True,
                "reason_code": "needs choices",
                "dialogue_act": "micro_check_confusion",
            }

    adapter = RecordingAdapter()

    payload = adapter.edf_policy_decision(
        current_learner_state="CLARIFYING",
        current_policy="give_choices",
        current_route="dialogue",
        current_strategy="give_choices",
        current_node_id="node_1",
        current_node_label="Node One",
        recent_safe_signals=("unknown",),
        recent_dialogue_acts=("micro_check_confusion",),
        mastery_summary="mastered=0, not_mastered=1",
    )

    assert payload["reason_code"] == "needs_choices"
    assert "allowed_routes: fast, slow, dialogue" in adapter.user_prompt
    assert "allowed_strategies:" in adapter.user_prompt
    assert "recent_safe_signals: unknown" in adapter.user_prompt
    assert "recent_dialogue_acts: micro_check_confusion" in adapter.user_prompt


def test_llm_tutor_proposal_prompt_includes_humanities_explain_check_contract() -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.user_prompt = ""

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.user_prompt = user
            return {
                "response": "先建立事件脈絡，再請你先選一個關鍵轉折點。",
                "pedagogical_move": "explain_then_restate",
                "summary": "Generate humanities explanation before mastery check.",
            }

    adapter = RecordingAdapter()

    adapter.tutor_proposal(
        strategy=TutoringStrategy.EXPLANATION,
        node_id="context_foundation",
        node_label="背景脈絡",
        base_prompt="請說明這個事件的背景。",
        learner_state="EXPLORING",
        edf_policy="probe_understanding",
        recent_signals=("unknown",),
        evidence_signal="partial_correct",
        learner_answer="簡單來說，這是改革與西化，為了趕上西方現代化。",
        domain_category=DomainCategory.HUMANITIES.value,
        concept_description="理解事件發生前的時代條件與主要人物。",
        expected_answer="學生應能說出背景、人物與因果關係。",
        remediation_template="先補事件背景，再確認因果鏈。",
        teaching_methodology={"sequencing": "先背景，再事件，最後因果。"},
        dialogue_act="micro_check_confusion",
        dialogue_target="turning_point",
    )

    assert "domain_style_contract for humanities" in adapter.user_prompt
    assert "Generate a topic-specific explanatory mini-lesson" in adapter.user_prompt
    assert "latest_learner_answer: 簡單來說，這是改革與西化，為了趕上西方現代化。" in adapter.user_prompt
    assert "dialogue_act: micro_check_confusion" in adapter.user_prompt
    assert "dialogue_target: turning_point" in adapter.user_prompt
    assert "start by acknowledging the specific useful idea" in adapter.user_prompt
    assert "先不用完整重述" in adapter.user_prompt
    assert "最關鍵的轉折點或原因" in adapter.user_prompt
    assert "concept_description: 理解事件發生前的時代條件與主要人物。" in adapter.user_prompt
    assert "remediation_template: 先補事件背景，再確認因果鏈。" in adapter.user_prompt


def test_llm_category_model_route_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PELICAN_LLM_MODEL", raising=False)
    monkeypatch.delenv("PELICAN_SKILL_MODEL", raising=False)
    monkeypatch.delenv("PELICAN_TUTOR_MODEL", raising=False)
    monkeypatch.delenv("PELICAN_STEM_MODEL", raising=False)
    config = LlmConfig(api_key="test", model="legacy", base_url="test")
    adapter = LlmAdapter(config=config)

    assert adapter.model_route_for_category(DomainCategory.STEM) == "openai/gpt-5.5"
    assert adapter.model_route_for_category(DomainCategory.HUMANITIES) == "~google/gemini-pro-latest"
    assert adapter.tutor_model_route() == "google/gemini-3.1-flash-lite"

    monkeypatch.setenv("PELICAN_LLM_MODEL", "global/model")
    assert adapter.model_route_for_category(DomainCategory.BUSINESS) == "global/model"
    assert adapter.tutor_model_route() == "global/model"

    monkeypatch.setenv("PELICAN_SKILL_MODEL", "skill/model")
    assert adapter.model_route_for_category(DomainCategory.BUSINESS) == "skill/model"

    monkeypatch.setenv("PELICAN_STEM_MODEL", "stem/model")
    assert adapter.model_route_for_category(DomainCategory.STEM) == "stem/model"

    monkeypatch.setenv("PELICAN_TUTOR_MODEL", "tutor/model")
    assert adapter.tutor_model_route() == "tutor/model"


def test_generate_domain_skill_uses_requested_route() -> None:
    payload = valid_skill_payload()
    payload["lifecycle"] = "runtime_generated"

    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.model_seen = None

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.model_seen = model
            return payload

    adapter = RecordingAdapter()
    skill = adapter.generate_domain_skill("深度學習", DomainCategory.STEM, model_route="stem/model")

    assert adapter.model_seen == "stem/model"
    assert skill is not None
    assert skill.skill_id == "deep_learning"
    assert skill.lifecycle.value == "runtime_generated"


def test_generate_domain_skill_payload_uses_strict_schema_for_openai_auto_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.response_format = None

        def _json(self, system: str, user: str, *, model: str | None = None, response_format=None):
            self.response_format = response_format
            return valid_skill_payload()

    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODE", raising=False)
    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODELS", raising=False)
    adapter = RecordingAdapter()

    adapter.generate_domain_skill_payload("深度學習", DomainCategory.STEM, model_route="openai/gpt-5.5")

    assert adapter.response_format["type"] == "json_schema"
    assert adapter.response_format["json_schema"]["strict"] is True
    assert adapter.response_format["json_schema"]["schema"]["properties"]["domain_category"]["enum"] == ["stem"]


def test_generate_domain_skill_payload_keeps_gemini_route_in_json_object_auto_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.response_format = "not-called"

        def _json(self, system: str, user: str, *, model: str | None = None, response_format=None):
            self.response_format = response_format
            return valid_skill_payload()

    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODE", raising=False)
    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODELS", raising=False)
    adapter = RecordingAdapter()

    adapter.generate_domain_skill_payload(
        "中國清朝歷史",
        DomainCategory.HUMANITIES,
        model_route="~google/gemini-pro-latest",
    )

    assert adapter.response_format is None


def test_generate_domain_skill_payload_includes_goal_context_and_humanities_quality_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.user_prompt = ""

        def _json(self, system: str, user: str, *, model: str | None = None, response_format=None):
            self.user_prompt = user
            return valid_skill_payload()

    monkeypatch.setenv("PELICAN_SKILL_SCHEMA_MODE", "json_object")
    adapter = RecordingAdapter()

    adapter.generate_domain_skill_payload(
        "中國清朝歷史",
        DomainCategory.HUMANITIES,
        model_route="~google/gemini-pro-latest",
        goal_context="想了解為何滿清能入關",
    )

    assert "learner_goal: 想了解為何滿清能入關" in adapter.user_prompt
    assert "at least 6 focused concepts" in adapter.user_prompt
    assert "Traditional Chinese" in adapter.user_prompt


def test_generate_domain_skill_payload_can_force_strict_schema_for_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.response_format = None

        def _json(self, system: str, user: str, *, model: str | None = None, response_format=None):
            self.response_format = response_format
            return valid_skill_payload()

    monkeypatch.setenv("PELICAN_SKILL_SCHEMA_MODE", "strict")
    adapter = RecordingAdapter()

    adapter.generate_domain_skill_payload(
        "中國清朝歷史",
        DomainCategory.HUMANITIES,
        model_route="~google/gemini-pro-latest",
    )

    assert adapter.response_format["type"] == "json_schema"


def test_generate_domain_skill_payload_auto_falls_back_when_schema_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.response_formats = []

        def _json(self, system: str, user: str, *, model: str | None = None, response_format=None):
            self.response_formats.append(response_format)
            if response_format is not None:
                raise LlmUnavailable(
                    "LLM request failed: BadRequestError",
                    reason_codes=("llm_request_failed", "llm_api_error_unsupported_parameter"),
                    api_status_code=400,
                    api_error_type="unsupported_parameter",
                )
            return valid_skill_payload()

    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODE", raising=False)
    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODELS", raising=False)
    adapter = RecordingAdapter()

    payload = adapter.generate_domain_skill_payload("深度學習", DomainCategory.STEM, model_route="openai/gpt-5.5")

    assert payload["skill_id"] == "deep_learning"
    assert adapter.response_formats[0]["type"] == "json_schema"
    assert adapter.response_formats[1] is None


def test_generate_domain_skill_payload_logs_schema_debug_metadata(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))

        def _json(self, system: str, user: str, *, model: str | None = None, response_format=None):
            if response_format is not None:
                raise LlmUnavailable(
                    "LLM request failed: BadRequestError",
                    reason_codes=("llm_request_failed", "llm_api_error_unsupported_parameter"),
                    api_status_code=400,
                    api_error_type="unsupported_parameter",
                )
            return valid_skill_payload()

    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODE", raising=False)
    monkeypatch.delenv("PELICAN_SKILL_SCHEMA_MODELS", raising=False)
    adapter = RecordingAdapter()

    with caplog.at_level(logging.DEBUG, logger="pelican_mvp"):
        adapter.generate_domain_skill_payload("深度學習", DomainCategory.STEM, model_route="openai/gpt-5.5")

    selected = next(item for item in caplog.records if item.message == "pelican_skill_schema_mode_selected")
    fallback = next(item for item in caplog.records if item.message == "pelican_skill_schema_provider_fallback")
    assert selected.debug_channel == "skill"
    assert selected.schema_mode == "auto"
    assert selected.schema_format == "json_schema"
    assert selected.schema_strict is True
    assert selected.schema_fallback is False
    assert fallback.schema_format == "json_object"
    assert fallback.schema_fallback is True
    assert fallback.reason_code == "structured_output_unsupported"
    assert fallback.api_status_code == 400
    assert "深度學習" not in caplog.text


def test_intake_question_uses_domain_route() -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.model_seen = None

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.model_seen = model
            return {"question": "你想從朝代脈絡、人物事件，還是制度文化開始？"}

    adapter = RecordingAdapter()
    question = adapter.intake_question(
        topic="中國歷史",
        domain_category=DomainCategory.HUMANITIES,
        stage="goal",
        model_route="humanities/model",
    )

    assert adapter.model_seen == "humanities/model"
    assert question == "你想從朝代脈絡、人物事件，還是制度文化開始？"


def test_classify_intake_semantics_returns_bounded_signal() -> None:
    class RecordingAdapter(LlmAdapter):
        def __init__(self) -> None:
            super().__init__(LlmConfig(api_key="test", model="legacy", base_url="test"))
            self.model_seen = None

        def _json(self, system: str, user: str, *, model: str | None = None):
            self.model_seen = model
            return {
                "intent": "topic_revision",
                "new_topic": "春秋時期歷史",
                "confidence": 1.8,
                "reason_code": "explicit_correction",
            }

    adapter = RecordingAdapter()
    signal = adapter.classify_intake_semantics(
        current_topic="明朝歷史",
        answer="我說錯了，是春秋時期歷史",
        stage="level",
        domain_category=DomainCategory.HUMANITIES,
        model_route="humanities/model",
    )

    assert adapter.model_seen == "humanities/model"
    assert signal.intent == "topic_revision"
    assert signal.new_topic == "春秋時期歷史"
    assert signal.confidence == 1.0
    assert signal.reason_code == "explicit_correction"
