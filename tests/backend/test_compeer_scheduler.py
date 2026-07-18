import pytest
import time
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock, ANY

import backend.services.compeer_scheduler as compeer
from config import settings


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"trigger_present": False}, "absent_trigger"),
        (
            {"trigger_present": True, "cooldown_active": True},
            "cooldown_active",
        ),
        (
            {"trigger_present": False, "inactive_seconds": 30, "scroll_count": 6},
            "inactivity_threshold",
        ),
        (
            {"trigger_present": False, "inactive_seconds": 90, "scroll_count": 3},
            "insufficient_scroll_evidence",
        ),
        (
            {
                "trigger_present": False,
                "inactive_seconds": 90,
                "scroll_count": 6,
                "importance_passed": False,
            },
            "importance_gate_failed",
        ),
        (
            {"trigger_present": True, "existing_pending_task": True},
            "existing_pending_task",
        ),
        (
            {"trigger_present": True, "daily_sent_count": 2, "daily_send_limit": 2},
            "daily_limit_reached",
        ),
    ],
)
def test_proactive_preflight_returns_stable_block_reasons(kwargs, reason):
    result = compeer.evaluate_proactive_preflight(**kwargs)

    assert result.eligible is False
    assert result.block_reason == reason


def test_proactive_preflight_allows_explicit_and_behavior_triggers():
    explicit = compeer.evaluate_proactive_preflight(trigger_present=True)
    behavior = compeer.evaluate_proactive_preflight(
        trigger_present=False,
        inactive_seconds=90,
        scroll_count=6,
        importance_passed=True,
    )

    assert explicit.eligible is True
    assert behavior.eligible is True


def test_preflight_log_contains_only_safe_metadata(caplog):
    result = compeer.evaluate_proactive_preflight(
        trigger_present=False,
        inactive_seconds=90,
        scroll_count=2,
    )

    with caplog.at_level("INFO"):
        compeer._log_proactive_preflight("user-1", "iteration-1", result)

    assert "compeer.preflight_evaluated" in caplog.text
    assert "iteration_id=iteration-1" in caplog.text
    assert "reason=insufficient_scroll_evidence" in caplog.text
    assert "event_summary" not in caplog.text
    assert "content=" not in caplog.text


def test_preflight_log_includes_cooldown_remaining_seconds(caplog):
    result = compeer.evaluate_proactive_preflight(
        trigger_present=False,
        cooldown_active=True,
        inactive_seconds=90,
        cooldown_remaining_seconds=1732,
    )

    with caplog.at_level("INFO"):
        compeer._log_proactive_preflight("user-1", "iteration-1", result)

    assert "cooldown_remaining_seconds=1732" in caplog.text
    assert "reason=cooldown_active" in caplog.text


def test_empty_absent_trigger_preflight_is_debug_noise(caplog):
    result = compeer.evaluate_proactive_preflight(
        trigger_present=False,
        inactive_seconds=90,
        scroll_count=0,
    )

    with caplog.at_level("INFO"):
        compeer._log_proactive_preflight("user-1", "iteration-1", result)

    assert "compeer.preflight_evaluated" not in caplog.text
    assert "reason=absent_trigger" not in caplog.text

    caplog.clear()
    with caplog.at_level("DEBUG"):
        compeer._log_proactive_preflight("user-1", "iteration-1", result)

    assert "compeer.preflight_evaluated" in caplog.text
    assert "reason=absent_trigger" in caplog.text


@pytest.mark.asyncio
async def test_scheduler_isolates_each_user_failure(caplog):
    store = MagicMock()
    store.redis = AsyncMock()
    store.redis.scan = AsyncMock(
        return_value=(0, ["areqa:hot_memory:user-a", "areqa:hot_memory:user-b"])
    )
    processed = []

    async def process_user(_store, user_id):
        processed.append(user_id)
        if user_id == "user-a":
            raise ConnectionError("redis unavailable")

    with patch("memory_store.get_global_store", return_value=store), patch.object(
        compeer,
        "_process_proactive_user",
        side_effect=process_user,
    ), patch.object(
        compeer.asyncio,
        "sleep",
        new=AsyncMock(side_effect=RuntimeError("stop loop")),
    ):
        with pytest.raises(RuntimeError, match="stop loop"):
            await compeer.proactive_scheduler_loop()

    assert processed == ["user-a", "user-b"]
    assert "compeer.user_iteration_failed user_id=user-a" in caplog.text

