"""Behavior checks for file-backed prompt loading and existing renderers."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from services import prompt_skills
from services.conversation import answer_style, tutor_profile
from services.query_policy.pdf_guardrails import paper_auto_explain_instruction


def _document(payload):
    return (
        "# Maintenance notes\nDO_NOT_INJECT_THIS_NOTE\n"
        "<!-- AREQA_RUNTIME_PROMPT_BEGIN -->\n```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```\n<!-- AREQA_RUNTIME_PROMPT_END -->\n"
        "## Implementation map\nbackend/private_reference.py\n"
    )


@pytest.fixture
def skill_root(tmp_path, monkeypatch):
    prompt_skills.load_prompt_skill.cache_clear()
    monkeypatch.setattr(prompt_skills, "_SKILLS_ROOT", tmp_path)
    yield tmp_path
    prompt_skills.load_prompt_skill.cache_clear()


def test_payload_changes_answer_without_injecting_maintenance_notes(skill_root):
    source = skill_root / "paper_auto_explain_skill.md"
    source.write_text(_document({"instruction": "Explain the verified finding first."}))

    prompt = paper_auto_explain_instruction()

    assert "Explain the verified finding first." in prompt
    assert "AREQA_TEACHING_V1" in prompt
    assert "DO_NOT_INJECT_THIS_NOTE" not in prompt
    assert "Implementation map" not in prompt
    assert "backend/private_reference.py" not in prompt


def test_successful_load_is_cached_and_immutable(skill_root):
    source = skill_root / "english_tutor_skill.md"
    source.write_text(_document({"rules": ["Original rule"]}))
    first = prompt_skills.load_prompt_skill("english-tutor")
    source.write_text(_document({"rules": ["Changed rule"]}))

    assert prompt_skills.load_prompt_skill("english-tutor") is first
    assert first["rules"] == ("Original rule",)
    with pytest.raises(TypeError):
        first["rules"] = ("Mutation",)
    prompt_skills.load_prompt_skill.cache_clear()
    assert prompt_skills.load_prompt_skill("english-tutor")["rules"] == ("Changed rule",)


def test_failed_load_is_cached_until_restart(skill_root):
    assert prompt_skills.load_prompt_skill("english-tutor") is None
    (skill_root / "english_tutor_skill.md").write_text(_document({"rules": ["New rule"]}))
    assert prompt_skills.load_prompt_skill("english-tutor") is None
    prompt_skills.load_prompt_skill.cache_clear()
    assert prompt_skills.load_prompt_skill("english-tutor")["rules"] == ("New rule",)


@pytest.mark.parametrize("content", [
    b"\xff", b"no runtime block", b"x" * (64 * 1024 + 1),
    _document({"instruction": ""}).encode(),
    _document({"instruction": 5}).encode(),
    _document({"instruction": "ok", "unexpected": "bad"}).encode(),
    _document({"rules": ["wrong skill schema"]}).encode(),
    _document({"instruction": "ok"}).replace('"ok"', "invalid-json").encode(),
    _document({"instruction": "ok"}).replace('"instruction": "ok"', '"instruction": "a", "instruction": "b"').encode(),
    (_document({"instruction": "ok"}) + "<!-- AREQA_RUNTIME_PROMPT_BEGIN -->").encode(),
    _document({"instruction": "ok"}).replace("<!-- AREQA_RUNTIME_PROMPT_END -->", "").encode(),
])
def test_invalid_paper_skill_preserves_legacy_fallback(skill_root, content, caplog):
    (skill_root / "paper_auto_explain_skill.md").write_bytes(content)

    prompt = paper_auto_explain_instruction()

    assert "研究動機與目的" in prompt
    assert "研究方法與模型架構" in prompt
    assert "實驗設計與資料集" in prompt
    assert "實驗結果與消融分析" in prompt
    assert "局限與可延伸方向" in prompt
    assert "PDF 中沒有足夠資訊" in prompt
    assert "prompt_skill.fallback" in caplog.text
    assert "invalid-json" not in caplog.text
    assert "unexpected" not in caplog.text


@pytest.mark.parametrize("rules", [[], [""], [3], "not a list", ["rule"] * 33])
def test_invalid_rule_lists_fall_back(skill_root, rules):
    (skill_root / "english_tutor_skill.md").write_text(_document({"rules": rules}))
    assert tutor_profile.get_tutor_profile("english") is tutor_profile.ENGLISH_TUTOR_PROFILE


def test_io_error_falls_back_without_logging_exception_content(skill_root, monkeypatch, caplog):
    def fail_open(*args, **kwargs):
        raise PermissionError("PRIVATE_DIAGNOSTIC")

    monkeypatch.setattr(Path, "open", fail_open)
    assert prompt_skills.load_prompt_skill("english-tutor") is None
    assert "PRIVATE_DIAGNOSTIC" not in caplog.text


def test_english_skill_only_applies_to_selected_profile(skill_root):
    (skill_root / "english_tutor_skill.md").write_text(_document({"rules": ["Custom speaking instruction"]}))
    assert tutor_profile.render_tutor_profile_prompt("general") == ""
    assert tutor_profile.render_tutor_profile_prompt("unknown") == ""
    assert "Custom speaking instruction" in tutor_profile.render_tutor_profile_prompt("english")
    assert "不得覆蓋回答語言" in tutor_profile.render_tutor_profile_prompt("english")


def test_pedagogy_payload_updates_shared_contract_and_preserves_identifiers(skill_root):
    from dataclasses import asdict

    fallback = answer_style.AREQA_TEACHING_V1
    payload = asdict(fallback)
    for field in ("version", "skill_id", "skill_path"):
        payload.pop(field)
    payload["explanation_order_rule"] = "Start with a concrete example."
    (skill_root / "pedagogy_tutor_skill.md").write_text(_document(payload))
    contract = answer_style._load_teaching_contract(fallback)

    assert contract.version == fallback.version
    assert contract.skill_id == fallback.skill_id
    assert "Start with a concrete example." in answer_style.render_base_persona(contract)
    assert "Start with a concrete example." in answer_style.render_paper_overview_style(contract)
    assert isinstance(contract.learnlm_rules, tuple)


def test_missing_skills_preserve_pedagogy_and_english_fallbacks(skill_root):
    fallback = replace(answer_style.AREQA_TEACHING_V1, identity="Known fallback")
    assert answer_style._load_teaching_contract(fallback) is fallback
    assert tutor_profile.get_tutor_profile("english") is tutor_profile.ENGLISH_TUTOR_PROFILE


def test_caller_cannot_choose_arbitrary_file(skill_root):
    with pytest.raises(ValueError, match="Unsupported prompt skill"):
        prompt_skills.load_prompt_skill("../../credentials")


def test_app_creation_preloads_all_skills(skill_root):
    from app.bootstrap import create_app

    (skill_root / "english_tutor_skill.md").write_text(_document({"rules": ["Startup rule"]}))
    assert create_app().title == "XiaoHong Ancient Chinese QA - RAG Backend API"
    assert prompt_skills.load_prompt_skill.cache_info().currsize == 3
    (skill_root / "english_tutor_skill.md").unlink()
    assert "Startup rule" in tutor_profile.render_tutor_profile_prompt("english")


def test_shipped_payloads_are_valid_and_hide_implementation_details():
    prompt_skills.load_prompt_skill.cache_clear()
    try:
        prompt_skills.preload_prompt_skills()
        for skill_id in ("pedagogy-tutor", "english-tutor", "paper-auto-explain"):
            assert prompt_skills.load_prompt_skill(skill_id) is not None
        assert "Runtime prompt payload" not in paper_auto_explain_instruction()
        assert "Implementation map" not in paper_auto_explain_instruction()
        assert "backend/services" not in tutor_profile.render_tutor_profile_prompt("english")
    finally:
        prompt_skills.load_prompt_skill.cache_clear()


def test_fresh_process_uses_skill_edits_in_default_prompts_without_request_time_io(tmp_path):
    """Exercise default arguments and app prompt constants in a fresh worker."""

    source_root = Path(prompt_skills.__file__).resolve().parents[1] / "prompts" / "skills"
    for filename in ("pedagogy_tutor_skill.md", "english_tutor_skill.md", "paper_auto_explain_skill.md"):
        content = (source_root / filename).read_text(encoding="utf-8")
        if filename == "pedagogy_tutor_skill.md":
            content = content.replace("先講白話直覺，再補必要術語", "CUSTOM_PEDAGOGY_RULE")
        elif filename == "english_tutor_skill.md":
            content = content.replace("English Tutor scope:", "CUSTOM_ENGLISH_RULE:")
        else:
            content = content.replace("【PDF 論文自動解說任務】", "CUSTOM_PAPER_RULE")
        (tmp_path / filename).write_text(content, encoding="utf-8")

    script = '''
import sys
from pathlib import Path
from services import prompt_skills
prompt_skills._SKILLS_ROOT = Path(sys.argv[1])
from app.bootstrap import create_app
create_app()
from app.prompts import BASE_PERSONA
from services.conversation.answer_style import render_paper_overview_style, response_policy_overlays
from services.conversation.tutor_profile import render_tutor_profile_prompt
from services.query_policy.pdf_guardrails import paper_auto_explain_instruction
def forbid_read(*args, **kwargs):
    raise AssertionError("Request-time file read")
Path.open = forbid_read
assert "CUSTOM_PEDAGOGY_RULE" in BASE_PERSONA
assert "CUSTOM_PEDAGOGY_RULE" in render_paper_overview_style()
assert "CUSTOM_PEDAGOGY_RULE" in response_policy_overlays()["TUTORING"]
assert "CUSTOM_ENGLISH_RULE" in render_tutor_profile_prompt("english")
assert render_tutor_profile_prompt("general") == ""
assert "CUSTOM_PAPER_RULE" in paper_auto_explain_instruction()
'''
    env = dict(os.environ, PYTHONPATH=str(source_root.parents[1]))
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
