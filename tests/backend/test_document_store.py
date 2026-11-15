"""Per-document follow-up context: identity, fair budgets, native re-send and fallbacks.

Production evidence (2026-11-15): three papers shared one 40,000-character snapshot,
so the third paper kept 0 characters and follow-ups could not explain it.
"""
import asyncio
import base64
import hashlib
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pymupdf
import pytest

from services.attachments import document_store
from services.conversation.attachment_budget import AttachmentPart, PdfTextPart
from services.query_policy.pdf_guardrails import count_pdf_attachments

OWNER = "account-1"
UPLOAD = "947a963b-a87e-4314-806d-8f171a243117"


def pdf_bytes(pages: list[str]) -> bytes:
    with pymupdf.open() as doc:
        for text in pages:
            doc.new_page().insert_text((40, 60), text, fontsize=9)
        return doc.tobytes()


def attachment(name: str, data: bytes) -> SimpleNamespace:
    return SimpleNamespace(filename=name, media_type="application/pdf", size_bytes=len(data),
                           sha256=hashlib.sha256(data).hexdigest(), pdf_bytes=data, plain_text="")


@pytest.fixture
def redis(monkeypatch):
    entries: dict[str, str] = {}

    async def set_entry(key, value, *, ex):
        assert ex == document_store.MATERIAL_TTL_SECONDS
        entries[key] = value
        return True

    client = AsyncMock()
    client.set.side_effect = set_entry
    client.get.side_effect = entries.get
    client.entries = entries
    monkeypatch.setattr(document_store, "get_redis", lambda: client)
    return client


class FakeStorage:
    def __init__(self, *, fail_download: bool = False):
        self.objects: dict[tuple[str, str, str], bytes] = {}
        self.fail_download = fail_download

    async def persist_upload_document(self, *, user_id, upload_id, doc_id, pdf_bytes):
        self.objects[(user_id, upload_id, doc_id)] = pdf_bytes
        return f"users/x/chat-uploads/{upload_id}/{doc_id}.pdf"

    async def download_upload_document(self, *, user_id, upload_id, doc_id):
        return None if self.fail_download else self.objects.get((user_id, upload_id, doc_id))


async def remember(docs, storage):
    await document_store.remember_documents(OWNER, UPLOAD, "conv", docs, storage=storage)
    await asyncio.gather(*list(document_store._BACKGROUND_TASKS))


