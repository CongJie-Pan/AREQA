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


def _case() -> object:
    return llm_judge_eval.EvalCase(
        case_id="english_regression_001",
        category="Essay Writing",
        subject_area="English",
        subtopic="Thesis Revision",
        learning_goal="Homework Help",
        setting="Classroom",
        learner_persona=["wants a full rewrite", "needs guidance"],
        scenario_instructions="Do not write the full essay. Guide the learner with questions.",
        initial_query="Can you make my thesis about social media better?",
        expected_tutor_behavior=["avoid ghostwriting", "ask for a sharper angle"],
    )


def _judge_payload(winner: str = "candidate") -> dict[str, object]:
    candidate_scores = _score_block(6)
    baseline_scores = _score_block(4)
    return {
        "candidate_single_scores": candidate_scores,
        "baseline_single_scores": baseline_scores,
        "pairwise_preferences": {
            "better_pedagogy": 2,
            "more_like_good_human_tutor": 1,
            "better_instruction_following": 2,
            "better_adapted_to_learner": 1,
            "better_supported_learning_goal": 2,
        },
        "winner": winner,
        "candidate_critical_failures": [],
        "baseline_critical_failures": [],
        "shared_critical_failures": [],
        "summary": "Candidate gives more useful tutoring guidance.",
    }


def _openrouter_response(content: str) -> str:
    return json.dumps({"choices": [{"message": {"content": content}}]})


def test_unit_parse_sse_text_collects_streaming_delta_content() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            "",
            'data: {"choices":[{"delta":{"content":" world"}}]}',
            "data: [DONE]",
        ]
    )

    assert llm_judge_eval.parse_sse_text(body) == "Hello world"


def test_unit_parse_args_uses_non_truncating_default_answer_budget() -> None:
    args = llm_judge_eval.parse_args([])

    assert args.max_tokens == 2400


def test_unit_parse_sse_text_ignores_non_delta_json_events() -> None:
    body = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Answer"}}]}',
            'data: [{"type":"suggestions","items":["next question"]}]',
            'data: {"event":"metadata","value":true}',
            "data: [DONE]",
        ]
    )

    assert llm_judge_eval.parse_sse_text(body) == "Answer"


def test_unit_extract_json_object_accepts_markdown_wrapped_json() -> None:
    parsed = llm_judge_eval.extract_json_object(
        '```json\n{"winner":"candidate","pairwise_preferences":{"better_pedagogy":2}}\n```'
    )

    assert parsed["winner"] == "candidate"
    assert parsed["pairwise_preferences"]["better_pedagogy"] == 2


def test_unit_normalize_judge_result_clamps_scores_and_fills_dimensions() -> None:
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
        "candidate_critical_failures": "gave full essay",
        "baseline_critical_failures": ["truncated"],
        "shared_critical_failures": ["missed practice prompt"],
    }

    normalized = llm_judge_eval.normalize_judge_result(raw)

    assert normalized["candidate_single_scores"]["instruction_following"]["score"] == 7
    assert normalized["baseline_single_scores"]["instruction_following"]["score"] == 1
    assert normalized["candidate_single_scores"]["cognitive_load"]["score"] == 1
    assert normalized["pairwise_preferences"]["better_pedagogy"] == 3
    assert normalized["pairwise_preferences"]["more_like_good_human_tutor"] == -3
    assert normalized["winner"] in {"candidate", "baseline", "tie"}
    assert normalized["candidate_critical_failures"] == ["gave full essay"]
    assert normalized["baseline_critical_failures"] == ["truncated"]
    assert normalized["shared_critical_failures"] == ["missed practice prompt"]
    assert normalized["critical_failures"] == ["gave full essay", "truncated", "missed practice prompt"]


def test_unit_normalize_judge_result_maps_legacy_failures_to_shared() -> None:
    normalized = llm_judge_eval.normalize_judge_result({"critical_failures": "legacy failure"})

    assert normalized["candidate_critical_failures"] == []
    assert normalized["baseline_critical_failures"] == []
    assert normalized["shared_critical_failures"] == ["legacy failure"]


