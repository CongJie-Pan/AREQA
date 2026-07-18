"""
ComPeer Scheduler Module.

This module provides background loops and scheduling services for the proactive 
ComPeer system. It manages user cooldown periods, schedules daily reflection 
and proactive care tasks, and dispatches delayed "letters" (messages) to the user 
based on learning states, behavioral telemetry (e.g., scrolling), or explicit 
avatar summons.
"""

import asyncio
import json
import logging
import os
import random
import hashlib
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time as _time

from redis_client import get_redis
from services.hot_memory_service import remove_typed_entry


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProactivePreflight:
    """Describe one proactive scheduling decision using safe metadata only.

    The task ID is the correlation boundary between scheduler and mailbox
    events. Raw hot-memory values, event summaries, and generated mail content
    are intentionally excluded from this result.
    """

    trigger_present: bool
    avatar_pending: bool
    cooldown_active: bool
    inactive_seconds: float | None = None
    scroll_count: int = 0
    signal_source: str = "not_evaluated"
    behavior_signal_count: int = 0
    recent_scroll_count: int = 0
    legacy_scroll_count: int = 0
    delivery_delay_seconds: int | None = None
    cooldown_remaining_seconds: int | None = None
    daily_sent_count: int | None = None
    daily_send_limit: int | None = None
    importance_passed: bool | None = None
    existing_pending_task: bool = False
    scheduling_succeeded: bool | None = None
    task_id: str | None = None
    block_reason: str | None = None

    @property
    def eligible(self) -> bool:
        """Return whether the preflight permits a scheduling attempt."""

        return self.block_reason is None


def evaluate_proactive_preflight(
    *,
    trigger_present: bool,
    avatar_pending: bool = False,
    cooldown_active: bool = False,
    inactive_seconds: float | None = None,
    scroll_count: int = 0,
    signal_source: str = "not_evaluated",
    behavior_signal_count: int = 0,
    recent_scroll_count: int = 0,
    legacy_scroll_count: int = 0,
    delivery_delay_seconds: int | None = None,
    cooldown_remaining_seconds: int | None = None,
    daily_sent_count: int | None = None,
    daily_send_limit: int | None = None,
    importance_passed: bool | None = None,
    existing_pending_task: bool = False,
) -> ProactivePreflight:
    """Evaluate proactive eligibility once without reading or writing user data.

    Explicit avatar summons bypass the ordinary cooldown. Explicit proactive
    triggers bypass inactivity and scroll gates. Behaviour-derived scheduling
    fails closed when its required evidence or importance decision is absent.
    Signal counters and delivery delay are safe observability metadata; they do
    not affect the decision reason.
    """

    reason = None
    if existing_pending_task:
        reason = "existing_pending_task"
    elif avatar_pending:
        reason = None
    elif (
        daily_send_limit is not None
        and daily_send_limit >= 0
        and daily_sent_count is not None
        and daily_sent_count >= daily_send_limit
    ):
        reason = "daily_limit_reached"
    elif cooldown_active:
        reason = "cooldown_active"
    elif trigger_present:
        reason = None
    elif inactive_seconds is not None and inactive_seconds <= 60:
        reason = "inactivity_threshold"
    elif scroll_count == 0:
        reason = "absent_trigger"
    elif scroll_count < 6:
        reason = "insufficient_scroll_evidence"
    elif importance_passed is not True:
        reason = "importance_gate_failed"

    return ProactivePreflight(
        trigger_present=trigger_present,
        avatar_pending=avatar_pending,
        cooldown_active=cooldown_active,
        inactive_seconds=inactive_seconds,
        scroll_count=scroll_count,
        signal_source=signal_source,
        behavior_signal_count=behavior_signal_count,
        recent_scroll_count=recent_scroll_count,
        legacy_scroll_count=legacy_scroll_count,
        delivery_delay_seconds=delivery_delay_seconds,
        cooldown_remaining_seconds=cooldown_remaining_seconds,
        daily_sent_count=daily_sent_count,
        daily_send_limit=daily_send_limit,
        importance_passed=importance_passed,
        existing_pending_task=existing_pending_task,
        block_reason=reason,
    )


