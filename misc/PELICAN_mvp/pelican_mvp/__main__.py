"""Command-line entry point for the PELICAN MVP web server."""

import argparse
import logging
import os
import signal
import socket
import time
from pathlib import Path

import uvicorn

from .observability import DEBUG_CHANNELS, DebugChannelFilter, normalize_debug_channels


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROC_ROOT = Path("/proc")
LOG_FIELDS = (
    "event",
    "debug_channel",
    "learner_token",
    "reason_code",
    "phase",
    "activity_code",
    "activity_status",
    "detail_code",
    "skill_id",
    "node_id",
    "domain_category",
    "route",
    "skill_source",
    "diagnostic_source",
    "intake_source",
    "semantic_intent",
    "semantic_confidence",
    "model_route",
    "api_status_code",
    "api_error_type",
    "remediation_reason",
    "learner_state",
    "strategy",
    "edf_transition",
    "memory_event",
    "endpoint",
)


class SafePelicanFormatter(logging.Formatter):
    """Fill structured log defaults so local activity logs never break formatting.

    The CLI formatter prints only allow-listed metadata from
    ``pelican_mvp.observability.log_event``. Including ``reason_code`` is a
    debugging boundary: it exposes stable failure handles such as
    ``llm_request_failed`` or ``missing_remediation`` without printing raw
    learner answers, prompts, model output, credentials, or exception messages.
    """

    def format(self, record: logging.LogRecord) -> str:
        for field in LOG_FIELDS:
            if not hasattr(record, field) or getattr(record, field) is None:
                setattr(record, field, "-")
        return super().format(record)


def main(argv: list[str] | None = None) -> None:
    """Run the MVP server after cleaning up stale local PELICAN listeners."""
    parser = argparse.ArgumentParser(description="Run the PELICAN MVP web server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--no-cleanup-stale-server",
        action="store_true",
        help="Do not terminate an older PELICAN MVP process already bound to this host/port.",
    )
    parser.add_argument(
        "--pelican-log",
        choices=("off", "info", "debug"),
        default=os.environ.get("PELICAN_LOG_MODE", "info"),
        help="Terminal PELICAN structured log mode. Env: PELICAN_LOG_MODE.",
    )
    parser.add_argument(
        "--pelican-log-channels",
        default=os.environ.get("PELICAN_LOG_CHANNELS", "all"),
        help=(
            "Comma-separated PELICAN debug channels to show: "
            f"{', '.join(DEBUG_CHANNELS)}. Use 'all' for every channel. Env: PELICAN_LOG_CHANNELS."
        ),
    )
    args = parser.parse_args(argv)
    configure_runtime_logging(args.pelican_log, args.pelican_log_channels)
    if not args.no_cleanup_stale_server:
        cleanup_stale_pelican_server(args.host, args.port)
    uvicorn.run("pelican_mvp.server:app", host=args.host, port=args.port)


def configure_runtime_logging(mode: str | None = None, channels: str | None = None) -> None:
    """Print safe PELICAN activity events beside uvicorn access logs.

    Args:
        mode: ``off`` disables the CLI handler, ``info`` prints normal
            structured events, and ``debug`` also permits DEBUG-level events.
            ``None`` reads ``PELICAN_LOG_MODE`` with ``info`` fallback.
        channels: Comma-separated channel list or ``all``. ``None`` reads
            ``PELICAN_LOG_CHANNELS`` with ``all`` fallback.

    Raises:
        ValueError: If an unknown mode or channel is provided.

    Side Effects:
        Installs or updates exactly one CLI stream handler on the package
        logger. The formatter prints only allow-listed safe metadata and never
        raw learner answers, prompts, model outputs, credentials, or exception
        bodies.
    """
    selected_mode = (mode or os.environ.get("PELICAN_LOG_MODE", "info")).strip().lower()
    if selected_mode not in {"off", "info", "debug"}:
        raise ValueError("PELICAN log mode must be one of: off, info, debug")
    channel_filter = DebugChannelFilter(normalize_debug_channels(channels or os.environ.get("PELICAN_LOG_CHANNELS", "all")))
    logger = logging.getLogger("pelican_mvp")
    logger.setLevel(logging.DEBUG if selected_mode == "debug" else logging.INFO)
    cli_handlers = [handler for handler in logger.handlers if getattr(handler, "_pelican_cli_handler", False)]
    if selected_mode == "off":
        for handler in cli_handlers:
            logger.removeHandler(handler)
        logger.propagate = False
        return
    if cli_handlers:
        handler = cli_handlers[0]
    else:
        handler = logging.StreamHandler()
        handler._pelican_cli_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    handler.setLevel(logging.DEBUG if selected_mode == "debug" else logging.INFO)
    handler.filters.clear()
    handler.addFilter(channel_filter)
    handler.setFormatter(
        SafePelicanFormatter(
            "PELICAN %(levelname)s channel=%(debug_channel)s event=%(event)s endpoint=%(endpoint)s "
            "learner=%(learner_token)s phase=%(phase)s activity=%(activity_code)s "
            "status=%(activity_status)s reason=%(reason_code)s detail=%(detail_code)s domain=%(domain_category)s "
            "route=%(route)s api_status=%(api_status_code)s api_error=%(api_error_type)s "
            "skill=%(skill_id)s skill_source=%(skill_source)s "
            "intake_source=%(intake_source)s semantic=%(semantic_intent)s confidence=%(semantic_confidence)s "
            "diagnostic_source=%(diagnostic_source)s "
            "node=%(node_id)s edf=%(learner_state)s strategy=%(strategy)s "
            "edf_transition=%(edf_transition)s memory=%(memory_event)s remediation=%(remediation_reason)s"
        )
    )
    logger.propagate = False


