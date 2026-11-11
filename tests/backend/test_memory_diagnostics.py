import logging

from services import memory_diagnostics


def test_memory_snapshot_reports_process_and_container_counters(tmp_path, monkeypatch, caplog):
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "status").write_text("VmRSS:\t2048 kB\nVmHWM:\t4096 kB\n")
    (proc / "cgroup").write_text("0::/worker\n")
    cgroup = tmp_path / "cgroup"
    worker = cgroup / "worker"
    worker.mkdir(parents=True)
    (worker / "memory.current").write_text("67108864\n")
    (worker / "memory.peak").write_text("100663296\n")
    (worker / "memory.max").write_text("134217728\n")
    (worker / "memory.events").write_text("oom 3\noom_kill 2\n")
    monkeypatch.setattr(memory_diagnostics, "_PROC", proc)
    monkeypatch.setattr(memory_diagnostics, "_CGROUP", cgroup)
    caplog.set_level(logging.INFO, logger=memory_diagnostics.__name__)

    memory_diagnostics.log_memory_snapshot(
        "pdf_text_worker_failed", conversation_id="test-turn", attachment_bytes=1234, worker_returncode=-9,
    )

    assert "stage=pdf_text_worker_failed" in caplog.text
    assert "conversation_id=test-turn" in caplog.text
    assert "rss_bytes=2097152 rss_peak_bytes=4194304" in caplog.text
    assert "cgroup_memory_bytes=67108864 cgroup_peak_bytes=100663296 cgroup_limit_bytes=134217728" in caplog.text
    assert "cgroup_oom_total=3 cgroup_oom_kill_total=2 attachment_bytes=1234 worker_returncode=-9" in caplog.text


def test_missing_metrics_and_unsafe_ids_are_logged_without_failing(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(memory_diagnostics, "_PROC", tmp_path / "missing_proc")
    monkeypatch.setattr(memory_diagnostics, "_CGROUP", tmp_path / "missing_cgroup")
    caplog.set_level(logging.INFO, logger=memory_diagnostics.__name__)

    memory_diagnostics.log_memory_snapshot("startup", request_id="private\ncontent")

    assert "request_id=none" in caplog.text
    assert "rss_bytes=None" in caplog.text
    assert "cgroup_oom_kill_total=None" in caplog.text
    assert "private" not in caplog.text