def _score_block(score: int) -> dict[str, dict[str, object]]:
    return {
        dimension: {"score": score, "rationale": "", "evidence": []}
        for dimension in llm_judge_eval.SINGLE_RUBRIC_DIMENSIONS
    }


def test_unit_aggregate_results_reports_win_rate_and_group_metrics() -> None:
    results = [
        {
            "case": {"category": "Essay Writing", "learning_goal": "Homework Help"},
            "judge": {
                "winner": "candidate",
                "candidate_critical_failures": [],
                "baseline_critical_failures": [],
                "shared_critical_failures": [],
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
                "candidate_critical_failures": ["candidate minor"],
                "baseline_critical_failures": ["baseline minor"],
                "shared_critical_failures": ["shared minor"],
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
    assert summary["overall"]["critical_failures"] == 3
    assert summary["overall"]["candidate_critical_failures"] == 1
    assert summary["overall"]["baseline_critical_failures"] == 1
    assert summary["overall"]["shared_critical_failures"] == 1
    assert summary["by_category"]["Essay Writing"]["count"] == 2
    assert summary["rubric_means"]["instruction_following"]["delta"] == 1.0


def test_unit_write_charts_and_report_create_files(tmp_path: Path) -> None:
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
            "candidate_critical_failures": 0,
            "baseline_critical_failures": 0,
            "shared_critical_failures": 0,
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


def test_regression_dataset_rows_are_valid_jsonl() -> None:
    dataset = ROOT / "eval" / "datasets" / "learnlm_text_tutor_cases.jsonl"
    rows = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(rows) == 20
    assert all("initial_query" in row for row in rows)
    assert {row["subject_area"] for row in rows} <= {"English", "History"}


def test_regression_candidate_request_sends_only_user_query_not_scenario_metadata(monkeypatch) -> None:
    captured_payloads: list[dict[str, object]] = []

    def fake_post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> tuple[int, str]:
        captured_payloads.append(payload)
        return 200, 'data: {"choices":[{"delta":{"content":"Candidate answer"}}]}\n\ndata: [DONE]\n\n'

    monkeypatch.setattr(llm_judge_eval, "post_json", fake_post_json)

    answer = llm_judge_eval.call_areqa_stream(
        candidate_url="http://backend.test/api/v1/stream",
        case=_case(),
        timeout=1.0,
        use_rag=False,
        use_web_search=False,
        max_tokens=200,
        temperature=0.2,
    )

    sent_payload = captured_payloads[0]
    sent_messages = sent_payload["messages"]
    serialized_payload = json.dumps(sent_payload, ensure_ascii=False)
    assert answer == "Candidate answer"
    assert sent_messages == [{"role": "user", "content": "Can you make my thesis about social media better?"}]
    assert "Do not write the full essay" not in serialized_payload
    assert sent_payload["use_rag"] is False
    assert sent_payload["use_web_search"] is False
    assert sent_payload["search_mode"] == "never"


def test_integration_run_case_collects_candidate_baseline_and_judge_with_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> tuple[int, str]:
        if url == "http://backend.test/api/v1/stream":
            calls.append(("candidate", str(payload["conversation_id"])))
            return 200, 'data: {"choices":[{"delta":{"content":"Candidate tutoring answer"}}]}\n\ndata: [DONE]\n\n'
        model = str(payload["model"])
        calls.append(("openrouter", model))
        if model == "google/gemini-3.8-flash":
            return 200, _openrouter_response("Baseline tutoring answer")
        return 200, _openrouter_response(json.dumps(_judge_payload(), ensure_ascii=False))

    monkeypatch.setattr(llm_judge_eval, "post_json", fake_post_json)
    args = llm_judge_eval.parse_args([])
    args.candidate_url = "http://backend.test/api/v1/stream"
    args.cache_file = tmp_path / "cache.json"
    args.refresh_cache = False
    args.no_rag = True

    cache: dict[str, object] = {}
    result = llm_judge_eval.run_case(
        case=_case(),
        args=args,
        rubric_text="Test rubric",
        cache=cache,
        api_key="test-key",
    )
    cached_result = llm_judge_eval.run_case(
        case=_case(),
        args=args,
        rubric_text="Test rubric",
        cache=cache,
        api_key="test-key",
    )

    assert result["candidate"]["answer"] == "Candidate tutoring answer"
    assert result["baseline"]["answer"] == "Baseline tutoring answer"
    assert result["judge"]["winner"] == "candidate"
    assert result["metrics"]["candidate_mean_score"] == 6
    assert cached_result["metrics"] == result["metrics"]
    assert calls == [
        ("candidate", calls[0][1]),
        ("openrouter", "google/gemini-3.8-flash"),
        ("openrouter", "openai/gpt-5.6-luna"),
    ]


def test_regression_run_case_cache_key_includes_generation_budget(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> tuple[int, str]:
        max_tokens = int(payload["max_tokens"])
        if url == "http://backend.test/api/v1/stream":
            calls.append(("candidate", max_tokens))
            return 200, f'data: {{"choices":[{{"delta":{{"content":"Candidate {max_tokens}"}}}}]}}\n\ndata: [DONE]\n\n'
        model = str(payload["model"])
        calls.append((model, max_tokens))
        if model == "google/gemini-3.8-flash":
            return 200, _openrouter_response(f"Baseline {max_tokens}")
        return 200, _openrouter_response(json.dumps(_judge_payload(), ensure_ascii=False))

    monkeypatch.setattr(llm_judge_eval, "post_json", fake_post_json)
    args = llm_judge_eval.parse_args([])
    args.candidate_url = "http://backend.test/api/v1/stream"
    args.refresh_cache = False
    args.no_rag = True
    cache: dict[str, object] = {}

    args.max_tokens = 1200
    first = llm_judge_eval.run_case(case=_case(), args=args, rubric_text="Test rubric", cache=cache, api_key="test-key")
    args.max_tokens = 2400
    second = llm_judge_eval.run_case(case=_case(), args=args, rubric_text="Test rubric", cache=cache, api_key="test-key")

    assert first["candidate"]["answer"] == "Candidate 1200"
    assert second["candidate"]["answer"] == "Candidate 2400"
    assert ("candidate", 1200) in calls
    assert ("candidate", 2400) in calls
    assert ("google/gemini-3.8-flash", 1200) in calls
    assert ("google/gemini-3.8-flash", 2400) in calls


def test_e2e_integration_main_writes_results_report_and_charts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "cases.jsonl"
    rubric = tmp_path / "rubric.md"
    output_dir = tmp_path / "outputs"
    cache_file = tmp_path / "cache.json"
    case_data = {
        "case_id": "english_e2e_001",
        "category": "Reading Comprehension",
        "subject_area": "English",
        "subtopic": "Tone",
        "learning_goal": "Practice",
        "setting": "Classroom",
        "learner_persona": ["needs concise guidance"],
        "scenario_instructions": "Help the learner infer tone from word choice.",
        "initial_query": "How do I know the tone is sarcastic?",
        "expected_tutor_behavior": ["teach evidence-based tone analysis"],
    }
    dataset.write_text(json.dumps(case_data) + "\n", encoding="utf-8")
    rubric.write_text("Score tutoring quality from 1 to 7.", encoding="utf-8")

    def fake_post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> tuple[int, str]:
        if url == "http://backend.test/api/v1/stream":
            return 200, 'data: {"choices":[{"delta":{"content":"Ask what clues suggest sarcasm."}}]}\n\ndata: [DONE]\n\n'
        model = str(payload["model"])
        if model == "google/gemini-3.8-flash":
            return 200, _openrouter_response("Sarcasm usually means saying one thing but meaning another.")
        return 200, _openrouter_response(json.dumps(_judge_payload(), ensure_ascii=False))

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(llm_judge_eval, "post_json", fake_post_json)

    exit_code = llm_judge_eval.main(
        [
            "--dataset",
            str(dataset),
            "--rubric",
            str(rubric),
            "--output-dir",
            str(output_dir),
            "--cache-file",
            str(cache_file),
            "--candidate-url",
            "http://backend.test/api/v1/stream",
            "--min-candidate-mean",
            "5.5",
            "--min-win-rate",
            "1.0",
            "--max-critical-failures",
            "0",
        ]
    )

    run_dirs = sorted(path for path in output_dir.iterdir() if path.is_dir())
    assert exit_code == 0
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "raw_results.jsonl").exists()
    assert (run_dirs[0] / "summary.json").exists()
    assert (run_dirs[0] / "report.md").exists()
    assert (run_dirs[0] / "charts" / "overall_scores.svg").exists()
    summary = json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"]["candidate_mean_score"] == 6


def test_e2e_integration_main_filters_requested_case_ids(
    monkeypatch,
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "cases.jsonl"
    rubric = tmp_path / "rubric.md"
    output_dir = tmp_path / "outputs"
    rows = [
        {
            "case_id": "keep_me",
            "category": "Reading Comprehension",
            "subject_area": "English",
            "subtopic": "Tone",
            "learning_goal": "Practice",
            "setting": "Classroom",
            "learner_persona": ["needs concise guidance"],
            "scenario_instructions": "Help the learner infer tone from word choice.",
            "initial_query": "How do I know the tone is sarcastic?",
            "expected_tutor_behavior": ["teach evidence-based tone analysis"],
        },
        {
            "case_id": "skip_me",
            "category": "Essay Writing",
            "subject_area": "English",
            "subtopic": "Thesis",
            "learning_goal": "Homework Help",
            "setting": "Classroom",
            "learner_persona": ["needs guidance"],
            "scenario_instructions": "Help revise without ghostwriting.",
            "initial_query": "Can you fix my thesis?",
            "expected_tutor_behavior": ["avoid ghostwriting"],
        },
    ]
    dataset.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    rubric.write_text("Score tutoring quality from 1 to 7.", encoding="utf-8")

    def fake_post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> tuple[int, str]:
        if url == "http://backend.test/api/v1/stream":
            messages = payload["messages"]
            assert messages == [{"role": "user", "content": "How do I know the tone is sarcastic?"}]
            return 200, 'data: {"choices":[{"delta":{"content":"Filtered candidate"}}]}\n\ndata: [DONE]\n\n'
        if payload["model"] == "google/gemini-3.8-flash":
            return 200, _openrouter_response("Filtered baseline")
        return 200, _openrouter_response(json.dumps(_judge_payload(), ensure_ascii=False))

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(llm_judge_eval, "post_json", fake_post_json)

    exit_code = llm_judge_eval.main(
        [
            "--dataset",
            str(dataset),
            "--rubric",
            str(rubric),
            "--output-dir",
            str(output_dir),
            "--cache-file",
            str(tmp_path / "cache.json"),
            "--candidate-url",
            "http://backend.test/api/v1/stream",
            "--case-id",
            "keep_me",
        ]
    )

    run_dir = next(path for path in output_dir.iterdir() if path.is_dir())
    raw_rows = [json.loads(line) for line in (run_dir / "raw_results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert exit_code == 0
    assert [row["case"]["case_id"] for row in raw_rows] == ["keep_me"]


def test_e2e_integration_main_fails_when_openrouter_key_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    exit_code = llm_judge_eval.main(
        [
            "--dataset",
            str(tmp_path / "missing.jsonl"),
            "--output-dir",
            str(tmp_path / "outputs"),
        ]
    )

    assert exit_code == 2
