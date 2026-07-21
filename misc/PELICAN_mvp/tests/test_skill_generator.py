import logging
import json
from pathlib import Path

import pytest

from pelican_mvp.domain_skill import DomainCategory, DomainSkill, SkillLifecycle
from pelican_mvp.llm import LlmAdapter, LlmUnavailable
from pelican_mvp.skill_artifacts import save_validated_skill_artifact
from pelican_mvp.skill_generator import DomainSkillGenerator, SkillGenerationError
from test_domain_skill import valid_skill_payload


class FakeLlm(LlmAdapter):
    def __init__(self, skills):
        self.skills = list(skills)
        self.calls = []
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    def model_route_for_category(self, category: DomainCategory) -> str:
        return f"route/{category.value}"

    def generate_domain_skill(self, topic: str, category: DomainCategory, *, model_route: str | None = None):
        self.calls.append((topic, category, model_route))
        item = self.skills.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class PayloadLlm(FakeLlm):
    def __init__(self, payloads):
        super().__init__([])
        self.payloads = list(payloads)
        self.payload_calls = []

    def generate_domain_skill_payload(
        self,
        topic: str,
        category: DomainCategory,
        *,
        model_route: str | None = None,
        repair_issues=(),
    ):
        self.payload_calls.append((topic, category, model_route, tuple(repair_issues)))
        item = self.payloads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_skill(**updates) -> DomainSkill:
    payload = valid_skill_payload()
    payload.update(updates)
    return DomainSkill.from_dict(payload)


def test_generator_prefers_catalog_skill_without_llm_call() -> None:
    llm = FakeLlm([make_skill()])
    generator = DomainSkillGenerator(llm)

    skill, route = generator.generate("深度學習")

    assert skill.skill_id == "deep_learning"
    assert route == "catalog"
    assert llm.calls == []


def test_generator_routes_missing_stem_skill_to_model(tmp_path: Path) -> None:
    skill = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    llm = FakeLlm([skill])
    generator = DomainSkillGenerator(llm, artifact_root=tmp_path)

    generated, route = generator.generate("機器學習", force_regenerate=True)

    assert generated.skill_id == "machine_learning"
    assert generated.lifecycle is SkillLifecycle.VALIDATED_GENERATED
    assert route == "route/stem"
    assert llm.calls == [("機器學習", DomainCategory.STEM, "route/stem")]
    assert (tmp_path / "validated" / "機器學習.validated.json").exists()


def test_generator_reuses_validated_runtime_skill_cache(tmp_path: Path) -> None:
    cached = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    save_validated_skill_artifact(cached, topic="機器學習", route="route/stem", root=tmp_path)
    llm = FakeLlm([])
    generator = DomainSkillGenerator(llm, artifact_root=tmp_path)

    skill, route = generator.generate("機器學習")

    assert skill.skill_id == "machine_learning"
    assert route == "runtime_cache"
    assert llm.calls == []


def test_generator_ignores_invalid_runtime_skill_cache(tmp_path: Path) -> None:
    cached = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    save_validated_skill_artifact(cached, topic="機器學習", route="route/stem", root=tmp_path)
    path = tmp_path / "validated" / "機器學習.validated.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["skill"]["remediation_paths"] = payload["skill"]["remediation_paths"][:1]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    replacement = make_skill(skill_id="machine_learning_v2", supported_topics=["機器學習"])
    llm = FakeLlm([replacement])
    generator = DomainSkillGenerator(llm, artifact_root=tmp_path)

    skill, route = generator.generate("機器學習")

    assert skill.skill_id == "machine_learning_v2"
    assert route == "route/stem"
    assert len(llm.calls) == 1


def test_generator_retries_once_after_invalid_skill(tmp_path: Path) -> None:
    invalid = make_skill()
    object.__setattr__(invalid, "remediation_paths", invalid.remediation_paths[:1])
    valid = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    llm = FakeLlm([invalid, valid])
    generator = DomainSkillGenerator(llm, max_retries=1, artifact_root=tmp_path)

    skill, route = generator.generate("機器學習", force_regenerate=True)

    assert skill.skill_id == "machine_learning"
    assert route == "route/stem"
    assert len(llm.calls) == 2