def cleanup_stale_pelican_server(host: str, port: int) -> list[int]:
    """Terminate stale PELICAN MVP processes that own the requested socket.

    The cleanup is intentionally conservative: it only targets processes whose
    listening socket matches the requested host/port and whose command/cwd looks
    like this MVP. Other services on the same port are left alone so uvicorn can
    fail with the normal address-in-use error.
    """
    inodes = _listening_socket_inodes(host, port)
    if not inodes:
        return []
    terminated: list[int] = []
    for pid in sorted(_pids_for_socket_inodes(inodes)):
        if pid == os.getpid() or not _is_pelican_mvp_process(pid):
            continue
        if _terminate_process(pid):
            terminated.append(pid)
    if terminated:
        print(f"Stopped stale PELICAN MVP server process(es): {', '.join(map(str, terminated))}")
    return terminated


def _listening_socket_inodes(host: str, port: int) -> set[str]:
    """Return socket inodes listening on the requested IPv4 host/port."""
    try:
        host_ip = socket.gethostbyname(host)
    except OSError:
        host_ip = host
    wanted_hosts = {_ipv4_proc_hex(host_ip)}
    if host_ip in {"127.0.0.1", "0.0.0.0"}:
        wanted_hosts.add(_ipv4_proc_hex("0.0.0.0"))
    wanted_port = f"{port:04X}"
    inodes: set[str] = set()
    tcp_path = PROC_ROOT / "net" / "tcp"
    try:
        lines = tcp_path.read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return inodes
    for line in lines:
        parts = line.split()
        if len(parts) < 10 or parts[3] != "0A":
            continue
        local_address = parts[1]
        address_hex, port_hex = local_address.split(":")
        if port_hex.upper() == wanted_port and address_hex.upper() in wanted_hosts:
            inodes.add(parts[9])
    return inodes


def _pids_for_socket_inodes(inodes: set[str]) -> set[int]:
    """Map socket inodes to owning PIDs through ``/proc/<pid>/fd``."""
    pids: set[int] = set()
    for proc_entry in PROC_ROOT.iterdir():
        if not proc_entry.name.isdigit():
            continue
        fd_dir = proc_entry / "fd"
        try:
            fd_entries = list(fd_dir.iterdir())
        except OSError:
            continue
        for fd_entry in fd_entries:
            try:
                target = os.readlink(fd_entry)
            except OSError:
                continue
            if target.startswith("socket:[") and target[8:-1] in inodes:
                pids.add(int(proc_entry.name))
                break
    return pids


def _is_pelican_mvp_process(pid: int) -> bool:
    """Return whether a PID appears to be this project's PELICAN server."""
    proc_dir = PROC_ROOT / str(pid)
    try:
        cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore")
    except OSError:
        return False
    if "pelican_mvp" not in cmdline:
        return False
    if "pelican_mvp.server:app" in cmdline:
        return True
    try:
        cwd = (proc_dir / "cwd").resolve()
    except OSError:
        return False
    return cwd == PROJECT_ROOT or PROJECT_ROOT in cwd.parents


def _terminate_process(pid: int, timeout_seconds: float = 3.0) -> bool:
    """Terminate one stale process, escalating to SIGKILL only if needed."""
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    if _wait_for_exit(pid, timeout_seconds):
        return True
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return False
    return _wait_for_exit(pid, 1.0)


def _wait_for_exit(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    proc_path = PROC_ROOT / str(pid)
    while time.monotonic() < deadline:
        if not proc_path.exists():
            return True
        time.sleep(0.05)
    return not proc_path.exists()


def _ipv4_proc_hex(ip_address: str) -> str:
    packed = socket.inet_aton(ip_address)
    return "".join(f"{byte:02X}" for byte in packed[::-1])


if __name__ == "__main__":
    main()
