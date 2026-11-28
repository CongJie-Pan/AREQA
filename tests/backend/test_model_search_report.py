"""The model-search rollout report pairs decisions and groups latency correctly."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "scripts" / "performance"
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("report_model_search", ROOT / "report_model_search.py")
report_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report_module
SPEC.loader.exec_module(report_module)


def _decision(conversation, reason, should_search=False):
    return (f"x orchestration.search_decision run_id=r conversation_id={conversation} request_id=q "
            f"effective_search_mode=auto should_search={should_search} reason={reason} use_rag=False")


def _summary(conversation, ttfa):
    payload = {"conversation_id": conversation, "time_to_first_answer_ms": ttfa}
    return f"x orchestration.turn_trace_summary run_id=r conversation_id={conversation} summary={json.dumps(payload)}"


def test_pairs_shadow_with_model_choice_even_when_shadow_logs_late():
    lines = [
        _decision("a", "MODEL_TOOL_ROUTING"),
        "x orchestration.model_search_decision conversation_id=a called=True",
        "x orchestration.model_search_shadow run_id=r conversation_id=a classifier_search=False reason=X latency_ms=900",
        _summary("a", 4000),
        _decision("a", "MODEL_TOOL_ROUTING"),
        "x orchestration.model_search_shadow run_id=r conversation_id=a classifier_search=True reason=X latency_ms=800",
        "x orchestration.model_search_decision conversation_id=a called=True",
        _summary("a", 3000),
        _decision("b", "EXTERNAL_SEARCH_REQUIRED", should_search=True),
        _summary("b", 5000),
        _decision("c", "INTERNAL_KNOWLEDGE_SUFFICIENT"),
        _summary("c", 1500),
    ]
    report = report_module.build_report(lines)
    assert report.agreement[(True, False)] == 1 and report.agreement[(True, True)] == 1
    assert report.unpaired_decisions == 0
    assert report.ttfa["model_search"] == [4000, 3000]
    assert report.ttfa["classifier_search"] == [5000]
    assert report.ttfa["classifier_direct"] == [1500]
    text = report_module.render(report)
    assert "agreement=50.0%" in text and "recall_vs_classifier=100.0%" in text
