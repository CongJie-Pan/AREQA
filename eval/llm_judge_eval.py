#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "eval" / "datasets" / "english_tutor_cases_eval.json"
DEFAULT_RUBRIC = ROOT / "eval" / "rubrics" / "learnlm_pedagogy_rubric.md"
DEFAULT_OUTPUT_DIR = ROOT / "eval" / "outputs"
DEFAULT_CACHE = DEFAULT_OUTPUT_DIR / "llm_judge_cache.json"
PEDAGOGY_TUTOR_SKILL = ROOT / "backend" / "prompts" / "skills" / "pedagogy_tutor_skill.md"
ENGLISH_TUTOR_SKILL = ROOT / "backend" / "prompts" / "skills" / "english_tutor_skill.md"

SINGLE_RUBRIC_DIMENSIONS = [
    "instruction_following",
    "cognitive_load",
    "active_learning",
    "metacognition",
    "curiosity_affect",
    "adaptivity",
    "factual_accuracy_uncertainty",
    "learning_goal_support",
    "overall_tutor_quality",
]

PAIRWISE_DIMENSIONS = [
    "better_pedagogy",
    "more_like_good_human_tutor",
    "better_instruction_following",
    "better_adapted_to_learner",
    "better_supported_learning_goal",
]


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: str
    subject_area: str
    subtopic: str
    learning_goal: str
    setting: str
    learner_persona: list[str]
    scenario_instructions: str
    initial_query: str
    expected_tutor_behavior: list[str]


@dataclass(frozen=True)
class EvalSkillContext:
    """Skill specifications used by the judge for profile-specific evaluation.

    Args:
        tutor_profile: Candidate tutor profile being evaluated.
        skill_ids: Stable skill identifiers expected in the evaluated behavior.
        text: Compact concatenation of the relevant skill specifications.

    Side effects:
        None.

    Compatibility:
        Skill context is sent only to the judge and written to reports. It is
        deliberately not sent to the AREQA candidate request, so each eval case
        still measures runtime prompt/profile behavior.
    """

    tutor_profile: str
    skill_ids: tuple[str, ...]
    text: str


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL row") from exc
    return rows


def load_cases(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for row in load_jsonl(path):
        cases.append(
            EvalCase(
                case_id=str(row["case_id"]),
                category=str(row["category"]),
                subject_area=str(row["subject_area"]),
                subtopic=str(row["subtopic"]),
                learning_goal=str(row["learning_goal"]),
                setting=str(row["setting"]),
                learner_persona=list(row["learner_persona"]),
                scenario_instructions=str(row["scenario_instructions"]),
                initial_query=str(row["initial_query"]),
                expected_tutor_behavior=list(row["expected_tutor_behavior"]),
            )
        )
    return cases


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_skill_spec(path: Path) -> str:
    """Read a skill specification for judge-only evaluation context."""

    return path.read_text(encoding="utf-8").strip()


def resolve_eval_skill_context(tutor_profile: str) -> EvalSkillContext:
    """Return the skill contract context expected for an eval tutor profile.

    Args:
        tutor_profile: Raw tutor profile value from CLI arguments.

    Returns:
        The base pedagogy skill for general profile, and base pedagogy plus the
        English subject overlay for the English tutor profile.

    Side effects:
        Reads local skill specification markdown files.

    Raises:
        ValueError: If an unsupported tutor profile is supplied.
    """

    normalized = str(tutor_profile or "general").strip().lower()
    if normalized == "general":
        return EvalSkillContext(
            tutor_profile="general",
            skill_ids=("PEDAGOGY_TUTOR_SKILL_V1",),
            text=_read_skill_spec(PEDAGOGY_TUTOR_SKILL),
        )
    if normalized == "english":
        specs = [
            _read_skill_spec(PEDAGOGY_TUTOR_SKILL),
            _read_skill_spec(ENGLISH_TUTOR_SKILL),
        ]
        return EvalSkillContext(
            tutor_profile="english",
            skill_ids=("PEDAGOGY_TUTOR_SKILL_V1", "ENGLISH_TUTOR_SKILL_V1"),
            text="\n\n---\n\n".join(specs),
        )
    raise ValueError(f"unsupported tutor profile for eval: {tutor_profile}")


def cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def parse_sse_text(body: str) -> str:
    chunks: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if isinstance(event, dict) and event.get("error"):
            chunks.append(f"[ERROR] {event['error']}")
            continue
        for choice in event.get("choices", []):
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str):
                chunks.append(content)
    return "".join(chunks).strip()