def test_generator_default_repair_loop_allows_three_repairs(tmp_path: Path) -> None:
    invalid_payload = valid_skill_payload()
    invalid_payload["remediation_paths"] = invalid_payload["remediation_paths"][:1]
    valid_payload = valid_skill_payload()
    valid_payload["skill_id"] = "machine_learning"
    valid_payload["supported_topics"] = ["機器學習"]
    llm = PayloadLlm([invalid_payload, invalid_payload, invalid_payload, valid_payload])
    generator = DomainSkillGenerator(llm, artifact_root=tmp_path)

    skill, route = generator.generate("機器學習", force_regenerate=True)

    assert skill.skill_id == "machine_learning"
    assert route == "route/stem"
    assert len(llm.payload_calls) == 4
    assert "missing_remediation" in llm.payload_calls[1][3]
    assert "missing_remediation" in llm.payload_calls[2][3]
    assert "missing_remediation" in llm.payload_calls[3][3]


def test_generator_repairs_with_validation_reason_codes(tmp_path: Path) -> None:
    invalid_payload = valid_skill_payload()
    invalid_payload["remediation_paths"] = invalid_payload["remediation_paths"][:1]
    valid_payload = valid_skill_payload()
    valid_payload["skill_id"] = "machine_learning"
    valid_payload["supported_topics"] = ["機器學習"]
    llm = PayloadLlm([invalid_payload, valid_payload])
    generator = DomainSkillGenerator(llm, max_retries=1, artifact_root=tmp_path)

    skill, route = generator.generate("機器學習", force_regenerate=True)

    assert skill.skill_id == "machine_learning"
    assert route == "route/stem"
    assert llm.payload_calls[0][3] == ()
    assert "missing_remediation" in llm.payload_calls[1][3]


def test_generator_uses_generic_skill_after_bounded_retry(tmp_path: Path) -> None:
    invalid = make_skill()
    object.__setattr__(invalid, "remediation_paths", invalid.remediation_paths[:1])
    llm = FakeLlm([invalid, invalid])
    generator = DomainSkillGenerator(llm, max_retries=1, artifact_root=tmp_path)

    skill, route = generator.generate("機器學習", force_regenerate=True)

    assert skill.skill_id == "generic_stem"
    assert route == "generic:stem"
    assert len(llm.calls) == 2
    failed = json.loads((tmp_path / "failed" / "機器學習.failed.json").read_text(encoding="utf-8"))
    assert failed["reason_codes"] == ["missing_remediation"]
    assert [item["stage"] for item in failed["attempts"]] == ["validation", "validation"]


def test_generator_records_llm_failure_as_generation_failure(caplog, tmp_path: Path) -> None:
    llm = PayloadLlm([LlmUnavailable("LLM request failed: JSONDecodeError")])
    generator = DomainSkillGenerator(llm, max_retries=0, artifact_root=tmp_path)

    with caplog.at_level(logging.WARNING, logger="pelican_mvp"):
        skill, route = generator.generate("中國歷史", force_regenerate=True)

    failed = json.loads((tmp_path / "failed" / "中國歷史.failed.json").read_text(encoding="utf-8"))
    assert skill.skill_id == "generic_humanities"
    assert route == "generic:humanities"
    assert failed["reason_codes"] == ["llm_request_failed", "llm_jsondecodeerror"]
    assert failed["attempts"][0]["event"] == "pelican_skill_generation_failed"
    assert failed["attempts"][0]["stage"] == "llm_request"
    assert "pelican_skill_generation_failed" in caplog.text
    assert "pelican_skill_validation_rejected" not in caplog.text


def test_generator_without_api_key_uses_generic_domain_skill() -> None:
    llm = FakeLlm([])
    llm._available = False
    generator = DomainSkillGenerator(llm)

    skill, route = generator.generate("機器學習", force_regenerate=True)

    assert skill.skill_id == "generic_stem"
    assert route == "generic:stem"


def test_generator_logs_safe_metadata_only(caplog, tmp_path: Path) -> None:
    skill = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    llm = FakeLlm([skill])
    generator = DomainSkillGenerator(llm, artifact_root=tmp_path)
    raw_model_text = "raw model output must not be logged"

    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        generator.generate(f"機器學習 {raw_model_text}", force_regenerate=True)

    assert "pelican_skill_generation_attempt" in caplog.text
    assert raw_model_text not in caplog.text