def _log_proactive_preflight(
    user_id: str,
    iteration_id: str,
    preflight: ProactivePreflight,
) -> None:
    """Emit the allowlisted result of one scheduler preflight.

    Ordinary idle polling for users with no usable trigger is intentionally
    debug-level noise. INFO is reserved for actionable states: visible evidence,
    eligibility, scheduling, cooldown, failures, or non-empty behavior signals.
    """

    log_level = logging.INFO
    if (
        preflight.block_reason in {"absent_trigger", "inactivity_threshold"}
        and preflight.scroll_count == 0
        and not preflight.trigger_present
        and not preflight.avatar_pending
        and not preflight.existing_pending_task
        and preflight.scheduling_succeeded is None
    ):
        log_level = logging.DEBUG

    logger.log(
        log_level,
        "compeer.preflight_evaluated user_id=%s iteration_id=%s "
        "trigger_present=%s avatar_pending=%s cooldown_active=%s "
        "inactive_seconds=%s scroll_count=%s importance_passed=%s "
        "signal_source=%s behavior_signal_count=%s recent_scroll_count=%s "
        "legacy_scroll_count=%s delivery_delay_seconds=%s "
        "cooldown_remaining_seconds=%s daily_sent_count=%s daily_send_limit=%s "
        "existing_pending_task=%s scheduling_succeeded=%s task_id=%s",
        user_id,
        iteration_id,
        preflight.trigger_present,
        preflight.avatar_pending,
        preflight.cooldown_active,
        (
            round(preflight.inactive_seconds, 3)
            if preflight.inactive_seconds is not None
            else "not_evaluated"
        ),
        preflight.scroll_count,
        preflight.importance_passed,
        preflight.signal_source,
        preflight.behavior_signal_count,
        preflight.recent_scroll_count,
        preflight.legacy_scroll_count,
        (
            preflight.delivery_delay_seconds
            if preflight.delivery_delay_seconds is not None
            else "not_evaluated"
        ),
        (
            preflight.cooldown_remaining_seconds
            if preflight.cooldown_remaining_seconds is not None
            else "not_evaluated"
        ),
        (
            preflight.daily_sent_count
            if preflight.daily_sent_count is not None
            else "not_evaluated"
        ),
        (
            preflight.daily_send_limit
            if preflight.daily_send_limit is not None
            else "not_evaluated"
        ),
        preflight.existing_pending_task,
        preflight.scheduling_succeeded,
        preflight.task_id or "none",
    )
    if preflight.block_reason:
        logger.log(
            log_level,
            "compeer.preflight_blocked user_id=%s iteration_id=%s reason=%s "
            "cooldown_remaining_seconds=%s daily_sent_count=%s daily_send_limit=%s",
            user_id,
            iteration_id,
            preflight.block_reason,
            (
                preflight.cooldown_remaining_seconds
                if preflight.cooldown_remaining_seconds is not None
                else "not_evaluated"
            ),
            (
                preflight.daily_sent_count
                if preflight.daily_sent_count is not None
                else "not_evaluated"
            ),
            (
                preflight.daily_send_limit
                if preflight.daily_send_limit is not None
                else "not_evaluated"
            ),
        )


async def _clear_persisted_trigger(store, user_id: str, trigger_key: str) -> None:
    """Clear a trigger only after its delayed-mail intent is durable."""

    async with _flag_lock:
        hot_memory = await store.get_hot_memory(user_id)
        if not hot_memory.get(trigger_key):
            return
        remove_typed_entry(hot_memory, trigger_key)
        await store.redis.set(
            f"areqa:hot_memory:{user_id}",
            json.dumps(hot_memory, ensure_ascii=False),
        )
    logger.info(
        "compeer.trigger_cleared user_id=%s trigger=%s reason=durable_task_created",
        user_id,
        trigger_key,
    )

async def is_in_cooldown(user_id: str) -> bool:
    """
    Check if the user is currently within a proactive communication cooldown period.

    Args:
        user_id (str): The unique identifier for the user.

    Returns:
        bool: True if the user is in cooldown, False otherwise.
    """
    redis = get_redis()
    return await redis.exists(f"areqa:cooldown:{user_id}") > 0


async def get_cooldown_remaining_seconds(user_id: str) -> int | None:
    """Return the Redis TTL for the ComPeer cooldown key, if it is active."""

    redis = get_redis()
    ttl = await redis.ttl(f"areqa:cooldown:{user_id}")
    return ttl if ttl is not None and ttl >= 0 else None


async def clear_cooldown(user_id: str) -> bool:
    """Clear a user's ComPeer cooldown key for development/manual testing."""

    redis = get_redis()
    deleted = await redis.delete(f"areqa:cooldown:{user_id}")
    logger.info(
        "compeer.cooldown_cleared user_id=%s deleted=%s",
        user_id,
        bool(deleted),
    )
    return bool(deleted)


def _compeer_daily_counter_key(user_id: str, now: datetime | None = None) -> str:
    """Return the UTC daily proactive-mail counter key for a user."""

    current = now or datetime.now(timezone.utc)
    return f"areqa:compeer_daily_count:{current.strftime('%Y-%m-%d')}:{user_id}"


def _seconds_until_next_utc_day(now: datetime | None = None) -> int:
    """Return seconds until the next UTC day boundary."""

    current = now or datetime.now(timezone.utc)
    next_day = current.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(1, int((next_day - current).total_seconds()))


async def get_daily_proactive_sent_count(user_id: str) -> int:
    """Return how many ComPeer proactive mails have been scheduled today."""

    redis = get_redis()
    value = await redis.get(_compeer_daily_counter_key(user_id))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def has_reached_daily_proactive_limit(user_id: str) -> tuple[bool, int, int]:
    """Return whether the user has reached the configured daily ComPeer limit."""

    from config import settings

    limit = settings.compeer_daily_proactive_limit
    sent_count = await get_daily_proactive_sent_count(user_id)
    if limit < 0:
        return False, sent_count, limit
    return sent_count >= limit, sent_count, limit


