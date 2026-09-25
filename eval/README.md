# AREQA Text Tutor LLM Judge Eval

This folder contains offline evaluation tooling for AREQA's text-only tutor answers.

The evaluation target is skill-aligned text tutoring without RAG, web search,
voice, LiveKit, or avatar flows. Each case sends only the learner's
`initial_query` to AREQA. Scenario metadata and skill specs are kept for the
judge so the score reflects the intended learning context without injecting
extra per-case system prompts into AREQA.

The runner loads skill specs by tutor profile:

- `general`: `PEDAGOGY_TUTOR_SKILL_V1`
- `english`: `PEDAGOGY_TUTOR_SKILL_V1` + `ENGLISH_TUTOR_SKILL_V1`

The English judge contract uses the same runtime rules rendered by
`backend/services/tutor_profile_service.py`. The Markdown skill describes those
rules for maintainers.

## Run

Start the backend first:

```bash
./backend/.venv/bin/python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Then run:

```bash
python eval/llm_judge_eval.py \
  --dataset eval/datasets/english_tutor_cases_eval.json \
  --candidate-url http://127.0.0.1:8000/api/v1/stream \
  --tutor-profile english \
  --baseline-model google/gemini-3.8-flash \
  --judge-model openai/gpt-5.6-luna \
  --no-rag
```

For the general pedagogy skill, use:

```bash
python eval/llm_judge_eval.py \
  --dataset eval/datasets/pedagogy_general_skill_cases.jsonl \
  --candidate-url http://127.0.0.1:8000/api/v1/stream \
  --tutor-profile general \
  --baseline-model google/gemini-3.8-flash \
  --judge-model openai/gpt-5.6-luna \
  --no-rag
```

The default answer budget is `--max-tokens 2400`. A smaller budget caused
truncated tutor answers in early validation runs, while larger budgets increase
cost without consistently reducing judge-reported failures.

The script writes a timestamped run folder under `eval/outputs/` with:

- `raw_results.jsonl`: one full result per case.
- `summary.json`: aggregate metrics.
- `report.md`: human-readable report.
- `charts/*.svg`: generated charts.

Human-readable dataset mirrors are available under `eval/datasets/markdown/`.

## Evaluation Shape

The rubric is adapted from the LearnLM evaluation design:

- scenario-guided learner tasks
- single-conversation pedagogical scoring
- pairwise candidate-vs-baseline preference
- active AREQA skill contract supplied to the judge
- aggregation by category and learning goal

The runner intentionally uses a compact rubric rather than the full LearnLM 29-item
survey so it can be run regularly without excessive cost.
