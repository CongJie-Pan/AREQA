"""Command-line entry point for the PELICAN MVP web server."""

import argparse
import os
import signal
import socket
import time
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROC_ROOT = Path("/proc")


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
    args = parser.parse_args(argv)
    if not args.no_cleanup_stale_server:
        cleanup_stale_pelican_server(args.host, args.port)
    uvicorn.run("pelican_mvp.server:app", host=args.host, port=args.port)


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