async def record_daily_proactive_send(user_id: str) -> int:
    """Increment the user's UTC daily proactive-mail counter after durable scheduling."""

    redis = get_redis()
    key = _compeer_daily_counter_key(user_id)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _seconds_until_next_utc_day())
    logger.info(
        "compeer.daily_send_recorded user_id=%s daily_sent_count=%s",
        user_id,
        count,
    )
    return int(count)


async def set_cooldown(user_id: str, state: str = "default") -> None:
    """
    Set a communication cooldown period dynamically based on the current learner state.

    Args:
        user_id (str): The unique identifier for the user.
        state (str): The current pedagogical state of the learner. Defaults to "default".
    """
    COOLDOWN_BY_STATE = {
        "NOT_STARTED": 2.0,
        "GIVING_UP": 0.25,
        "STARTING": 1.0,
        "TINKERING": 0.5,
        "MASTERY": 2.0,
        "default": 0.5
    }
    hours = COOLDOWN_BY_STATE.get(state, COOLDOWN_BY_STATE["default"])
    expire_seconds = int(hours * 3600)
    from config import settings

    if settings.compeer_cooldown_override_seconds is not None:
        expire_seconds = max(0, settings.compeer_cooldown_override_seconds)
    
    redis = get_redis()
    if expire_seconds <= 0:
        await redis.delete(f"areqa:cooldown:{user_id}")
        logger.info(
            "compeer.cooldown_set user_id=%s learner_state=%s "
            "cooldown_seconds=%s override_active=%s action=cleared",
            user_id,
            state,
            expire_seconds,
            True,
        )
        return

    await redis.setex(f"areqa:cooldown:{user_id}", expire_seconds, "1")
    logger.info(
        "compeer.cooldown_set user_id=%s learner_state=%s "
        "cooldown_seconds=%s override_active=%s",
        user_id,
        state,
        expire_seconds,
        settings.compeer_cooldown_override_seconds is not None,
    )
    
    # Also persist to hot_memory
    from memory_store import get_global_store
    store = get_global_store()
    if store:
        try:
            expire_time = _time.time() + expire_seconds
            await store.update_hot_memory_async(user_id, "user_cooldown_until", expire_time)
        except Exception as e:
            print(f"[EDF-LOG] Error setting cooldown in hot memory: {e}")

async def evaluate_importance_gate(event: dict) -> bool:
    """
    Determine probabilistically whether an event should trigger based on its importance.

    Args:
        event (dict): The event dictionary containing an 'importance' score.

    Returns:
        bool: True if the event passes the gate, False otherwise.
    """
    importance = float(event.get("importance", 0.5))
    passed = random.random() < importance
    logger.info(
        "compeer.importance_evaluated importance=%s passed=%s",
        importance,
        passed,
    )
    return passed

async def tick_proactive_schedule(user_id: str):
    """
    Evaluate and trigger scheduled proactive care events for a user if their time has arrived.

    Args:
        user_id (str): The unique identifier for the user.
    """
    project_root = Path(__file__).resolve().parents[2]
    schedule_path = project_root / "data" / "gum_data" / f"schedule_{user_id}.json"
    
    if not os.path.exists(schedule_path):
        return
        
    try:
        with open(schedule_path, "r", encoding="utf-8") as f:
            events = json.load(f)
    except Exception:
        return
        
    now_dt = datetime.now()
    changed = False
    
    for event in events:
        if event.get("fired", False):
            continue
            
        timing_str = event.get("Timing", "")
        if not timing_str:
            continue
            
        try:
            event_time = datetime.strptime(timing_str, "%H:%M").time()
        except ValueError:
            continue
            
        event_dt = datetime.combine(now_dt.date(), event_time)
        
        # 2-minute window
        if abs((now_dt - event_dt).total_seconds()) <= 120:
            if not await is_in_cooldown(user_id):
                passed = await evaluate_importance_gate(event)
                if passed:
                    from memory_store import get_global_store
                    store = get_global_store()
                    if store:
                        content = event.get("Content", "學習狀況還好嗎？")
                        logger.info(
                            "compeer.legacy_schedule_due user_id=%s",
                            user_id,
                        )
                        learner_state = await store.get_learner_state(user_id) if store else "default"
                        edf_policy = await store.get_current_strategy(user_id) if store else "default"
                        from gum_integration import get_hot_memory_snapshot, query_cold_memory_for_context
                        snapshot = await get_hot_memory_snapshot(user_id)
                        allow_topic_specific = should_allow_topic_specific_care(
                            snapshot,
                            content,
                            trust_event_summary=True,
                        )
                        cold_ctx = await query_cold_memory_for_context(user_id, content) if allow_topic_specific else ""
                        hot_mem = await store.get_hot_memory(user_id)
                        task_id = await schedule_areqa_care_letter(
                            user_id=user_id,
                            learner_state=learner_state,
                            edf_policy=edf_policy,
                            event_summary=content,
                            hot_memory_snapshot=snapshot,
                            cold_memory_context=cold_ctx,
                            last_compeer_message=hot_mem.get("last_compeer_message", ""),
                            allow_topic_specific=allow_topic_specific,
                        )
                        if not task_id:
                            logger.warning(
                                "compeer.legacy_schedule_not_durable user_id=%s reason=missing_task_id",
                                user_id,
                            )
                            continue
                        await set_cooldown(user_id, state=learner_state)
                
            event["fired"] = True
            changed = True
            
    if changed:
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

