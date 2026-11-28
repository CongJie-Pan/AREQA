"""Jev teaching decision mapping and the gemini / jev / shadow policy backends."""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

import config as runtime_config
from services.query_policy import policy_backend
from services.query_policy.models import (
    AnswerDepth,
    FollowupMode,
    LearningMode,
    PedagogicalAction,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualReason,
    VisualSupport,
    default_response_policy,
)
from services.query_policy.paper_intent import JEV_ENDPOINT, JEV_MODEL
from services.query_policy.policy_backend import classify_with_backend
from services.query_policy.teaching_jev import (
    QUESTIONS,
    TEACHING_MOVES,
    TeachingDecision,
    classify_teaching_decision,
    policy_from_decision,
    previous_turn,
)

SECRET = "PRIVATE_LEARNER_TEXT"
REAL_STORE = policy_backend._store


def _decision(move="PRACTICE_HINT", intent="ANSWER_EXAM", depth="SCAFFOLDED", visual="NONE", evidence="NONE", technique="NONE"):
    return TeachingDecision(move, intent, depth, visual, evidence, technique)


def _jev_client(**overrides):
    answers = {"teaching_move": "PRACTICE_HINT", "task_intent": "ANSWER_EXAM", "answer_depth": "DIRECT",
               "visual_support": "NONE", "evidence_mode": "NONE", "learning_technique": "NONE", **overrides}
    client = MagicMock()
    client.with_options.return_value.post = AsyncMock(
        return_value={"answers": {name: {"choice": label} for name, label in answers.items()}},
    )
    return client


@pytest.mark.parametrize("move", sorted(TEACHING_MOVES))
def test_every_offered_move_maps_to_a_coherent_policy(move):
    policy = policy_from_decision(_decision(move=move))

    mode, action = move.split("_", 1)
    assert (policy.learning_mode.value, policy.pedagogical_action.value) == (mode, action)
    if mode == "PRACTICE":
        assert policy.pedagogical_action is not PedagogicalAction.ANSWER
        assert policy.followup_mode is FollowupMode.REQUIRED
        assert policy.legacy_policy == "PROBE_UNDERSTANDING"


def test_reference_direct_answers_plainly_and_briefly():
    policy = policy_from_decision(_decision(move="REFERENCE_ANSWER", intent="GENERAL_QA", depth="DIRECT"))

    assert (policy.tone, policy.structure, policy.followup_mode) == (ResponseTone.PLAIN, ResponseStructure.SHORT, FollowupMode.OPTIONAL)
    assert policy.legacy_policy == "NORMAL"


@pytest.mark.parametrize(("intent", "structure", "tone"), [
    ("WRITE_NOTE", ResponseStructure.NOTE_DRAFT, ResponseTone.TUTORING),
    ("DISCUSS_IDEA", ResponseStructure.ARGUMENT, ResponseTone.ANALYTICAL),
    ("EXPLAIN_TEXT", ResponseStructure.STEP_BY_STEP, ResponseTone.PLAIN),
])
def test_task_intent_shapes_structure_and_tone(intent, structure, tone):
    policy = policy_from_decision(_decision(move="LEARN_EXPLAIN_PREREQ", intent=intent))

    assert (policy.task_intent, policy.structure, policy.tone) == (TaskIntent(intent), structure, tone)


@pytest.mark.parametrize(("visual", "move", "reason"), [
    ("REQUIRED", "LEARN_EXPLAIN_PREREQ", VisualReason.EXPLICIT_VISUAL_REQUEST),
    ("OPTIONAL", "LEARN_EXPLAIN_PREREQ", VisualReason.KNOWLEDGE_EXPLANATION),
    ("OPTIONAL", "PRACTICE_HINT", VisualReason.ANSWER_SEEKING),
    ("NONE", "LEARN_EXPLAIN_PREREQ", VisualReason.NOT_NEEDED),
])
def test_visual_reason_follows_visual_support(visual, move, reason):
    policy = policy_from_decision(_decision(move=move, visual=visual))

    assert (policy.visual_support, policy.visual_reason) == (VisualSupport(visual), reason)


