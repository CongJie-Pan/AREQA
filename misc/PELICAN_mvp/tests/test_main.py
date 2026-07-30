import logging
import signal

import pelican_mvp.__main__ as main_module
from pelican_mvp.observability import log_event


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


def test_safe_pelican_formatter_fills_missing_structured_fields() -> None:
    formatter = main_module.SafePelicanFormatter(
        "PELICAN %(levelname)s %(event)s phase=%(phase)s activity=%(activity_code)s detail=%(detail_code)s"
    )
    record = logging.LogRecord(
        name="pelican_mvp",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="pelican_activity",
        args=(),
        exc_info=None,
    )

    assert formatter.format(record) == "PELICAN INFO - phase=- activity=- detail=-"


def test_safe_pelican_formatter_prints_safe_reason_code() -> None:
    formatter = main_module.SafePelicanFormatter(
        "PELICAN %(levelname)s %(event)s reason=%(reason_code)s"
    )
    record = logging.LogRecord(
        name="pelican_mvp",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="pelican_skill_generation_failed",
        args=(),
        exc_info=None,
    )
    record.event = "pelican_skill_generation_failed"
    record.reason_code = "llm_request_failed|llm_jsondecodeerror"

    assert formatter.format(record) == (
        "PELICAN WARNING pelican_skill_generation_failed "
        "reason=llm_request_failed|llm_jsondecodeerror"
    )


def test_compact_pelican_formatter_omits_empty_structured_fields() -> None:
    formatter = main_module.CompactPelicanFormatter()
    record = logging.LogRecord(
        name="pelican_mvp",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="pelican_activity",
        args=(),
        exc_info=None,
    )
    record.event = "pelican_activity"
    record.debug_channel = "activity"
    record.activity_code = "intake_question_generated"

    output = formatter.format(record)

    assert output == "PELICAN INFO event=pelican_activity channel=activity activity=intake_question_generated"
    assert "api_status=-" not in output
    assert "phase=-" not in output


def test_configure_runtime_logging_filters_terminal_channels(capsys) -> None:
    logger = logging.getLogger("pelican_mvp")
    for handler in list(logger.handlers):
        if getattr(handler, "_pelican_cli_handler", False):
            logger.removeHandler(handler)

    main_module.configure_runtime_logging("info", "api")
    log_event("pelican_api_start", "student", endpoint="/api/start", reason_code="ok")
    log_event("pelican_skill_loaded", "student", skill_id="deep_learning", reason_code="ok")

    output = capsys.readouterr().err

    assert "channel=api" in output
    assert "endpoint=/api/start" in output
    assert "learner=" in output
    assert "phase=-" not in output
    assert "pelican_skill_loaded" not in output


def test_configure_runtime_logging_prints_schema_debug_fields(capsys) -> None:
    logger = logging.getLogger("pelican_mvp")
    for handler in list(logger.handlers):
        if getattr(handler, "_pelican_cli_handler", False):
            logger.removeHandler(handler)

    main_module.configure_runtime_logging("debug", "skill")
    log_event(
        "pelican_skill_schema_mode_selected",
        level=logging.DEBUG,
        model_route="openai/gpt-5.5",
        schema_mode="auto",
        schema_format="json_schema",
        schema_strict=True,
        schema_fallback=False,
    )

    output = capsys.readouterr().err

    assert "event=pelican_skill_schema_mode_selected" in output
    assert "schema_mode=auto" in output
    assert "schema_format=json_schema" in output
    assert "schema_strict=True" in output
    assert "schema_fallback=False" in output


def test_configure_runtime_logging_prints_orchestration_debug_fields(capsys) -> None:
    logger = logging.getLogger("pelican_mvp")
    for handler in list(logger.handlers):
        if getattr(handler, "_pelican_cli_handler", False):
            logger.removeHandler(handler)

    main_module.configure_runtime_logging("info", "methodology")
    log_event(
        "pelican_learning_orchestrator_decided",
        "student",
        turn_id="turn_1",
        cycle_id="cycle_1",
        phase="diagnosis",
        action="call_capability",
        capability="diagnose_answer",
        policy="write_proposed",
        target_phase="cognitive_diagnosis",
        confidence_bucket="high",
        proposal_source="llm",
        outcome="accepted",
        idempotency_key="turn_1:snapshot:call_capability:diagnose_answer",
        reason_code="active_prompt_answer",
        raw_answer="private learner text",
    )

    output = capsys.readouterr().err

    assert "event=pelican_learning_orchestrator_decided" in output
    assert "turn=turn_1" in output
    assert "cycle=cycle_1" in output
    assert "action=call_capability" in output
    assert "capability=diagnose_answer" in output
    assert "policy=write_proposed" in output
    assert "target=cognitive_diagnosis" in output
    assert "confidence_bucket=high" in output
    assert "proposal_source=llm" in output
    assert "outcome=accepted" in output
    assert "idempotency=turn_1:snapshot:call_capability:diagnose_answer" in output
    assert "api_status=-" not in output
    assert "private learner text" not in output


def test_configure_runtime_logging_off_removes_cli_handler() -> None:
    logger = logging.getLogger("pelican_mvp")

    main_module.configure_runtime_logging("info", "all")
    assert any(getattr(handler, "_pelican_cli_handler", False) for handler in logger.handlers)

    main_module.configure_runtime_logging("off", "all")

    assert not any(getattr(handler, "_pelican_cli_handler", False) for handler in logger.handlers)