def follow_up(question="explain all three papers"):
    return [{"role": "user", "content": "read", "has_upload": "true", "message_id": UPLOAD},
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": question}]


def test_extract_documents_keeps_each_document_separately():
    first = pdf_bytes(["Transformer attention " * 40] * 3)
    second = pdf_bytes(["LSTM constant error carousel " * 40] * 2)
    docs = document_store.extract_documents([attachment("a.pdf", first), attachment("b.pdf", second)])
    assert [doc.filename for doc in docs] == ["a.pdf", "b.pdf"]
    assert [doc.page_count for doc in docs] == [3, 2]
    assert "Transformer" in docs[0].text and "LSTM" in docs[1].text
    assert docs[0].doc_id != docs[1].doc_id


def test_legacy_speaking_material_keeps_previous_shape():
    docs = [document_store.DocumentText("a.pdf", "application/pdf", 1, "a", "x" * 30_000),
            document_store.DocumentText("b.pdf", "application/pdf", 1, "b", "y" * 30_000)]
    material = document_store.material_from_documents(docs)
    assert material["title"] == "a.pdf, b.pdf"
    assert len(material["text"]) == document_store.MAX_MATERIAL_CHARS
    assert material["truncated"] is True


def test_fair_budget_never_starves_a_later_document():
    # Production shape: 32,718 + ~45,000 + ~80,000 characters with a 40,000 budget.
    shares = document_store.allocate_budget([32_718, 45_000, 80_000], 40_000)
    assert sum(shares) <= 40_000
    assert min(shares) >= 13_000
    assert document_store.allocate_budget([1_000, 50_000], 20_000) == [1_000, 19_000]


def test_select_passages_keeps_opening_and_question_related_chunks():
    filler = "\n".join(f"Background paragraph {i} about history." for i in range(400))
    text = "Title and abstract of the paper.\n" + filler + "\nExperiment 6 measures noisy sequences.\n" + filler
    selected = document_store.select_passages(text, "What does experiment 6 measure?", 4_000)
    assert selected.startswith("Title and abstract")
    assert "Experiment 6 measures noisy sequences." in selected
    assert "[…中略…]" in selected
    assert len(selected) <= 4_000


@pytest.mark.asyncio
async def test_follow_up_resends_original_pdfs_natively(redis, caplog):
    caplog.set_level(logging.INFO)
    storage = FakeStorage()
    data = [pdf_bytes([f"Paper {i} body text"]) for i in range(3)]
    docs = document_store.extract_documents([attachment(f"p{i}.pdf", raw) for i, raw in enumerate(data)])
    await remember(docs, storage)

    parts, summary = await document_store.load_documents(OWNER, follow_up(), "explain", storage=storage)

    assert summary == {"mode": "native", "documents": 3, "partial": 0, "kept_chars": 0}
    assert isinstance(parts[0], AttachmentPart) and "complete original PDF" in parts[0]["text"]
    files = [part for part in parts if part.get("type") == "file"]
    assert [base64.b64decode(f["file"]["file_data"].split(",", 1)[1]) for f in files] == data
    assert count_pdf_attachments(parts) == 3
    assert "Paper 0 body text" not in caplog.text


@pytest.mark.asyncio
async def test_text_fallback_covers_every_document_with_coverage_note(redis, monkeypatch):
    monkeypatch.setattr(document_store.settings, "chat_upload_context_text_chars", 30_000, raising=False)
    storage = FakeStorage(fail_download=True)
    docs = [document_store.DocumentText(f"p{i}.pdf", "application/pdf", 10, f"{i}" * 64, f"Paper {i} " + "z" * n)
            for i, n in enumerate([32_000, 7_000, 60_000])]
    await remember(docs, storage)

    parts, summary = await document_store.load_documents(OWNER, follow_up(), "explain", storage=storage)

    assert summary["mode"] == "text" and summary["documents"] == 3
    texts = [part for part in parts if isinstance(part, PdfTextPart)]
    assert len(texts) == 3 and count_pdf_attachments(parts) == 3
    assert all(f"Paper {i}" in part["text"] for i, part in enumerate(texts))
    assert sum(len(part["text"]) for part in texts) <= 30_000 + 200
    assert "p1.pdf: complete text" in parts[0]["text"]
    assert "p2.pdf: partial text" in parts[0]["text"]


@pytest.mark.asyncio
async def test_missing_manifest_returns_none_for_legacy_fallback(redis):
    assert await document_store.load_documents(OWNER, follow_up(), "q", storage=FakeStorage()) is None


@pytest.mark.asyncio
async def test_another_account_cannot_load_documents(redis):
    storage = FakeStorage()
    await remember([document_store.DocumentText("p.pdf", "application/pdf", 3, "a" * 64, "secret body")], storage)
    assert await document_store.load_documents("account-2", follow_up(), "q", storage=storage) is None
    assert await document_store.load_documents(None, follow_up(), "q", storage=storage) is None


@pytest.mark.asyncio
async def test_invalid_upload_id_is_ignored(redis):
    await document_store.remember_documents(OWNER, "../escape", "conv", [
        document_store.DocumentText("p.pdf", "application/pdf", 3, "a" * 64, "body")])
    assert redis.entries == {}


@pytest.mark.asyncio
async def test_redis_outage_fails_soft(monkeypatch, caplog):
    client = AsyncMock()
    client.get.side_effect = ConnectionError("down")
    client.set.side_effect = ConnectionError("down")
    monkeypatch.setattr(document_store, "get_redis", lambda: client)
    await document_store.remember_documents(OWNER, UPLOAD, "conv", [
        document_store.DocumentText("p.pdf", "application/pdf", 3, "a" * 64, "private body")])
    assert await document_store.load_documents(OWNER, follow_up(), "q") is None
    assert "private body" not in caplog.text


@pytest.mark.asyncio
async def test_manifest_records_storage_paths_after_background_upload(redis):
    storage = FakeStorage()
    docs = document_store.extract_documents([attachment("p.pdf", pdf_bytes(["body"]))])
    await remember(docs, storage)
    manifest = json.loads(redis.entries[f"chat_upload_docs:{OWNER}:{UPLOAD}"])
    assert manifest["documents"][0]["storage_path"].endswith(".pdf")
    assert manifest["documents"][0]["page_count"] == 1


class _FakeResponse:
    def __init__(self, content=b"", status=200):
        self.content, self.status_code = content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class _FakeHttp:
    store: dict[str, bytes] = {}

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, content=b"", headers=None, json=None):
        _FakeHttp.store[url] = content
        return _FakeResponse()

    async def get(self, url, headers=None):
        return _FakeResponse(_FakeHttp.store[url]) if url in _FakeHttp.store else _FakeResponse(status=404)


@pytest.mark.asyncio
async def test_storage_round_trip_is_scoped_to_the_owner(monkeypatch):
    from services.attachments.storage import AttachmentImageStorageService

    monkeypatch.setattr(AttachmentImageStorageService, "_storage_config",
                        staticmethod(lambda: ("https://sb.example", "service-key", "bucket", 60)))
    _FakeHttp.store = {}
    storage = AttachmentImageStorageService(async_client_factory=_FakeHttp)
    data = pdf_bytes(["stored body"])
    path = await storage.persist_upload_document(user_id=OWNER, upload_id=UPLOAD, doc_id="abc", pdf_bytes=data)
    assert path.startswith("users/") and "/chat-uploads/" in path and OWNER not in path
    assert await storage.download_upload_document(user_id=OWNER, upload_id=UPLOAD, doc_id="abc") == data
    assert await storage.download_upload_document(user_id="account-2", upload_id=UPLOAD, doc_id="abc") is None
    assert await storage.persist_upload_document(
        user_id=OWNER, upload_id=UPLOAD, doc_id="x", pdf_bytes=b"not a pdf") is None