def call_areqa_stream(
    *,
    candidate_url: str,
    case: EvalCase,
    timeout: float,
    use_rag: bool,
    use_web_search: bool,
    max_tokens: int,
    temperature: float,
    tutor_profile: str,
) -> str:
    payload = {
        "messages": [{"role": "user", "content": case.initial_query}],
        "conversation_id": f"eval-{case.case_id}-{uuid.uuid4()}",
        "use_rag": use_rag,
        "use_web_search": use_web_search,
        "search_mode": "never",
        "interface_language": "en",
        "tutor_profile": tutor_profile,
        "response_mode": "text",
        "force_think": False,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
    }
    status, body = post_json(
        candidate_url,
        payload,
        {"Content-Type": "application/json"},
        timeout,
    )
    if status >= 400:
        raise RuntimeError(f"AREQA candidate request failed with HTTP {status}: {body[:500]}")
    text = parse_sse_text(body)
    if not text:
        raise RuntimeError("AREQA candidate returned an empty SSE response")
    return text


def call_openrouter_chat(
    *,
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
    timeout: float,
    max_tokens: int,
    temperature: float,
    response_format: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format
    status, body = post_json(
        "https://openrouter.ai/api/v1/chat/completions",
        payload,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/AREQA/eval",
            "X-Title": "AREQA LLM Judge Eval",
        },
        timeout,
    )
    if status >= 400:
        raise RuntimeError(f"OpenRouter request failed for {model} with HTTP {status}: {body[:500]}")
    try:
        response = json.loads(body)
        return str(response["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenRouter response for {model} did not contain message content") from exc


def build_baseline_messages(case: EvalCase) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a helpful English humanities tutor. Answer the learner's message naturally. "
                "Do not use external retrieval tools."
            ),
        },
        {"role": "user", "content": case.initial_query},
    ]


def render_case_for_judge(case: EvalCase) -> str:
    return json.dumps(
        {
            "case_id": case.case_id,
            "category": case.category,
            "subject_area": case.subject_area,
            "subtopic": case.subtopic,
            "learning_goal": case.learning_goal,
            "setting": case.setting,
            "learner_persona": case.learner_persona,
            "scenario_instructions": case.scenario_instructions,
            "initial_query": case.initial_query,
            "expected_tutor_behavior": case.expected_tutor_behavior,
        },
        ensure_ascii=False,
        indent=2,
    )


