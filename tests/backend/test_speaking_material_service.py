"""Regression coverage for conversation-scoped voice practice material."""

from types import SimpleNamespace

import pytest

from services import speaking_material_service as material_service


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    async def set(self, key, value, *, ex):
        self.values[key] = value
        self.ttls[key] = ex

    async def get(self, key):
        return self.values.get(key)


@pytest.mark.asyncio
async def test_material_is_scoped_to_learner_and_conversation(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(material_service, "get_redis", lambda: redis)
    source = {"title": "dialogue.txt", "text": "Student: I disagree with the campus plan.", "truncated": False}

    assert await material_service.save_material("learner-a", "conversation-a", source)
    assert await material_service.load_material("learner-a", "conversation-a") == source
    assert await material_service.load_material("learner-b", "conversation-a") is None
    assert await material_service.load_material("learner-a", "conversation-b") is None
    assert list(redis.ttls.values()) == [material_service.MATERIAL_TTL_SECONDS]


def test_text_material_is_extracted_and_voice_excerpt_marks_truncation():
    attachment = SimpleNamespace(
        media_type="text/plain",
        content_part={"type": "text", "text": "Student: I disagree.\nProfessor: Why?"},
        filename="dialogue.txt",
        pdf_bytes=b"",
        plain_text="Student: I disagree.\nProfessor: Why?",
    )
    material = material_service.extract_material([attachment])
    assert material == {
        "title": "dialogue.txt",
        "text": "Student: I disagree.\nProfessor: Why?",
        "truncated": False,
    }
    long_material = {"title": "long", "text": "x" * 13_000, "truncated": False}
    excerpt = material_service.voice_excerpt(long_material)
    assert len(excerpt["text"]) == material_service.MAX_VOICE_EXCERPT_CHARS
    assert excerpt["truncated"] is True


def test_pdf_transcript_text_is_extracted_without_guessing_images():
    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Student: The library should stay open.")
    pdf_bytes = document.tobytes()
    document.close()
    attachment = SimpleNamespace(
        media_type="application/pdf",
        content_part={"type": "file"},
        filename="dialogue.pdf",
        pdf_bytes=pdf_bytes,
    )

    material = material_service.extract_material([attachment])
    assert material["title"] == "dialogue.pdf"
    assert "The library should stay open" in material["text"]


def test_pasted_dialogue_requires_actual_source_text():
    request = "我給你了一個對話的逐字稿，然後我想要依此練習托福英文口說，你可以陪我練習嗎？"
    assert material_service.extract_pasted_material(request) is None
    dialogue = (
        "Student: I think the campus library should stay open longer because we need a quiet place to study.\n"
        "Professor: What is the main reason students would use it at night?"
    )
    assert material_service.extract_pasted_material(dialogue)["text"] == dialogue
