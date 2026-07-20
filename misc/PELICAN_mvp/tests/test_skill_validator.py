import pytest

from pelican_mvp.domain_skill import DomainSkill
from pelican_mvp.skill_validator import SkillValidationError, validate_domain_skill
from test_domain_skill import valid_skill_payload


def reason_codes(error: SkillValidationError) -> set[str]:
    return {issue.reason_code for issue in error.issues}


def test_validate_domain_skill_accepts_complete_skill() -> None:
    skill = DomainSkill.from_dict(valid_skill_payload())

    validate_domain_skill(skill)


def test_validate_domain_skill_rejects_cycle_and_answer_leak() -> None:
    payload = valid_skill_payload()
    payload["prerequisites"][0]["prerequisites"] = ["forward_pass"]
    payload["diagnostic_rules"][0]["prompt"] = (
        "請回答：用來衡量預測和目標的差距。這句為什麼是 loss 的功能？"
    )
    skill = DomainSkill.from_dict(payload)

    with pytest.raises(SkillValidationError) as exc_info:
        validate_domain_skill(skill)

    codes = reason_codes(exc_info.value)
    assert "cyclic_prerequisite" in codes
    assert "answer_leaked_in_prompt" in codes


def test_validate_domain_skill_requires_remediation_coverage() -> None:
    payload = valid_skill_payload()
    payload["remediation_paths"] = payload["remediation_paths"][:1]
    skill = DomainSkill.from_dict(payload)

    with pytest.raises(SkillValidationError) as exc_info:
        validate_domain_skill(skill)

    assert "missing_remediation" in reason_codes(exc_info.value)


def test_validate_domain_skill_rejects_missing_single_concept_diagnostic() -> None:
    payload = valid_skill_payload()
    payload["diagnostic_rules"][1]["tests_single_concept"] = False
    del payload["diagnostic_rules"][0]
    skill = DomainSkill.from_dict(payload)

    with pytest.raises(SkillValidationError) as exc_info:
        validate_domain_skill(skill)

    codes = reason_codes(exc_info.value)
    assert "multi_concept_diagnostic" in codes
    assert "missing_diagnostic" in codes


def test_validate_domain_skill_enforces_legal_education_boundary() -> None:
    payload = valid_skill_payload()
    payload["skill_id"] = "legal_knowledge"
    payload["domain_category"] = "humanities"
    payload["supported_topics"] = ["法律知識"]
    payload["assessment_policy"] = {
        "mode": "formative",
        "education_only": False,
        "notes": "可回答個案。",
    }
    skill = DomainSkill.from_dict(payload)

    with pytest.raises(SkillValidationError) as exc_info:
        validate_domain_skill(skill)

    codes = reason_codes(exc_info.value)
    assert "legal_policy_not_education_only" in codes
    assert "legal_policy_missing_boundary" in codes
