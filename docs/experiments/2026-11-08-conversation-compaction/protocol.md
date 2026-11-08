# Flash-Lite conversation compaction comparison protocol

Source: local `temp/areqa-chat-2026-11-07.pdf`; do not commit the private PDF,
extracted transcript, complete summaries or credentials. Save raw artifacts only
under `temp/compaction-comparison-2026-11-08/`.

Research question: can Gemini 2.5 Flash-Lite replace 3.1 Flash-Lite for this
conversation's compaction without losing continuation-critical user intent?
A stronger model's suitability is a hypothesis, not an assumed result.

## Inputs and controls

Extract text using pypdf with anchored AREQA role markers. Preserve all 106
messages, including six repeated final user submissions, and record PDF SHA-256.
No OCR, duplicate removal or factual correction. These are conversation claims,
not an independently fact-checked international relations dataset.

- Models: `google/gemini-2.5-flash-lite`, `google/gemini-3.1-flash-lite`.
- Same production summary instruction, temperature 0.1, max_tokens 1536.
- OpenRouter default provider routing; no explicit thinking override. Record actual
  reasoning tokens and cached input tokens rather than assume they are zero.
- Single-pass: three paired trials, alternating model order; all 106 messages in
  one summary request. This measures summary capacity, not production chunking.
- Rolling: one sequence per model at prefixes 25, 51, 77 and 106. Start with empty
  process cache, then reuse valid prefixes. Use production prepare_history with
  context allowance 32768, output reserve 2048, summary cap 1536, total timeout 20s.
- Record call status, actual usage/cost, finish reason and wall time. Completed API
  calls are not automatically accepted summaries: empty/length outputs fail.
- No retry in the benchmark. Cancelled calls can incur unreported charges.

## Quality rubric

Review complete single-pass summaries for these source-grounded items. IDs are
one-based extracted message numbers. Mark present, partial, absent, or contradicted;
do not treat lexical keyword presence as semantic proof. The same investigator
reviews both outputs; this is not an independent or blinded evaluation.

| ID | Evidence | Expected information | Priority |
| --- | --- | --- | --- |
| Q1 | 101–106 | Latest focus: South Korean semiconductor strategic autonomy under Trumpism, using neoclassical realism | Critical |
| Q2 | 13,17 | Overseas international-relations master's application; writing sample/research proposal goal | Critical |
| Q3 | 41 | Preference for qualitative research and a focused, operationalizable question | Critical |
| Q4 | 21,23 | Two selected indicators: subsidy share for Korean investment in US; global irreplaceability of specific Korean chips; reject vague additional indicators | Critical |
| Q5 | 89,91 | Elite perceptions as a core variable; Schweller underbalancing, threat/strategy disagreement and low elite cohesion | Critical |
| Q6 | 95,97,99 | Strategic shirking/de-risking, reducing US dependence and bargaining with existing leverage are explored, not proven outcomes | Critical |
| Q7 | 71,73 | Earlier identity argument: sadae tradition vs national identity; not simply party ideology | Supporting |
| Q8 | 43,47,49 | Earlier France case: normative narratives, securitization and anti-separatism law | Supporting |
| Q9 | 79,81 | User doubts feasibility of a third path; uncertainty must survive | Supporting |
| Q10 | Throughout | Separate user positions from assistant suggestions; no fabricated accepted method, mastery or completed proposal | Critical |

Acceptance is not a single keyword score. Q1 must be present, no critical item
may be contradicted, and omissions must be considered against the tight output
budget. Partial/truncated summaries are diagnostic only, not production-accepted
quality evidence. For rolling outputs, only judge source items already seen and
separate summary information from recent originals/recall snippets.

## Reproduction

Requires backend dependencies plus `pypdf` (installed separately for this local
experiment). Configure root `.env` with `OPENROUTER_API_KEY`; never pass it in CLI.

```sh
backend/.venv/bin/python scripts/evaluate_conversation_compaction.py --pdf temp/areqa-chat-2026-11-07.pdf --output temp/compaction-comparison-2026-11-08 --repetitions 3
```

Limitations: one transcript; three single-pass samples and one rolling sequence
per model; routing/network and cache variability; manually reviewed summaries;
no downstream answer evaluation, durable storage, browser e2e or long-term drift
validation. Initial 1536-token output and chunk-size choices may dominate model
quality. If an intervention is needed, report it separately from the baseline.

## Diagnostic interventions

The baseline instruction allowed transcript copying (2.5) or answering the last
question (3.1). A second, explicitly separate variant changes only the summary
instruction: English state notes, <=450 requested words, fixed sections, no
answering or proposals, and explicit distinction between user choices and
assistant suggestions. The output token cap and generation settings are unchanged.
This variant is stored in the production `_INSTRUCTION`; the original instruction
and both result sets are retained in the evidence artifacts. It is a diagnostic
iteration, not a preregistered blinded trial.

Sparse rolling checkpoints are catch-up stress tests, not every-turn replay.
A third run uses `--repetitions 0 --cadence turns` with the revised instruction,
replaying every actual user message (including the six duplicate submissions)
with valid summary cache reuse. This distinguishes large catch-up bursts from
normal turn-by-turn progression. No summary-length guard or timeout was relaxed.

Install optional PDF tooling with:

```sh
backend/.venv/bin/python -m pip install -r scripts/requirements-compaction-eval.txt
```

Reproduce the original prompt with `--baseline`; use the current production prompt
without that flag. Use different output directories to preserve each run:

```sh
backend/.venv/bin/python scripts/evaluate_conversation_compaction.py --pdf temp/areqa-chat-2026-11-07.pdf --output temp/compaction-comparison-2026-11-08 --repetitions 3 --baseline
backend/.venv/bin/python scripts/evaluate_conversation_compaction.py --pdf temp/areqa-chat-2026-11-07.pdf --output temp/compaction-comparison-strict-2026-11-08 --repetitions 3
backend/.venv/bin/python scripts/evaluate_conversation_compaction.py --pdf temp/areqa-chat-2026-11-07.pdf --output temp/compaction-comparison-turns-2026-11-08 --repetitions 0 --cadence turns
```
