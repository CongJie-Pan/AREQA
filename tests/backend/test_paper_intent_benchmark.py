import json

import httpx
import pytest

from scripts.benchmark_paper_intent import JEV_MODEL, classify_jev, summarize
from services.query_policy.models import AttachmentTask, default_response_policy
from services.query_policy.pdf_guardrails import apply_pdf_auto_explain_guardrail


@pytest.mark.parametrize(
    ("message", "has_pdf", "expected"),
    [
        ("請幫我解釋這一篇論文", True, AttachmentTask.PAPER_AUTO_EXPLAIN),
        ("帮我解释这一篇论文", True, AttachmentTask.PAPER_AUTO_EXPLAIN),
        ("請幫我解釋這一篇論文", False, AttachmentTask.NONE),
        ("請幫我解釋這一篇論文的圖 2", True, AttachmentTask.NONE),
        ("請幫我解釋這一篇論文的第 3 節", True, AttachmentTask.NONE),
        ("不用解釋這一篇論文，請把摘要翻成英文", True, AttachmentTask.NONE),
    ],
)
def test_local_pdf_overview_respects_intent_and_pdf_availability(message, has_pdf, expected):
    policy = apply_pdf_auto_explain_guardrail(
        default_response_policy(), user_msg=message, has_pdf_attachment=has_pdf,
    )
    assert policy.attachment_task is expected


@pytest.mark.asyncio
async def test_jev_decision_uses_only_current_question_and_topic():
    def reply(request):
        assert request.url.path == "/api/alpha/decisions"
        payload = json.loads(request.content)
        assert payload["model"] == JEV_MODEL
        assert payload["state"] == {
            "latest_user_message": "那接下來呢？",
            "previous_topic": "約定接下來只談實驗方法",
            "pdf_available": True,
        }
        assert payload["questions"]["paper_intent"]["type"] == "choice"
        return httpx.Response(200, json={"answers": {"paper_intent": {"choice": "targeted"}}})

    async with httpx.AsyncClient(base_url="https://openrouter.ai", transport=httpx.MockTransport(reply)) as client:
        assert await classify_jev(client, "那接下來呢？", "約定接下來只談實驗方法") == "targeted"


def test_summary_counts_late_correct_and_failed_predictions_as_misses():
    rows = [
        {"expected": "overview", "prediction": "overview", "status": "ok", "ms": 720},
        {"expected": "overview", "prediction": None, "status": "timeout", "ms": 8000},
        {"expected": "targeted", "prediction": "overview", "status": "ok", "ms": 350},
        {"expected": "other", "prediction": "other", "status": "ok", "ms": 620},
    ]
    result = summarize(rows, budget_ms=700)
    assert result["within_budget"] == 2
    assert result["correct_within_budget"] == 1
    assert result["overview_missed_within_budget"] == 2
    assert result["false_overview_within_budget"] == 1
    assert result["p95_ms"] == 720