@pytest.mark.asyncio
async def test_is_in_cooldown_false_when_no_entry():
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0
        mock_get_redis.return_value = mock_redis
        
        assert await compeer.is_in_cooldown("default_user") is False

@pytest.mark.asyncio
async def test_is_in_cooldown_true_within_period():
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1
        mock_get_redis.return_value = mock_redis
        
        assert await compeer.is_in_cooldown("default_user") is True


@pytest.mark.asyncio
async def test_get_cooldown_remaining_seconds_returns_active_ttl():
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.ttl.return_value = 123
        mock_get_redis.return_value = mock_redis

        assert await compeer.get_cooldown_remaining_seconds("default_user") == 123


@pytest.mark.asyncio
async def test_get_cooldown_remaining_seconds_returns_none_when_inactive():
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.ttl.return_value = -2
        mock_get_redis.return_value = mock_redis

        assert await compeer.get_cooldown_remaining_seconds("default_user") is None


@pytest.mark.asyncio
async def test_clear_cooldown_deletes_key():
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.delete.return_value = 1
        mock_get_redis.return_value = mock_redis

        assert await compeer.clear_cooldown("default_user") is True
        mock_redis.delete.assert_awaited_once_with("areqa:cooldown:default_user")


@pytest.mark.asyncio
async def test_daily_proactive_limit_detects_reached_limit(monkeypatch):
    monkeypatch.setattr(settings, "compeer_daily_proactive_limit", 2)
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "2"
        mock_get_redis.return_value = mock_redis

        reached, sent_count, limit = await compeer.has_reached_daily_proactive_limit("default_user")

    assert reached is True
    assert sent_count == 2
    assert limit == 2


@pytest.mark.asyncio
async def test_record_daily_proactive_send_sets_expiry_on_first_send():
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        mock_get_redis.return_value = mock_redis

        count = await compeer.record_daily_proactive_send("default_user")

    assert count == 1
    mock_redis.incr.assert_awaited_once()
    mock_redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_cooldown_stores_correct_timestamp(mock_store):
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        
        await compeer.set_cooldown("default_user", state="default")
        
        mock_redis.setex.assert_called_once()
        mock_store.update_hot_memory_async.assert_called_once()


@pytest.mark.asyncio
async def test_set_cooldown_uses_configured_override_seconds(mock_store, monkeypatch):
    monkeypatch.setattr(settings, "compeer_cooldown_override_seconds", 7)
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await compeer.set_cooldown("default_user", state="STARTING")

        mock_redis.setex.assert_awaited_once_with(
            "areqa:cooldown:default_user",
            7,
            "1",
        )


@pytest.mark.asyncio
async def test_set_cooldown_zero_override_clears_key(mock_store, monkeypatch):
    monkeypatch.setattr(settings, "compeer_cooldown_override_seconds", 0)
    with patch("backend.services.compeer_scheduler.get_redis") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await compeer.set_cooldown("default_user", state="STARTING")

        mock_redis.delete.assert_awaited_once_with("areqa:cooldown:default_user")
        mock_redis.setex.assert_not_called()
        mock_store.update_hot_memory_async.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_importance_gate_passes_high_importance():
    event = {"importance": 0.999}
    passes = 0
    for _ in range(100):
        if await compeer.evaluate_importance_gate(event):
            passes += 1
    assert passes > 90

@pytest.mark.asyncio
async def test_evaluate_importance_gate_fails_low_importance():
    event = {"importance": 0.0}
    for _ in range(10):
        assert await compeer.evaluate_importance_gate(event) is False

