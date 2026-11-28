from datetime import date

from scripts.shadow_policy_report import render_markdown, summarize

TS = 1_764_288_000  # 2025-11-28 08:00 Asia/Taipei


def _record(gemini="PRACTICE_HINT", jev="PRACTICE_HINT", *, gemini_ms=1100.0, jev_ms=400.0, gemini_status="ok",
            jev_status="ok", has_pdf=False, ts=TS, depth="SCAFFOLDED"):
    return {"ts": ts, "gemini_move": gemini, "jev_move": jev, "gemini_depth": depth, "jev_depth": depth,
            "gemini_status": gemini_status, "jev_status": jev_status, "gemini_ms": gemini_ms, "jev_ms": jev_ms,
            "budget_ms": 1500, "has_pdf": has_pdf}


def test_agreement_counts_only_turns_where_both_answered():
    records = [
        _record(),
        _record(gemini="LEARN_FEEDBACK", jev="PRACTICE_FEEDBACK"),
        _record(jev="none", jev_status="ValueError"),
    ]

    summary = summarize(records, min_samples=2)

    assert summary["agreement"] == {"turns": 2, "mode": 0.5, "move": 0.5, "depth": 1.0}
    assert summary["verdict"] == "READY"
    assert summary["practice_only_jev"] == 1
    assert summary["practice_only_gemini"] == 0
    assert summary["top_disagreements"] == [("LEARN_FEEDBACK -> PRACTICE_FEEDBACK", 1)]
    assert summary["jev"]["statuses"] == {"ok": 2, "ValueError": 1}


def test_budget_latency_and_window_are_reported():
    records = [
        _record(gemini_ms=900.0, ts=TS),
        _record(gemini_ms=2200.0, ts=TS + 86_400, has_pdf=True),
    ]

    summary = summarize(records, min_samples=200)

    assert summary["verdict"] == "INSUFFICIENT_SAMPLES"
    assert summary["gemini"]["in_budget"] == 0.5
    assert summary["jev"]["in_budget"] == 1.0
    assert summary["gemini"]["p95_ms"] == 2200.0
    assert (summary["first_day"], summary["last_day"], summary["days_with_traffic"]) == ("2025-11-28", "2025-11-29", 2)
    assert summary["agreement_with_pdf"]["turns"] == 1


def test_empty_experiment_renders_without_errors():
    text = render_markdown(summarize([]), until="2026-12-12", today=date(2026, 12, 1))

    assert "INSUFFICIENT_SAMPLES" in text
    assert "Next steps" not in text


def test_final_report_adds_next_steps_after_the_end_date():
    summary = summarize([_record()], min_samples=1)

    interim = render_markdown(summary, until="2026-12-12", today=date(2026, 12, 12))
    final = render_markdown(summary, until="2026-12-12", today=date(2026, 12, 13))

    assert "(final)" not in interim and "Next steps" not in interim
    assert "(final)" in final and "### Next steps" in final
    assert "POLICY_CLASSIFIER_BACKEND=jev" in final
