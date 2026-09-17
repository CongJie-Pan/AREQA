from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "eval" / "llm_judge_eval.py"
SPEC = importlib.util.spec_from_file_location("llm_judge_eval", MODULE_PATH)
assert SPEC and SPEC.loader
llm_judge_eval = importlib.util.module_from_spec(SPEC)
sys.modules["llm_judge_eval"] = llm_judge_eval
SPEC.loader.exec_module(llm_judge_eval)


def test_parse_sse_text_collects_streaming_delta_content() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":" world"}}]}',
            "data: [DONE]",
        ]
    )

    assert llm_judge_eval.parse_sse_text(body) == "Hello world"


def test_extract_json_object_accepts_markdown_wrapped_json() -> None:
    parsed = llm_judge_eval.extract_json_object(
        '```json\n{"winner":"candidate","pairwise_preferences":{"better_pedagogy":2}}\n```'
    )

    assert parsed["winner"] == "candidate"
    assert parsed["pairwise_preferences"]["better_pedagogy"] == 2


def test_normalize_judge_result_clamps_scores_and_fills_dimensions() -> None:
    raw = {
        "candidate_single_scores": {
            "instruction_following": {"score": 9, "rationale": "great", "evidence": "clear"}
        },
        "baseline_single_scores": {
            "instruction_following": {"score": 0, "rationale": "weak"}
        },
        "pairwise_preferences": {
            "better_pedagogy": 5,
            "more_like_good_human_tutor": -5,
        },
        "winner": "unexpected",
        "critical_failures": "gave full essay",
    }

    normalized = llm_judge_eval.normalize_judge_result(raw)

    assert normalized["candidate_single_scores"]["instruction_following"]["score"] == 7
    assert normalized["baseline_single_scores"]["instruction_following"]["score"] == 1
    assert normalized["candidate_single_scores"]["cognitive_load"]["score"] == 1
    assert normalized["pairwise_preferences"]["better_pedagogy"] == 3
    assert normalized["pairwise_preferences"]["more_like_good_human_tutor"] == -3
    assert normalized["winner"] in {"candidate", "baseline", "tie"}
    assert normalized["critical_failures"] == ["gave full essay"]


def _score_block(score: int) -> dict[str, dict[str, object]]:
    return {
        dimension: {"score": score, "rationale": "", "evidence": []}
        for dimension in llm_judge_eval.SINGLE_RUBRIC_DIMENSIONS
    }


def test_aggregate_results_reports_win_rate_and_group_metrics() -> None:
    results = [
        {
            "case": {"category": "Essay Writing", "learning_goal": "Homework Help"},
            "judge": {
                "winner": "candidate",
                "critical_failures": [],
                "candidate_single_scores": _score_block(6),
                "baseline_single_scores": _score_block(4),
            },
            "metrics": {
                "candidate_mean_score": 6.0,
                "baseline_mean_score": 4.0,
                "pairwise_mean_preference": 1.0,
            },
        },
        {
            "case": {"category": "Essay Writing", "learning_goal": "Homework Help"},
            "judge": {
                "winner": "tie",
                "critical_failures": ["minor"],
                "candidate_single_scores": _score_block(5),
                "baseline_single_scores": _score_block(5),
            },
            "metrics": {
                "candidate_mean_score": 5.0,
                "baseline_mean_score": 5.0,
                "pairwise_mean_preference": 0.0,
            },
        },
    ]

    summary = llm_judge_eval.aggregate_results(results)

    assert summary["cases"] == 2
    assert summary["overall"]["candidate_mean_score"] == 5.5
    assert summary["overall"]["baseline_mean_score"] == 4.5
    assert summary["overall"]["candidate_win_rate"] == 0.5
    assert summary["overall"]["critical_failures"] == 1
    assert summary["by_category"]["Essay Writing"]["count"] == 2
    assert summary["rubric_means"]["instruction_following"]["delta"] == 1.0


def test_write_charts_and_report_create_files(tmp_path: Path) -> None:
    summary = {
        "cases": 1,
        "overall": {
            "candidate_mean_score": 6.0,
            "baseline_mean_score": 5.0,
            "mean_score_delta": 1.0,
            "mean_pairwise_preference": 1.0,
            "candidate_win_rate": 1.0,
            "baseline_win_rate": 0.0,
            "critical_failures": 0,
        },
        "by_category": {
            "Reading Comprehension": {
                "count": 1,
                "candidate_mean_score": 6.0,
                "baseline_mean_score": 5.0,
                "mean_pairwise_preference": 1.0,
                "candidate_win_rate": 1.0,
                "baseline_win_rate": 0.0,
            }
        },
        "rubric_means": {
            "instruction_following": {"candidate": 6.0, "baseline": 5.0, "delta": 1.0}
        },
    }

    args = llm_judge_eval.parse_args([])
    args.dataset = Path("dataset.jsonl")
    args.candidate_url = "http://backend/api/v1/stream"
    args.baseline_model = "google/gemini-3.8-flash"
    args.judge_model = "openai/gpt-5.6-luna"

    llm_judge_eval.write_charts(summary, tmp_path / "charts")
    llm_judge_eval.write_report(summary, tmp_path, args)

    assert (tmp_path / "charts" / "overall_scores.svg").exists()
    assert (tmp_path / "charts" / "rubric_delta.svg").exists()
    assert (tmp_path / "charts" / "win_rate_by_category.svg").exists()
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "AREQA Text Tutor LLM Judge Eval Report" in report
    assert "google/gemini-3.8-flash" in report


def test_dataset_rows_are_valid_jsonl() -> None:
    dataset = ROOT / "eval" / "datasets" / "learnlm_text_tutor_cases.jsonl"
    rows = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 20
    assert all("initial_query" in row for row in rows)
    assert {row["subject_area"] for row in rows} <= {"English", "History"}