async def initialize_daily_schedule(user_id: str, reflection_outputs: list):
    """
    Generate a daily proactive communication schedule based on the user's past reflections.

    Args:
        user_id (str): The unique identifier for the user.
        reflection_outputs (list): A list of insights generated from the previous day's reflections.
    """
    try:
        from gum_integration import get_gum_instance
        gum_instance, _ = await get_gum_instance(user_id)
        if not gum_instance:
            return
            
        prompt = f"""基於以下昨日的學習反思，請為學生規劃今日的主動關懷排程。
反思紀錄:
{reflection_outputs}

請嚴格回傳 JSON 格式...
"""
        from pydantic import BaseModel
        class ScheduleItem(BaseModel):
            Timing: str
            Content: str
            importance: float
        class ScheduleList(BaseModel):
            events: list[ScheduleItem]

        rsp = await gum_instance.client.chat.completions.create(
            model=gum_instance.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": "schedule", "schema": ScheduleList.model_json_schema()}},
            temperature=0.3
        )
        import re
        content = rsp.choices[0].message.content.strip()
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
        data = json.loads(content)
        events = data.get("events", [])
        
        project_root = Path(__file__).resolve().parents[2]
        schedule_path = project_root / "data" / "gum_data" / f"schedule_{user_id}.json"
        with open(schedule_path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"[Daily Schedule] Failed to initialize: {e}")

async def run_reflection_and_initialization(user_id: str):
    """
    Execute the reflection process for a user and initialize their schedule for the new day.

    Args:
        user_id (str): The unique identifier for the user.
    """
    try:
        from gum_integration import run_reflection
        insights = await run_reflection(user_id)

        if not insights:
            return

        await initialize_daily_schedule(user_id, insights)

    except Exception as e:
        print(f"[Daily Scheduler] run_reflection_and_initialization failed: {e}")

async def daily_scheduler_loop():
    """
    Background worker loop that runs daily reflections and schedule initialization 
    for all active users.
    """
    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            from memory_store import get_global_store
            store = get_global_store()
            if store:
                redis = store.redis
                cursor = 0
                all_users = set()
                while True:
                    cursor, keys = await redis.scan(cursor, match="areqa:hot_memory:*", count=100)
                    for key in keys:
                        k_str = key
                        all_users.add(k_str.split("areqa:hot_memory:")[1])
                    if cursor == 0:
                        break
                
                for user_id in all_users:
                    hot_mem = await store.get_hot_memory(user_id)
                    last_reflection = hot_mem.get("last_reflection_date")
                    
                    if last_reflection != today_str:
                        if now.hour >= 23 or last_reflection is None:
                            from gum_integration import run_reflection
                            insights = await run_reflection(user_id)
                            await store.update_hot_memory_async(
                                user_id,
                                "last_reflection_attempt_at",
                                now.isoformat(),
                            )
                            if insights:
                                await initialize_daily_schedule(user_id, insights)
                                await store.update_hot_memory_async(
                                    user_id,
                                    "last_reflection_date",
                                    today_str,
                                )
            
            await asyncio.sleep(60)
        except Exception as e:
            await asyncio.sleep(60)

_send_lock = asyncio.Lock()
_flag_lock = asyncio.Lock()

_GENERIC_EVENT_MARKERS = (
    "EDF 系統偵測到",
    "系統偵測到",
    "學習瓶頸",
    "低壓力關懷",
    "需要低壓力關懷",
)
PROACTIVE_SCROLL_SIGNAL_THRESHOLD = 6
PROACTIVE_SCROLL_SIGNAL_WINDOW_SECONDS = 15 * 60


def has_current_learning_evidence(hot_memory_snapshot: str) -> bool:
    """
    Check if there is current semantic learning evidence in the user's working memory.

    Args:
        hot_memory_snapshot (str): The current snapshot of the user's hot memory.

    Returns:
        bool: True if prompt-visible working memory has semantic content, False otherwise.
    """
    if not hot_memory_snapshot or "【工作記憶" not in hot_memory_snapshot:
        return False

    working_section = hot_memory_snapshot.split("【工作記憶", 1)[1]
    evidence_markers = (
        "Session summary:",
        "Current focus:",
        "Explicit memory:",
    )
    if any(marker in working_section for marker in evidence_markers):
        return True

    return any(line.strip().startswith("- ") and len(line.strip()) > 2 for line in working_section.splitlines())


def is_generic_event_summary(event_summary: str) -> bool:
    """
    Determine if an event summary is purely generic (e.g., generic system alerts) 
    rather than specific to a learning topic.

    Args:
        event_summary (str): The text of the event summary.

    Returns:
        bool: True if the summary is generic or empty, False otherwise.
    """
    text = (event_summary or "").strip()
    if not text:
        return True
    return any(marker in text for marker in _GENERIC_EVENT_MARKERS)


