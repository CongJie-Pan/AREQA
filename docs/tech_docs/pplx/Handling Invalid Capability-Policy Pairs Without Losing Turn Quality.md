<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

## Handling Invalid Capability-Policy Pairs Without Losing Turn Quality

The core issue is that your validator treats **capability-policy mismatch** the same way it would treat a **malformed/unparseable output** — both trigger full fallback. Production best practice distinguishes these as different failure classes requiring different repair strategies, and conflating them is exactly what causes the quality regression you're describing.

### 1. Invalid decisions with useful semantic content

Current guidance on structured-output failure handling explicitly separates failures into syntax, structural, and semantic/business-rule categories, and recommends different remediation for each. A capability-policy violation like `tutor_response + write_proposed` is a **business-rule (semantic) violation on a single field** — the JSON parsed correctly, the enum values are individually valid, only the *combination* is disallowed by your manifest. This is explicitly the category where partial validation and field-level repair is recommended over full discard: "skipping a field... but explicitly mark partial results as such and handle accordingly downstream," rather than throwing away the entire object. Your `turn_interpretation` — the actual semantic read of "student answered correctly, ready to advance" — has passed no rule at all; discarding it along with the invalid policy is treating a targeted rule violation as if it were total decision corruption.[^1][^2][^3]

### 2. Discard-and-fallback vs. preserve-and-repair

Preserve and repair the invalid field; do not discard the whole decision. The output-contract framework used in production systems asks explicitly: "which fields can be repaired?" vs. "which failures must stop the workflow?" — and recommends that low-risk syntax/schema/business-rule mismatches get a bounded, targeted repair attempt, while only high-risk semantic failures (e.g., an action that would cause unsafe state writes) should stop the workflow or go to review. In your case:[^3]

- `capability=tutor_response` is valid and low-risk (content-generation only).
- `turn_interpretation` is valid and carries the useful signal.
- Only `policy=write_proposed` is invalid for this capability — and it is invalid in the "denied," not "ambiguous," sense, since your manifest already defines the *correct* replacement (`specialist`) deterministically.

This means the correction is not even a probabilistic repair — it's a deterministic remap: the manifest itself, given `capability=tutor_response`, already implies the maximal *allowed* policy. A pure discard-to-fallback pipeline throws away information the system already possesses.

### 3. Best practices for validation/repair loops, specifically for capability-policy validation

The consistent structure across current tooling (Pydantic-based validators, Zod-based contracts, LangChain/LangGraph repair nodes) is a **layered validation pipeline**: extract → parse → schema-validate → business-rule-validate → repair-if-cheap → escalate-if-not. Two concrete implications for capability-policy checks:[^4][^5][^3]

- **Classify the failure before deciding the response.** A "close variant" or auto-correctable mismatch (enum drift like `cancelled` vs `canceled`) merits automatic repair; a genuine semantic/business-rule violation should only auto-repair if the correction is unambiguous, and should otherwise escalate. Capability-policy denial where the manifest names exactly one lower-privilege fallback policy (as in `tutor_response` → `specialist`) is the unambiguous case — safe for deterministic auto-repair, no LLM round-trip needed.[^3]
- **Repair prompts should carry the specific violated rule, not a generic retry.** When repair *does* require the LLM (e.g., ambiguous cases where the manifest allows multiple policies), feed back the exact constraint violated: "policy `write_proposed` is not permitted for capability `tutor_response`; allowed policies are `[specialist, none]`" rather than a raw error trace[ from prior research]. This is the same "healing retry, not blind retry" principle documented across current structured-output tooling.[^4]
- **Budget repairs strictly and separate repair tiers by risk.** A repeatedly cited rollout pattern: one repair attempt for syntax/schema issues, no automatic repair for higher-risk semantic/permission failures, human/deterministic review only as last resort. Capability-policy repair sits in a special "deterministic-safe" tier below LLM repair because the manifest itself supplies the correct value — it should resolve in zero LLM calls, not consume your retry budget at all.[^6][^3]


