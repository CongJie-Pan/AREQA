"""Execute checkpoint SQL against SQLite; no network or production data access."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.conversation.history import _CACHE, prepare_history
from services.conversation.summary_store import SummaryStore


@pytest_asyncio.fixture
async def storage(tmp_path):
    url = f'sqlite+aiosqlite:///{tmp_path / "checkpoints.db"}'
    engine = create_async_engine(url)
    user, conversation = str(uuid4()), str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(text('CREATE TABLE conversations (id TEXT PRIMARY KEY, user_id TEXT)'))
        await connection.execute(text('''CREATE TABLE conversation_summary_checkpoints (
            user_id TEXT, conversation_id TEXT, model TEXT, prompt_hash TEXT,
            source_hash TEXT, covered INTEGER, summary TEXT, updated_at INTEGER,
            PRIMARY KEY (user_id, conversation_id, model, prompt_hash, source_hash))'''))
        await connection.execute(text('INSERT INTO conversations VALUES (:id, :user)'), {'id': conversation, 'user': user})
    yield SummaryStore(engine), (user, conversation, 'test-model', 'prompt'), url
    await engine.dispose()
    _CACHE.clear()


@pytest.mark.asyncio
async def test_store_restart_ownership_upsert_and_scope(storage):
    store, scope, url = storage
    await store.save(scope, 'prefix', 5, 'private derived notes')
    await store.save(scope, 'prefix', 5, 'updated notes')
    await store._engine.dispose()
    restarted = SummaryStore(create_async_engine(url))
    try:
        assert await restarted.load(scope) == [('prefix', 5, 'updated notes')]
        assert await restarted.load((str(uuid4()), *scope[1:])) == []
        assert await restarted.load((*scope[:2], 'other-model', scope[3])) == []
        assert await restarted.load((*scope[:3], 'other-prompt')) == []
        await restarted.save((str(uuid4()), *scope[1:]), 'bad', 5, 'must not save')
        async with restarted._engine.begin() as connection:
            assert (await connection.execute(text('SELECT count(*) FROM conversation_summary_checkpoints'))).scalar() == 1
    finally:
        await restarted._engine.dispose()


@pytest.mark.asyncio
async def test_store_retains_only_16_versions_and_ignores_expired(storage):
    store, scope, _ = storage
    for i in range(20):
        await store.save((*scope[:2], f'model-{i}', scope[3]), f'hash-{i}', i + 1, 'notes')
    async with store._engine.begin() as connection:
        assert (await connection.execute(text('SELECT count(*) FROM conversation_summary_checkpoints'))).scalar() == 16
        await connection.execute(text('UPDATE conversation_summary_checkpoints SET updated_at = 0'))
    assert await store.load((*scope[:2], 'model-19', scope[3])) == []


@pytest.mark.asyncio
async def test_missing_schema_fails_soft_with_private_error_hidden(tmp_path, caplog):
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "empty.db"}', hide_parameters=True)
    store = SummaryStore(engine)
    scope = (str(uuid4()), str(uuid4()), 'model', 'prompt')
    try:
        assert await store.load(scope) == []
        await store.save(scope, 'hash', 1, 'PRIVATE SUMMARY')
        assert 'history.checkpoint_unavailable operation=load error_type=OperationalError' in caplog.text
        assert 'PRIVATE SUMMARY' not in caplog.text
        assert scope[0] not in caplog.text
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_history_restores_checkpoint_after_process_cache_clear(storage, monkeypatch, caplog):
    import logging
    import services.conversation.history as module
    store, scope, _ = storage
    monkeypatch.setattr(module, 'summary_store', store)
    caplog.set_level(logging.INFO)
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content='Preserve the user choices.'), finish_reason='stop')]))
    messages = [{'role': role, 'content': f'{i} ' + 'prior discussion ' * 70}
                for i in range(55) for role in ('user', 'assistant')]
    messages.append({'role': 'user', 'content': 'Continue.'})
    kwargs = dict(messages=messages, tools=[], client=SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create))), user_id=scope[0], conversation_id=scope[1],
        model=scope[2], output_tokens=500, context_tokens=8000, summary_tokens=256)
    _CACHE.clear()
    first = await prepare_history(**kwargs)
    assert create.await_count == 1
    _CACHE.clear()
    # A fresh repository/engine represents another worker or restart.
    restarted = SummaryStore(create_async_engine(storage[2]))
    monkeypatch.setattr(module, 'summary_store', restarted)
    try:
        again = await prepare_history(**kwargs)
        assert again.messages == first.messages
        assert create.await_count == 1
        assert 'cache_source=database' in caplog.text
        messages[0]['content'] = 'Corrected earlier decision. ' + messages[0]['content']
        await prepare_history(**kwargs)
        assert create.await_count == 2
    finally:
        await restarted._engine.dispose()


@pytest.mark.asyncio
async def test_storage_timeout_opens_retry_circuit(caplog):
    import asyncio
    from unittest.mock import Mock

    class SlowConnection:
        async def __aenter__(self):
            await asyncio.sleep(10)

        async def __aexit__(self, *args):
            pass

    engine = SimpleNamespace(begin=Mock(return_value=SlowConnection()))
    store = SummaryStore(engine)
    scope = (str(uuid4()), str(uuid4()), 'model', 'prompt')
    assert await store.load(scope) == []
    assert 'error_type=TimeoutError' in caplog.text
    assert await store.load(scope) == []
    assert engine.begin.call_count == 1