def should_allow_topic_specific_care(
    hot_memory_snapshot: str,
    event_summary: str,
    *,
    trust_event_summary: bool = False,
) -> bool:
    """
    Determine if a proactive care letter can reference specific learning topics.
    Cold memory alone must not authorize a specific proactive topic unless there 
    is current evidence or the event summary is explicitly trusted.

    Args:
        hot_memory_snapshot (str): The current snapshot of the user's hot memory.
        event_summary (str): The text of the event summary.
        trust_event_summary (bool): Whether to trust the event summary as specific context. Defaults to False.

    Returns:
        bool: True if topic-specific care is allowed, False otherwise.
    """
    if has_current_learning_evidence(hot_memory_snapshot):
        return True
    return trust_event_summary and not is_generic_event_summary(event_summary)


def _stable_task_id(prefix: str, user_id: str, *parts: str) -> str:
    """
    Generate a stable, deterministic task ID based on user and task parameters.

    Args:
        prefix (str): A string prefix for the task ID.
        user_id (str): The ID of the user.
        *parts (str): Additional strings to hash into the task ID.

    Returns:
        str: A unique SHA-256 based task ID string.
    """
    raw = "|".join([user_id, *[str(part or "") for part in parts]])
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _parse_behavior_signal_timestamp(signal: dict) -> float | None:
    """Return a UNIX timestamp for one behavior signal when it is trustworthy.

    ComPeer consumes UI telemetry from `behavior_signals` rather than hot
    memory so scroll events stay out of prompt-visible memory. Invalid or
    missing timestamps are ignored because a stale or malformed signal must not
    create a proactive message.

    Args:
        signal: A behavior-signal dictionary persisted by `MemoryStore`.

    Returns:
        A UNIX timestamp in seconds, or `None` when the timestamp is invalid.
    """
    timestamp = signal.get("timestamp") if isinstance(signal, dict) else None
    if isinstance(timestamp, (int, float)):
        return float(timestamp)
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None

    normalized = timestamp.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _collect_recent_scroll_behavior_signals(
    signals: list[dict],
    *,
    now: float,
    window_seconds: float,
) -> list[dict]:
    """Filter recent scroll signals for behavior-derived ComPeer scheduling.

    The scheduler requires enough recent scroll evidence before asking the LLM
    proactive-event detector. This preserves the existing minimum-evidence
    invariant while using the current behavior-signal storage path.

    Args:
        signals: Behavior signals returned by `MemoryStore.get_behavior_signals`.
        now: Current UNIX timestamp in seconds.
        window_seconds: Maximum signal age to consider eligible.

    Returns:
        Scroll signal dictionaries inside the eligible time window.
    """
    recent_scrolls = []
    for signal in signals:
        if not isinstance(signal, dict) or signal.get("type") != "scroll":
            continue
        timestamp = _parse_behavior_signal_timestamp(signal)
        if timestamp is None:
            continue
        if 0 <= now - timestamp <= window_seconds:
            recent_scrolls.append(signal)
    return recent_scrolls


async def schedule_areqa_care_letter(
    user_id: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str,
    hot_memory_snapshot: str,
    cold_memory_context: str,
    last_compeer_message: str = "",
    allow_topic_specific: bool = False,
):
    """
    Generate and schedule a proactive care letter from the ComPeer system via an LLM.

    Args:
        user_id (str): The user's ID.
        learner_state (str): The current learning state of the user.
        edf_policy (str): The pedagogical policy to apply.
        event_summary (str): The summary of the triggering event.
        hot_memory_snapshot (str): The current state of working memory.
        cold_memory_context (str): Relevant long-term memory facts.
        last_compeer_message (str): The last message sent by ComPeer. Defaults to "".
        allow_topic_specific (bool): Whether the letter can reference specific learning topics. Defaults to False.

    Returns:
        str: The task ID of the scheduled letter.
    """
    from gum_integration import generate_areqa_care_letter_via_llm
    from mailbox_store import get_mailbox_store
    from memory_store import get_global_store
    from config import settings

    safe_cold_memory_context = cold_memory_context if allow_topic_specific else ""
    subject, content = await generate_areqa_care_letter_via_llm(
        user_id=user_id,
        hot_memory_snapshot=hot_memory_snapshot,
        cold_memory_context=safe_cold_memory_context,
        learner_state=learner_state,
        edf_policy=edf_policy,
        event_summary=event_summary,
        last_compeer_message=last_compeer_message,
        allow_topic_specific=allow_topic_specific,
    )

    date_bucket = datetime.now().strftime("%Y-%m-%d")
    task_id = _stable_task_id("compeer", user_id, event_summary, date_bucket)
    mb_store = get_mailbox_store()
    await mb_store.schedule_delayed_mail(
        user_id=user_id,
        mail_data={
            "kind": "compeer_care",
            "sender": "AREQA",
            "recipient": "User",
            "subject": subject,
            "content": content,
            "conversation_id": f"compeer-{date_bucket}",
            "event_hash": hashlib.sha256(event_summary.encode("utf-8")).hexdigest()[:24],
            "task_id": task_id,
        },
        delay_seconds=settings.compeer_delivery_delay_seconds,
    )

    logger.info(
        "compeer.scheduled task_id=%s user_id=%s kind=compeer_care delay_seconds=%s",
        task_id,
        user_id,
        settings.compeer_delivery_delay_seconds,
    )

    return task_id


