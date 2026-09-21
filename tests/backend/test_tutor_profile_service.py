from backend.services.tutor_profile_service import (
    ENGLISH_TUTOR_SKILL_ID,
    ENGLISH_TUTOR_SKILL_PATH,
    get_tutor_profile,
    normalize_tutor_profile,
    render_tutor_profile_prompt,
)


def test_normalize_tutor_profile_falls_back_to_general():
    assert normalize_tutor_profile(None) == "general"
    assert normalize_tutor_profile("history") == "general"
    assert normalize_tutor_profile(" english ") == "english"


def test_english_tutor_profile_renders_subject_rules():
    prompt = render_tutor_profile_prompt("english")

    assert "Tutor Profile：English Tutor" in prompt
    assert ENGLISH_TUTOR_SKILL_ID in prompt
    assert ENGLISH_TUTOR_SKILL_PATH not in prompt
    assert "must not force English output" in prompt
    assert "Anti-ghostwriting rule" in prompt
    assert "Author/Source, Audience, Purpose, Context, Evidence, Limitation" in prompt
    assert get_tutor_profile("general").rules == ()


def test_general_tutor_profile_renders_empty_prompt():
    assert render_tutor_profile_prompt("general") == ""
