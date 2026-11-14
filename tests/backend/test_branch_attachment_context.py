from unittest.mock import AsyncMock

import pytest

from services.attachments import branch_context
from services.conversation.attachment_budget import PdfTextPart


OWNER = "account-1"
FIRST_UPLOAD = "947a963b-a87e-4314-806d-8f171a243117"
SECOND_UPLOAD = "225675b3-dd84-4dd9-ab20-11e599e56dba"
MISSING_UPLOAD = "9dc60829-4880-43f1-80c3-930ab2576e79"


@pytest.fixture
def redis(monkeypatch):
    entries = {}

    async def set_entry(key, value, *, nx, ex):
        assert nx is True
        assert ex == branch_context.MATERIAL_TTL_SECONDS
        if key in entries:
            return False
        entries[key] = value
        return True

    client = AsyncMock()
    client.set.side_effect = set_entry
    client.get.side_effect = entries.get
    monkeypatch.setattr(branch_context, "get_redis", lambda: client)
    return client


async def save(owner, upload_id, text, *, pdf=True, truncated=False):
    await branch_context.remember_upload(
        owner,
        {"role": "user", "message_id": upload_id},
        {"title": "Original document", "text": text, "truncated": truncated},
        pdf=pdf,
    )


def inherited(upload_id):
    return {"role": "user", "attachment_source_id": upload_id}


@pytest.mark.asyncio
async def test_loads_original_pdf_context_for_same_owner_without_replacing_snapshot(redis):
    await save(OWNER, FIRST_UPLOAD, "Original text", truncated=True)
    await save(OWNER, FIRST_UPLOAD, "Changed after branching")

    result = await branch_context.load_inherited_upload(
        OWNER, [inherited(FIRST_UPLOAD), {"role": "user", "content": "What was the method?"}]
    )

    assert len(result) == 1
    assert isinstance(result[0], PdfTextPart)
    assert result[0]["text"] == (
        "Source document: Original document\nOriginal text\n"
        "[Only the beginning of the source document is available.]"
    )
    assert redis.set.await_count == 2


@pytest.mark.asyncio
async def test_shared_upload_identifier_cannot_read_another_accounts_snapshot(redis):
    await save(OWNER, FIRST_UPLOAD, "Private data")

    assert await branch_context.load_inherited_upload("another-account", [inherited(FIRST_UPLOAD)]) == []


@pytest.mark.asyncio
async def test_guests_cannot_save_or_load_snapshots(redis):
    await save(None, FIRST_UPLOAD, "Guest data")

    assert await branch_context.load_inherited_upload(None, [inherited(FIRST_UPLOAD)]) == []
    redis.set.assert_not_awaited()
    redis.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_latest_upload_takes_precedence_and_missing_snapshot_never_falls_back(redis):
    await save(OWNER, FIRST_UPLOAD, "First")
    await save(OWNER, SECOND_UPLOAD, "Second", pdf=False)
    history = [
        inherited(FIRST_UPLOAD),
        {"role": "assistant", "attachment_source_id": MISSING_UPLOAD},
        {"role": "user", "has_upload": "true", "message_id": SECOND_UPLOAD},
    ]

    assert await branch_context.load_inherited_upload(OWNER, history) == [
        {"type": "text", "text": "Source document: Original document\nSecond"}
    ]
    assert await branch_context.load_inherited_upload(
        OWNER, [*history, inherited(MISSING_UPLOAD)]
    ) == []


@pytest.mark.asyncio
async def test_redis_outage_fails_softly_without_logging_document_text(redis, caplog):
    redis.set.side_effect = RuntimeError("private document text")
    redis.get.side_effect = RuntimeError("private document text")

    await save(OWNER, FIRST_UPLOAD, "private document text")
    assert await branch_context.load_inherited_upload(OWNER, [inherited(FIRST_UPLOAD)]) == []
    assert "private document text" not in caplog.text
