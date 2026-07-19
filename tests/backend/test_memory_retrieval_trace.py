from backend.services.memory_retrieval_trace import MemoryRetrievalTrace


def test_memory_retrieval_trace_snapshot_is_privacy_safe():
    trace = MemoryRetrievalTrace(route_reason="EXPLICIT_RECALL_REQUEST")

    trace.record_step("cold memory / embedding", 12, outcome="completed")
    trace.finish(outcome="retrieved", cache_status="cache_miss", result_count=7)

    snapshot = trace.snapshot()

    assert snapshot["route_reason"] == "explicit_recall_request"
    assert snapshot["result_count_bucket"] == "6+"
    assert snapshot["steps"][0]["name"] == "cold_memory___embedding"
    assert "你還記得" not in str(snapshot)
    assert "memory text" not in str(snapshot)
