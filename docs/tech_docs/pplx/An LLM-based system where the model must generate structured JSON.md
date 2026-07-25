<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# I am building an LLM-based system where the model must generate structured JSON that conforms to a strict nested schema. The current problem is that the model often returns JSON that is syntactically valid

but does not match the required schema: missing required fields, wrong nested object shapes, wrong enum values, or incomplete arrays.

Context:

- The system generates a "DomainSkill" object for an educational tutoring engine.
- The schema includes nested arrays and objects such as prerequisites, calibration_questions, diagnostic_rules, teaching_moves, remediation_paths, assessment_policy, teaching_methodology,
remediation_templates, and safety_notes.
- We validate the output server-side. If validation fails, we retry with repair instructions.
- However, repair is weak when the validator only returns coarse errors like "missing_required_field" instead of field-specific paths.
- We do not want to store or log raw model output for privacy/safety reasons, but we can store safe schema error metadata such as field paths and reason codes.

Question:
What are current best practices in 2025–2026 for making LLMs reliably produce JSON that conforms to a strict nested schema?

Please compare practical approaches such as:

1. OpenAI / Anthropic / Gemini structured output or JSON schema constrained decoding
2. Function calling / tool calling
3. Pydantic / Zod / JSON Schema validation with automatic repair loops
4. Grammar-constrained decoding
5. Instructor, Outlines, Guidance, Guardrails, LangChain structured output, or similar frameworks
6. Splitting generation into smaller schema-specific steps instead of one large JSON
7. Returning field-specific validation errors back to the model
8. Using deterministic post-processing vs rejecting and regenerating
9. Storing safe schema issue metadata without storing raw model output

I want an engineering-focused answer:

- Recommended architecture
- Retry/repair loop design
- How to produce useful validation errors
- How to avoid infinite retries and latency blowups
- How to handle fallback behavior honestly
- Example prompt/schema design
- Tradeoffs between provider-native structured outputs and application-level validation
- Sources or references to current documentation and papers

I have enough detail now to write a comprehensive, engineering-focused answer.

## Direct Answer

The best 2025–2026 approach is layered: use **provider-native constrained decoding** (OpenAI Structured Outputs, Anthropic Structured Outputs/tool-use, Gemini `response_schema`) as the primary defense to guarantee shape, then keep **application-level Pydantic/Zod validation plus a bounded, field-specific repair loop** as a backstop, since constrained decoding guarantees structure but not semantic correctness.[^1][^2]

## Provider-Native Constrained Decoding

All three major providers now compile your JSON Schema into a token-level grammar (finite-state machine) so invalid tokens get zero probability, making structurally malformed output effectively impossible. OpenAI has supported this since GPT-4o (August 2024) via `strict: true` in `response_format`/`text.format`; Anthropic reached general availability in February 2026 with `output_config.format`, plus a separate tool-use path for agent actions; Gemini uses `response_mime_type: application/json` with `response_schema`, but accepts a smaller JSON Schema subset and can reject very deep/large schemas. Key constraints to design around: OpenAI strict mode requires every property in `required` (use `["type","null"]` for "optional" fields), forces `additionalProperties: false` everywhere, ignores `minLength`/`pattern`/`minItems`/etc., and caps nesting at 5 levels and 100 total properties. For your DomainSkill object with prerequisites, calibration_questions, diagnostic_rules, teaching_moves, remediation_paths, etc., this depth/size cap is the first thing to check — nine nested sub-schemas can easily blow past 100 properties or 5 levels.[^2][^3][^1]

## Function/Tool Calling vs Response-Format Structured Output

Function calling and `response_format`/`text.format` use the same underlying constrained-decoding mechanism but serve different purposes: function calling is for when the model needs to invoke your system's capabilities (query a DB, trigger a UI action), while `response_format`/`text.format` structured output is for when the model's final answer to the user should conform to a schema. For DomainSkill generation — a final structured artifact, not an action trigger — response-format-style structured output is the right primitive, not tool calling.[^4]

## Recommended Architecture

Build a four-layer pipeline:

1. **Schema-constrained generation** — send the JSON Schema with strict mode enabled as the first-line defense.[^2]
2. **Local validation regardless** — always re-validate with Pydantic/Zod even when the provider claims schema conformance, since SDK quirks, proxy rewrites, or non-native-support fallback models can still produce mismatches.[^1]
3. **Field-specific repair loop** — on failure, extract structured errors (`ValidationError.errors()` in Pydantic, `ZodError.errors` in Zod — both give `{path, message, expected_type}`) and feed only those specific errors back rather than "missing_required_field".[^5]
4. **Bounded fallback** — cap retries and degrade gracefully rather than looping indefinitely.[^5]

