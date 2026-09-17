# AREQA Text Tutor LLM Judge Eval

This folder contains offline evaluation tooling for AREQA's text-only tutor answers.

The first evaluation target is English humanities tutoring without RAG, web search,
voice, LiveKit, or avatar flows. Each case sends only the learner's `initial_query`
to AREQA. Scenario metadata is kept for the judge so the score reflects the intended
learning context without injecting extra per-case system prompts into AREQA.

## Run

Start the backend first:

```bash
./backend/.venv/bin/python -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Then run:

```bash
python eval/llm_judge_eval.py \
  --dataset eval/datasets/learnlm_text_tutor_cases.jsonl \
  --candidate-url http://127.0.0.1:8000/api/v1/stream \
  --baseline-model google/gemini-3.8-flash \
  --judge-model openai/gpt-5.6-luna \
  --no-rag
```

The script writes a timestamped run folder under `eval/outputs/` with:

- `raw_results.jsonl`: one full result per case.
- `summary.json`: aggregate metrics.
- `report.md`: human-readable report.
- `charts/*.svg`: generated charts.

## Evaluation Shape

The rubric is adapted from the LearnLM evaluation design:

- scenario-guided learner tasks
- single-conversation pedagogical scoring
- pairwise candidate-vs-baseline preference
- aggregation by category and learning goal

The runner intentionally uses a compact rubric rather than the full LearnLM 29-item
survey so it can be run regularly without excessive cost.