def test_deep_learning_turn_pushes_the_limit_and_diagnostic_learn_requires_followup():
    deep = policy_from_decision(_decision(move="LEARN_MODEL_ANALOGY", intent="EXPLAIN_TEXT", depth="DEEP_DIVE"))
    diagnostic = policy_from_decision(_decision(move="LEARN_DIAGNOSTIC_QUESTION", intent="GENERAL_QA"))

    assert (deep.answer_depth, deep.legacy_policy) == (AnswerDepth.DEEP_DIVE, "PUSH_LIMIT")
    assert diagnostic.followup_mode is FollowupMode.REQUIRED


def test_previous_turn_is_the_message_before_the_latest_user_turn():
    messages = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "剛給了提示"},
        {"role": "user", "content": "那下一步呢？"},
    ]

    assert previous_turn(messages) == "剛給了提示"
    assert previous_turn([{"role": "user", "content": "hi"}]) == ""


@pytest.mark.asyncio
async def test_teaching_decision_sends_only_bounded_message_and_topic():
    client = _jev_client()

    decision = await classify_teaching_decision(client, "x" * 5000, "y" * 900)

    client.with_options.assert_called_once_with(max_retries=0)
    post = client.with_options.return_value.post
    assert post.await_args.args == (JEV_ENDPOINT,)
    body = post.await_args.kwargs["body"]
    assert body["model"] == JEV_MODEL
    assert body["state"] == {"latest_user_message": "x" * 4000, "previous_topic": "y" * 500}
    assert set(body["questions"]) == set(QUESTIONS)
    assert decision.learning_mode == "PRACTICE"


@pytest.mark.asyncio
async def test_teaching_decision_rejects_labels_that_were_not_offered():
    with pytest.raises(ValueError):
        await classify_teaching_decision(_jev_client(teaching_move="PRACTICE_ANSWER"), "hi", "")


@pytest.mark.asyncio
async def test_gemini_backend_never_calls_jev(monkeypatch):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "gemini")
    client = _jev_client()
    served = default_response_policy()

    result = await classify_with_backend(AsyncMock(return_value=served), client, "hi", [])

    assert result is served
    client.with_options.assert_not_called()


@pytest.mark.asyncio
async def test_jev_backend_serves_jev_without_gemini(monkeypatch):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "jev")
    gemini = AsyncMock()

    result = await classify_with_backend(gemini, _jev_client(), "Solve 3x + 5 = 20", [])

    gemini.assert_not_called()
    assert (result.learning_mode, result.pedagogical_action) == (LearningMode.PRACTICE, PedagogicalAction.HINT)


@pytest.mark.asyncio
async def test_jev_backend_fails_soft_to_the_default_policy(monkeypatch, caplog):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "jev")
    client = MagicMock()
    client.with_options.return_value.post = AsyncMock(side_effect=RuntimeError(SECRET))

    with caplog.at_level(logging.WARNING, logger=policy_backend.__name__):
        result = await classify_with_backend(AsyncMock(), client, SECRET, [])

    assert result.learning_mode is LearningMode.LEARN
    assert "policy.jev_failed reason=RuntimeError" in caplog.text
    assert SECRET not in caplog.text


async def _shadow_done():
    await asyncio.gather(*list(policy_backend._shadow_tasks))


@pytest.fixture(autouse=True)
def stored_records(monkeypatch):
    """Keep shadow tests off the real Redis; collect what would be stored."""

    records = []

    async def store(record):
        records.append(record)

    monkeypatch.setattr(policy_backend, "_store", store)
    monkeypatch.setattr(runtime_config.settings, "policy_shadow_until", "")
    return records


