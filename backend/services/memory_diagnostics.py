"""Log process and container memory checkpoints without reading request content."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)
_PROC = Path("/proc/self")
_CGROUP = Path("/sys/fs/cgroup")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return ""


def _number(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _cgroup_memory() -> tuple[int | None, int | None, int | None, int | None, int | None]:
    # A container can mount its own cgroup as the root of the visible hierarchy.
    candidates = []
    for line in _read(_PROC / "cgroup").splitlines():
        if line.startswith("0::/"):
            relative = line[4:]
            if relative and ".." not in Path(relative).parts:
                candidates.append(_CGROUP / relative)
            break
    candidates.append(_CGROUP)

    for directory in candidates:
        current = _number(_read(directory / "memory.current"))
        if current is None:
            continue
        peak = _number(_read(directory / "memory.peak"))
        limit = _number(_read(directory / "memory.max"))
        events = {}
        for line in _read(directory / "memory.events").splitlines():
            fields = line.split()
            if len(fields) == 2:
                events[fields[0]] = fields[1]
        return current, peak, limit, _number(events.get("oom", "")), _number(events.get("oom_kill", ""))
    return None, None, None, None, None


def log_memory_snapshot(
    stage: str,
    *,
    conversation_id: str = "",
    request_id: str = "",
    attachment_bytes: int | None = None,
    worker_returncode: int | None = None,
) -> None:
    """Record Linux RSS and cgroup v2 counters where the host exposes them."""
    if not logger.isEnabledFor(logging.INFO):
        return
    rss = peak = None
    for line in _read(_PROC / "status").splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            fields = line.split()
            kb = _number(fields[1]) if len(fields) == 3 and fields[2] == "kB" else None
            value = kb * 1024 if kb is not None else None
            if fields[0] == "VmRSS:":
                rss = value
            else:
                peak = value
    current, cgroup_peak, limit, oom, oom_kill = _cgroup_memory()
    safe_conversation = conversation_id if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", conversation_id or "") else "none"
    safe_request = request_id if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id or "") else "none"
    logger.info(
        "memory.snapshot stage=%s pid=%d conversation_id=%s request_id=%s "
        "rss_bytes=%s rss_peak_bytes=%s cgroup_memory_bytes=%s cgroup_peak_bytes=%s cgroup_limit_bytes=%s "
        "cgroup_oom_total=%s cgroup_oom_kill_total=%s attachment_bytes=%s worker_returncode=%s",
        stage, os.getpid(), safe_conversation, safe_request, rss, peak, current, cgroup_peak, limit,
        oom, oom_kill, attachment_bytes, worker_returncode,
    )
