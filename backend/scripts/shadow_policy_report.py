"""Summarize the EDF policy shadow experiment (Gemini serves, Jev runs beside it).

Run from the backend directory with REDIS_URL pointing at the production Redis:
    python -m scripts.shadow_policy_report --until 2026-12-12
Records hold labels, statuses and timings only; this report prints aggregates.
It needs only the ``redis`` package, so CI can run it without the backend.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

SHADOW_KEY = "areqa:policy_shadow:v1"
TAIPEI = ZoneInfo("Asia/Taipei")
MIN_SAMPLES = 200


def _percentile(values: list[float], share: float) -> float | None:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * share) - 1] if ordered else None


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def _mode(move: str) -> str:
    return move.split("_", 1)[0]


def summarize(records: list[dict], *, min_samples: int = MIN_SAMPLES) -> dict:
    """Aggregate shadow records; agreement counts only turns where both sides answered."""

    both = [r for r in records if r["gemini_status"] == "ok" and r["jev_status"] == "ok"]
    pdf = [r for r in both if r.get("has_pdf")]
    days = sorted({datetime.fromtimestamp(r["ts"], TAIPEI).date().isoformat() for r in records})

    def agreement(rows: list[dict]) -> dict:
        return {
            "turns": len(rows),
            "mode": _rate(sum(_mode(r["gemini_move"]) == _mode(r["jev_move"]) for r in rows), len(rows)),
            "move": _rate(sum(r["gemini_move"] == r["jev_move"] for r in rows), len(rows)),
            "depth": _rate(sum(r["gemini_depth"] == r["jev_depth"] for r in rows), len(rows)),
        }

    def side(prefix: str) -> dict:
        ok = [r for r in records if r[f"{prefix}_status"] == "ok"]
        durations = [r[f"{prefix}_ms"] for r in ok]
        return {
            "statuses": dict(Counter(r[f"{prefix}_status"] for r in records)),
            "p50_ms": _percentile(durations, 0.5),
            "p95_ms": _percentile(durations, 0.95),
            "in_budget": _rate(sum(r[f"{prefix}_ms"] <= r["budget_ms"] for r in ok), len(records)),
        }

    return {
        "records": len(records),
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
        "days_with_traffic": len(days),
        "verdict": "READY" if len(both) >= min_samples else "INSUFFICIENT_SAMPLES",
        "min_samples": min_samples,
        "agreement": agreement(both),
        "agreement_with_pdf": agreement(pdf),
        # The costly disagreement: one side protects a practice step the other would answer.
        "practice_only_gemini": sum(_mode(r["gemini_move"]) == "PRACTICE" != _mode(r["jev_move"]) for r in both),
        "practice_only_jev": sum(_mode(r["jev_move"]) == "PRACTICE" != _mode(r["gemini_move"]) for r in both),
        "top_disagreements": Counter(
            f"{r['gemini_move']} -> {r['jev_move']}" for r in both if r["gemini_move"] != r["jev_move"]
        ).most_common(10),
        "gemini": side("gemini"),
        "jev": side("jev"),
    }


def render_markdown(summary: dict, *, until: str = "", today: date | None = None) -> str:
    """Render the summary for a GitHub issue comment."""

    today = today or datetime.now(TAIPEI).date()
    finished = bool(until) and today > date.fromisoformat(until)
    agreement = summary["agreement"]

    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1%}"

    lines = [
        f"## EDF policy shadow report — {today.isoformat()}" + (" (final)" if finished else ""),
        "",
        f"- Window: {summary['first_day']} → {summary['last_day']} ({summary['days_with_traffic']} days with traffic)"
        + (f", planned end {until}" if until else ""),
        f"- Records: {summary['records']}; both answered: {agreement['turns']} (need {summary['min_samples']}) → **{summary['verdict']}**",
        f"- Agreement: mode {pct(agreement['mode'])}, move {pct(agreement['move'])}, depth {pct(agreement['depth'])}",
        f"- With PDF: {summary['agreement_with_pdf']['turns']} turns, mode {pct(summary['agreement_with_pdf']['mode'])}",
        f"- Practice protected by only one side: Gemini {summary['practice_only_gemini']}, Jev {summary['practice_only_jev']}",
        "",
        "| | p50 | p95 | answered within budget | statuses |",
        "|---|---|---|---|---|",
    ]
    def ms(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.0f} ms"

    for name in ("gemini", "jev"):
        data = summary[name]
        lines.append(f"| {name} | {ms(data['p50_ms'])} | {ms(data['p95_ms'])} | {pct(data['in_budget'])} | {data['statuses']} |")
    if summary["top_disagreements"]:
        lines += ["", "Top disagreements (Gemini → Jev):", ""]
        lines += [f"- `{pair}` × {count}" for pair, count in summary["top_disagreements"]]
    if finished:
        lines += [
            "",
            "### Next steps",
            "- [ ] Review the disagreements above, especially practice turns protected by only one side.",
            "- [ ] If agreement and practice protection look good, run the eval A/B with `POLICY_CLASSIFIER_BACKEND=jev` "
            "(see `teaching-layer-eval-baseline` notes: tag candidate URLs with `?variant=`).",
            "- [ ] Decide: switch Render to `jev` and lower `POLICY_CLASSIFIER_TIMEOUT_MS` to ~700, or stay on `gemini`.",
            "- [ ] Remove `POLICY_CLASSIFIER_BACKEND=shadow` / `POLICY_SHADOW_UNTIL` from Render (shadow already stopped by date).",
        ]
    return "\n".join(lines) + "\n"


def load_records(redis_url: str) -> list[dict]:
    import redis

    client = redis.from_url(redis_url, decode_responses=True, socket_timeout=10)
    return [json.loads(item) for item in client.lrange(SHADOW_KEY, 0, -1)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until", default=os.getenv("POLICY_SHADOW_UNTIL", ""), help="Planned last day (YYYY-MM-DD).")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        parser.exit(2, "REDIS_URL must be set in the environment.\n")
    report = summarize(load_records(redis_url), min_samples=args.min_samples)
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report, until=args.until), end="")