## Retry/Repair Loop Design

Use a ladder of increasingly expensive interventions, cheapest first:[^5]

- **Heuristic repair (no model call)**: run `json_repair`/`fast-json-repair` to fix trailing commas, unclosed brackets, or stray markdown fences — this runs in milliseconds and resolves pure syntax issues for free.
- **Retry with field-specific errors (1 attempt)**: feed back exact `{path, reason_code, expected}` tuples, not coarse categories. Research cited in production guides shows this resolves 85–95% of failures on capable models when errors are specific.
- **Retry with schema simplification (1 attempt)**: if the same field fails twice, that's a signal the schema description is ambiguous for the model — rephrase, add an inline example for that sub-object, or split the nested object into its own generation call.
- **Cap at 2 retries total on the synchronous path.** Beyond that, the model is confused about the schema itself, and more retries just add latency without improving success rate.[^5]

For your DomainSkill object specifically, given 9 independent nested substructures, consider **decomposing generation**: generate the "skeleton" (id, name, top-level metadata) with the LLM, then generate each of prerequisites, calibration_questions, diagnostic_rules, teaching_moves, remediation_paths, assessment_policy, teaching_methodology, remediation_templates, and safety_notes as **separate constrained calls** using their own sub-schemas, then assemble server-side. This is explicitly recommended when a schema is "too complex for what the model can reliably produce in one shot" — smaller schemas fail less often, each failure is isolated to one sub-part, and you can retry only the failing sub-object instead of regenerating the whole nine-part structure.[^1][^5]

## Producing Useful Validation Errors

Coarse codes like `missing_required_field` are useless for repair because the model doesn't know *which* field or *what shape was expected*. Instead, capture from Pydantic/Zod:


| Element | Example |
| :-- | :-- |
| Field path | `remediation_paths[^2].diagnostic_rules[^0].trigger_condition` |
| Reason code | `enum_mismatch`, `type_mismatch`, `missing_required`, `array_too_short` |
| Expected constraint | `expected one of ["prerequisite_gap","misconception","skill_decay"]` |
| Actual value received (redacted/typed only) | `received type: string, expected: object` |

Serialize these into a compact, model-readable correction message (e.g., "Field `remediation_paths[^2].diagnostic_rules[^0].trigger_condition` must be one of: prerequisite_gap, misconception, skill_decay. You provided an invalid value.") rather than dumping a raw stack trace.[^5]

## Avoiding Infinite Retries and Latency Blowups

- Hard cap retries at 2 on the synchronous request path; each retry adds a full model round-trip (2–10s at p99), so 2 retries can turn a 3s call into a 9s+ call.[^5]
- Run cheap heuristic repair before any model retry — it costs milliseconds versus seconds.[^5]
- Move complex/low-priority generation (e.g., bulk remediation_template authoring) to an async background queue where latency is invisible to end users.
- Track a per-field failure counter across attempts; if the same field fails on both retries, stop retrying that field and apply a safe default or flag for human review instead of looping.
- Add a global timeout budget (e.g., 15–20s) for the whole validate→repair→retry cycle, independent of retry count.


## Honest Fallback Behavior

When retries exhaust, do not silently substitute plausible-looking fake content. Return an explicit partial result with a clear status: e.g., `{"status": "partial", "missing_fields": [...], "reason": "validation_exhausted"}`, and route to human review or a simplified template. For a tutoring system, fields like `safety_notes` or `assessment_policy` should never be auto-filled with fabricated defaults — flag and block skill activation instead, since bad safety metadata is worse than a visible failure.

## Storing Safe Metadata Without Raw Output

Since you don't want to log raw model output, store only the structured error object: field path, reason code, expected type/enum, retry attempt number, and timestamp — never the actual failing string content the model generated. This satisfies observability needs (spotting that `diagnostic_rules` fails validation more often after a model upgrade) while keeping raw generations out of logs. This error metadata is also exactly what feeds both your repair loop and your longer-term schema/prompt tuning — if a specific field path shows elevated failure rates over time, that's a signal to simplify that part of the schema or add a clearer prompt example, not just add more retries.[^5]

## Deterministic Post-Processing vs Reject-and-Regenerate