@pytest.fixture
def mock_store():
    store = MagicMock()
    # Provide an in-memory dictionary to simulate get_hot_memory
    hot_mem_data = {}
    behavior_signals = []
    
    async def mock_get_hot_memory(user_id):
        return hot_mem_data
        
    async def mock_update_hot_memory(user_id, key, value, **policy):
        hot_mem_data[key] = value

    async def mock_get_behavior_signals(user_id):
        return list(behavior_signals)

    async def mock_consume_behavior_signals(user_id, consumed):
        removed = 0
        for item in consumed:
            if item in behavior_signals:
                behavior_signals.remove(item)
                removed += 1
        return removed
        
    store.get_hot_memory = AsyncMock(side_effect=mock_get_hot_memory)
    store.update_hot_memory = AsyncMock(side_effect=mock_update_hot_memory)
    store.update_hot_memory_async = AsyncMock(side_effect=mock_update_hot_memory)
    store.get_behavior_signals = AsyncMock(side_effect=mock_get_behavior_signals)
    store.consume_behavior_signals = AsyncMock(side_effect=mock_consume_behavior_signals)
    store.behavior_signals = behavior_signals
    store.get_user_profile = AsyncMock(return_value={})
    store.get_working_memory = AsyncMock(return_value={})
    
    # Add these mock methods for Redis and strategy compatibility
    store.get_current_strategy = AsyncMock(return_value="default")
    store.get_learner_state = AsyncMock(return_value="STARTING")
    
    store.redis = AsyncMock()
    store.redis.scan = AsyncMock(return_value=(0, ["areqa:hot_memory:default_user"]))
    store.redis.set = AsyncMock()
    store.redis.get = AsyncMock(return_value="0")
    store.redis.incr = AsyncMock(return_value=1)
    store.redis.expire = AsyncMock()
    
    with patch("memory_store.get_global_store", return_value=store), patch(
        "backend.services.compeer_scheduler.get_redis", return_value=store.redis
    ):
        yield store

def test_topic_specific_care_requires_working_memory_by_default():
    assert compeer.should_allow_topic_specific_care("", "User stuck on poem") is False


def test_topic_specific_care_can_trust_scheduled_event_summary():
    assert compeer.should_allow_topic_specific_care(
        "",
        "使用者正在整理 README.md 的架構描述",
        trust_event_summary=True,
    ) is True


