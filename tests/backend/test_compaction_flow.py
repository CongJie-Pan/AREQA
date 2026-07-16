import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from backend.memory_store import MemoryStore
from backend.gum_integration import ObservationQueueWorker
from backend.services.hot_memory_service import (
    HotMemoryKind,
    attach_typed_entry,
    build_hot_memory_entry,
)
from backend.services.memory_ingestion_service import (
    MemoryEligibilityState,
    MemoryIngestionResult,
)

@pytest.mark.asyncio
async def test_end_to_end_compaction_flow(tmp_path, monkeypatch):
    hot_memory_path = tmp_path / "hot_memory.json"
    user_profile_path = tmp_path / "user_profile.json"
    
    store = MemoryStore(budget_limit=1000)
    
    # We will write a large string to force compaction.
    # To mock the compaction worker, we can patch it inside the code or just verify the budget exceed works and triggers compaction logic.
    
    mock_compaction_triggered = False
    
    async def mock_process_callback(uid, items, **kwargs):
        nonlocal mock_compaction_triggered
        mock_compaction_triggered = True
        
    worker = ObservationQueueWorker(process_callback=mock_process_callback, debounce_seconds=0.1)
    await worker.start()
    
    long_string = "王熙鳳的判詞是凡鳥偏從末世來，都知愛慕此生才。一從二令三人木，哭向金陵事更哀。" * 10
    
    # Normally, pushing observations adds to queue.
    for i in range(20):
        await worker.push("default_user", f"Observation {i}: {long_string}")
        
    await asyncio.sleep(0.5)
    
    # Verify the background worker triggered the compaction/processing
    assert mock_compaction_triggered
    await worker.stop()


@pytest.mark.asyncio
async def test_compaction_retains_user_evidence_when_candidate_persistence_fails():
    hot_memory = {}
    provenance = {
        "message_id": "message-1",
        "conversation_id": "conversation-1",
        "timestamp": "2026-07-16T00:00:00+00:00",
        "source_role": "user",
        "raw_user_text": "我偏好先看例子。",
        "evidence_quote": "我偏好先看例子。",
    }
    attach_typed_entry(
        hot_memory,
        "evidence-1",
        provenance["raw_user_text"],
        build_hot_memory_entry(
            "evidence-1",
            kind=HotMemoryKind.USER_EVIDENCE,
            source_role="user",
            cold_export_eligible=True,
            provenance=provenance,
        ),
    )
    store = AsyncMock()
    store.budget_limit = 1
    store.get_hot_memory.return_value = hot_memory
    ingestion = AsyncMock()
    ingestion.ingest_user_evidence.return_value = MemoryIngestionResult(
        state=MemoryEligibilityState.REJECTED,
        reason_code="candidate_persistence_rejected",
        category="passive_preference",
    )

    with patch("memory_store.get_global_store", return_value=store), patch(
        "services.memory_ingestion_service.create_memory_ingestion_service",
        return_value=ingestion,
    ):
        from backend.gum_integration import run_compaction

        await run_compaction("user-1")

    persisted = store.redis.set.await_args.args[1]
    assert "evidence-1" in persisted
