"""Compatibility facade for ComPeer scheduler domain modules.

Existing code and tests import and patch `services.compeer_scheduler` directly.
The implementation now lives under `services.compeer`, while this facade keeps
shared runtime objects and public symbols in the legacy module namespace.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

from redis_client import get_redis

_current_module = sys.modules[__name__]
sys.modules["services.compeer_scheduler"] = _current_module
sys.modules["backend.services.compeer_scheduler"] = _current_module


def _sync_import_aliases() -> None:
    if services_package := sys.modules.get("services"):
        setattr(services_package, "compeer_scheduler", _current_module)
    if backend_services_package := sys.modules.get("backend.services"):
        setattr(backend_services_package, "compeer_scheduler", _current_module)


_sync_import_aliases()

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

from services.compeer.care import (
    _collect_recent_scroll_behavior_signals,
    _parse_behavior_signal_timestamp,
    _schedule_areqa_care_letter_safely,
    _stable_task_id,
    has_current_learning_evidence,
    is_generic_event_summary,
    schedule_areqa_care_letter,
    should_allow_topic_specific_care,
)
from services.compeer.interactions import get_last_interaction_time, set_last_interaction_time
from services.compeer.legacy_schedule import (
    daily_scheduler_loop,
    evaluate_importance_gate,
    initialize_daily_schedule,
    run_reflection_and_initialization,
    tick_proactive_schedule,
)
from services.compeer.preflight import ProactivePreflight, _auto_proactive_enabled, evaluate_proactive_preflight, _log_proactive_preflight
from services.compeer.proactive import _process_proactive_user, proactive_scheduler_loop
from services.compeer.state import (
    _clear_persisted_trigger,
    _compeer_daily_counter_key,
    _compeer_proactive_mail_interval_key,
    _seconds_until_next_utc_day,
    clear_cooldown,
    get_cooldown_remaining_seconds,
    get_daily_proactive_sent_count,
    get_proactive_mail_interval_remaining_seconds,
    has_reached_daily_proactive_limit,
    is_in_cooldown,
    record_daily_proactive_send,
    record_proactive_mail_scheduled,
    set_cooldown,
)

_sync_import_aliases()
