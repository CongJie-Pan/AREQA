## The Core Architectural Problem

The scenario described — an LLM orchestrator, a deterministic validation pipeline, and a legacy rule-based `DialogueActAgent` all independently trying to interpret the same user turn — is a textbook symptom of **ownership diffusion**. Current best practice in agentic system design treats "who gets to interpret this turn" as a single, exclusive responsibility that must never silently transfer to a second interpreter with different semantics. Contemporary frameworks such as LangGraph formalize this by separating three distinct roles that are often conflated in legacy systems: the node that *classifies* intent, the function that *routes* based on that classification, and the node that *acts* on the routed decision. Ownership violations occur precisely when a downstream component (the rule-based classifier) is allowed to re-classify content that an upstream owner (the LLM orchestrator) already classified, using a different taxonomy and different evidence.[^1]

## 1. Single-Owner Turn Interpretation Patterns

The dominant pattern across LangGraph, Semantic Kernel, and agent-loop designs is the **classifier/router separation pattern**: one node owns semantic interpretation and writes a structured label into shared state; a separate, stateless routing function *only* maps that label to the next node name and is explicitly prohibited from performing its own semantic analysis. Applied to the tutoring scenario, this means the LLM orchestrator's JSON decision should be the *only* semantic interpretation of the turn. Any subsequent component — including the `DialogueActAgent` — must be restricted to translating that decision into an action, not re-deriving intent from raw text.[^1]

