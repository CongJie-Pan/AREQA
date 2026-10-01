"""Behavioral contracts at the domain migration boundaries."""

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize("legacy,canonical", [
    ("memory_store", "services.memory.store.service"),
    ("gum_integration", "services.memory.gum.runtime"),
    ("memory_gate", "services.memory.gate"),
    ("services.memory_ingestion_service", "services.memory.ingestion.service"),
    ("services.query_policy_service", "services.query_policy.classifier"),
    ("services.visual_answer_service", "services.visual_answer.service"),
])
def test_legacy_imports_share_the_canonical_module(legacy, canonical):
    """Aliases must share mutations, enum identity and singleton state."""
    implementation = importlib.import_module(canonical)
    assert importlib.import_module(legacy) is implementation
    assert importlib.import_module("backend." + legacy) is implementation


def test_memory_store_singleton_is_shared_across_import_paths(monkeypatch):
    canonical = importlib.import_module("services.memory.store.service")
    legacy = importlib.import_module("backend.memory_store")
    redis = object()
    monkeypatch.setattr(canonical, "_global_store", None)
    monkeypatch.setattr(canonical, "get_redis", lambda: redis)
    store = legacy.init_global_store(budget_limit=1234)
    assert canonical.get_global_store() is store
    assert legacy.get_global_store().redis is redis
    assert canonical.get_global_store().budget_limit == 1234


@pytest.mark.asyncio
async def test_concurrent_gum_initialization_shares_lock_and_stops_workers(monkeypatch, tmp_path):
    """Mixed imports must create one instance per user and one queue worker."""
    runtime = importlib.import_module("services.memory.gum.runtime")
    legacy = importlib.import_module("backend.gum_integration")
    for name in (
        "gum_instances", "text_observers", "importance_sums", "interaction_counts",
        "last_interaction_times", "reflection_locks", "_gum_init_locks",
    ):
        monkeypatch.setattr(runtime, name, {})
    monkeypatch.setattr(runtime, "obs_worker", None)
    monkeypatch.setattr(runtime, "gum_instance", None)
    monkeypatch.setattr(runtime, "reflection_task", None)
    monkeypatch.setattr(runtime, "project_root", tmp_path)
    instances = []

    def make_gum(*args, **kwargs):
        instance = MagicMock()
        # A coroutine side effect forces competing calls through the init lock.
        async def connect():
            await asyncio.sleep(0)
        instance.connect_db = AsyncMock(side_effect=connect)
        instance.stop_update_loop = AsyncMock()
        instance.batcher.start = AsyncMock()
        instance.batcher.stop = AsyncMock()
        instances.append(instance)
        return instance

    worker = MagicMock(start=AsyncMock(), stop=AsyncMock())
    worker_factory = MagicMock(return_value=worker)
    monkeypatch.setattr(runtime, "gum", make_gum)
    monkeypatch.setattr(runtime, "ObservationQueueWorker", worker_factory)
    results = await asyncio.gather(
        legacy.get_gum_instance("user-a"), runtime.get_gum_instance("user-a"),
        runtime.get_gum_instance("user-b"),
    )
    assert results[0][0] is results[1][0]
    assert results[0][0] is not results[2][0]
    assert len(instances) == 2
    worker_factory.assert_called_once()
    await legacy.stop_gum_instance()
    worker.stop.assert_awaited_once()
    assert runtime.gum_instances == {}
    assert runtime.obs_worker is None
    for instance in instances:
        instance.stop_update_loop.assert_awaited_once()
        instance.batcher.stop.assert_awaited_once()


def test_realtime_router_preserves_paths_validation_and_service_dispatch(monkeypatch):
    from backend.app.routes.realtime import router
    from auth import get_optional_current_user
    from services.realtime import openai_session

    service = AsyncMock(return_value={"client_secret": "test-ephemeral", "expires_at": 123})
    monkeypatch.setattr(openai_session, "create_realtime_session", service)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_optional_current_user] = lambda: "test-user"
    paths = app.openapi()["paths"]
    assert set(paths) == {
        "/api/v1/realtime/session", "/api/v1/realtime/livekit-avatar-session",
        "/api/v1/realtime/context", "/api/v1/realtime/attachments",
        "/api/v1/speech/transcribe", "/api/v1/speech/read",
    }
    assert all(set(operations) == {"post"} for operations in paths.values())
    with TestClient(app) as client:
        assert client.post("/api/v1/realtime/session", json={"interface_language": "invalid"}).status_code == 422
        service.assert_not_awaited()
        response = client.post("/api/v1/realtime/session", json={"conversation_id": "c1"})
    assert response.status_code == 200
    assert response.json()["client_secret"] == "test-ephemeral"
    assert service.await_args.kwargs["current_user_id"] == "test-user"
    assert service.await_args.kwargs["payload"].conversation_id == "c1"


def test_image_markers_preserve_output_at_every_chunk_boundary():
    from services.conversation.image_markers import ImageRequestMarkerFilter

    text = '例子。\n\n<AREQA_IMAGE_SLOT id="img_1" query="cell diagram" caption="細胞"/>結尾。'
    for boundary in range(len(text) + 1):
        parser = ImageRequestMarkerFilter()
        public = parser.feed(text[:boundary]) + parser.feed(text[boundary:]) + parser.finish()
        assert public == "例子。\n\n結尾。"
        assert len(parser.slots) == 1
        assert parser.slots[0].slot_id == "img_1"
        assert len(parser.drain_new_slots()) == 1
        assert parser.drain_new_slots() == []


@pytest.mark.asyncio
async def test_cold_recall_preserves_database_location_and_user_scope(monkeypatch):
    """Moving the context module must not move the existing database path."""
    from pathlib import Path

    import cold_memory
    from services.memory.gum import context
    from services.memory.store import service as store_service

    retriever = MagicMock(search=AsyncMock(return_value=[]))
    factory = MagicMock(return_value=retriever)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(cold_memory, "ColdMemoryRetriever", factory)
    monkeypatch.setattr(store_service, "get_global_store", lambda: None)
    monkeypatch.setattr(context, "generate_zpd_query_via_llm", AsyncMock(return_value="query"))
    assert await context.query_cold_memory_for_context("user-a", "query", client=object()) == ""
    backend_dir = Path(__file__).resolve().parents[2] / "backend"
    assert factory.call_args.args[0] == str(backend_dir / "data" / "gum_data" / "gum.db")
    retriever.search.assert_awaited_once_with("query", user_id="user-a", top_k=5)