@pytest.mark.asyncio
async def test_shadow_record_holds_labels_and_timings_only(monkeypatch, stored_records):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "shadow")

    await classify_with_backend(AsyncMock(return_value=default_response_policy()), _jev_client(), SECRET, [], has_pdf_attachment=True)
    await _shadow_done()

    (record,) = stored_records
    assert set(record) == {
        "ts", "gemini_move", "jev_move", "gemini_depth", "jev_depth", "gemini_status", "jev_status",
        "gemini_ms", "jev_ms", "budget_ms", "has_pdf", "served",
    }
    assert record["served"] == "gemini"
    assert (record["gemini_move"], record["jev_move"], record["has_pdf"]) == ("LEARN_EXPLAIN_PREREQ", "PRACTICE_HINT", True)
    assert SECRET not in repr(record)


@pytest.mark.asyncio
async def test_store_appends_to_a_capped_expiring_list(monkeypatch):
    import redis_client

    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[1, True, True])
    monkeypatch.setattr(redis_client, "get_redis", lambda: MagicMock(pipeline=MagicMock(return_value=pipeline)))

    await REAL_STORE({"ts": 1})

    pipeline.lpush.assert_called_once_with(policy_backend.SHADOW_KEY, '{"ts": 1}')
    pipeline.ltrim.assert_called_once_with(policy_backend.SHADOW_KEY, 0, policy_backend.SHADOW_MAX_RECORDS - 1)
    pipeline.expire.assert_called_once_with(policy_backend.SHADOW_KEY, policy_backend.SHADOW_TTL_SECONDS)


@pytest.mark.asyncio
async def test_store_failure_is_logged_without_raising(monkeypatch, caplog):
    import redis_client

    monkeypatch.setattr(redis_client, "get_redis", MagicMock(side_effect=ConnectionError("down")))

    with caplog.at_level(logging.WARNING, logger=policy_backend.__name__):
        await REAL_STORE({"ts": 1})

    assert "policy.shadow_store_failed reason=ConnectionError" in caplog.text


@pytest.mark.parametrize(("until", "today", "active"), [
    ("", "2030-01-01", True),
    ("2026-12-12", "2026-12-12", True),
    ("2026-12-12", "2026-12-13", False),
    ("not-a-date", "2026-11-28", False),
])
def test_shadow_runs_through_its_end_date(monkeypatch, until, today, active):
    from datetime import date

    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "shadow")
    monkeypatch.setattr(runtime_config.settings, "policy_shadow_until", until)

    assert policy_backend.shadow_active(date.fromisoformat(today)) is active


@pytest.mark.asyncio
async def test_expired_shadow_serves_gemini_without_calling_jev(monkeypatch, stored_records, caplog):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "shadow")
    monkeypatch.setattr(runtime_config.settings, "policy_shadow_until", "2000-01-01")
    monkeypatch.setattr(policy_backend, "_expiry_logged", False)
    client = _jev_client()
    served = default_response_policy()

    with caplog.at_level(logging.INFO, logger=policy_backend.__name__):
        result = await classify_with_backend(AsyncMock(return_value=served), client, "hi", [])

    assert result is served
    client.with_options.assert_not_called()
    assert stored_records == []
    assert "policy.shadow_expired until=2000-01-01 serving=gemini" in caplog.text


@pytest.mark.asyncio
async def test_shadow_serves_gemini_and_logs_labels_only(monkeypatch, caplog):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "shadow")
    served = default_response_policy()

    with caplog.at_level(logging.INFO, logger=policy_backend.__name__):
        result = await classify_with_backend(AsyncMock(return_value=served), _jev_client(), SECRET, [])
        await _shadow_done()

    assert result is served
    assert "policy.shadow_compared gemini_move=LEARN_EXPLAIN_PREREQ jev_move=PRACTICE_HINT" in caplog.text
    assert "agree_mode=False" in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.asyncio
async def test_shadow_measures_gemini_after_the_foreground_times_out(monkeypatch, caplog):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "shadow")
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_timeout_ms", 50)

    async def slow_gemini():
        await asyncio.sleep(0.2)
        return default_response_policy()

    with caplog.at_level(logging.INFO, logger=policy_backend.__name__):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(classify_with_backend(slow_gemini, _jev_client(), "hi", []), timeout=0.05)
        await _shadow_done()

    assert "gemini_status=ok" in caplog.text
    assert "gemini_in_budget=False jev_in_budget=True budget_ms=50" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["jev", "gemini"])
