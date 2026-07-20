import signal

import pelican_mvp.__main__ as main_module


def test_ipv4_proc_hex_matches_linux_proc_format() -> None:
    assert main_module._ipv4_proc_hex("127.0.0.1") == "0100007F"
    assert main_module._ipv4_proc_hex("0.0.0.0") == "00000000"


def test_cleanup_stale_pelican_server_only_terminates_owned_process(monkeypatch) -> None:
    killed: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr(main_module, "_listening_socket_inodes", lambda host, port: {"inode"})
    monkeypatch.setattr(main_module, "_pids_for_socket_inodes", lambda inodes: {111, 222})
    monkeypatch.setattr(main_module, "_is_pelican_mvp_process", lambda pid: pid == 111)
    monkeypatch.setattr(main_module, "_wait_for_exit", lambda pid, timeout_seconds: True)
    monkeypatch.setattr(main_module.os, "getpid", lambda: 999)
    monkeypatch.setattr(main_module.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    terminated = main_module.cleanup_stale_pelican_server("127.0.0.1", 8000)

    assert terminated == [111]
    assert killed == [(111, signal.SIGTERM)]


def test_cleanup_stale_pelican_server_ignores_current_process(monkeypatch) -> None:
    killed: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr(main_module, "_listening_socket_inodes", lambda host, port: {"inode"})
    monkeypatch.setattr(main_module, "_pids_for_socket_inodes", lambda inodes: {111})
    monkeypatch.setattr(main_module, "_is_pelican_mvp_process", lambda pid: True)
    monkeypatch.setattr(main_module.os, "getpid", lambda: 111)
    monkeypatch.setattr(main_module.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    terminated = main_module.cleanup_stale_pelican_server("127.0.0.1", 8000)

    assert terminated == []
    assert killed == []


def test_main_can_disable_cleanup(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(main_module, "cleanup_stale_pelican_server", lambda host, port: calls.append("cleanup"))
    monkeypatch.setattr(main_module.uvicorn, "run", lambda *args, **kwargs: calls.append("uvicorn"))

    main_module.main(["--no-cleanup-stale-server"])

    assert calls == ["uvicorn"]