async def _schedule_areqa_care_letter_safely(**kwargs):
    """Contain one user's scheduling failure so other users still progress."""

    user_id = kwargs.get("user_id", "")
    try:
        return await schedule_areqa_care_letter(**kwargs)
    except Exception as exc:
        logger.exception(
            "compeer.schedule_failed user_id=%s reason=%s trigger_retained=true",
            user_id,
            type(exc).__name__,
        )
        from memory_store import get_global_store

        store = get_global_store()
        if store:
            await store.update_hot_memory_async(
                user_id,
                "compeer_retry_reason",
                type(exc).__name__,
                kind="operational_state",
                prompt_safe=False,
                cold_export_eligible=False,
            )
            await store.update_hot_memory_async(
                user_id,
                "compeer_next_attempt_at",
                _time.time() + 30,
                kind="operational_state",
                prompt_safe=False,
                cold_export_eligible=False,
            )
        return None

async def get_last_interaction_time(user_id: str) -> float:
    """
    Retrieve the timestamp of the user's last interaction from Redis.

    Args:
        user_id (str): The ID of the user.

    Returns:
        float: The UNIX timestamp of the last interaction.
    """
    redis = get_redis()
    val = await redis.get(f"areqa:last_interaction:{user_id}")
    return float(val) if val else _time.time()

async def set_last_interaction_time(user_id: str, timestamp: float):
    """
    Save the timestamp of the user's latest interaction to Redis.

    Args:
        user_id (str): The ID of the user.
        timestamp (float): The UNIX timestamp to save.
    """
    redis = get_redis()
    await redis.set(f"areqa:last_interaction:{user_id}", str(timestamp))


