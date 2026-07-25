import logging

import pytest

from pelican_mvp.domain_catalog import resolve_domain_category, resolve_model_route
from pelican_mvp.domain_skill import DomainCategory, DomainSkill, DomainSkillError, IntentType, SkillLifecycle
from pelican_mvp.observability import log_event


def valid_skill_payload() -> dict:
    return {
        "skill_id": "deep_learning",
        "version": "0.1.0",
        "title": "Deep Learning Foundations",
        "domain_category": "stem",
        "lifecycle": "validated_generated",
        "supported_topics": ["深度學習", "deep learning"],
        "intent_types": ["conceptual", "implementation"],
        "prerequisites": [
            {
                "concept_id": "math_intuition",
                "label": "數學直覺",
                "prerequisites": [],
                "description": "理解向量、函數與誤差的直覺。",
            },
            {
                "concept_id": "forward_pass",
                "label": "前向傳播直覺",
                "prerequisites": ["math_intuition"],
                "description": "理解模型如何產生預測。",
            },
        ],
        "calibration_questions": [
            {
                "question_id": "goal",
                "prompt": "你想先理解概念、做實作、完成專案，還是準備考試？",
                "intent_targets": ["conceptual", "implementation"],
                "level_targets": ["beginner", "intermediate"],
            }
        ],
        "canonical_path": {
            "conceptual": ["math_intuition", "forward_pass"],
            "implementation": ["math_intuition", "forward_pass"],
        },
        "diagnostic_rules": [
            {
                "rule_id": "diag_math",
                "concept_id": "math_intuition",
                "prompt": "如果模型預測和答案不同，為什麼需要一個誤差衡量？",
                "expected_answer": "用來衡量預測和目標的差距",
            },
            {
                "rule_id": "diag_forward",
                "concept_id": "forward_pass",
                "prompt": "前向傳播主要是在做什麼？",
                "expected_answer": "把輸入轉成預測",
            },
        ],
        "teaching_moves": [
            {
                "move_id": "decompose",
                "strategy": "decomposition",
                "description": "把概念拆成可回答的小問題。",
            }
        ],
        "remediation_paths": [
            {"signal": "unknown", "action": "scaffold_prerequisite", "target": "math_intuition"},
            {"signal": "too_detailed", "action": "recalibrate_level", "target": "goal"},
            {"signal": "too_easy", "action": "accelerate", "target": "forward_pass"},
            {"signal": "project_goal", "action": "switch_path", "target": "implementation"},
            {"signal": "assessment_goal", "action": "switch_path", "target": "conceptual"},
        ],
        "assessment_policy": {
            "mode": "formative",
            "education_only": True,
            "notes": "Only formative checks are used in the MVP.",
        },
        "safety_notes": ["Do not start with implementation trivia for broad beginner requests."],
    }


def test_domain_skill_round_trips_structured_payload() -> None:
    skill = DomainSkill.from_dict(valid_skill_payload())
    restored = DomainSkill.from_dict(skill.to_dict())

    assert restored == skill
    assert restored.domain_category is DomainCategory.STEM
    assert restored.lifecycle is SkillLifecycle.VALIDATED_GENERATED
    assert restored.intent_types == (IntentType.CONCEPTUAL, IntentType.IMPLEMENTATION)
    assert restored.canonical_path[IntentType.CONCEPTUAL][0] == "math_intuition"


def test_domain_skill_reports_missing_top_level_field_path() -> None:
    payload = valid_skill_payload()
    payload.pop("title")

    with pytest.raises(DomainSkillError) as excinfo:
        DomainSkill.from_dict(payload)

    assert excinfo.value.reason_code == "missing_required_field"
    assert excinfo.value.field_path == "title"


def test_domain_skill_reports_missing_nested_diagnostic_field_path() -> None:
    payload = valid_skill_payload()
    payload["diagnostic_rules"][0].pop("expected_answer")

    with pytest.raises(DomainSkillError) as excinfo:
        DomainSkill.from_dict(payload)

    assert excinfo.value.reason_code == "missing_required_field"
    assert excinfo.value.field_path == "diagnostic_rules[0].expected_answer"


def test_domain_skill_reports_invalid_nested_canonical_path_list() -> None:
    payload = valid_skill_payload()
    payload["canonical_path"]["conceptual"] = "math_intuition"

    with pytest.raises(DomainSkillError) as excinfo:
        DomainSkill.from_dict(payload)

    assert excinfo.value.reason_code == "invalid_required_list"
    assert excinfo.value.field_path == "canonical_path.conceptual"


def test_domain_catalog_routes_supported_and_unknown_topics() -> None:
    stem = resolve_domain_category("我想學深度學習")
    humanities = resolve_domain_category("我想了解法律知識")
    unknown = resolve_domain_category("我想學一個你不確定的東西")

    assert stem.category is DomainCategory.STEM
    assert stem.route_slug == resolve_model_route(DomainCategory.STEM)
    assert humanities.category is DomainCategory.HUMANITIES
    assert unknown.category is DomainCategory.UNKNOWN
    assert unknown.needs_clarification is True


def test_domain_catalog_routes_spring_autumn_history_aliases_to_humanities() -> None:
    aliases = [
        "中國春秋時期歷史",
        "春秋時期",
        "春秋五霸",
        "諸侯爭霸",
        "周王室",
        "尊王攘夷",
        "禮崩樂壞",
        "戰國",
    ]

    for topic in aliases:
        resolution = resolve_domain_category(topic)
        assert resolution.category is DomainCategory.HUMANITIES
        assert resolution.route_slug == resolve_model_route(DomainCategory.HUMANITIES)


def test_observability_allows_skill_metadata_but_redacts_raw_content(caplog) -> None:
    raw_topic = "private learner topic"
    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        log_event(
            "pelican_skill_validated",
            learner_id="student",
            skill_id="deep_learning",
            skill_version="0.1.0",
            domain_category="stem",
            intake_decision="calibrate",
            route="openrouter_gpt_5_5",
            reason_code="ok",
            topic=raw_topic,
        )

    assert "pelican_skill_validated" in caplog.text
    record = caplog.records[0]
    assert record.skill_id == "deep_learning"
    assert record.route == "openrouter_gpt_5_5"
    assert record.debug_channel == "skill"
    assert raw_topic not in caplog.text
    assert not hasattr(record, "topic")


def test_observability_allows_api_endpoint_and_keeps_debug_channel_safe(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="pelican_mvp"):
        log_event(
            "pelican_api_error",
            learner_id="student",
            endpoint="/api/respond",
            reason_code="validation_error",
            answer="raw private answer",
        )

    record = caplog.records[0]
    assert record.debug_channel == "api"
    assert record.endpoint == "/api/respond"
    assert "raw private answer" not in caplog.text
    assert not hasattr(record, "answer")
