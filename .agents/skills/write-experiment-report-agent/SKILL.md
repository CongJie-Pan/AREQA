---
name: write-experiment-report-agent
description: Write or revise general-purpose, evidence-based English experiment reports for software, product, research, and system experiments. Use when Codex must turn an experiment report, test script, transcripts, logs, screenshots, measurements, code findings, or prior experiment into a structured report with expected behavior, actual behavior, Mermaid data flows, cause hypotheses, concise solutions, and a defensible conclusion.
---

# Write Experiment Report Agent

Produce a natural, professional English experiment report from the supplied artifacts. Extract the reusable structure and reasoning style from `docs/worklog/202607/2026_07_16_experiment/experiment_report.md` when it is available, but do not hardcode its domain, terminology, acceptance rules, conclusions, or implementation assumptions. Derive those from the current experiment's own requirements and evidence.

The report must distinguish what was observed from what is inferred. A clean UI is not proof that backend state is safe, and a missing log is not proof that an operation never happened. Label unsupported claims as `not verified`, `insufficient evidence`, or `hypothesis`.

## Workflow

1. Read the complete experiment directory recursively before drafting. Include the test script, report template or prior report, transcripts, screenshots, logs, measurements, error traces, test output, and failure notes.
2. Read the relevant requirements, implementation plan, research notes, and technical principles when the experiment references them. Inspect relevant source code only when the user asks for code-grounded analysis or when the artifacts cannot establish the result.
3. Extract the experiment's domain vocabulary, variables, actors, states, acceptance criteria, and timing boundaries. Do not invent domain-specific rules from the reference report.
4. Build an evidence matrix before writing: test Act or scenario, input/action, expected behavior, observed behavior, supporting evidence, missing evidence, and verdict.
5. Compare each scenario against its own success criteria. Do not replace the test script's criteria with a more convenient interpretation.
5. Use these verdicts consistently:
   - `Pass`: the expected behavior is directly supported by sufficient evidence.
   - `Fail`: observed behavior contradicts a success criterion, including an HTTP 5xx, forbidden write, missing required delivery, or explicit failure note.
   - `Not verified`: the artifacts do not contain enough evidence to decide.
   - `Blocked`: the Act could not proceed because an earlier required Act failed.
6. Write the report to the requested path. Preserve existing useful sections when revising a report, but correct inconsistent claims and Mermaid syntax.

## Required English Report Format

Use the following structure unless the user explicitly requests another format:

```markdown
# <Date> <Experiment Name> Report

Summary:

<Short paragraph stating scope, major observed outcomes, the overall verdict, and the most important evidence limitation.>

---

## 1. Expected Results and Improvements over the Previous Experiment

<Explain the intended behavior, relevant previous baseline, and acceptance boundary in paragraphs.>

### Expected Data Flow (Mermaid)

```mermaid
flowchart TD
    A["User input"] --> B{"Safety or policy gate"}
    B -->|"Temporary context"| C["Short-lived state"]
    B -->|"Evidence meets minimum threshold"| D["Provisional result"]
    D --> E{"Independent validation"}
    E -->|"No"| F["Remain provisional"]
    E -->|"Yes"| G["Validated result"]
```

## 2. Actual Results

<Describe observed behavior Act by Act. Include visible behavior, persisted state, logs, errors, timing, and contradictions. Use paragraphs primarily; use a compact table when it improves traceability.>

| Act | Expected | Observed | Verdict | Evidence |
|---|---|---|---|---|

### Actual Data Flow (Mermaid)

```mermaid
flowchart TD
    A["Observed input"] --> B["Observed processing"]
    B --> C["Observed state or failure"]
```

## 3. Hypotheses About the Causes

<Explain the most plausible root-cause hypotheses and the evidence for and against each. Include architectural, lifecycle, privacy, classification, concurrency, delivery, and observability causes when relevant. Do not present hypotheses as confirmed facts.>

## 4. Solutions

<Give concise, precise solutions mapped to the hypotheses. Separate immediate fixes, architectural changes, regression tests, and observability improvements when useful. Do not write an implementation plan unless requested.>

## 5. Conclusion

<State the overall result plainly: successful, partially successful, failed, not verified, or blocked. Explain which Acts passed, failed, or remain unverified, and identify the next required validation.>
```

## Evidence and Verdict Rules

- Read all files in the experiment directory, not only files whose names look like reports. Use `rg --files`, `rg`, and line-numbered reads to find Act names, expected results, error terms, task IDs, timestamps, and structured event names.
- Cite local evidence with clickable absolute file links and line numbers in the final report when the repository format supports it.
- Preserve identifiers needed for traceability: experiment ID, run ID, actor or user ID, scenario ID, timestamps, request IDs, task IDs, version numbers, measurements, HTTP status, and event names, using only identifiers present or relevant to the current experiment. Redact secrets, tokens, raw credentials, and unnecessary personal data.
- Distinguish the experiment's own state layers and claims. For example, a visible result, an intermediate state, a persisted record, a queued task, a completed operation, and a user-observed outcome may be different claims; use the domain's actual names rather than assuming a fixed architecture.
- Check the boundaries relevant to the experiment: input provenance, classification, lifecycle, persistence, isolation, deduplication, concurrency, retries, timing, reproducibility, and observability. Include only applicable dimensions.
- For asynchronous or multi-step workflows, verify the complete state transition defined by the test: trigger, durable state, processing, completion, user-visible result, idempotency, and failure or retry path when applicable.
- A log saying `triggered`, `generated`, or `HTTP 200` does not prove persistence or delivery. A missing required event makes the criterion unverified unless another artifact proves the state.
- An explicit error, `HTTP 4xx/5xx`, stack trace, empty required output, forbidden write, or statement such as `no progress due to ... failed` is a failure for the affected Act.
- Do not silently convert a failed Act into `not verified`. Use `not verified` only when the test outcome genuinely cannot be established.
- If an Act depends on a failed earlier Act, mark it `Blocked` and explain what prerequisite failed. Do not count a blocked Act as passed.
- Do not infer success from automated test results unless the experiment asks for code-level validation and the test output is actually present in the artifacts.

## Hypothesis Writing Rules

- Start with the observed symptom, then connect it to a possible mechanism.
- Distinguish direct evidence, strong inference, and speculation.
- Prefer boundary-based explanations: input capture, classification, state transitions, ownership boundaries, persistence, external dependencies, concurrency, recovery, user-visible behavior, and observability. Select only the boundaries relevant to the experiment.
- Explain alternative causes when the evidence cannot discriminate between them.
- Do not blame a model, prompt, database, queue, external service, or user interface without an artifact that supports that explanation.

## Mermaid Rules

- Use valid Mermaid syntax. Quote labels containing punctuation, parentheses, slashes, colons, question marks, or long natural-language text, for example `A["User asks a question"]`.
- Keep expected and actual flows small enough to review. Show the decision boundaries, state transitions, and failure path that matter to the experiment.
- Do not put raw user text, secrets, tokens, or sensitive personal content into diagrams.

## Final Review

Before delivering, confirm that the report is written entirely in English; every required section exists; every Act has an evidence-backed verdict; failed and blocked Acts are not described as successes; missing evidence is explicit; hypotheses are not stated as facts; solutions address the observed causes; Mermaid diagrams parse conceptually and use safe quoted labels; and the conclusion matches the per-Act verdicts.