### 4. Preventing fallback from violating single-owner turn interpretation

The critical architectural discipline: **fallback must never re-derive semantic interpretation from raw text; it may only re-map or restrict an already-produced interpretation.** Concretely:

- The deterministic pipeline should receive the orchestrator's `turn_interpretation` object as an *input*, not bypass it and reprocess the raw user turn. If your current fallback pipeline is regenerating "Correct, this concept can be considered understood" from scratch rather than consuming the orchestrator's own semantic read of "answer correct, advance," it is re-owning interpretation — precisely the single-owner violation from your first architecture question.
- Fallback should operate at the narrowest possible scope: **policy remap**, not **capability reassignment**, not **re-classification of the turn**. Governance/policy-engine patterns for agent systems formalize this as checkpointed enforcement — a policy engine intercepts only the specific action-parameter that violates a rule and substitutes the nearest compliant one, leaving the rest of the request pipeline (which capability was chosen, why) untouched.[^7][^8]
- Practically: build a `repair_policy(capability, requested_policy, manifest) -> allowed_policy` pure function that runs *before* any fallback-pipeline invocation. If it succeeds (as it deterministically will for `tutor_response+write_proposed → specialist`), the orchestrator's decision is repaired in-place and executed with the corrected policy — the legacy pipeline is never invoked, and turn ownership never leaves the orchestrator.


### 5. Should capability-policy rules be static, manifest-generated, learned, or negotiated?

A **manifest-generated, statically-versioned rule set** is the right default for this stage of system maturity, with clear reasoning:


| Approach | Fit for capability-policy validation | Rationale |
| :-- | :-- | :-- |
| Hardcoded static rules | Poor | Duplicates logic already in the manifest; drifts when manifest changes[^3] |
| Manifest-generated (your current design) | **Recommended** | Single source of truth; deterministic; supports the zero-LLM-call repair described above; schema-versioning practices apply directly[^4][^3] |
| Learned/statistical | Not recommended for this layer | Safety-critical policy gating should not be probabilistic — the entire point is a hard boundary preventing untrusted writes to mastery state |
| Dynamic negotiation (orchestrator argues for exception) | Situational, advanced | Could work as an *escalation* tier for ambiguous cases (multiple allowed policies), but should never bypass the manifest's hard denials |

The manifest-driven approach also enables the deterministic remap in Section 3: because the manifest already encodes the maximal permitted policy per capability, a policy_denied event carries an implicit "nearest safe value," which is what makes zero-latency, zero-LLM auto-repair possible. This mirrors the "output contract" and schema-versioning discipline recommended in production structured-output tooling, applied to policy rather than syntax.[^4][^3]

### 6. Handling "correct answer → advance" transitions safely and naturally

The specific quality bug — an abrupt, disconnected transition — stems from the fallback pipeline treating "advance to next concept" as a **new, context-free turn** rather than a continuation of the orchestrator's already-formed pedagogical intent. The fix follows directly from Sections 2–4:

- **Separate the state-write from the utterance-generation.** `diagnose_answer` (with `policy=write_proposed`) should own the mastery-state update — that's correctly gated and safe. `tutor_response` (with the repaired `policy=specialist`) should then be invoked *with the orchestrator's own `turn_interpretation`* (which already contains "answer correct, transitioning to next concept") as context, so the generated utterance is a natural transition rather than a generic template stitched to the next diagnostic question.
- **Sequence, don't fork.** The two capabilities should be called as a small orchestrated sequence within the *same* turn-decision — diagnose (write) then respond (generate) — rather than the diagnosis committing a rigid canned string and a separate legacy step bolting on the next question. This preserves state-write safety (mastery update is still gated through the validated, write-capable path) while giving the specialist policy full context to phrase a natural pedagogical bridge ("Nice, that concept's solid now — let's look at...").
- This is consistent with the output-contract principle that only high-risk fields (mastery state) need the strictest gating, while low-risk fields (phrasing, tone, transition language) should be handled by the most capable available generator, not the most restrictive fallback path.[^3]