@pytest.mark.asyncio
async def test_safe_schedule_retains_trigger_on_durable_failure(mock_store):
    await mock_store.update_hot_memory("default_user", "trigger_proactive", True)

    with patch.object(
        compeer,
        "schedule_areqa_care_letter",
        new_callable=AsyncMock,
        side_effect=RuntimeError("database unavailable"),
    ):
        task_id = await compeer._schedule_areqa_care_letter_safely(
            user_id="default_user",
            learner_state="STARTING",
            edf_policy="NORMAL",
            event_summary="event",
            hot_memory_snapshot="",
            cold_memory_context="",
        )

    hot_memory = await mock_store.get_hot_memory("default_user")
    assert task_id is None
    assert hot_memory["trigger_proactive"] is True
    assert hot_memory["compeer_retry_reason"] == "RuntimeError"
    assert hot_memory["compeer_next_attempt_at"] > time.time()

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.asyncio.sleep", new_callable=AsyncMock)
@patch("mailbox_store.get_mailbox_store")
@patch("gum_integration.generate_areqa_care_letter_via_llm", new_callable=AsyncMock)
@patch("gum_integration.query_cold_memory_for_context", new_callable=AsyncMock)
@patch("backend.services.compeer_scheduler.is_in_cooldown", new_callable=AsyncMock)
async def test_trigger_proactive_schedules_areqa_care_mail(mock_in_cooldown, mock_query, mock_gen, mock_get_mailbox, mock_sleep, mock_store):
    # Setup hot memory with trigger_proactive = True
    await mock_store.update_hot_memory("default_user", "trigger_proactive", True)
    await mock_store.update_hot_memory("default_user", "current_learner_state", "GIVING_UP")
    
    mock_mailbox = MagicMock()
    mock_mailbox.schedule_delayed_mail = AsyncMock()
    mock_get_mailbox.return_value = mock_mailbox
    mock_gen.return_value = ("給你的學習小箋", "Test Care Letter")
    mock_query.return_value = "Mocked cold context"
    mock_in_cooldown.return_value = False
    
    # We want proactive_scheduler_loop to run one iteration and then raise an exception to exit the infinite loop
    # In compeer_scheduler, there are two sleeps. We side_effect both.
    mock_sleep.side_effect = [None, Exception("Stop Loop"), Exception("Stop Loop")]
    
    with pytest.raises(Exception, match="Stop Loop"):
        await compeer.proactive_scheduler_loop()

    # Yield to event loop to allow asyncio.create_task to execute
    for _ in range(5):
        await mock_store.update_hot_memory("default_user", "dummy", True)
        
    hot_mem = await mock_store.get_hot_memory("default_user")
    assert "trigger_proactive" not in hot_mem
    mock_mailbox.schedule_delayed_mail.assert_awaited_once()
    call_kwargs = mock_mailbox.schedule_delayed_mail.call_args.kwargs
    assert call_kwargs["user_id"] == "default_user"
    assert call_kwargs["mail_data"]["kind"] == "compeer_care"
    assert call_kwargs["mail_data"]["sender"] == "AREQA"
    assert call_kwargs["mail_data"]["content"] == "Test Care Letter"
    mock_query.assert_not_awaited()
    mock_gen.assert_awaited_once()
    assert mock_gen.call_args.kwargs["allow_topic_specific"] is False
    assert mock_gen.call_args.kwargs["cold_memory_context"] == ""

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.asyncio.sleep", new_callable=AsyncMock)
@patch("mailbox_store.get_mailbox_store")
@patch("gum_integration.generate_areqa_care_letter_via_llm", new_callable=AsyncMock)
@patch("gum_integration.query_cold_memory_for_context", new_callable=AsyncMock)
@patch("gum_integration.get_hot_memory_snapshot", new_callable=AsyncMock)
@patch("backend.services.compeer_scheduler.is_in_cooldown", new_callable=AsyncMock)
async def test_trigger_proactive_allows_topic_specific_care_with_current_focus(
    mock_in_cooldown,
    mock_snapshot,
    mock_query,
    mock_gen,
    mock_get_mailbox,
    mock_sleep,
    mock_store,
):
    await mock_store.update_hot_memory("default_user", "trigger_proactive", True)
    await mock_store.update_hot_memory("default_user", "current_learner_state", "GIVING_UP")

    mock_mailbox = MagicMock()
    mock_mailbox.schedule_delayed_mail = AsyncMock()
    mock_get_mailbox.return_value = mock_mailbox
    mock_snapshot.return_value = "【工作記憶 (Working Memory)】\n- Current focus: README.md 更新"
    mock_query.return_value = "Mocked cold context"
    mock_gen.return_value = ("給你的學習小箋", "Specific Care Letter")
    mock_in_cooldown.return_value = False
    mock_sleep.side_effect = [None, Exception("Stop Loop"), Exception("Stop Loop")]

    with pytest.raises(Exception, match="Stop Loop"):
        await compeer.proactive_scheduler_loop()

    mock_query.assert_awaited_once()
    mock_gen.assert_awaited_once()
    assert mock_gen.call_args.kwargs["allow_topic_specific"] is True
    assert mock_gen.call_args.kwargs["cold_memory_context"] == "Mocked cold context"

@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.asyncio.sleep", new_callable=AsyncMock)
@patch("backend.services.compeer_scheduler.is_in_cooldown", new_callable=AsyncMock)
async def test_no_trigger_when_in_cooldown(mock_in_cooldown, mock_sleep, mock_store):
    await mock_store.update_hot_memory("default_user", "trigger_proactive", True)
    mock_in_cooldown.return_value = True
    
    mock_sleep.side_effect = [None, Exception("Stop Loop"), Exception("Stop Loop")]
    
    with pytest.raises(Exception, match="Stop Loop"):
        await compeer.proactive_scheduler_loop()
        
    # Since in cooldown, shouldn't consume trigger or broadcast
    hot_mem = await mock_store.get_hot_memory("default_user")
    assert "trigger_proactive" in hot_mem

def test_avatar_summon_preflight_bypasses_cooldown():
    result = compeer.evaluate_proactive_preflight(
        trigger_present=False,
        avatar_pending=True,
        cooldown_active=True,
    )

    assert result.eligible is True
    assert result.block_reason is None


