import asyncio
import logging
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import settings
from services.query_policy import attachment_turn_policy as module
from services.query_policy.attachment_turn_policy import (
    classify_attachment_turn_policy,
    gate_paper_overview,
)
from services.query_policy.models import (
    AttachmentReason,
    AttachmentTask,
    LearningMode,
    PedagogicalAction,
    default_response_policy,
)
from services.query_policy.pdf_guardrails import _pdf_auto_explain_policy_from

TEACHING = replace(
    default_response_policy(),
    learning_mode=LearningMode.PRACTICE,
    pedagogical_action=PedagogicalAction.HINT,
)


def jev_client(label="overview", delay=0.0):
    async def post(*_args, **_kwargs):
        await asyncio.sleep(delay)
        return {"answers": {"paper_intent": {"choice": label}}}

    client = MagicMock()
    client.with_options.return_value = SimpleNamespace(post=AsyncMock(side_effect=post))
    return client


async def run(client, dialogue_classifier):
    return await classify_attachment_turn_policy(
        client,
        dialogue_classifier=dialogue_classifier,
        dialogue_model="edf-model",
        message="帶我看這篇論文",
        messages=[{"role": "user", "content": "帶我看這篇論文"}],
        pdf_attachment_count=1,
        conversation_id="conv-1",
    )


@pytest.mark.asyncio
async def test_merges_teaching_from_edf_and_attachment_task_from_jev(caplog):
    caplog.set_level(logging.INFO)
    edf = AsyncMock(return_value=TEACHING)

    policy = await run(jev_client("overview"), edf)

    assert policy.attachment_task is AttachmentTask.PAPER_AUTO_EXPLAIN
    assert policy.learning_mode is LearningMode.PRACTICE
    assert policy.pedagogical_action is PedagogicalAction.HINT
    edf.assert_awaited_once()
    assert edf.await_args.kwargs == {"has_pdf_attachment": True, "pdf_attachment_count": 1}
    timing = next(r.getMessage() for r in caplog.records if "attachment_policy_timing" in r.getMessage())
    assert "jev_status=ok" in timing and "edf_status=ok" in timing
    assert "jev_ms=" in timing and "edf_ms=" in timing and "parallel_wall_ms=" in timing
    assert "teaching_source=edf attachment_source=jev" in timing
    assert "帶我看這篇論文" not in caplog.text


@pytest.mark.asyncio
async def test_runs_both_classifiers_in_parallel_not_in_sequence():
    async def slow_edf(*_args, **_kwargs):
        await asyncio.sleep(0.15)
        return TEACHING

    with patch.object(settings, "pdf_intent_classifier_timeout_ms", 1000), \
         patch.object(settings, "policy_classifier_timeout_ms", 1000):
        started = asyncio.get_running_loop().time()
        await run(jev_client(delay=0.15), slow_edf)
        elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.28


@pytest.mark.asyncio
async def test_edf_timeout_keeps_jev_decision_with_default_teaching(caplog):
    caplog.set_level(logging.INFO)

    async def hung_edf(*_args, **_kwargs):
        await asyncio.sleep(5)

    with patch.object(settings, "policy_classifier_timeout_ms", 20):
        policy = await run(jev_client("targeted"), hung_edf)

    assert policy.attachment_task is AttachmentTask.PAPER_TARGETED_QA
    assert policy.learning_mode is default_response_policy().learning_mode
    assert "edf_status=timeout" in caplog.text
    assert "teaching_source=default attachment_source=jev" in caplog.text


@pytest.mark.asyncio
async def test_jev_failure_keeps_edf_teaching(caplog):
    caplog.set_level(logging.INFO)
    client = MagicMock()
    client.with_options.return_value = SimpleNamespace(post=AsyncMock(side_effect=RuntimeError("down")))

    policy = await run(client, AsyncMock(return_value=TEACHING))

    assert policy.learning_mode is LearningMode.PRACTICE
    assert policy.attachment_task is AttachmentTask.NONE
    assert "edf_status=ok" in caplog.text


@pytest.mark.asyncio
async def test_timing_is_logged_even_when_the_caller_gives_up(caplog):
    caplog.set_level(logging.INFO)

    async def hung_edf(*_args, **_kwargs):
        await asyncio.sleep(5)

    with patch.object(settings, "policy_classifier_timeout_ms", 5000):
        task = asyncio.create_task(run(jev_client(), hung_edf))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert "orchestration.attachment_policy_timing" in caplog.text


def test_outer_budget_covers_the_slower_classifier():
    with patch.object(settings, "pdf_intent_classifier_timeout_ms", 900), \
         patch.object(settings, "policy_classifier_timeout_ms", 700):
        assert module.attachment_policy_timeout_ms() > 900


def test_paper_overview_gate_requires_paper_evidence():
    paper_policy = _pdf_auto_explain_policy_from(default_response_policy())
    no_evidence = SimpleNamespace(allows_paper_overview=lambda _msg: False, log_fields=lambda: "pdf=1")
    evidence = SimpleNamespace(allows_paper_overview=lambda _msg: True, log_fields=lambda: "pdf=1")

    gated = gate_paper_overview(paper_policy, user_msg="這些附件有什麼", manifest=no_evidence)
    assert gated.attachment_task is AttachmentTask.NONE
    assert gated.attachment_reason is AttachmentReason.ATTACHMENT_OVERVIEW

    assert gate_paper_overview(paper_policy, user_msg="論文", manifest=evidence) is paper_policy
    # Follow-up turns have no fresh upload, so the earlier decision path stays as is.
    assert gate_paper_overview(paper_policy, user_msg="x", manifest=None) is paper_policy