Multi-agent orchestration surveys describe this as agents assuming distinct, non-overlapping roles that exchange structured information rather than re-processing raw input independently. The critical design rule is: **once the orchestrator has committed a decision to state, no other component may treat the raw user utterance as unclassified input again.** If the legacy `DialogueActAgent` re-reads the raw text ("I think maybe X?") and classifies it from scratch, it is acting as a second, competing owner — the exact failure mode in the query. The fix is architectural: the dialogue-act agent should never receive the raw turn as its primary input when the orchestrator has already produced a valid decision; it should only see the raw turn when the orchestrator's output has failed validation and even then, its output should be constrained to *filling gaps*, not *overriding* the orchestrator's committed distinction (e.g., it can classify low-confidence *unparsed* fields, but it cannot flip "answer" into "clarification" if the orchestrator's structured output — even a partially invalid one — already signaled "this is an answer").[^2]

## 2. Structured Output Reliability Engineering

### Strict schemas and constrained decoding over "best-effort" JSON

The most consequential shift in 2024–2026 production practice is moving from prompted JSON ("please output JSON") to **schema-constrained generation**, where the provider masks invalid tokens at decode time so the enum literally cannot be violated. OpenAI's Structured Outputs feature converts a supplied JSON Schema into a context-free grammar and performs dynamic constrained decoding, masking every token that would not be valid at each generation step. This means that if `action` is defined as an enum of `["answer", "clarify", "hint", "explain"]`, the model is structurally incapable of emitting `"maybe_clarify"` or any other invalid literal — the failure mode of "parseable JSON but invalid enum" is eliminated at the source rather than caught downstream.[^3][^4][^5]

Enum-constrained decoding has documented edge cases worth designing around: enums containing special characters (quotes, newlines) can be rejected by strict schema validators, and structured-outputs enum support varies slightly by provider and character set. Comparative benchmarking shows the reliability gap between approaches is substantial — strict, schema-enforced structured outputs hold roughly 99.9% schema compliance, while plain "JSON mode" prompting fails 8–15% of the time. This gap directly explains the reported bug: the orchestrator is likely using unconstrained or loosely-validated JSON generation rather than strict, schema-enforced decoding, which is why invalid enum values are reaching the validator at all.[^6][^7]

| Approach | Mechanism | Reliability | Best fit |
|---|---|---|---|
| Prompt-only JSON | Instructional formatting | Probabilistic; can emit prose or wrong shape[^8] | Prototypes only |
| JSON mode | Guarantees valid JSON syntax, not schema | Valid JSON but schema drift possible[^6] | Low-stakes extraction |
| Strict structured outputs / function calling | Context-free grammar + constrained decoding[^5] | ~99.9% schema compliance[^6] | Production orchestrator decisions |
| Tool/function calling with `strict: true` | Same CFG mechanism applied to tool argument schema[^5] | Same as above, integrates with agent loop | Orchestrators driving downstream actions |

### Retry, repair, and enum normalization as a second layer

Even with constrained decoding, semantic correctness (choosing the *right* enum value, not just a *valid* one) is not guaranteed — structured outputs only guarantees shape, not meaning. Best practice therefore layers three defenses: (1) constrained decoding to eliminate invalid-shape errors at the source, (2) a **validation node** that checks required fields and enum membership, writing an explicit `parse_error`/`validation_error` signal into state rather than crashing or silently falling through, and (3) a bounded **repair loop** that re-prompts the model with the specific validation error as feedback (not a raw traceback) and enforces a hard retry cap of 2–3 attempts before falling back, since some failures are not retry-fixable. Enum normalization (mapping near-miss strings like `"Clarify"`, `"clarification"`, `"CLARIFY_Q"` to the canonical `"clarify"` value) should happen inside this validation layer, before any routing decision is made, so that trivial casing/synonym drift never triggers a full fallback cascade.[^9][^10][^11][^8]

## 3. Should Rule-Based Classifiers Be Tools, Validators, Fallbacks, or Independent Routers?

Given the single-owner principle, the legacy `DialogueActAgent` should be architecturally demoted from an **independent router** (its current role, since it "takes over" classification) to one of two roles, and never both simultaneously:

- **Validator/normalizer role**: invoked only to check or lightly correct the orchestrator's declared enum values (e.g., confirm "answer" is plausible given surface features), never to substitute its own top-level intent label.
- **Tool called by the orchestrator itself**: the LLM orchestrator can explicitly invoke the dialogue-act classifier as a function/tool when it is uncertain, inspect its output, and decide whether to incorporate it — preserving the orchestrator as the sole decision owner. This mirrors the LangGraph "classifier node writes a label; router only translates it" separation, generalized so that legacy rule-based logic is nested *inside* the orchestrator's evidence-gathering step rather than sitting downstream of it as a competing decision-maker.[^1]

The failure mode in the query arises because the `DialogueActAgent` currently acts as an **independent fallback router** — the worst of the four options, because it fully re-interprets the turn with a different, narrower taxonomy (built for classifying dialogue acts in isolation, not for resolving ambiguity in the context of a specific tutor prompt) and has no visibility into the orchestrator's original — even if imperfectly-formed — intent signal.

## 4. Designing Fallback Without Violating Orchestrator Intent

Fallback-node design literature is explicit that fallback exists for **survival, not quality** — its job is to keep the system from crashing, not to re-derive the "correct" interpretation from scratch. The best-practice fallback hierarchy, in order of preference, is:[^12]

1. **Constrained retry with error feedback**: re-invoke the orchestrator LLM itself with the specific validation failure, since it retains full context and generated the original signal — this is a "retry," not a handoff.[^11][^12]
2. **Partial acceptance / degraded mode**: if the JSON has a valid, high-confidence field (e.g., `policy` is fine but `action` enum is malformed), accept the valid parts and only re-resolve the malformed field, rather than discarding the entire decision and handing the raw turn to a different interpreter.[^12]
3. **Heuristic fallback restricted to the failed field only**: if a rule-based fallback must run, it should operate strictly on the narrow field that failed validation, using the orchestrator's other already-valid fields (e.g., "this followed a tutor prompt expecting an answer") as constraints — not as a fresh, context-free classification of the entire turn.[^12]
4. **Human/deterministic safe-default as last resort**: only after retries and narrow-scope fallback are exhausted should the system fall back to a maximally safe deterministic default (e.g., "treat as answer with low confidence" rather than "treat as clarification"), because in a tutoring context the two defaults carry asymmetric risk (see Section 5).[^11][^12]

Critically, fallback logging and metrics ("track fallback frequency," "never allow silent failure") should be treated as first-class signals: repeated fallback into the `DialogueActAgent` for the same enum failure is a signal that the schema or prompt needs revision, not that the fallback path is working as intended.[^12]

## 5. Preserving Safety Around State Writes

The specific harm described — misclassifying "I think maybe X?" as a clarification question rather than a tentative answer — is a **state-write safety issue**, not merely a routing inconvenience. If the system writes "clarification requested" to persistent learner-state when the input was actually a hedged answer, it can corrupt downstream tutoring logic: skipping assessment of the answer, repeating content the student already engaged with, or worse, logging a non-response where an answer attempt should have been scored. Best practice in dialogue-system state design is to treat classification outputs as provisional until validated against session context, and to make state writes for consequential fields (e.g., "student got X wrong," "student needs clarification") **conservative and reversible** rather than committed on first pass.[^9]

Practical safeguards include:

- **Context-anchored disambiguation**: any classifier (LLM or rule-based) that labels a turn as "clarification" should be required to check it against the *type* of the immediately preceding system turn. A tentative, hedged reply ("I think maybe X?") immediately following a direct tutor question should be biased toward "low-confidence answer," not "clarification," because clarification requests normatively target the system's prior utterance, not restate an answer candidate.[^1]
- **Confidence-gated writes**: state fields with high downstream consequence (marking an answer wrong, ending a turn) should require a confidence threshold from the owning classifier; sub-threshold cases should route to a lightweight "confirm with student" turn rather than committing an interpretation, echoing the "human fallback" and "degraded mode" categories in fallback design.[^12]
- **Idempotent staging before commit**: writing the orchestrator's decision to a staging field first, and only promoting it to persistent learner state after downstream validation passes, prevents an invalid or fallback-derived interpretation from silently becoming ground truth in the learner model.

## 6. Concrete Implementation Patterns Across Frameworks

**LangGraph** offers the clearest primitives for this exact problem. Its recommended architecture uses `with_structured_output(Schema)` on the LLM call so the model is constrained to return one of an explicit set of routing keys — a grading/decision node in a Corrective-RAG-style graph can only emit `"relevant"` or `"not_relevant"`, never unexpected free text, because the schema is enforced at generation time. State design explicitly separates raw input from extracted fields and uses a `parse_error`/`doc_grade` field as the *sole* signal traveling between extraction, validation, and routing layers — this is directly transferable to the tutoring case: the orchestrator writes `action`, `policy`, and a `validation_error` field; the routing function reads only these; and the `DialogueActAgent`, if invoked, is a node the router can reach *only* when `validation_error` is set, scoped to repairing that specific error. LangGraph's `add_conditional_edges` with an explicit mapping dictionary additionally enforces that the router can only return one of a fixed, named set of next-node keys, causing a runtime error (rather than silent misrouting) if an unmapped value appears.[^13][^9][^1]

**OpenAI structured outputs / function calling** is the mechanism that should sit upstream of all of this: defining `action` and `policy` as `strict: true` enum-typed parameters in a function/tool schema (or a `json_schema` response format) makes the "parseable but invalid enum" bug structurally impossible, since the constrained decoder cannot sample a token sequence outside the declared enum. This converts what is currently a downstream validation-and-fallback problem into a non-issue at the generation layer — the single highest-leverage fix for the reported bug, ahead of any changes to `DialogueActAgent` behavior.[^5][^3]

**Fallback-node patterns** in production LangGraph deployments formalize the retry-vs-fallback distinction with an explicit routing function: check `state["error"]`; if none, proceed to `end`; if error and `retries < MAX_RETRIES`, route to `retry` (i.e., re-prompt the same owning LLM); only after retries are exhausted route to `fallback`. Applied here, this means the `DialogueActAgent` should sit behind a retry-exhaustion gate, not be the first responder to an invalid enum.[^12]

For frameworks like **Semantic Kernel, AutoGen, and CrewAI**, the same governing principle applies even though tooling differs: each favors a designated "planner" or "manager" agent that owns turn-level decisions and delegates narrowly-scoped sub-tasks to specialist agents/tools, rather than allowing specialist agents to independently re-interpret the same raw input the planner already processed. The architectural takeaway generalizes across all these ecosystems: **structured, schema-constrained output from the orchestrator is the primary defense; validation and repair are the secondary defense operating only on the orchestrator's own output; and legacy rule-based components are demoted to narrowly-scoped tools or validators invoked by the orchestrator, never independent routers competing to interpret the same raw turn**.[^2][^1][^12]

## Summary Recommendations for the Reported Bug

| Problem | Root cause | Recommended fix |
|---|---|---|
| Invalid enum values reach validator | Orchestrator likely uses unconstrained/loose JSON generation | Switch to strict schema-constrained structured outputs / function calling with `strict: true` so invalid enums cannot be generated[^5][^3] |
| Validator falls back to legacy router on any invalid enum | No retry/repair layer between generation and fallback | Add a bounded repair loop (2–3 retries) with validation error fed back as instruction before ever invoking the rule-based agent[^11][^9] |
| `DialogueActAgent` re-classifies the whole turn from scratch | It operates as an independent router, not a scoped tool | Restrict it to repairing only the specific invalid field, using the orchestrator's other valid fields (e.g., prior tutor-prompt type) as constraints[^12][^1] |
| Hedged answers misclassified as clarification | Classifier ignores context of preceding tutor turn | Require context-anchored disambiguation and confidence-gated state writes before committing "clarification" to learner state[^1][^12] |

---

## References

1. [Conditional Routing Patterns for Scalable AI Agent Workflows](https://www.educative.io/courses/langgraph-from-langchain-user-to-agent-builder/conditional-routing-patterns) - Learn how to structure complex routing logic with separate classifier and routing functions to impro...

2. [LLM-Based Multi-Agent Orchestration: A Survey of ...](https://www.preprints.org/manuscript/202604.2147) - by Y Zhu · 2026 · Cited by 1 — The answer, LLM-based multi-agent orchestration, is a paradigm in whi...

3. [Idea: Use constrained decoding (structured output) so that ...](https://github.com/BishopFox/raink/issues/11) - Instead of needing to retry and incure higher costs, you can enforce the model to always return the ...

4. [Structured Outputs Deep-dive - #39 by nicholishen - API](https://community.openai.com/t/structured-outputs-deep-dive/930169/39) - In OpenAI’s article titled “Introducing Structured Outputs in the API” there’s an entire section on ...

5. [Introducing Structured Outputs in the API](https://openai.com/index/introducing-structured-outputs-in-the-api/) - Today we're introducing Structured Outputs in the API, a new feature designed to ensure model-genera...

6. [Reliable JSON From LLMs: Structured Outputs Compared 2026 ...](https://hamzashabbir.dev/article/reliable-json-llm-structured-outputs-compared-2026) - Strict structured outputs hold ~99.9% schema compliance while plain JSON mode fails 8-15% of the tim...

7. [Limitations on enum values in Structured Outputs - API](https://community.openai.com/t/limitations-on-enum-values-in-structured-outputs/984464) - The documentation for Structured Outputs just says that Enums are supported, but that doesn’t seem t...

8. [Structured outputs: JSON Schema, OpenAI, Claude, Gemini](https://logic.inc/resources/structured-outputs-guide) - Structured outputs are model responses constrained to a schema. The schema defines fields, types, re...

9. [Structured Outputs and Validation in LangGraph Workflows](https://www.educative.io/courses/langgraph-from-langchain-user-to-agent-builder/structured-outputs-and-validation) - Learn how to ensure reliable AI workflow outputs with structured JSON validation, error handling, an...

10. [LLM Output Validation: Structured Outputs & Guardrails](https://iotdigitaltwinplm.com/llm-output-validation-structured-outputs-guardrails-2026/) - A production 2026 pattern for LLM output validation: constrained decoding, JSON-schema structured ou...

11. [Retry Loops for LLM Validation Failures That Converge](https://thepromptbench.com/structured-outputs/retry-loops-for-validation-failures/) - The validate-and-re-prompt pattern done right: Zod or pydantic checks, error feedback written as ins...

12. [Fallback Node in LangGraph](https://svgoudar.github.io/Learn-LangGraph/langgraph/3-nodes/17-fallback-node.html)

13. [LangGraph Advanced: Part 3 — RAG Pipeline with Conditional ...](https://shafiqulai.github.io/blogs/blog_16.html) - Most AI agents answer from training data alone — but company policies change. This post builds a Cor...