def build_judge_prompt(
    *,
    case: EvalCase,
    rubric_text: str,
    candidate_answer: str,
    baseline_answer: str,
    candidate_label: str,
    baseline_label: str,
    skill_context: EvalSkillContext,
) -> str:
    profile_note = (
        "general AREQA pedagogy tutor"
        if skill_context.tutor_profile == "general"
        else "AREQA English tutor overlay on the general pedagogy tutor"
    )
    return f"""You are an expert pedagogy evaluator for AREQA text tutoring.

Evaluate two tutor answers for the same learner query. The learner query is the only
message sent to the tutors. The scenario metadata is for your evaluation context.

Do not reward verbosity. Reward helpful tutoring that supports learning, follows
the scenario, manages cognitive load, and avoids simply doing the learner's work.
Evaluate the candidate against the active AREQA skill contract, not against a
generic prompt-writing style. The active candidate target is: {profile_note}.

Return JSON only, with this exact shape:
{{
  "candidate_single_scores": {{
    "instruction_following": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "cognitive_load": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "active_learning": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "metacognition": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "curiosity_affect": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "adaptivity": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "factual_accuracy_uncertainty": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "learning_goal_support": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "overall_tutor_quality": {{"score": 1, "rationale": "...", "evidence": ["..."]}}
  }},
  "baseline_single_scores": {{
    "instruction_following": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "cognitive_load": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "active_learning": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "metacognition": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "curiosity_affect": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "adaptivity": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "factual_accuracy_uncertainty": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "learning_goal_support": {{"score": 1, "rationale": "...", "evidence": ["..."]}},
    "overall_tutor_quality": {{"score": 1, "rationale": "...", "evidence": ["..."]}}
  }},
  "pairwise_preferences": {{
    "better_pedagogy": 0,
    "more_like_good_human_tutor": 0,
    "better_instruction_following": 0,
    "better_adapted_to_learner": 0,
    "better_supported_learning_goal": 0
  }},
  "winner": "candidate|baseline|tie",
  "candidate_critical_failures": [],
  "baseline_critical_failures": [],
  "shared_critical_failures": [],
  "summary": "short comparison"
}}

Single scores must be integers from 1 to 7.
Pairwise preferences must be integers from -3 to +3, where positive favors
{candidate_label} and negative favors {baseline_label}.

Rubric:
{rubric_text}

Active AREQA skill contract for the candidate:
skill_ids: {", ".join(skill_context.skill_ids)}
{skill_context.text}

Scenario:
{render_case_for_judge(case)}

{candidate_label} answer:
{candidate_answer}

{baseline_label} answer:
{baseline_answer}
"""


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("judge response did not contain a JSON object")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("judge JSON was not an object")
    return parsed


def clamp_int(value: Any, lower: int, upper: int) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        numeric = lower
    return max(lower, min(upper, numeric))


