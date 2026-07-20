import logging

import pytest

from pelican_mvp.domain_skill import DomainCategory, DomainSkill, SkillLifecycle
from pelican_mvp.llm import LlmAdapter
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


def test_generator_routes_missing_stem_skill_to_model() -> None:
    skill = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    llm = FakeLlm([skill])
    generator = DomainSkillGenerator(llm)

    generated, route = generator.generate("機器學習", force_regenerate=True)

    assert generated.skill_id == "machine_learning"
    assert generated.lifecycle is SkillLifecycle.VALIDATED_GENERATED
    assert route == "route/stem"
    assert llm.calls == [("機器學習", DomainCategory.STEM, "route/stem")]


def test_generator_retries_once_after_invalid_skill() -> None:
    invalid = make_skill()
    object.__setattr__(invalid, "remediation_paths", invalid.remediation_paths[:1])
    valid = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    llm = FakeLlm([invalid, valid])
    generator = DomainSkillGenerator(llm, max_retries=1)

    skill, route = generator.generate("機器學習", force_regenerate=True)

    assert skill.skill_id == "machine_learning"
    assert route == "route/stem"
    assert len(llm.calls) == 2


def test_generator_fails_after_bounded_retry() -> None:
    invalid = make_skill()
    object.__setattr__(invalid, "remediation_paths", invalid.remediation_paths[:1])
    llm = FakeLlm([invalid, invalid])
    generator = DomainSkillGenerator(llm, max_retries=1)

    with pytest.raises(SkillGenerationError):
        generator.generate("機器學習", force_regenerate=True)

    assert len(llm.calls) == 2


def test_generator_without_api_key_fails_for_missing_catalog() -> None:
    llm = FakeLlm([])
    llm._available = False
    generator = DomainSkillGenerator(llm)

    with pytest.raises(SkillGenerationError, match="LLM unavailable"):
        generator.generate("機器學習", force_regenerate=True)


def test_generator_logs_safe_metadata_only(caplog) -> None:
    skill = make_skill(skill_id="machine_learning", supported_topics=["機器學習"])
    llm = FakeLlm([skill])
    generator = DomainSkillGenerator(llm)
    raw_model_text = "raw model output must not be logged"

    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        generator.generate(f"機器學習 {raw_model_text}", force_regenerate=True)

    assert "pelican_skill_generation_attempt" in caplog.text
    assert raw_model_text not in caplog.text
