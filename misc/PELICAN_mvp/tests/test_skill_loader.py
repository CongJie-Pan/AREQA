import json
from pathlib import Path

import pytest

from pelican_mvp.domain_skill import DomainCategory
from pelican_mvp.skill_loader import SkillLoadError, load_catalog_skill, load_skill
from test_domain_skill import valid_skill_payload


def test_load_catalog_skill_loads_deep_learning_asset() -> None:
    skill = load_catalog_skill("深度學習")

    assert skill.skill_id == "deep_learning"
    assert skill.domain_category is DomainCategory.STEM
    assert skill.lifecycle.value == "validated_generated"


def test_load_catalog_skill_rejects_unknown_topic() -> None:
    with pytest.raises(SkillLoadError, match="no catalog skill"):
        load_catalog_skill("未知冷門主題")


def test_load_skill_rejects_broken_asset_without_partial_skill(tmp_path: Path) -> None:
    payload = valid_skill_payload()
    payload["prerequisites"][1]["prerequisites"] = ["missing_concept"]
    path = tmp_path / "broken.yaml"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(SkillLoadError):
        load_skill(path)


def test_load_skill_rejects_oversized_asset(tmp_path: Path) -> None:
    path = tmp_path / "too_large.yaml"
    path.write_text(" " * 128_001, encoding="utf-8")

    with pytest.raises(SkillLoadError, match="too large"):
        load_skill(path)
