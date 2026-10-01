"""Verify service discovery and shared state without pytest's module cache."""

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALIASES = {
    "answer_style_service": "conversation.answer_style",
    "cache_service": "retrieval.cache",
    "compeer_scheduler": "compeer.runtime",
    "connection_manager": "notifications.connections",
    "generated_image_quota": "visual.generation_quota",
    "generated_image_service": "visual.generation",
    "message_intent_service": "orchestration.message_intent",
    "pdf_visual_extraction_service": "pdf_visual.extraction",
    "post_turn_service": "orchestration.post_turn",
    "response_boundary_validator": "conversation.response_boundary",
    "speaking_material_service": "realtime.speaking_material",
    "turn_intake_service": "orchestration.intake",
    "turn_latency_trace": "orchestration.trace",
    "turn_plan_service": "orchestration.turn_plan",
    "tutor_profile_service": "conversation.tutor_profile",
    "attachment_image_storage_service": "attachments.storage",
    "attachment_service": "attachments.parsing",
    "conversation_context_service": "conversation.context",
    "conversation_stream_service": "conversation.stream",
    "explicit_memory_cache": "memory.recall_cache",
    "hot_memory_service": "memory.hot",
    "memory_extraction_agent": "memory.extraction",
    "memory_ingestion_service": "memory.ingestion.service",
    "memory_retrieval_trace": "memory.retrieval_trace",
    "memory_semantic_analyzer": "memory.semantic_analysis",
    "orchestration_service": "orchestration.service",
    "output_image_service": "visual.output",
    "paper_visual_planner_service": "paper_visual.planner",
    "parts_context_service": "conversation.parts",
    "query_policy_service": "query_policy.classifier",
    "visual_affordance_registry": "visual.affordance",
    "visual_answer_service": "visual_answer.service",
    "visual_grounding_agent": "visual.grounding",
    "visual_input_service": "visual.input",
    "visual_understanding_agent": "visual.understanding"
}


@pytest.mark.parametrize("first", ["canonical", "legacy", "backend_legacy"])
def test_legacy_aliases_share_state_in_every_import_order(first):
    script = r'''
import importlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "backend"))
import services
assert "openai" not in sys.modules
assert "services.compeer.runtime" not in sys.modules
# Bootstrap can add the other source root after importing backend services.
assert importlib.util.find_spec("services.router_service") is not None
assert importlib.util.find_spec("services.suggestion_service") is not None
sys.path.insert(0, str(root / "src/main/python"))
for old, target in json.loads(sys.argv[2]).items():
    names = {
        "canonical": "services." + target,
        "legacy": "services." + old,
        "backend_legacy": "backend.services." + old,
    }
    first = importlib.import_module(names[sys.argv[3]])
    modules = [importlib.import_module(name) for name in names.values()]
    assert all(module is first for module in modules), names
    sentinel = object()
    first._compat_contract_sentinel = sentinel
    assert all(module._compat_contract_sentinel is sentinel for module in modules)
    del first._compat_contract_sentinel
    for parent in ("services", "backend.services"):
        package = importlib.import_module(parent)
        assert getattr(package, old) is first
from services.visual import generation
assert generation._image_skill_rules()
'''
    result = subprocess.run(
        [sys.executable, "-c", script, str(ROOT), json.dumps(ALIASES), first],
        cwd=ROOT, capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stderr