async def _process_proactive_user(store, user_id: str) -> None:
    """Process one user and emit a safe proactive-scheduling preflight event.

    The scheduler records only eligibility metadata so operators can correlate a
    later mailbox task without exposing hot-memory or generated-message content.
    """

    iteration_id = uuid.uuid4().hex
    trigger_proactive = False
    avatar_summon = False
    learner_state = "STARTING"
    active_avatar = None
    cooldown_active = False

    async with _flag_lock:
        hot_mem = await store.get_hot_memory(user_id)
        if hot_mem.get("avatar_summon_pending"):
            avatar_summon = True
            active_avatar = hot_mem.get("active_avatar")
        else:
            cooldown_active = await is_in_cooldown(user_id)
            if hot_mem.get("trigger_proactive") and not cooldown_active:
                trigger_proactive = True
                learner_state = hot_mem.get("current_learner_state", "STARTING")
                active_avatar = hot_mem.get("active_avatar")

    if avatar_summon and active_avatar:
        from gum_integration import (
            generate_epistolary_letter_via_llm,
            get_hot_memory_snapshot,
            query_cold_memory_for_context,
        )
        from mailbox_store import get_mailbox_store
        snapshot = await get_hot_memory_snapshot(user_id)
        event_summary = f"與 {active_avatar} 進行深度歷史哲學探討"
        cold_ctx = await query_cold_memory_for_context(user_id, event_summary)
        subject, letter_content = await generate_epistolary_letter_via_llm(
            user_id, active_avatar, snapshot, cold_ctx
        )
        mail_data = {
            "id": str(uuid.uuid4()),
            "kind": "avatar_letter",
            "user_id": user_id,
            "active_avatar": active_avatar,
            "sender": active_avatar,
            "recipient": "User",
            "subject": subject,
            "content": letter_content,
            "timestamp": _time.time(),
            "read": False,
            "task_id": _stable_task_id(
                "letter", user_id, "legacy-avatar-summon", active_avatar
            ),
        }
        task_id = await get_mailbox_store().schedule_delayed_mail(
            user_id=user_id,
            mail_data=mail_data,
            delay_seconds=300,
        )
        if task_id:
            await _clear_persisted_trigger(store, user_id, "avatar_summon_pending")
        preflight = evaluate_proactive_preflight(
            trigger_present=False,
            avatar_pending=True,
            cooldown_active=False,
        )
        if not task_id:
            preflight = replace(preflight, block_reason="scheduling_failed")
        _log_proactive_preflight(
            user_id,
            iteration_id,
            replace(
                preflight,
                scheduling_succeeded=bool(task_id),
                task_id=task_id,
            ),
        )
        await tick_proactive_schedule(user_id)
        return
    elif trigger_proactive:
        daily_limit_reached, daily_sent_count, daily_send_limit = (
            await has_reached_daily_proactive_limit(user_id)
        )
        if daily_limit_reached:
            _log_proactive_preflight(
                user_id,
                iteration_id,
                evaluate_proactive_preflight(
                    trigger_present=True,
                    cooldown_active=False,
                    daily_sent_count=daily_sent_count,
                    daily_send_limit=daily_send_limit,
                ),
            )
            await tick_proactive_schedule(user_id)
            return

        from gum_integration import get_hot_memory_snapshot, query_cold_memory_for_context

        snapshot = await get_hot_memory_snapshot(user_id)
        event_summary = f"EDF 系統偵測到使用者遭遇學習瓶頸 (狀態: {learner_state})"
        allow_topic_specific = should_allow_topic_specific_care(snapshot, event_summary)
        cold_ctx = (
            await query_cold_memory_for_context(user_id, event_summary)
            if allow_topic_specific
            else ""
        )
        edf_policy = await store.get_current_strategy(user_id)
        hot_mem = await store.get_hot_memory(user_id)
        task_id = await _schedule_areqa_care_letter_safely(
            user_id=user_id,
            learner_state=learner_state,
            edf_policy=edf_policy,
            event_summary=event_summary,
            hot_memory_snapshot=snapshot,
            cold_memory_context=cold_ctx,
            last_compeer_message=hot_mem.get("last_compeer_message", ""),
            allow_topic_specific=allow_topic_specific,
        )
        if task_id:
            await record_daily_proactive_send(user_id)
            await _clear_persisted_trigger(store, user_id, "trigger_proactive")
            await set_cooldown(user_id, state=learner_state)
        preflight = evaluate_proactive_preflight(
            trigger_present=True,
            cooldown_active=False,
        )
        if not task_id:
            preflight = replace(preflight, block_reason="scheduling_failed")
        _log_proactive_preflight(
            user_id,
            iteration_id,
            replace(
                preflight,
                scheduling_succeeded=bool(task_id),
                task_id=task_id,
            ),
        )
        await tick_proactive_schedule(user_id)
        return

    await tick_proactive_schedule(user_id)

    last_time = await get_last_interaction_time(user_id)
    inactive_seconds = max(0.0, _time.time() - last_time)
    cooldown_active = await is_in_cooldown(user_id)
    cooldown_remaining_seconds = (
        await get_cooldown_remaining_seconds(user_id) if cooldown_active else None
    )
    if cooldown_active or inactive_seconds <= 60:
        _log_proactive_preflight(
            user_id,
            iteration_id,
            evaluate_proactive_preflight(
                trigger_present=bool(hot_mem.get("trigger_proactive")),
                avatar_pending=avatar_summon,
                cooldown_active=cooldown_active,
                inactive_seconds=inactive_seconds,
                cooldown_remaining_seconds=cooldown_remaining_seconds,
            ),
        )
        return

    behavior_signals = await store.get_behavior_signals(user_id)
    from config import settings

    recent_scroll_signals = _collect_recent_scroll_behavior_signals(
        behavior_signals,
        now=_time.time(),
        window_seconds=PROACTIVE_SCROLL_SIGNAL_WINDOW_SECONDS,
    )
    hot_mem = await store.get_hot_memory(user_id)
    legacy_scroll_keys = [
        key
        for key, value in hot_mem.items()
        if key.startswith("obs_") and "Type: scroll" in str(value)
    ]
    scroll_count = len(recent_scroll_signals)
    signal_source = "behavior_signals"
    if scroll_count == 0 and legacy_scroll_keys:
        scroll_count = len(legacy_scroll_keys)
        signal_source = "legacy_hot_memory"

    behavior_eval_level = logging.INFO if scroll_count > 0 else logging.DEBUG
    logger.log(
        behavior_eval_level,
        "compeer.behavior_signals_evaluated user_id=%s iteration_id=%s "
        "signal_source=%s behavior_signal_count=%s recent_scroll_count=%s "
        "legacy_scroll_count=%s scroll_count=%s delivery_delay_seconds=%s",
        user_id,
        iteration_id,
        signal_source,
        len(behavior_signals),
        len(recent_scroll_signals),
        len(legacy_scroll_keys),
        scroll_count,
        settings.compeer_delivery_delay_seconds,
    )

    if scroll_count < PROACTIVE_SCROLL_SIGNAL_THRESHOLD:
        _log_proactive_preflight(
            user_id,
            iteration_id,
            evaluate_proactive_preflight(
                trigger_present=False,
                cooldown_active=False,
                inactive_seconds=inactive_seconds,
                scroll_count=scroll_count,
                signal_source=signal_source,
                behavior_signal_count=len(behavior_signals),
                recent_scroll_count=len(recent_scroll_signals),
                legacy_scroll_count=len(legacy_scroll_keys),
                delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
            ),
        )
        return

    daily_limit_reached, daily_sent_count, daily_send_limit = (
        await has_reached_daily_proactive_limit(user_id)
    )
    if daily_limit_reached:
        _log_proactive_preflight(
            user_id,
            iteration_id,
            evaluate_proactive_preflight(
                trigger_present=False,
                cooldown_active=False,
                inactive_seconds=inactive_seconds,
                scroll_count=scroll_count,
                signal_source=signal_source,
                behavior_signal_count=len(behavior_signals),
                recent_scroll_count=len(recent_scroll_signals),
                legacy_scroll_count=len(legacy_scroll_keys),
                delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
                daily_sent_count=daily_sent_count,
                daily_send_limit=daily_send_limit,
            ),
        )
        return

    from gum_integration import (
        detect_proactive_event_via_llm,
        get_hot_memory_snapshot,
        query_cold_memory_for_context,
    )

    snapshot = await get_hot_memory_snapshot(user_id)
    event = await detect_proactive_event_via_llm(user_id, snapshot)
    importance_passed = bool(event["has_event"] and event["importance"] >= 0.7)
    if not importance_passed:
        logger.info(
            "compeer.behavior_trigger_rejected user_id=%s iteration_id=%s "
            "signal_source=%s scroll_count=%s reason=importance_gate_failed",
            user_id,
            iteration_id,
            signal_source,
            scroll_count,
        )
        _log_proactive_preflight(
            user_id,
            iteration_id,
            evaluate_proactive_preflight(
                trigger_present=False,
                cooldown_active=False,
                inactive_seconds=inactive_seconds,
                scroll_count=scroll_count,
                signal_source=signal_source,
                behavior_signal_count=len(behavior_signals),
                recent_scroll_count=len(recent_scroll_signals),
                legacy_scroll_count=len(legacy_scroll_keys),
                delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
                importance_passed=False,
            ),
        )
        return

    event_summary = event["event_summary"]
    logger.info(
        "compeer.behavior_trigger_eligible user_id=%s iteration_id=%s "
        "signal_source=%s scroll_count=%s delivery_delay_seconds=%s",
        user_id,
        iteration_id,
        signal_source,
        scroll_count,
        settings.compeer_delivery_delay_seconds,
    )
    allow_topic_specific = should_allow_topic_specific_care(snapshot, event_summary)
    cold_ctx = (
        await query_cold_memory_for_context(user_id, event_summary)
        if allow_topic_specific
        else ""
    )
    learner_state = await store.get_learner_state(user_id)
    task_id = await _schedule_areqa_care_letter_safely(
        user_id=user_id,
        learner_state=learner_state,
        edf_policy=await store.get_current_strategy(user_id),
        event_summary=event_summary,
        hot_memory_snapshot=snapshot,
        cold_memory_context=cold_ctx,
        last_compeer_message=hot_mem.get("last_compeer_message", ""),
        allow_topic_specific=allow_topic_specific,
    )
    if task_id:
        await record_daily_proactive_send(user_id)
        # Consume only after the delayed mailbox intent is durable; otherwise
        # retry needs the same behavior evidence to remain available.
        if signal_source == "behavior_signals":
            consumed_count = await store.consume_behavior_signals(
                user_id,
                recent_scroll_signals,
            )
        else:
            for key in legacy_scroll_keys:
                remove_typed_entry(hot_mem, key)
            await store.redis.set(
                f"areqa:hot_memory:{user_id}",
                json.dumps(hot_mem, ensure_ascii=False),
            )
            consumed_count = len(legacy_scroll_keys)
        logger.info(
            "compeer.behavior_signals_consumed user_id=%s iteration_id=%s "
            "signal_source=%s consumed_count=%s task_id=%s",
            user_id,
            iteration_id,
            signal_source,
            consumed_count,
            task_id,
        )
        await set_cooldown(user_id, state=learner_state)
    preflight = evaluate_proactive_preflight(
        trigger_present=False,
        cooldown_active=False,
        inactive_seconds=inactive_seconds,
        scroll_count=scroll_count,
        signal_source=signal_source,
        behavior_signal_count=len(behavior_signals),
        recent_scroll_count=len(recent_scroll_signals),
        legacy_scroll_count=len(legacy_scroll_keys),
        delivery_delay_seconds=settings.compeer_delivery_delay_seconds,
        importance_passed=True,
    )
    if not task_id:
        preflight = replace(preflight, block_reason="scheduling_failed")
    _log_proactive_preflight(
        user_id,
        iteration_id,
        replace(
            preflight,
            scheduling_succeeded=bool(task_id),
            task_id=task_id,
        ),
    )


async def proactive_scheduler_loop():
    """
    Background worker loop that periodically checks for triggers to send proactive 
    care letters. It evaluates user inactivity, avatar summons, and learning bottlenecks.
    """
    logger.info("compeer.scheduler_started")
    while True:
        try:
            async with _send_lock:
                from memory_store import get_global_store
                store = get_global_store()
                if store:
                    redis = store.redis
                    cursor = 0
                    all_users = set()
                    while True:
                        cursor, keys = await redis.scan(cursor, match="areqa:hot_memory:*", count=100)
                        for key in keys:
                            k_str = key
                            all_users.add(k_str.split("areqa:hot_memory:")[1])
                        if cursor == 0:
                            break
                    for user_id in sorted(all_users):
                        try:
                            await _process_proactive_user(store, user_id)
                        except Exception as exc:
                            logger.warning(
                                "compeer.user_iteration_failed user_id=%s reason=%s",
                                user_id,
                                type(exc).__name__,
                                exc_info=True,
                            )

            await asyncio.sleep(10)
        except Exception:
            logger.exception("compeer.scheduler_iteration_failed")
            await asyncio.sleep(10)
