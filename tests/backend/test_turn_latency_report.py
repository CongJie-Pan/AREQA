"""The latency baseline report attributes turns and cache use correctly."""
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "performance" / "report_turn_latency.py"
SPEC = importlib.util.spec_from_file_location("report_turn_latency", SCRIPT_PATH)
report_module = importlib.util.module_from_spec(SPEC)
# dataclasses resolve their module through sys.modules.
sys.modules[SPEC.name] = report_module
SPEC.loader.exec_module(report_module)


def _summary(conversation: str, ttfa: int, routing: int = 0) -> str:
    payload = {"conversation_id": conversation, "time_to_first_answer_ms": ttfa,
               "phase_durations_ms": {"search_routing": routing}}
    return f"x orchestration.turn_trace_summary run_id=r conversation_id={conversation} summary={json.dumps(payload)}"


def test_compaction_turns_cache_and_routing_are_separated():
    lines = [
        "x history.budget_evaluated conversation_id=a chat_bytes=9 chat_budget=1 compaction_required=True",
        "x orchestration.stream_started conversation_id=a model=m attachment_parser=True image_slot_cap=2",
        "x orchestration.provider_finish conversation_id=a finish_reason=stop prompt_tokens=100 cached_tokens=80",
        "x orchestration.search_decision run_id=r conversation_id=a effective_search_mode=auto should_search=True",
        _summary("a", 9000, routing=1400),
        "x history.budget_evaluated conversation_id=a chat_bytes=1 chat_budget=9 compaction_required=False",
        "x orchestration.stream_started conversation_id=b model=m attachment_parser=False image_slot_cap=2",
        "x orchestration.provider_finish conversation_id=b finish_reason=stop prompt_tokens=50 cached_tokens=0",
        _summary("a", 2000),
    ]
    report = report_module.build_report(lines)
    assert report.ttfa_compacted == [9000]
    assert report.ttfa_plain == [2000]
    assert report.cache[True] == [80, 100]
    assert report.cache[False] == [0, 50]
    assert report.routing_ms == [1400]
    assert report.search_decisions == [True]
    assert "share=50.0%" in report_module.render(report)


def test_percentile_nearest_rank():
    assert report_module.percentile([], 0.5) is None
    assert report_module.percentile([5, 1, 3], 0.5) == 3
    assert report_module.percentile(list(range(1, 21)), 0.95) == 19