def normalize_score_block(block: Any) -> dict[str, dict[str, Any]]:
    block = block if isinstance(block, dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for dimension in SINGLE_RUBRIC_DIMENSIONS:
        raw = block.get(dimension, {})
        if not isinstance(raw, dict):
            raw = {"score": raw}
        evidence = raw.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        if not isinstance(evidence, list):
            evidence = []
        normalized[dimension] = {
            "score": clamp_int(raw.get("score"), 1, 7),
            "rationale": str(raw.get("rationale", ""))[:1000],
            "evidence": [str(item)[:500] for item in evidence[:3]],
        }
    return normalized


def normalize_failure_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        value = []
    return [str(item)[:500] for item in value]


def normalize_judge_result(raw: dict[str, Any]) -> dict[str, Any]:
    pairwise = raw.get("pairwise_preferences", {})
    pairwise = pairwise if isinstance(pairwise, dict) else {}
    normalized_pairwise = {
        dimension: clamp_int(pairwise.get(dimension), -3, 3)
        for dimension in PAIRWISE_DIMENSIONS
    }
    candidate_failures = normalize_failure_list(raw.get("candidate_critical_failures"))
    baseline_failures = normalize_failure_list(raw.get("baseline_critical_failures"))
    shared_failures = normalize_failure_list(raw.get("shared_critical_failures"))
    legacy_failures = normalize_failure_list(raw.get("critical_failures"))
    if legacy_failures and not any((candidate_failures, baseline_failures, shared_failures)):
        shared_failures = legacy_failures
    winner = str(raw.get("winner", "tie")).lower()
    if winner not in {"candidate", "baseline", "tie"}:
        mean_pref = statistics.fmean(normalized_pairwise.values())
        winner = "candidate" if mean_pref > 0 else "baseline" if mean_pref < 0 else "tie"
    return {
        "candidate_single_scores": normalize_score_block(raw.get("candidate_single_scores")),
        "baseline_single_scores": normalize_score_block(raw.get("baseline_single_scores")),
        "pairwise_preferences": normalized_pairwise,
        "winner": winner,
        "candidate_critical_failures": candidate_failures,
        "baseline_critical_failures": baseline_failures,
        "shared_critical_failures": shared_failures,
        "critical_failures": candidate_failures + baseline_failures + shared_failures,
        "summary": str(raw.get("summary", ""))[:2000],
    }


def mean_single_score(scores: dict[str, dict[str, Any]]) -> float:
    return round(statistics.fmean(item["score"] for item in scores.values()), 3)


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "cases": 0,
            "overall": {},
            "by_category": {},
            "by_learning_goal": {},
            "rubric_means": {},
        }

    candidate_scores = [row["metrics"]["candidate_mean_score"] for row in results]
    baseline_scores = [row["metrics"]["baseline_mean_score"] for row in results]
    pairwise_means = [row["metrics"]["pairwise_mean_preference"] for row in results]
    candidate_wins = sum(1 for row in results if row["judge"]["winner"] == "candidate")
    baseline_wins = sum(1 for row in results if row["judge"]["winner"] == "baseline")
    ties = len(results) - candidate_wins - baseline_wins
    candidate_critical_failures = sum(
        len(row["judge"].get("candidate_critical_failures", [])) for row in results
    )
    baseline_critical_failures = sum(
        len(row["judge"].get("baseline_critical_failures", [])) for row in results
    )
    shared_critical_failures = sum(
        len(row["judge"].get("shared_critical_failures", [])) for row in results
    )
    critical_failures = candidate_critical_failures + baseline_critical_failures + shared_critical_failures

    summary = {
        "cases": len(results),
        "overall": {
            "candidate_mean_score": round(statistics.fmean(candidate_scores), 3),
            "baseline_mean_score": round(statistics.fmean(baseline_scores), 3),
            "mean_score_delta": round(statistics.fmean(candidate_scores) - statistics.fmean(baseline_scores), 3),
            "mean_pairwise_preference": round(statistics.fmean(pairwise_means), 3),
            "candidate_win_rate": round(candidate_wins / len(results), 3),
            "baseline_win_rate": round(baseline_wins / len(results), 3),
            "tie_rate": round(ties / len(results), 3),
            "critical_failures": critical_failures,
            "candidate_critical_failures": candidate_critical_failures,
            "baseline_critical_failures": baseline_critical_failures,
            "shared_critical_failures": shared_critical_failures,
        },
        "by_category": aggregate_group(results, "category"),
        "by_learning_goal": aggregate_group(results, "learning_goal"),
        "rubric_means": aggregate_rubric_means(results),
    }
    return summary