### 7. Framework patterns applicable to this exact problem

- **LangGraph**: model this as two graph nodes with a conditional edge — a `validate_policy` node that runs the manifest-based remap deterministically (not an LLM call), and only routes to a `repair_llm` node when the manifest itself lists more than one candidate policy (genuine ambiguity). The `with_structured_output(Schema)` pattern for the orchestrator's own decision generation, combined with a downstream reducer that patches only the `policy` field in state, keeps the rest of `turn_interpretation` untouched and traveling forward through the graph[ from prior research].
- **OpenAI structured outputs / function calling**: use `strict: true` schemas to guarantee `action`, `capability`, and `policy` are each individually valid enum members (eliminating one class of failure at generation time), then apply the manifest cross-field check as a business-rule validator layered on top — since structured outputs guarantee shape but not cross-field semantic validity.[^9][^3]
- **Governance/policy-engine patterns** (e.g., checkpointed policy enforcement in the request pipeline) generalize this to any agent framework: intercept at the narrowest checkpoint (policy field), apply the manifest's compliant substitute, log the correction as a metric, and pass the corrected request onward without re-entering the whole pipeline. This is directly transferable to Semantic Kernel (planner + validated skill invocation), AutoGen (manager agent + constrained tool schema), and CrewAI (task validation before agent dispatch), since all three share the same planner-owns-intent, tool-executes-narrowly structure.[^8][^7]

**The key distinction your question raises — safety validation vs. quality-regression-inducing over-validation** — comes down to granularity: validating the *entire decision object* and falling back wholesale is over-broad safety that destroys quality; validating and repairing the *single non-compliant field* while preserving everything else the orchestrator already determined is the correct scope for safety, and it's what current structured-output and policy-engine literature converges on.[^1][^8][^3]
<span style="display:none">[^10][^11][^12][^13][^14][^15]</span>

<div align="center">⁂</div>

[^1]: https://promptz2h.com/chapter_16_structured_output_and_reliability_engineering/series_01_json_mode_and_schema_enforced_output/validation_repair

[^2]: https://arxiv.org/html/2606.09395

[^3]: https://dev.to/jackm-singularity/llm-structured-output-validation-stop-json-breaks-before-they-hit-production-1f64

[^4]: https://dev.to/velsof/bulletproofing-llm-structured-output-in-python-healing-retries-cost-caps-and-drift-detection-c89

[^5]: https://www.kunalganglani.com/learning-paths/ai-software-developer/aidev-structured-output-parsing

[^6]: https://lawzava.com/blog/2024-04-29-structured-output-patterns/

[^7]: https://dev.to/alexgardenmnemom/building-proactive-ai-agent-governance-policy-engines-in-the-request-pipeline-16if

[^8]: https://github.com/microsoft/agent-governance-toolkit/blob/main/docs/specs/AGENT-OS-POLICY-ENGINE-1.0.md

[^9]: https://community.openai.com/t/partially-structured-output-free-text-output-but-force-correct-tool-call-json/955147

[^10]: https://news.ycombinator.com/item?id=46345333

[^11]: https://github.com/pydantic/pydantic-ai/issues/1192

[^12]: https://community.n8n.io/t/model-output-doesnt-fit-required-format-structured-output-parser/106424

[^13]: https://raw.githubusercontent.com/langflow-ai/langflow/refs/heads/main/src/lfx/src/lfx/components/llm_operations/structured_output.py

[^14]: https://stackoverflow.com/questions/79594814/llm-structured-output-sometimes-incomplete-or-incoherent-when-generating-json-p

[^15]: https://cran.r-project.org/web/packages/LLMR/vignettes/about-schema.html