Apply deterministic fixes only for low-risk, mechanical mismatches: type coercion (`"3"` → `3`), trimming whitespace, normalizing near-enum values via fuzzy match to the canonical set. Reserve reject-and-regenerate for anything semantic or safety-relevant — wrong nested object shape, missing required sub-arrays, or invalid `safety_notes` content — where silent coercion could hide a real generation failure.[^5]

## Frameworks

**Instructor** (Python, 3M+ monthly downloads) wraps OpenAI/Anthropic/15+ SDKs, auto-converts Pydantic models to JSON Schema, and runs a built-in `max_retries` validate-and-repair loop, making it the most ergonomic default for Python pipelines. **Zod v4** (TypeScript) now ships a native `.toJSONSchema()` method, removing the need for `zod-to-json-schema`. **Outlines**/XGrammar power grammar-constrained decoding for open-source/self-hosted models (vLLM, SGLang, Ollama's `format` parameter), giving you the same token-masking guarantee locally that OpenAI/Anthropic/Gemini give as hosted APIs — relevant if you ever self-host for cost or privacy reasons. Guardrails and LangChain's structured-output helpers offer similar validate+retry wrappers but are less dominant than Instructor/Zod as of 2026.[^2][^5]

## Tradeoffs: Provider-Native vs Application-Level Validation

| Dimension | Provider-native structured output | Application-level validation |
| :-- | :-- | :-- |
| Guarantees | Syntax + schema shape (required fields, types, enums) [^1] | Anything you code: semantic rules, cross-field logic, business constraints |
| Failure rate | Near-zero for structural errors [^2] | Catches what providers can't (semantic correctness) |
| Schema support | Subset of JSON Schema only (no regex, no length bounds, capped depth) [^3] | Full expressiveness via Pydantic validators |
| Portability | Differs per provider; a schema tuned for OpenAI may not run unchanged on Gemini/Claude [^2] | Portable, provider-agnostic |
| Latency/cost | Near-zero overhead once schema is cached; first call to a new complex schema has warm-up cost [^1] | Runs client-side, effectively free |

Use both together: provider-native for structural guarantees, Pydantic/Zod for semantic rules (e.g., "assessment_policy.passing_threshold must be between 0 and 1", "remediation_paths must reference an existing diagnostic_rule id") that JSON Schema alone can't express.[^3][^1]

## Example Schema Design Pattern

For a field like `diagnostic_rules`, avoid ambiguous free-text conditions; use tightly-scoped enums plus a `$defs` sub-schema referenced by `$ref`, and add inline `description` fields (providers use these to guide generation):[^3]

```json
"diagnostic_rules": {
  "type": "array",
  "items": { "$ref": "#/$defs/diagnostic_rule" }
},
"$defs": {
  "diagnostic_rule": {
    "type": "object",
    "properties": {
      "trigger_condition": { "type": "string", "enum": ["prerequisite_gap","misconception","skill_decay"] },
      "action": { "type": "string", "description": "Remediation action id to invoke" }
    },
    "required": ["trigger_condition","action"],
    "additionalProperties": false
  }
}
```

Keep descriptions short and unambiguous, name keys intuitively, and validate iteratively with evals — OpenAI explicitly recommends building evals to find the schema structure that minimizes model mistakes.[^3]

## References

- OpenAI Structured Outputs guide and best practices[^4][^3]
- DevToolLab, "LLM Structured Outputs: Get JSON That Always Parses" (2026) — provider comparison, constrained decoding mechanics[^2]
- AI/TLDR, "Schema Validation for LLM Output: Zod \& Pydantic" — retry-repair patterns, pitfalls[^5]
- OpenReview, "PSC: Efficient Grammar-Constrained Decoding via Parser..." (2025)[^6]

<div align="center">⁂</div>

[^1]: https://iotdigitaltwinplm.com/llm-json-mode-structured-output-benchmark-2026/

[^2]: https://devtoollab.com/blog/llm-structured-outputs-guide-2026

[^3]: https://promptz2h.com/chapter_16_structured_output_and_reliability_engineering/series_01_json_mode_and_schema_enforced_output/validation_repair

[^4]: https://platform.openai.com/docs/guides/structured-outputs/best-practices

[^5]: https://ai-tldr.dev/learn/production-llmops/guardrails-reliability/llm-output-schema-validation/

[^6]: https://openreview.net/forum?id=SEjxNfQTHN