def aggregate_group(results: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        groups.setdefault(str(row["case"][field]), []).append(row)
    output: dict[str, Any] = {}
    for name, rows in sorted(groups.items()):
        candidate_wins = sum(1 for row in rows if row["judge"]["winner"] == "candidate")
        baseline_wins = sum(1 for row in rows if row["judge"]["winner"] == "baseline")
        output[name] = {
            "count": len(rows),
            "candidate_mean_score": round(statistics.fmean(row["metrics"]["candidate_mean_score"] for row in rows), 3),
            "baseline_mean_score": round(statistics.fmean(row["metrics"]["baseline_mean_score"] for row in rows), 3),
            "mean_pairwise_preference": round(statistics.fmean(row["metrics"]["pairwise_mean_preference"] for row in rows), 3),
            "candidate_win_rate": round(candidate_wins / len(rows), 3),
            "baseline_win_rate": round(baseline_wins / len(rows), 3),
        }
    return output


def aggregate_rubric_means(results: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for dimension in SINGLE_RUBRIC_DIMENSIONS:
        candidate = [
            row["judge"]["candidate_single_scores"][dimension]["score"]
            for row in results
        ]
        baseline = [
            row["judge"]["baseline_single_scores"][dimension]["score"]
            for row in results
        ]
        output[dimension] = {
            "candidate": round(statistics.fmean(candidate), 3),
            "baseline": round(statistics.fmean(baseline), 3),
            "delta": round(statistics.fmean(candidate) - statistics.fmean(baseline), 3),
        }
    return output


def svg_bar_chart(title: str, values: dict[str, float], path: Path, *, max_value: float | None = None) -> None:
    width = 840
    row_h = 42
    margin_l = 250
    margin_r = 40
    margin_t = 64
    height = margin_t + row_h * max(1, len(values)) + 36
    max_v = max_value or max([abs(v) for v in values.values()] + [1.0])
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="24" y="34" font-family="Arial" font-size="22" font-weight="700">{html.escape(title)}</text>',
    ]
    for idx, (label, value) in enumerate(values.items()):
        y = margin_t + idx * row_h
        bar_w = int((abs(value) / max_v) * (width - margin_l - margin_r))
        color = "#1f77b4" if value >= 0 else "#d62728"
        lines.append(f'<text x="24" y="{y + 23}" font-family="Arial" font-size="14">{html.escape(label)}</text>')
        lines.append(f'<rect x="{margin_l}" y="{y + 7}" width="{bar_w}" height="22" fill="{color}" rx="3"/>')
        lines.append(f'<text x="{margin_l + bar_w + 8}" y="{y + 23}" font-family="Arial" font-size="14">{value:.3g}</text>')
    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_charts(summary: dict[str, Any], charts_dir: Path) -> None:
    charts_dir.mkdir(parents=True, exist_ok=True)
    overall = summary.get("overall", {})
    svg_bar_chart(
        "Overall Mean Scores",
        {
            "candidate": float(overall.get("candidate_mean_score", 0)),
            "baseline": float(overall.get("baseline_mean_score", 0)),
            "candidate win rate": float(overall.get("candidate_win_rate", 0)),
        },
        charts_dir / "overall_scores.svg",
        max_value=7,
    )
    rubric_values = {
        key: float(value.get("delta", 0))
        for key, value in summary.get("rubric_means", {}).items()
    }
    svg_bar_chart(
        "Rubric Delta: Candidate Minus Baseline",
        rubric_values,
        charts_dir / "rubric_delta.svg",
        max_value=max([abs(v) for v in rubric_values.values()] + [1.0]),
    )
    category_values = {
        key: float(value.get("candidate_win_rate", 0))
        for key, value in summary.get("by_category", {}).items()
    }
    svg_bar_chart(
        "Candidate Win Rate By Category",
        category_values,
        charts_dir / "win_rate_by_category.svg",
        max_value=1,
    )


def write_report(summary: dict[str, Any], output_dir: Path, args: argparse.Namespace) -> None:
    overall = summary.get("overall", {})
    skill_context = resolve_eval_skill_context(args.tutor_profile)
    lines = [
        "# AREQA Text Tutor LLM Judge Eval Report",
        "",
        f"- Dataset: `{args.dataset}`",
        f"- Candidate source: `{args.candidate_url}`",
        f"- Tutor profile: `{args.tutor_profile}`",
        f"- Eval skill IDs: `{', '.join(skill_context.skill_ids)}`",
        f"- Baseline model: `{args.baseline_model}`",
        f"- Judge model: `{args.judge_model}`",
        f"- Cases: `{summary.get('cases', 0)}`",
        "",
        "## Overall",
        "",
        f"- Candidate mean score: `{overall.get('candidate_mean_score', 0)}`",
        f"- Baseline mean score: `{overall.get('baseline_mean_score', 0)}`",
        f"- Mean score delta: `{overall.get('mean_score_delta', 0)}`",
        f"- Mean pairwise preference: `{overall.get('mean_pairwise_preference', 0)}`",
        f"- Candidate win rate: `{overall.get('candidate_win_rate', 0)}`",
        f"- Baseline win rate: `{overall.get('baseline_win_rate', 0)}`",
        f"- Critical failures: `{overall.get('critical_failures', 0)}`",
        f"- Candidate critical failures: `{overall.get('candidate_critical_failures', 0)}`",
        f"- Baseline critical failures: `{overall.get('baseline_critical_failures', 0)}`",
        f"- Shared critical failures: `{overall.get('shared_critical_failures', 0)}`",
        "",
        "## Charts",
        "",
        "- [Overall Scores](charts/overall_scores.svg)",
        "- [Rubric Delta](charts/rubric_delta.svg)",
        "- [Win Rate By Category](charts/win_rate_by_category.svg)",
        "",
        "## By Category",
        "",
        "| Category | Count | Candidate | Baseline | Pairwise | Win Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for category, row in summary.get("by_category", {}).items():
        lines.append(
            f"| {category} | {row['count']} | {row['candidate_mean_score']} | "
            f"{row['baseline_mean_score']} | {row['mean_pairwise_preference']} | {row['candidate_win_rate']} |"
        )
    lines.extend(["", "## Rubric Means", "", "| Dimension | Candidate | Baseline | Delta |", "|---|---:|---:|---:|"])
    for dimension, row in summary.get("rubric_means", {}).items():
        lines.append(f"| {dimension} | {row['candidate']} | {row['baseline']} | {row['delta']} |")
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def case_to_public_dict(case: EvalCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "category": case.category,
        "subject_area": case.subject_area,
        "subtopic": case.subtopic,
        "learning_goal": case.learning_goal,
        "setting": case.setting,
    }


def run_case(
    *,
    case: EvalCase,
    args: argparse.Namespace,
    rubric_text: str,
    cache: dict[str, Any],
    api_key: str,
    skill_context: EvalSkillContext | None = None,
) -> dict[str, Any]:
    skill_context = skill_context or resolve_eval_skill_context(args.tutor_profile)
    candidate_key = cache_key(
        "candidate",
        args.candidate_url,
        args.no_rag,
        args.max_tokens,
        args.temperature,
        args.tutor_profile,
        case.case_id,
        case.initial_query,
    )
    if args.refresh_cache or candidate_key not in cache:
        cache[candidate_key] = call_areqa_stream(
            candidate_url=args.candidate_url,
            case=case,
            timeout=args.timeout,
            use_rag=not args.no_rag,
            use_web_search=False,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            tutor_profile=args.tutor_profile,
        )
    candidate_answer = str(cache[candidate_key])

    baseline_key = cache_key(
        "baseline",
        args.baseline_model,
        args.max_tokens,
        args.temperature,
        case.case_id,
        case.initial_query,
    )
    if args.refresh_cache or baseline_key not in cache:
        cache[baseline_key] = call_openrouter_chat(
            model=args.baseline_model,
            messages=build_baseline_messages(case),
            api_key=api_key,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    baseline_answer = str(cache[baseline_key])

    judge_prompt = build_judge_prompt(
        case=case,
        rubric_text=rubric_text,
        candidate_answer=candidate_answer,
        baseline_answer=baseline_answer,
        candidate_label="AREQA candidate",
        baseline_label=args.baseline_model,
        skill_context=skill_context,
    )
    judge_key = cache_key(
        "judge",
        args.judge_model,
        case.case_id,
        candidate_answer,
        baseline_answer,
        rubric_text,
        skill_context.skill_ids,
        skill_context.text,
    )
    if args.refresh_cache or judge_key not in cache:
        judge_content = call_openrouter_chat(
            model=args.judge_model,
            messages=[
                {"role": "system", "content": "Return strict JSON only. Do not include markdown."},
                {"role": "user", "content": judge_prompt},
            ],
            api_key=api_key,
            timeout=args.timeout,
            max_tokens=args.judge_max_tokens,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        cache[judge_key] = normalize_judge_result(extract_json_object(judge_content))
    judge = normalize_judge_result(cache[judge_key])

    candidate_mean = mean_single_score(judge["candidate_single_scores"])
    baseline_mean = mean_single_score(judge["baseline_single_scores"])
    pairwise_mean = round(statistics.fmean(judge["pairwise_preferences"].values()), 3)
    return {
        "case": case_to_public_dict(case),
        "eval_skill_context": {
            "tutor_profile": skill_context.tutor_profile,
            "skill_ids": list(skill_context.skill_ids),
        },
        "input": {"initial_query": case.initial_query},
        "candidate": {"source": args.candidate_url, "answer": candidate_answer},
        "baseline": {"model": args.baseline_model, "answer": baseline_answer},
        "judge": judge,
        "metrics": {
            "candidate_mean_score": candidate_mean,
            "baseline_mean_score": baseline_mean,
            "score_delta": round(candidate_mean - baseline_mean, 3),
            "pairwise_mean_preference": pairwise_mean,
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate AREQA text tutor answers with a LearnLM-style LLM judge.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cache-file", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--candidate-url", default="http://127.0.0.1:8000/api/v1/stream")
    parser.add_argument("--baseline-model", default="google/gemini-3.8-flash")
    parser.add_argument("--judge-model", default="openai/gpt-5.6-luna")
    parser.add_argument(
        "--tutor-profile",
        choices=["general", "english"],
        default="english",
        help="AREQA tutor profile to apply to candidate answers.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Evaluate only the specified case id. Repeat for multiple cases.",
    )
    parser.add_argument("--max-cases", type=int, default=0, help="Limit cases for smoke runs. 0 means all.")
    parser.add_argument("--max-tokens", type=int, default=2400)
    parser.add_argument("--judge-max-tokens", type=int, default=3500)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--no-rag", action="store_true", default=True)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--min-candidate-mean", type=float, default=0.0)
    parser.add_argument("--min-win-rate", type=float, default=0.0)
    parser.add_argument("--max-critical-failures", type=int, default=999999)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("OPENROUTER_API_KEY is required for baseline and judge calls.", file=sys.stderr)
        return 2

    cases = load_cases(args.dataset)
    if args.case_id:
        requested = set(args.case_id)
        cases = [case for case in cases if case.case_id in requested]
        missing = sorted(requested - {case.case_id for case in cases})
        if missing:
            print(f"Requested case ids not found: {', '.join(missing)}", file=sys.stderr)
            return 2
    if args.max_cases > 0:
        cases = cases[: args.max_cases]
    rubric_text = args.rubric.read_text(encoding="utf-8")
    skill_context = resolve_eval_skill_context(args.tutor_profile)
    cache = load_cache(args.cache_file)

    run_id = dt.datetime.now(dt.UTC).strftime("run_%Y%m%d_%H%M%S")
    output_dir = args.output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    raw_path = output_dir / "raw_results.jsonl"
    with raw_path.open("w", encoding="utf-8") as raw_file:
        for idx, case in enumerate(cases, start=1):
            started = time.monotonic()
            print(f"[{idx}/{len(cases)}] evaluating {case.case_id}", file=sys.stderr)
            result = run_case(
                case=case,
                args=args,
                rubric_text=rubric_text,
                cache=cache,
                api_key=api_key,
                skill_context=skill_context,
            )
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            results.append(result)
            raw_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            raw_file.flush()
            save_cache(args.cache_file, cache)

    summary = aggregate_results(results)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_charts(summary, output_dir / "charts")
    write_report(summary, output_dir, args)

    overall = summary.get("overall", {})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    passed = (
        float(overall.get("candidate_mean_score", 0.0)) >= args.min_candidate_mean
        and float(overall.get("candidate_win_rate", 0.0)) >= args.min_win_rate
        and int(overall.get("critical_failures", 0)) <= args.max_critical_failures
    )
    print(f"Report: {output_dir / 'report.md'}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