def _recent_scroll_signals(count: int):
    """Build recent scroll signals that match MemoryStore behavior telemetry."""

    timestamp = datetime.now(timezone.utc).isoformat()
    return [
        {
            "type": "scroll",
            "context": {"scrollY": 100 + index},
            "weight": 0.2,
            "timestamp": timestamp,
        }
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_behavior_signals_schedule_proactive_mail_without_legacy_obs(mock_store, caplog):
    mock_store.behavior_signals.extend(_recent_scroll_signals(6))
    mock_store.behavior_signals[0]["context"] = {"raw_user_text": "SECRET_CONTEXT"}
    scheduled = AsyncMock(return_value="task-1")

    with patch.object(
        compeer,
        "get_last_interaction_time",
        new=AsyncMock(return_value=time.time() - 120),
    ), patch.object(
        compeer,
        "is_in_cooldown",
        new=AsyncMock(return_value=False),
    ), patch.object(
        compeer,
        "tick_proactive_schedule",
        new=AsyncMock(),
    ), patch(
        "gum_integration.get_hot_memory_snapshot",
        new=AsyncMock(return_value="【工作記憶 (Working Memory)】\n- Current focus: force"),
    ), patch(
        "gum_integration.detect_proactive_event_via_llm",
        new=AsyncMock(
            return_value={
                "has_event": True,
                "importance": 0.9,
                "event_summary": "User paused while reviewing force.",
            }
        ),
    ), patch(
        "gum_integration.query_cold_memory_for_context",
        new=AsyncMock(return_value=""),
    ), patch.object(
        compeer,
        "_schedule_areqa_care_letter_safely",
        new=scheduled,
    ), patch.object(
        compeer,
        "set_cooldown",
        new=AsyncMock(),
    ):
        with caplog.at_level("INFO"):
            await compeer._process_proactive_user(mock_store, "default_user")

    scheduled.assert_awaited_once()
    mock_store.consume_behavior_signals.assert_awaited_once()
    hot_memory = await mock_store.get_hot_memory("default_user")
    assert not [key for key in hot_memory if key.startswith("obs_")]
    assert "compeer.behavior_signals_evaluated" in caplog.text
    assert "compeer.behavior_trigger_eligible" in caplog.text
    assert "compeer.behavior_signals_consumed" in caplog.text
    assert "signal_source=behavior_signals" in caplog.text
    assert "recent_scroll_count=6" in caplog.text
    assert "delivery_delay_seconds=120" in caplog.text
    assert "task_id=task-1" in caplog.text
    assert "SECRET_CONTEXT" not in caplog.text


@pytest.mark.asyncio
async def test_behavior_signals_do_not_schedule_after_daily_limit(mock_store, caplog, monkeypatch):
    monkeypatch.setattr(settings, "compeer_daily_proactive_limit", 2)
    mock_store.redis.get.return_value = "2"
    mock_store.behavior_signals.extend(_recent_scroll_signals(6))
    scheduled = AsyncMock(return_value="task-1")

    with patch.object(
        compeer,
        "get_last_interaction_time",
        new=AsyncMock(return_value=time.time() - 120),
    ), patch.object(
        compeer,
        "is_in_cooldown",
        new=AsyncMock(return_value=False),
    ), patch.object(
        compeer,
        "tick_proactive_schedule",
        new=AsyncMock(),
    ), patch(
        "gum_integration.detect_proactive_event_via_llm",
        new=AsyncMock(),
    ) as detect_event, patch.object(
        compeer,
        "_schedule_areqa_care_letter_safely",
        new=scheduled,
    ):
        with caplog.at_level("INFO"):
            await compeer._process_proactive_user(mock_store, "default_user")

    scheduled.assert_not_awaited()
    detect_event.assert_not_awaited()
    mock_store.consume_behavior_signals.assert_not_awaited()
    assert "reason=daily_limit_reached" in caplog.text
    assert "daily_sent_count=2" in caplog.text
    assert "daily_send_limit=2" in caplog.text


@pytest.mark.asyncio
async def test_behavior_signals_below_threshold_do_not_schedule(mock_store, caplog):
    mock_store.behavior_signals.extend(_recent_scroll_signals(5))
    scheduled = AsyncMock(return_value="task-1")

    with patch.object(
        compeer,
        "get_last_interaction_time",
        new=AsyncMock(return_value=time.time() - 120),
    ), patch.object(
        compeer,
        "is_in_cooldown",
        new=AsyncMock(return_value=False),
    ), patch.object(
        compeer,
        "tick_proactive_schedule",
        new=AsyncMock(),
    ), patch.object(
        compeer,
        "_schedule_areqa_care_letter_safely",
        new=scheduled,
    ):
        with caplog.at_level("INFO"):
            await compeer._process_proactive_user(mock_store, "default_user")

    scheduled.assert_not_awaited()
    mock_store.consume_behavior_signals.assert_not_awaited()
    assert "compeer.behavior_signals_evaluated" in caplog.text
    assert "signal_source=behavior_signals" in caplog.text
    assert "recent_scroll_count=5" in caplog.text
    assert "reason=insufficient_scroll_evidence" in caplog.text


@pytest.mark.asyncio
async def test_empty_behavior_polling_is_debug_noise(mock_store, caplog):
    scheduled = AsyncMock(return_value="task-1")

    with patch.object(
        compeer,
        "get_last_interaction_time",
        new=AsyncMock(return_value=time.time() - 120),
    ), patch.object(
        compeer,
        "is_in_cooldown",
        new=AsyncMock(return_value=False),
    ), patch.object(
        compeer,
        "tick_proactive_schedule",
        new=AsyncMock(),
    ), patch.object(
        compeer,
        "_schedule_areqa_care_letter_safely",
        new=scheduled,
    ):
        with caplog.at_level("INFO"):
            await compeer._process_proactive_user(mock_store, "default_user")

    scheduled.assert_not_awaited()
    assert "compeer.behavior_signals_evaluated" not in caplog.text
    assert "reason=absent_trigger" not in caplog.text


@pytest.mark.asyncio
async def test_malformed_behavior_signal_timestamps_do_not_count_or_crash(mock_store):
    mock_store.behavior_signals.extend(
        [
            {"type": "scroll", "context": {"secret": "must-not-log"}, "timestamp": "not-a-date"},
            {
                "type": "scroll",
                "context": {"scrollY": 1},
                "timestamp": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            },
        ]
    )
    scheduled = AsyncMock(return_value="task-1")

    with patch.object(
        compeer,
        "get_last_interaction_time",
        new=AsyncMock(return_value=time.time() - 120),
    ), patch.object(
        compeer,
        "is_in_cooldown",
        new=AsyncMock(return_value=False),
    ), patch.object(
        compeer,
        "tick_proactive_schedule",
        new=AsyncMock(),
    ), patch.object(
        compeer,
        "_schedule_areqa_care_letter_safely",
        new=scheduled,
    ):
        await compeer._process_proactive_user(mock_store, "default_user")

    scheduled.assert_not_awaited()
    mock_store.consume_behavior_signals.assert_not_awaited()


@pytest.mark.asyncio
async def test_behavior_trigger_rejection_logs_safe_reason(mock_store, caplog):
    mock_store.behavior_signals.extend(_recent_scroll_signals(6))
    scheduled = AsyncMock(return_value="task-1")

    with patch.object(
        compeer,
        "get_last_interaction_time",
        new=AsyncMock(return_value=time.time() - 120),
    ), patch.object(
        compeer,
        "is_in_cooldown",
        new=AsyncMock(return_value=False),
    ), patch.object(
        compeer,
        "tick_proactive_schedule",
        new=AsyncMock(),
    ), patch(
        "gum_integration.get_hot_memory_snapshot",
        new=AsyncMock(return_value="【工作記憶 (Working Memory)】\n- Current focus: force"),
    ), patch(
        "gum_integration.detect_proactive_event_via_llm",
        new=AsyncMock(
            return_value={
                "has_event": False,
                "importance": 0.0,
                "event_summary": "SECRET_EVENT_SUMMARY",
            }
        ),
    ), patch.object(
        compeer,
        "_schedule_areqa_care_letter_safely",
        new=scheduled,
    ):
        with caplog.at_level("INFO"):
            await compeer._process_proactive_user(mock_store, "default_user")

    scheduled.assert_not_awaited()
    mock_store.consume_behavior_signals.assert_not_awaited()
    assert "compeer.behavior_trigger_rejected" in caplog.text
    assert "reason=importance_gate_failed" in caplog.text
    assert "SECRET_EVENT_SUMMARY" not in caplog.text
