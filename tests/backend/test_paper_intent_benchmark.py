import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from config import settings
from scripts.benchmark_paper_intent import summarize
from services.query_policy.paper_intent import JEV_ENDPOINT, JEV_MODEL, classify_jev, classify_pdf_response_policy
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
    client = MagicMock()
    post = AsyncMock(return_value={"answers": {"paper_intent": {"choice": "targeted"}}})
    client.with_options.return_value.post = post
    assert await classify_jev(client, "那接下來呢？", "約定接下來只談實驗方法") == "targeted"
    client.with_options.assert_called_once_with(max_retries=0)
    assert post.await_args.args == (JEV_ENDPOINT,)
    payload = post.await_args.kwargs["body"]
    assert payload["model"] == JEV_MODEL
    assert payload["state"] == {
        "latest_user_message": "那接下來呢？",
        "previous_topic": "約定接下來只談實驗方法",
        "pdf_available": True,
    }
    assert payload["questions"]["paper_intent"]["type"] == "choice"


@pytest.mark.asyncio
@pytest.mark.parametrize(("label", "task"), [
    ("overview", AttachmentTask.PAPER_AUTO_EXPLAIN),
    ("targeted", AttachmentTask.PAPER_TARGETED_QA),
    ("other", AttachmentTask.NONE),
    ("invalid", AttachmentTask.NONE),
])
async def test_pdf_policy_maps_jev_output_and_falls_back_on_invalid_label(label, task, caplog):
    client = MagicMock()
    client.with_options.return_value.post = AsyncMock(
        return_value={"answers": {"paper_intent": {"choice": label}}},
    )
    message = "那接下來呢？"
    messages = [
        {"role": "user", "content": "舊問題"},
        {"role": "assistant", "content": "接下來談研究方法"},
        {"role": "user", "content": message},
        {"role": "assistant", "content": "本輪草稿"},
    ]
    with caplog.at_level("INFO", logger="services.query_policy.paper_intent"):
        policy = await classify_pdf_response_policy(client, message, messages, conversation_id="paper-test")
    assert policy.attachment_task is task
    if label != "invalid":
        assert f"label={label} conversation_id=paper-test duration_ms=" in caplog.text
        assert message not in caplog.text
    client.chat.completions.create.assert_not_called()
    body = client.with_options.return_value.post.await_args.kwargs["body"]
    assert body["state"]["previous_topic"] == "接下來談研究方法"


@pytest.mark.asyncio
async def test_jev_timeout_does_not_retry_or_call_gemini(monkeypatch):
    monkeypatch.setattr(settings, "pdf_intent_classifier_timeout_ms", 10)
    client = MagicMock()

    async def slow_response(*args, **kwargs):
        await asyncio.sleep(1)

    post = AsyncMock(side_effect=slow_response)
    client.with_options.return_value.post = post
    with pytest.raises(asyncio.TimeoutError):
        await classify_pdf_response_policy(client, "可以帶我讀一下嗎？", [])
    post.assert_awaited_once()
    client.chat.completions.create.assert_not_called()


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