async def test_orchestration_entry_point_uses_the_configured_backend(monkeypatch, backend):
    """Integration: the orchestration classifier wrapper routes through the backend selector."""

    from services.orchestration.utils import classify_dialogue_policy

    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", backend)
    client = _jev_client()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("gemini unavailable"))

    policy = await classify_dialogue_policy(client, "model", "Solve 3x + 5 = 20", [{"role": "user", "content": "Solve 3x + 5 = 20"}])

    if backend == "jev":
        client.chat.completions.create.assert_not_awaited()
        assert policy.pedagogical_action is PedagogicalAction.HINT
    else:
        client.with_options.assert_not_called()
        client.chat.completions.create.assert_awaited()


@pytest.mark.asyncio
async def test_jev_shadow_serves_jev_and_still_measures_gemini(monkeypatch, stored_records):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "jev_shadow")
    gemini = AsyncMock(return_value=default_response_policy())

    result = await classify_with_backend(gemini, _jev_client(), "Solve 3x + 5 = 20", [])
    await _shadow_done()

    assert (result.learning_mode, result.pedagogical_action) == (LearningMode.PRACTICE, PedagogicalAction.HINT)
    gemini.assert_awaited_once()
    (record,) = stored_records
    assert (record["served"], record["gemini_move"], record["jev_move"]) == ("jev", "LEARN_EXPLAIN_PREREQ", "PRACTICE_HINT")


@pytest.mark.asyncio
async def test_jev_shadow_failure_serves_default_and_records_the_failure(monkeypatch, stored_records):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "jev_shadow")
    client = MagicMock()
    client.with_options.return_value.post = AsyncMock(side_effect=RuntimeError(SECRET))

    result = await classify_with_backend(AsyncMock(return_value=default_response_policy()), client, "hi", [])
    await _shadow_done()

    assert result.learning_mode is LearningMode.LEARN
    (record,) = stored_records
    assert (record["jev_status"], record["jev_move"], record["gemini_status"]) == ("RuntimeError", "none", "ok")


@pytest.mark.asyncio
async def test_gemini_shadow_records_jev_failure_instead_of_a_default_label(monkeypatch, stored_records):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "shadow")
    client = MagicMock()
    client.with_options.return_value.post = AsyncMock(side_effect=RuntimeError("down"))

    await classify_with_backend(AsyncMock(return_value=default_response_policy()), client, "hi", [])
    await _shadow_done()

    (record,) = stored_records
    assert (record["jev_status"], record["jev_move"]) == ("RuntimeError", "none")


@pytest.mark.asyncio
async def test_expired_jev_shadow_keeps_serving_jev_alone(monkeypatch, stored_records):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "jev_shadow")
    monkeypatch.setattr(runtime_config.settings, "policy_shadow_until", "2000-01-01")
    gemini = AsyncMock()

    result = await classify_with_backend(gemini, _jev_client(), "hi", [])

    gemini.assert_not_called()
    assert result.pedagogical_action is PedagogicalAction.HINT
    assert stored_records == []


@pytest.mark.asyncio
async def test_jev_shadow_foreground_timeout_leaves_jev_measured(monkeypatch, stored_records):
    monkeypatch.setattr(runtime_config.settings, "policy_classifier_backend", "jev_shadow")
    client = _jev_client()
    answer = client.with_options.return_value.post.return_value

    async def slow_post(*args, **kwargs):
        await asyncio.sleep(0.2)
        return answer

    client.with_options.return_value.post = AsyncMock(side_effect=slow_post)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(classify_with_backend(AsyncMock(return_value=default_response_policy()), client, "hi", []), timeout=0.05)
    await _shadow_done()

    (record,) = stored_records
    assert (record["jev_status"], record["jev_move"]) == ("ok", "PRACTICE_HINT")
