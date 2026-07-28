# Learning Manager Orchestrator

## Ownership Model

`LearningManagerOrchestrator` is the turn-level decision owner. It reads an immutable `LearningManagerTurnContext` and proposes one bounded action: answer directly, call a capability, delegate a capability, resume the pipeline, continue the pipeline, or fall back to the legacy pipeline.

`PelicanEngine` remains the state owner. It validates the orchestrator proposal, dispatches only legal capability requests, records methodology events, persists session state, and owns all mastery writes.

The six-stage PELICAN pipeline remains the deterministic learning-state guardrail:

1. Goal framing
2. Skill construction
3. Cognitive diagnosis
4. Knowledge state update
5. EDF strategy selection
6. Tutor response

Specialist agents are exposed as engine-owned capabilities instead of fixed pipeline job takers. The orchestrator can choose a capability, but cannot execute it directly.

## Capability Policy

`CapabilityPolicy` controls what an orchestrated action is allowed to request:

- `none`: no tool or state-writing capability; used for direct clarification and no-write dialogue.
- `read`: read/resume behavior only.
- `specialist`: run a specialist capability that does not write mastery evidence.
- `write_proposed`: propose that the engine run a write-capable specialist. This is not permission to write; `PelicanEngine` must still validate the phase, snapshot, idempotency key, and capability metadata.

Current capability labels include:

- `diagnose_answer`
- `clarify_current_prompt`
- `tutor_response`
- `edf_policy`
- `slow_simulator`
- `resume_pipeline`

## Model Routing

Learner-facing tutor responses default to `google/gemini-3.5-flash-lite`.

Learning manager decisions also default to `google/gemini-3.5-flash-lite`.

Skill generation remains category-routed through `model_route_for_category()` so stronger or domain-specific generation routes are not overwritten by the lower-latency tutor/orchestrator route.

## Structured Output Health

`LlmAdapter.check_orchestrator_structured_output_health()` probes whether the selected orchestrator route accepts strict OpenAI/OpenRouter `json_schema` response formatting. If strict schema is unsupported, unavailable, or unknown, the orchestrator call falls back to JSON-object prompting and local validation.

Local validation remains mandatory in both paths. Invalid action names, policy names, confidence scores, stale snapshot ids, missing capabilities, and unknown capabilities are reduced to deterministic fallback.

## Same-Turn Trace

The safe debugging path for one turn is:

1. `pelican_turn_started`
2. `pelican_learning_orchestrator_decided` or `pelican_learning_orchestrator_fallback`
3. `pelican_learning_capability_selected`
4. `pelican_learning_capability_no_write_guarded` when the capability is no-write
5. Existing specialist/pipeline events
6. `pelican_learning_capability_completed`

Rejected or duplicate decisions emit `pelican_learning_orchestrator_action_rejected`.

Capability registry rejections emit `pelican_learning_capability_rejected`.

## Privacy Boundary

Structured logs may include safe labels such as `turn_id`, `cycle_id`, `phase`, `node_id`, `action`, `capability`, `policy`, `target_phase`, `confidence_bucket`, `proposal_source`, `idempotency_key`, `outcome`, and `reason_code`.

Structured logs must not include raw learner text, prompts, model output, provider response bodies, credentials, tokens, or hidden reasoning.
