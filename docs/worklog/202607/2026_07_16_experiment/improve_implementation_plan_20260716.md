The July 16 failures should be addressed in four gated phases. The first phase makes hot memory an explicit working-state layer with controlled expiry and controlled export to cold memory. The second phase establishes a trustworthy cold-memory ingestion and profile-promotion boundary using only a user's exact evidence. The third phase makes ComPeer delivery durable and observable when Redis is slow or unavailable. The final phase extracts these responsibilities from the orchestration service without changing the existing streaming contract, while separating instructional claims about learner understanding from durable memory. This order is intentional: no hot-memory observation, scheduler flag, or model inference may bypass the evidence boundary during compaction.

The implementation decisions in this plan are governed by [AREQA Memory Management Principles](/workspaces/AREQA/docs/tech_docs/memory_managing_principle.md). That guide is the product-policy source of truth for source authority, permitted memory transitions, sensitivity handling, cold-memory lifecycles, promotion thresholds, prompt use, correction, and audit metrics. Where an older plan statement is less specific, the guide takes precedence; implementation must not reopen those policies implicitly.

Phase 2 includes a constrained semantic-analysis capability using `google/gemini-2.5-flash-lite` through the existing OpenRouter client boundary. It exists only to canonicalize an already eligible low-risk candidate and compare it with active candidates belonging to the same user. It is not an authority for source validation, safety classification, candidate creation, evidence counting, expiry, or profile promotion. The feature must begin in shadow mode and is enabled for candidate matching only after its regression and evaluation gate passes.

### Cross-Phase Observability Requirement

Every changed memory, compaction, scheduling, and orchestration boundary must emit structured logs through the project's existing logger so an engineer can follow the state in the terminal without inspecting Redis or the database first. Use stable event names and correlation fields appropriate to the flow: `request_id`, `user_id` or an approved redacted identifier, `conversation_id`, `message_id`, `candidate_id`, and `task_id` when available. Log successful state transitions at `INFO`, policy blocks and retryable conditions at `WARNING`, and unexpected failures with exception context at `ERROR`. Do not log raw user text, quoted evidence, prompt contents, sensitive classifications, credentials, or complete model output. Tests must assert event names and safe metadata for new critical transitions, rather than human-formatted log strings.

### Phase 1: Define Hot-Memory Ownership and Safe Hot-to-Cold Compaction

#### Problem

The system already has two short-lived state stores: `areqa:hot_memory:{user_id}` for Redis-backed operational state and `areqa:working_memory:{user_id}` for prompt-safe learning context. They currently contain a mixture of learner state, current strategy, observations, avatar and proactive-delivery flags, and values produced by background GUM processing. `run_compaction` in `backend/gum_integration.py` can write selected hot-memory entries directly to the cold-memory retriever after a budget overflow. Its current source check accepts a broad `source` label such as `user_message`, but does not require the complete message ID, conversation ID, timestamp, source role, and original quote required for a trustworthy user-memory write.

This means a strict cold-memory ingestion policy alone is insufficient. An inferred learning state, a behavioral observation, or an operational entry can be retained in hot memory and later reach cold storage through compaction if its metadata is incomplete or incorrectly labelled. The target behaviour is that hot memory remains available for current learning and ComPeer operations, but only explicitly classified, fully-provenanced user evidence can be considered for cold-memory export. All other hot entries remain working state, expire, or are discarded; they never become user memory.

#### Assumptions

This phase keeps Redis-backed hot memory and the current working-memory prompt snapshot in place. It does not replace the learner-state, strategy, avatar, cooldown, or ComPeer trigger mechanisms. Existing untyped hot-memory entries may remain readable for compatibility, but they must be treated as non-exportable during migration because they lack a reliable source classification. If an entry cannot be safely classified, compaction must retain it until its own expiry or discard it according to its operational policy; it must not write it to cold memory.

The plan assumes a hot entry can carry metadata without changing the public chat or SSE contract. Each hot category must have an explicit, configurable expiry policy represented by `created_at` and `expires_at`; it must not silently become durable. The implementation must support source/kind, confidence, export policy, and provenance fields. The policy guide fixes the durable-layer lifecycles introduced in Phase 2, while this phase makes expiry enforceable for all hot entries. Scheduler flags must preserve their current semantics until Phase 3 changes their durable-delivery ordering.

#### Solution

Introduce a typed hot-memory entry model and one ownership boundary for writing and reading it. Every newly written entry must be classified as one of: `user_evidence`, `working_context`, `model_inference`, `behavior_signal`, or `operational_state`. It must also declare whether it is prompt-safe and whether it is eligible for cold export. Only `user_evidence` entries with full immutable provenance are eligible for export; eligibility means “may be submitted to the Phase 2 ingestion service”, not “may be written directly to cold storage”.

`working_context`, `model_inference`, and `behavior_signal` entries may influence the current pedagogical response only under their TTL and confidence policy. They must not create profile facts. `operational_state` entries, including `trigger_proactive`, `avatar_summon_pending`, cooldowns, and active-avatar state, are never prompt-personalization evidence and never cold-memory export candidates. The compaction path must fail closed: before Phase 2 is available it retains or expires eligible source material rather than directly calling the cold-memory writer; after Phase 2 it submits only a validated evidence record to the ingestion boundary.

#### Implementation

> Context: Add Google-style docstrings to the proposed hot-memory service, the entry type, and every public read/write/export method. Comments must explain why hot memory is operational working state rather than user profile memory, why only fully-provenanced `user_evidence` may leave the hot layer, and why the compaction path must retain data when classification is incomplete. Add inline rationale at TTL filtering, prompt-safe filtering, export-policy checks, and critical structured-log emission; do not narrate ordinary Redis serialization. The code must make it difficult for a future writer to label a GUM inference or scheduler flag as user evidence by accident.

Add `backend/services/hot_memory_service.py` as the proposed owner of typed entry creation, expiry filtering, prompt-safe snapshots, and cold-export eligibility. Define a proposed `HotMemoryEntry` value object with `kind`, `source_role`, `created_at`, `expires_at`, `confidence`, `prompt_safe`, `cold_export_eligible`, and optional immutable user-evidence provenance fields. Use explicit kinds for `user_evidence`, `working_context`, `model_inference`, `behavior_signal`, and `operational_state`; no default kind may be exportable.

Update `backend/memory_store.py` so `get_hot_memory`, `update_hot_memory`, `update_learner_state_snapshot`, and `append_learning_observation` preserve the new envelope for newly written entries while continuing to read legacy values. Mark learner-state snapshots, strategy, observations, cooldowns, avatar state, and proactive triggers as `working_context` or `operational_state` with explicit expiry and `cold_export_eligible = false`. Preserve the existing `areqa:hot_memory:{user_id}` key and `areqa:working_memory:{user_id}` compatibility surface.

Update `backend/gum_integration.py`. `get_hot_memory_snapshot` must include only non-expired, prompt-safe working context and explicitly scoped user evidence; it must not expose scheduler flags or raw model-inference entries as user facts. Change `run_compaction` so it first filters typed entries by `kind == user_evidence`, complete provenance, and `cold_export_eligible == true`. During this phase it must not call `ColdMemoryRetriever.insert_memory` directly for any hot entry; an eligible entry remains in hot memory until Phase 2 provides the server-owned ingestion handoff. Untyped legacy entries and every non-user category must be retained, expired, or deleted according to their local lifecycle, never exported.

Update direct hot-memory writers in `backend/services/compeer_scheduler.py` and `backend/services/orchestration_service.py` to use the typed writer for operational keys without changing their current scheduling behavior. Phase 3 will later change when proactive triggers are cleared, but this phase must already guarantee that these entries cannot reach prompt-visible user memory or cold storage.

Emit safe structured events for hot-entry creation, expiry, prompt-snapshot exclusion, export handoff eligibility, and blocked export. Include entry kind, expiry status, policy reason, and available correlation IDs, but never the value, original quote, or prompt content. This must make a terminal trace answer why an entry was used, expired, excluded, retained, or refused for cold handoff.

#### Expected File Tree After Phase 1

```text
backend/
├── gum_integration.py                                      [modified]
├── memory_store.py                                         [modified]
└── services/
    ├── compeer_scheduler.py                                [modified]
    ├── hot_memory_service.py                               [new]
    └── orchestration_service.py                            [modified]
tests/backend/
├── test_compaction_flow.py                                 [modified]
├── test_compaction_prompt_safety.py                        [modified]
├── test_gum_integration.py                                 [modified]
├── test_memory_injection_regression.py                     [modified]
└── test_memory_store.py                                    [modified]
```

#### Work List

1. [ ] Create `backend/services/hot_memory_service.py`.
   - [ ] Add the proposed `HotMemoryEntry` type and typed write/read helpers for `user_evidence`, `working_context`, `model_inference`, `behavior_signal`, and `operational_state`.
   - [ ] Add the proposed `is_cold_export_eligible()` check requiring complete immutable user provenance and an explicit export flag.
2. [ ] Modify `MemoryStore` in `backend/memory_store.py`.
   - [ ] Update `get_hot_memory()` and `update_hot_memory()` to preserve typed entries while treating untyped legacy entries as non-exportable.
   - [ ] Update `update_learner_state_snapshot()` and `append_learning_observation()` to write non-exportable working-context or observation entries with expiry metadata.
3. [ ] Modify `run_compaction()` and `get_hot_memory_snapshot()` in `backend/gum_integration.py`.
   - [ ] Remove direct `ColdMemoryRetriever.insert_memory()` export from hot compaction until the Phase 2 ingestion boundary receives a validated evidence record.
   - [ ] Filter expired, non-prompt-safe, and operational entries before creating the prompt snapshot.
4. [ ] Modify direct writers in `backend/services/compeer_scheduler.py` and `backend/services/orchestration_service.py`.
   - [ ] Mark `trigger_proactive`, `avatar_summon_pending`, cooldown, and avatar entries as `operational_state` with `cold_export_eligible = false`.
5. [ ] Add safe hot-memory observability through the existing logging abstraction.
   - [ ] Emit stable events for `hot_memory.created`, `hot_memory.expired`, `hot_memory.snapshot_excluded`, `hot_memory.export_eligible`, and `hot_memory.export_blocked` from `backend/services/hot_memory_service.py` or its integration boundary.
   - [ ] Include only kind, reason code, lifecycle state, and correlation IDs; confirm no raw hot-memory value, user quote, or prompt content is logged.
6. [ ] Extend `tests/backend/test_compaction_flow.py`, `test_compaction_prompt_safety.py`, `test_gum_integration.py`, `test_memory_injection_regression.py`, and `test_memory_store.py` for hot-entry classification, expiry, snapshot filtering, blocked hot-to-cold export, and safe critical-event metadata.

#### Test Plan

Extend `tests/backend/test_compaction_flow.py` to verify that a fully provenanced `user_evidence` entry is retained when Phase 2 ingestion is unavailable, while model inference, behavior signals, and operational state never invoke the cold-memory writer. Extend `tests/backend/test_compaction_prompt_safety.py` and `test_memory_injection_regression.py` to assert that a prompt snapshot excludes `trigger_proactive`, `avatar_summon_pending`, raw observations, expired entries, and model-inference entries that would be phrased as user facts. Extend `tests/backend/test_memory_store.py` and `test_gum_integration.py` for typed-entry serialization, legacy-entry fail-closed behavior, expiry filtering, and capture of `hot_memory.export_blocked` without raw memory content.

Run:

```bash
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_compaction_flow.py \
  tests/backend/test_compaction_prompt_safety.py \
  tests/backend/test_gum_integration.py \
  tests/backend/test_memory_injection_regression.py \
  tests/backend/test_memory_store.py
```

#### Expected Output / Result

Hot memory remains usable for current learning state, prompt context, and ComPeer operations, but it has an explicit lifecycle and export boundary. A GUM inference, scroll/behavior observation, learner-state value, avatar state, cooldown, or proactive trigger cannot be compacted into cold memory or rendered as a user profile fact. Only a typed `user_evidence` entry with complete provenance can become eligible for the Phase 2 ingestion handoff; until that handoff exists, compaction retains or expires it without a direct cold-memory write. The terminal shows safe, correlated events explaining each critical export and snapshot decision.

#### Testing Script

##### Act 01: Operational State Cannot Become Cold Memory

Create hot entries for `trigger_proactive`, `avatar_summon_pending`, a cooldown, and a learner-state snapshot, then force hot-memory compaction.

Pass condition: no cold-memory write occurs for any operational entry, and no operational value appears in the prompt snapshot as a user fact.

##### Act 02: Model Inference Remains Working State Only

Create a hot entry classified as `model_inference` with text indicating that the user appears to learn visually, then force compaction and request a prompt snapshot.

Pass condition: the entry is not exported to cold memory or profile memory, and the prompt does not state the inference as a confirmed user preference.

##### Act 03: Complete User Evidence Is Held for the Ingestion Boundary

Create a `user_evidence` hot entry with a source message ID, conversation ID, timestamp, source role, and original text, then force compaction before Phase 2 is enabled.

Pass condition: direct cold-memory insertion does not occur; the evidence remains available or expires according to its lifecycle, preserving its provenance for the Phase 2 handoff.

#### Gate to Enter the Next Phase

All Phase 1 tests must pass. Preserve test evidence showing that no non-user hot entry calls the cold-memory writer and that legacy untyped entries fail closed for export. If any export, snapshot, or expiry assertion fails, remain in this phase and fix the classification or lifecycle boundary before beginning Phase 2; do not re-enable direct compaction writes as a workaround.

### Phase 2: Establish a Trusted Memory-Ingestion and Promotion Boundary

#### Problem

The current memory flow has more than one authority for deciding whether a candidate becomes durable. `backend/memory_gate.py` still contains `MemoryRetentionDecision` and `evaluate_memory_retention_policy`; both are invoked from `backend/gum_integration.py` during candidate persistence and from `backend/memory_store.py` during promotion. In parallel, `classify_user_message` treats a phrase matching `"我偏好..."` as an explicit memory before it considers whether the whole utterance is a question. This explains why the fourth-act question was eligible to become a memory.

Candidate extraction is safer than an unrestricted model summary because it filters to user-role messages, but it still starts with a broad chat-history input and returns a reconstructed candidate. The resulting evidence currently has only message text, quote, and index. The system therefore has insufficiently explicit provenance at the point where it counts independent conversations and promotes a candidate. The target behaviour is that only explicit user evidence can enter the candidate store, questions and model inferences never become profile facts, and promotion requires independently recorded evidence from the configured number of conversations. Filtering a derived proposition out of the memory page is not sufficient: inferred learner ability, anxiety, or one-off SpaceX context must remain outside durable profile storage.

#### Assumptions

The plan assumes that the request path can supply a stable user-message identifier and timestamp, or can create them at ingestion time. If the deployed message schema cannot provide either value, automatic promotion must remain disabled for that candidate until the schema is extended; it must not substitute assistant text or a list index as durable provenance. The default `memory_candidate_auto_promote_conversations` value must be two for passive low-risk preferences, and only distinct conversation IDs and message IDs count. It may remain configurable, but no production configuration may reduce passive-preference promotion below two independent conversations without an explicit product-policy revision.

The policy guide fixes the initial category routing: a low-risk explicit preference becomes a 90-day cold candidate after one declarative statement; a temporary learning goal becomes a 30-day candidate or is removed on completion; a user command to remember a low-risk fact or preference may promote directly after provenance and safety validation; sensitive information is not automatically stored; and model inference, behavior-derived traits, and one-off search or learning context are never cold/profile memory. Supported stable direct-fact categories must be explicitly defined before one-statement profile promotion is enabled. Until then, they remain candidates or require explicit user confirmation.

The plan also assumes that `MemoryRetentionDecision` is an internal type rather than a public compatibility contract. Its imports and all runtime callers must be enumerated before removal. If another deployed worker imports it, that caller must migrate in the same release or the type must be retained temporarily as a compatibility adapter with no independent decision logic.

OpenRouter remains the selected transport because the backend already uses its `AsyncOpenAI` client and JSON-schema response format. Add a dedicated memory-semantic model setting pinned to `google/gemini-2.5-flash-lite`; do not change the existing main-chat, GUM, or policy-classifier model settings. The deployment must disable OpenRouter input/output logging and data-use opt-ins, enforce a Zero Data Retention-compatible provider route where available, and prohibit provider/model fallback that would weaken the structured-output or data-policy requirement. If these deployment controls cannot be verified, semantic analysis remains disabled and the deterministic memory flow continues without it.

#### Solution

Introduce one server-owned memory-ingestion boundary whose input is a single user evidence record, rather than an unstructured conversation window. The boundary will first determine speech act and eligibility, then capture immutable evidence, then use semantic extraction or embedding-based grouping only to associate evidence with an existing candidate. Deterministic rules remain the final safety authority: non-user sources, interrogatives, temporary context, sensitive assertions, and unsupported model inferences cannot enter cold or profile memory. The service must apply the guide's category-specific routing, promotion, and expiry rules rather than treating every candidate alike. GUM propositions may still be retained as explicitly non-profile operational observations when needed, but they must have a separate type, storage boundary, and lifecycle from candidate and promoted user memory. A model classifier or embeddings may improve semantic matching, but they must not independently authorize a profile write.

Add an explicit `MemorySemanticAnalyzer` boundary after the deterministic gate. For an eligible passive low-risk preference or temporary goal, it receives only the current user evidence and minimal active-candidate summaries for the same user and compatible category. Gemini must return strict JSON containing a proposed canonical key and exactly one relation: `match_existing`, `create_candidate`, or `uncertain`, with an optional candidate ID. The server validates the schema, ownership, category, expiry, and relation before accepting it. `match_existing` only joins evidence to an existing candidate; the existing promotion rule still requires two distinct conversations. `uncertain`, an invalid response, a timeout, missing credentials, or disabled analysis must fail closed: do not merge candidates, do not increase corroboration, and do not promote. A valid explicit remember command continues through its deterministic safety path without requiring Gemini.

`backend/memory_gate.py` should be reduced to narrow message-level safety and intent decisions. Candidate lifecycle and cross-conversation promotion should move into a dedicated memory-ingestion service. After callers migrate, remove `MemoryRetentionDecision` and `evaluate_memory_retention_policy`, replacing them with a single typed eligibility result used by both candidate creation and promotion. This prevents the current split-policy behaviour.

#### Implementation

> Context: Add Google-style docstrings to the new memory-ingestion module, its public evidence/result types, and `ingest_user_evidence()`. These comments must explain why profile memory accepts only immutable user-originated evidence, why interrogatives are rejected before preference matching, and why GUM/reflection output has a separate non-profile lifecycle. Add inline rationale at provenance checks, de-duplication, promotion boundaries, and critical structured-log emission; do not restate assignments or obvious control flow. The code must contain enough documentation for a maintainer to preserve these trust boundaries when adding a new memory source.

Add `backend/services/memory_ingestion_service.py` as the new owner of candidate intake and promotion eligibility. Its public input should be an explicit user evidence object containing the user ID, message ID, conversation ID, timestamp, raw message text, and source role. It should return a typed decision with an eligibility state such as rejected, working-context-only, candidate, or promotion-eligible, plus a machine-readable reason code, content category, and required expiry/revalidation policy. Apply the guide's initial routing: 90 days for passive low-risk preference candidates, 30 days or completion removal for temporary goals, direct promotion only for safe explicit remember commands, and automatic rejection from durable memory for sensitive data, assistant content, GUM propositions, reflection text, and raw mixed-role histories.

Add `backend/services/memory_semantic_analyzer.py` as a replaceable `MemorySemanticAnalyzer` protocol and OpenRouter implementation. Define typed request and response values that expose only: the current exact user evidence, an allowlisted category, and the target user's non-sensitive active-candidate IDs plus canonical summaries. Configure `AsyncOpenAI(base_url="https://openrouter.ai/api/v1")` with the dedicated `Settings.model_memory_semantic_analyzer`, non-streaming requests, `temperature = 0`, a bounded timeout, and strict JSON Schema. The response schema must be closed (`additionalProperties = false`) and allow only `match_existing`, `create_candidate`, or `uncertain`; it must never return a promotion action, a TTL, a sensitive classification, or free-form reasoning. Do not send assistant text, mixed conversation history, profile contents outside the allowed category, candidate evidence quotes, or data belonging to another user.

Extend `backend/config.py` with a dedicated `model_memory_semantic_analyzer` default of `google/gemini-2.5-flash-lite`, a disabled-by-default shadow/activation flag, an analysis timeout, and a maximum same-user active-candidate comparison count. Update `backend/memory_gate.py` so its remaining deterministic classification emits the allowlisted category and a canonical-rule key where one is available; it must not use Gemini to rescue a rejected, sensitive, interrogative, hypothetical, or incomplete-provenance message. Update `memory_ingestion_service.py` to call the analyzer only after these checks, validate its response, and pass only a server-validated candidate ID to `MemoryStore.append_cold_candidate`.

Update `backend/services/orchestration_service.py` at the existing user-message handling point and `backend/gum_integration.py` at `async_evaluate_and_update_state` so they pass the same exact user evidence record to the new service. After Phase 1, `run_compaction` may submit only a fully-provenanced, typed `user_evidence` hot entry to this same service; it must not recreate a mixed chat history or call the cold-memory writer directly. The learner-state evaluation may continue to receive recent chat context for pedagogy, but its output must remain non-authoritative for user profile memory and must not reuse the candidate-memory persistence path. `extract_user_memory_candidates` should either be replaced by an evidence-record-based extractor or changed to accept only the collected user evidence records; it must preserve the original message ID, conversation ID, timestamp, quote, and source role in every returned candidate.

Modify `backend/memory_gate.py` so interrogative detection runs before `EXPLICIT_MEMORY_PATTERNS`. Messages such as `"我偏好什麼學習方法？"` must be classified as a query or current focus, never as an explicit memory, while a declarative statement such as `"我偏好用具體例子理解抽象概念。"` remains eligible as evidence. Preserve role-play, low-information, and sensitive-content handling. Move cross-conversation counting and evidence de-duplication into `MemoryStore.append_cold_candidate` and `MemoryStore.promote_cold_candidate`, using distinct conversation IDs and distinct message IDs rather than repeated observations in one conversation. A candidate without complete provenance may be stored only as non-promotable internal state.

Migrate `backend/memory_store.py` to consume the new typed eligibility result. A profile write through `perform_memory_operation` must continue to require `verified_user_evidence`, and promotion must verify the full evidence set immediately before writing. Remove `MemoryRetentionDecision` and its imports only after `backend/gum_integration.py`, `backend/memory_store.py`, and their tests use the new service. No historical candidate should be auto-promoted during migration; incomplete legacy evidence should remain pending or require explicit user confirmation.

Emit safe structured events for each ingestion decision, cold-candidate lifecycle transition, promotion block, profile promotion, correction, and expiry. The events must carry decision state, reason code, content category, candidate ID, and available correlation IDs, but not user text, quoted evidence, or a label that reveals sensitive content. This provides an auditable terminal sequence from user message to candidate, block, expiry, or verified profile write.

#### Expected File Tree After Phase 2

`[new]` marks a new file, `[modified]` marks an existing file expected to change, and `[removed]` marks code removed from an existing file rather than a file deletion.

```text
backend/
├── gum_integration.py                                      [modified]
├── memory_gate.py                                          [modified; MemoryRetentionDecision removed]
├── memory_store.py                                         [modified]
├── config.py                                               [modified]
└── services/
    ├── memory_ingestion_service.py                         [new]
    ├── memory_semantic_analyzer.py                         [new]
    └── orchestration_service.py                            [modified]
tests/backend/
├── test_config.py                                          [modified]
├── test_memory_gate.py                                     [modified]
├── test_memory_injection_regression.py                     [modified]
├── test_memory_semantic_analyzer.py                        [new]
├── test_memory_source_boundaries.py                        [modified]
├── test_memory_store.py                                    [modified]
└── test_real_memory_pipeline.py                            [modified]
```

#### Work List

1. [ ] Create `backend/services/memory_ingestion_service.py`.
   - [ ] Add the proposed `UserEvidence` value object: `user_id`, `message_id`, `conversation_id`, `timestamp`, `raw_message_text`, and `source_role`.
   - [ ] Add the proposed typed eligibility result with `rejected`, `working_context_only`, `candidate`, and `promotion_eligible` states, a machine-readable reason code, content category, and required expiry/revalidation fields.
   - [ ] Implement the proposed `ingest_user_evidence()` method that accepts one `UserEvidence` record; route passive low-risk preferences to a 90-day candidate, temporary goals to a 30-day/completion-based candidate, and valid explicit remember commands to safety-validated promotion eligibility.
   - [ ] Reject sensitive content, assistant/reflection/GUM input, model inference, behavior-derived traits, and one-off learning/search context from durable memory with stable reason codes.
2. [ ] Create `backend/services/memory_semantic_analyzer.py`.
   - [ ] Add the proposed `MemorySemanticAnalyzer`, `SemanticAnalysisRequest`, and `SemanticAnalysisResult` types, with only `match_existing`, `create_candidate`, and `uncertain` as accepted relations.
   - [ ] Implement the OpenRouter/Gemini adapter with `AsyncOpenAI`, `Settings.model_memory_semantic_analyzer`, non-streaming `temperature=0`, bounded timeout, strict JSON Schema, and no free-form reasoning field.
   - [ ] Limit each request to current eligible user evidence and a bounded set of same-user, same-category active candidate IDs and canonical summaries; reject any result that references another user, a missing/expired candidate, or a mismatched category.
   - [ ] Return a typed unavailable/uncertain result on missing credentials, timeout, provider error, or schema-validation failure; never retry by changing provider/model or make a durable-memory decision in the adapter.
3. [ ] Modify `backend/config.py` and `tests/backend/test_config.py`.
   - [ ] Add `model_memory_semantic_analyzer = "google/gemini-2.5-flash-lite"`, disabled-by-default shadow/activation settings, timeout, and same-user comparison limit with environment-variable overrides.
   - [ ] Verify the memory semantic setting is independent of `model_main_instruct`, `model_gum`, and `model_policy_classifier`.
4. [ ] Modify `backend/memory_gate.py` to make message-level eligibility unambiguous.
   - [ ] Change `classify_user_message` so interrogative detection runs before `EXPLICIT_MEMORY_PATTERNS`.
   - [ ] Keep declarative preferences eligible while classifying `我偏好什麼學習方法？` as a query/current-focus message.
   - [ ] Produce only allowlisted category and canonical-rule metadata for messages that pass deterministic safety checks; do not call the semantic analyzer for rejected or sensitive input.
   - [ ] Remove `MemoryRetentionDecision` and `evaluate_memory_retention_policy` only after runtime imports and callers have migrated.
5. [ ] Rewire candidate creation in `backend/gum_integration.py` and the ingestion service.
   - [ ] Update `async_evaluate_and_update_state` to pass exact user evidence to the new intake service.
   - [ ] Update `run_compaction()` to submit only Phase 1 `user_evidence` entries with complete provenance to `ingest_user_evidence()`, replacing the direct cold-memory write path.
   - [ ] Replace or narrow `extract_user_memory_candidates` so every returned candidate preserves message ID, conversation ID, timestamp, source role, and quoted source text.
   - [ ] Keep learner-state/GUM propositions on a non-profile path that cannot call profile-memory persistence.
   - [ ] Invoke `MemorySemanticAnalyzer.analyze()` only after the deterministic acceptance path; accept a semantic match only after server-side result validation, and treat `uncertain` or unavailable analysis as no merge/no corroboration.
6. [ ] Strengthen promotion in `backend/memory_store.py`.
   - [ ] Update `MemoryStore.append_cold_candidate` to de-duplicate evidence with message ID and conversation ID.
   - [ ] Persist the 90-day preference expiry and 30-day/completion-based goal lifecycle from the ingestion decision; prevent expired or completed candidates from promotion.
   - [ ] Update `MemoryStore.promote_cold_candidate` to require complete provenance and two distinct-conversation evidence records for passive preferences immediately before `perform_memory_operation`, while preserving the separately validated explicit-command route.
   - [ ] Keep legacy candidates with incomplete provenance pending and non-promotable.
7. [ ] Add safe memory-ingestion observability in `backend/services/memory_ingestion_service.py`, `backend/services/memory_semantic_analyzer.py`, and `backend/memory_store.py`.
   - [ ] Emit stable events for `memory.ingestion_decided`, `memory.candidate_created`, `memory.promotion_blocked`, `memory.profile_promoted`, `memory.candidate_expired`, and `memory.correction_applied`.
   - [ ] Include decision/reason/category, lifecycle state, and correlation IDs without raw message text, quoted evidence, or sensitive-content labels.
   - [ ] Emit `memory.semantic_shadow_result`, `memory.semantic_match_accepted`, and `memory.semantic_analysis_unavailable` with model ID, relation, safe reason code, candidate ID, and correlation IDs only.
8. [ ] Extend `tests/backend/test_memory_gate.py`, `test_memory_source_boundaries.py`, `test_memory_store.py`, `test_memory_injection_regression.py`, `test_real_memory_pipeline.py`, and new `test_memory_semantic_analyzer.py` with the Phase 2 regression cases and safe-event assertions.

#### Test Plan

Add focused unit coverage to `tests/backend/test_memory_gate.py` for interrogative preference wording, declarative preference wording, explicit "remember" requests, role-play, temporal statements, and sensitive-content rejection. Extend `tests/backend/test_memory_source_boundaries.py` to assert that assistant output, GUM/reflection inference, inferred learner ability or anxiety, a one-off SpaceX question, sensitive content, and an incomplete-provenance candidate cannot reach `perform_memory_operation` for a user profile. Add service-level tests for the new ingestion service that verify one passive preference creates a 90-day candidate, one temporary goal creates a 30-day/completion-based candidate, a validated explicit remember command follows its direct-promotion route, and two semantically matching declarative statements from different conversation IDs can become promotion-eligible. Repeated messages in one conversation cannot. The fixture for this positive case must use two actual distinct conversations; the July 16 third- and fourth-act inputs do not qualify because the fourth input is a question, not a second declaration.

Add `tests/backend/test_memory_semantic_analyzer.py` with mocked OpenRouter responses for: a strict-schema semantic match between the concrete-example preference phrasings; `create_candidate`; `uncertain`; invalid JSON/schema; timeout; missing key; a cross-user candidate ID; an expired candidate ID; and a category mismatch. Assert that the adapter never receives assistant text, mixed chat history, evidence quotes, sensitive input, or another user's candidate summary. Extend `tests/backend/test_memory_injection_regression.py` and `test_real_memory_pipeline.py` for shadow mode (analysis logged but no persistence change), active mode (only a validated same-user match can add evidence), and fail-closed fallback (unavailable analysis cannot merge, corroborate, or promote). Capture semantic event metadata and assert that it contains no raw user text or model response.

Retain and extend the integration path through `async_evaluate_and_update_state` and `run_compaction` with mocked model output. The assertions must prove that candidate extraction receives only user evidence records, a Phase 1 eligible hot entry is handed to the same ingestion service rather than directly persisted, and the exact fourth-act question does not create or promote a candidate. Capture representative `memory.ingestion_decided` and `memory.promotion_blocked` events and assert their reason codes/correlation IDs without exposing evidence text. Run:

```bash
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_memory_gate.py \
  tests/backend/test_memory_source_boundaries.py \
  tests/backend/test_memory_store.py \
  tests/backend/test_memory_injection_regression.py \
  tests/backend/test_memory_semantic_analyzer.py \
  tests/backend/test_real_memory_pipeline.py
```

#### Expected Output / Result

The system has one authoritative memory-ingestion path that receives complete, immutable user evidence. One passive low-risk preference becomes a 90-day cold candidate and becomes promotion-eligible only after two distinct conversations provide matching explicit evidence. Gemini 2.5 Flash-Lite may safely associate semantically equivalent, already eligible same-user candidates, but it cannot bypass the deterministic gate, create a profile write, or turn uncertainty into corroboration. A temporary goal receives a 30-day or completion-based lifecycle, while a low-risk explicit remember command uses a separately validated direct-promotion route. The question `"我偏好什麼學習方法？"`, a one-off Newton or SpaceX question, sensitive content, assistant text, and GUM/reflection-derived learner attributes all produce a non-promotable result with a recorded reason code. No inferred learner ability, anxiety, or temporary SpaceX context is written to cold or user-profile memory, even when the memory page would otherwise hide it. The terminal provides a safe, correlated decision trail for every candidate, semantic-analysis result, and promotion outcome.

#### Testing Script

##### Act 01: A Question Must Not Become a Preference Memory

Create a clean conversation and send: `我偏好什麼學習方法？`

Pass condition: the message is recorded as a query/current-focus decision with a non-promotable reason code. Neither the exact question nor a normalized preference appears in the user profile or long-term memory page.

##### Act 02: One Explicit Preference Is Evidence, Not Yet a Profile Fact

In conversation A, send: `我偏好用具體例子理解抽象概念。`

Pass condition: one candidate contains the original message ID, conversation ID, timestamp, source role, and quoted text. It remains unpromoted until the configured cross-conversation threshold is met.

##### Act 03: Only Independent Declarations Can Promote a Preference

Create conversation B and send the same declarative preference. Create additional distinct conversations only when the configured threshold is greater than two.

Pass condition: the preference is promoted only after the threshold is met using unique conversation IDs and message IDs. Repeating the statement inside one conversation does not add independent evidence.

##### Act 04: Derived Learning Context Must Stay Outside the Profile

With a clean user, ask one Newton question and one SpaceX question while the test double returns GUM/reflection propositions about weak physics ability, exam anxiety, or SpaceX context.

Pass condition: no such proposition reaches profile storage, whether or not the memory page filters it from view.

##### Act 05: Hot Evidence Uses the Same Ingestion Gate

Force compaction for one Phase 1 `user_evidence` hot entry with complete provenance and one `model_inference` hot entry.

Pass condition: only the user-evidence entry reaches `ingest_user_evidence()`; neither entry is written directly to cold or profile memory, and the model inference is rejected from the handoff.

##### Act 06: Category Lifecycles and Sensitive-Data Rejection Are Enforced

In separate clean conversations, send one passive preference, one explicit temporary learning goal, one valid low-risk `remember this` command, and one message containing sensitive personal information.

Pass condition: the preference has a 90-day candidate expiry, the goal has a 30-day or completion lifecycle, the explicit command follows the validated direct-promotion route, and the sensitive message has no cold or profile record.

##### Act 07: Gemini Can Match Equivalent Safe Preferences but Cannot Promote Them

Enable semantic-analysis shadow mode and send `我偏好用具體例子理解抽象概念。` in conversation A, then send `學抽象概念時，我希望先看具體案例再理解原理。` in conversation B. Review the safe terminal events, then enable active matching only after the shadow result is recorded.

Pass condition: shadow mode records a `match_existing` suggestion without changing stored evidence; active mode accepts the same-user, same-category match and records two distinct evidence records, after which the deterministic promotion rule, not Gemini, performs the one permitted profile promotion.

##### Act 08: Semantic-Analysis Failure Cannot Create Corroboration

For a second user with one active preference candidate, simulate an OpenRouter timeout, invalid schema response, and an `uncertain` response while submitting a semantically similar declaration.

Pass condition: each failure produces a safe unavailable/uncertain event, does not merge with the prior candidate, does not increase cross-conversation evidence, and does not promote a profile memory.

#### Gate to Enter the Next Phase

All Phase 2 tests must pass, including the new question, provenance, independent-conversation, category-lifecycle, sensitive-data, semantic-match, and semantic-failure assertions. The implementation must preserve the existing `perform_memory_operation` source guard, and a test must demonstrate that no live caller still depends on the retired retention policy. Before enabling active semantic matching, retain a shadow-mode evaluation sample showing no false match of question, sensitive, cross-user, expired, or category-mismatched candidates. Record the exact command and result in the worklog. If any test fails, stop in this phase, identify whether the fault is deterministic classification, semantic analysis, provenance propagation, lifecycle routing, or promotion logic, fix it, and rerun the complete Phase 2 command; do not weaken the evidence assertions, use model fallback, or bypass promotion checks.

### Phase 3: Make ComPeer Scheduling Durable and Observable

#### Problem

`backend/services/compeer_scheduler.py` clears `trigger_proactive` or `avatar_summon_pending` from hot memory before the delayed-mail task has been durably scheduled. A Redis timeout or later failure can therefore consume the trigger without leaving a recoverable delivery intent. The July 16 logs show a timeout in `proactive_scheduler_loop` and no evidence of the required sequence: trigger detected, task persisted, worker claimed, and mail delivered.

`backend/mailbox_store.py` already provides the core durable mechanisms: `schedule_delayed_mail` persists to `mailbox_delayed_tasks` when a database is available; `claim_delayed_task`, `mark_delayed_task_failed`, and `restore_delayed_queue_from_db` implement leasing, retry, and recovery. The worker currently restores only at startup and its traces do not consistently connect the triggering event to the final delivered mail. The target behaviour is that a scheduled ComPeer intent survives Redis queue failure, is retried or terminally failed with an explanation, and can be traced by one task ID end to end.

#### Assumptions

This phase assumes that the production deployment has the database schema for `mailbox_delayed_tasks`; otherwise Redis-only operation cannot meet the durability requirement and must be explicitly reported as degraded rather than claimed as reliable. It also assumes that duplicate care letters are unacceptable, so task IDs must stay deterministic and delivery must remain idempotent.

The LLM that generates a care letter may still fail. That failure is distinct from Redis failure: the trigger must remain retryable until a durable task exists, but the system must avoid an unbounded tight retry loop. Existing retry limits in `mark_delayed_task_failed` are the starting policy and should be made visible in logs and metrics.

#### Solution

Treat the delayed-mail database record as the source of truth and Redis as a dispatch accelerator. The scheduler should reserve a trigger under its existing lock, create the delayed-mail task successfully, and only then clear the trigger. If generation or persistence fails, it should retain or restore a retryable trigger state with a reason and next-attempt time. Errors must be isolated per user so one Redis or generation failure does not abort processing for other users.

The delayed-mail worker should periodically reconcile outstanding database tasks, not only restore them at process startup. It must log structured lifecycle events containing `task_id`, `user_id`, task kind, attempt count, and state for scheduled, claimed, delivered, retryable failure, and terminal failure. This creates the evidence the experiment script needs without relying on a single background-loop exception message.

#### Implementation

> Context: Add Google-style docstrings to the scheduler entry points, mailbox scheduling API, and delayed worker. Comments must explain why the database record is the delivery source of truth, why a trigger is cleared only after durable persistence, and why Redis failure is recoverable rather than a reason to drop the task. Add inline rationale at task-idempotency, lease, retry, and reconciliation transitions; do not narrate routine Redis or database calls. The code must make the failure-recovery contract understandable without reconstructing it from logs.

Refactor `proactive_scheduler_loop` in `backend/services/compeer_scheduler.py` so it does not delete `trigger_proactive` or `avatar_summon_pending` until `schedule_areqa_care_letter` or the equivalent avatar scheduling path returns a task ID. Store a short-lived in-progress marker only while the task is being generated, and clear or expire it safely so a crashed process cannot permanently suppress delivery. Keep the current idempotent `_stable_task_id` strategy. Wrap each user iteration in its own exception boundary and log an event with the user ID and trigger state before continuing to the next user.

Keep `MailboxStore.schedule_delayed_mail` as the single scheduling API in `backend/mailbox_store.py`. Ensure its database insert completes before a Redis enqueue is attempted, and surface whether Redis enqueue succeeded, failed but is recoverable, or was skipped as a duplicate. Extend `delayed_mail_worker` to call `restore_delayed_queue_from_db` on a bounded reconciliation interval and after recoverable Redis failures. Do not remove the database task until delivery is persisted; retain the existing claim lease and `mark_delayed_task_failed` path for retries.

Add lifecycle logging at the scheduler, mailbox store, and worker boundaries. The fields must use the same task ID so an operator can follow one letter from `scheduled` through `claimed` to `delivered`, or to `retryable_failed`/`terminal_failed`. Keep alert-broadcast failure non-fatal because delivery is already persisted, but log it as a separate notification failure.

#### Expected File Tree After Phase 3

```text
backend/
├── mailbox_store.py                                        [modified]
└── services/
    └── compeer_scheduler.py                                [modified]
tests/backend/
├── test_compeer_integration.py                             [modified]
├── test_compeer_scheduler.py                               [modified]
├── test_delayed_mail_tool.py                               [modified]
├── test_delayed_mail_worker.py                             [new]
├── test_mailbox_flow.py                                    [modified]
├── test_mailbox_leases.py                                  [modified]
└── test_mailbox_store.py                                   [modified]
```

#### Work List

1. [ ] Update `backend/services/compeer_scheduler.py` scheduling order.
   - [ ] Change `proactive_scheduler_loop` so `trigger_proactive` and `avatar_summon_pending` are cleared only after `schedule_areqa_care_letter` returns a durable task ID.
   - [ ] Preserve or restore a retryable trigger with a reason and next-attempt time when generation or persistence fails.
   - [ ] Retain `_stable_task_id` idempotency and isolate exceptions inside each user's scheduler iteration.
2. [ ] Make `backend/mailbox_store.py` the durable delivery authority.
   - [ ] Ensure `MailboxStore.schedule_delayed_mail` completes the `mailbox_delayed_tasks` database write before attempting Redis enqueue.
   - [ ] Surface Redis enqueue as succeeded, recoverably failed, or duplicate without deleting the database task.
   - [ ] Preserve the `claim_delayed_task` lease and `mark_delayed_task_failed` retry/terminal-failure flow until delivery is persisted.
3. [ ] Update `delayed_mail_worker()` in `backend/mailbox_store.py`.
   - [ ] Invoke `MailboxStore.restore_delayed_queue_from_db()` on a bounded reconciliation interval and after recoverable Redis failures.
   - [ ] Keep an already delivered task from being claimed or delivered again through the existing `claim_delayed_task` path.
4. [ ] Add lifecycle observability in `backend/services/compeer_scheduler.py` and `backend/mailbox_store.py`.
   - [ ] Emit correlated `scheduled`, `claimed`, `delivered`, `retryable_failed`, and `terminal_failed` events containing `task_id`, an approved user identifier, task kind, attempt count, and safe failure reason; do not log care-letter text or prompt data.
5. [ ] Extend `tests/backend/test_compeer_scheduler.py`, `test_compeer_integration.py`, `test_mailbox_store.py`, `test_mailbox_leases.py`, `test_mailbox_flow.py`, and `test_delayed_mail_tool.py`; add `tests/backend/test_delayed_mail_worker.py` for recovery and exactly-once delivery.

#### Test Plan

Extend `tests/backend/test_compeer_scheduler.py` to verify that a failed schedule leaves the proactive trigger retryable, a successful durable schedule clears it only afterward, and a failure for one user does not stop scheduling for another. Extend `tests/backend/test_mailbox_store.py` and `tests/backend/test_mailbox_leases.py` to cover database-success/Redis-failure recovery, duplicate deterministic task IDs, retryable-to-claimed recovery, and terminal failure after the configured retry limit.

Add a worker-level integration test, preferably in a new `tests/backend/test_delayed_mail_worker.py`, using the existing fake Redis and a mocked mailbox store. It must simulate a Redis timeout after a database record exists, run reconciliation, claim the task, persist exactly one mail, and assert the task transitions to delivered. A second test must assert that a WebSocket alert failure does not undo the persisted mailbox delivery. Run:

```bash
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_compeer_scheduler.py \
  tests/backend/test_compeer_integration.py \
  tests/backend/test_mailbox_store.py \
  tests/backend/test_mailbox_leases.py \
  tests/backend/test_mailbox_flow.py \
  tests/backend/test_delayed_mail_tool.py \
  tests/backend/test_delayed_mail_worker.py
```

#### Expected Output / Result

Each eligible ComPeer trigger produces one durable delayed-mail task before the trigger is cleared. Redis unavailability after database persistence does not lose the task: reconciliation restores it, one worker claims it, and exactly one mailbox message is persisted. The correlated lifecycle record for the same task ID shows `scheduled`, `claimed`, and `delivered`, or a bounded `retryable_failed`/`terminal_failed` path with an actionable reason. A failure for one user does not suppress scheduling for other users.

#### Testing Script

##### Act 01: Persist the Delivery Intent Before Clearing the Trigger

Prepare an eligible ComPeer trigger with the mailbox database enabled. Configure Redis to time out during queue insertion, then run one scheduler iteration.

Pass condition: a `mailbox_delayed_tasks` record and `scheduled` event exist with one task ID before the proactive trigger is cleared.

##### Act 02: Recover the Persisted Task and Deliver One Letter

Restore Redis, run delayed-task reconciliation, advance the test clock to the due time, and run the worker.

Pass condition: the same task ID is restored, claimed once, and produces exactly one mailbox message with a `delivered` event.

##### Act 03: Do Not Duplicate or Block Other Users

Run the scheduler and worker again for the same task, while forcing a scheduling failure for user A and providing a valid trigger for user B.

Pass condition: no duplicate task or letter is created for the original user; user A remains retryable with a reason and next attempt; user B still receives a durable task.

#### Gate to Enter the Next Phase

Every Phase 3 unit and integration test must pass, including the Redis-timeout recovery scenario and the assertion that the trigger is not cleared before durable scheduling. Preserve a log sample or test-captured records proving one task ID has scheduled, claimed, and delivered events. If recovery or idempotency fails, remain in Phase 3, correct the persistence/lease/reconciliation path, and rerun the full Phase 3 command. Do not accept an empty mailbox, a swallowed exception, or an uncorrelated log line as a successful delivery.

### Phase 4: Reduce Orchestration Service to a Streaming Controller

#### Problem

`backend/services/orchestration_service.py` currently coordinates request validation, routing, memory side effects, reflection scheduling, tool execution, prompt construction, streaming, and post-generation suggestions. This makes the service both controller and domain worker. The July 16 investigation required tracing several unrelated side effects through the same large execution path, which makes memory and ComPeer regressions harder to isolate and test.

The target is not a cosmetic line-count reduction. The target is a controller that owns execution order and the existing SSE contract, while domain services own memory ingestion, post-turn jobs, prompt/context assembly, tools, and suggestion generation. Existing public endpoints and emitted SSE events must remain compatible during the migration. The first-act response also made an unsupported claim that the learner already understood inertia. Learner-state assessment and response wording must therefore be treated as an explicit domain responsibility, not as an incidental side effect of prompt assembly.

#### Assumptions

The existing `OrchestrationService.execute` method and its SSE adapter are the compatibility boundary. No API or frontend contract change is included in this report unless contract tests identify an existing ambiguity. The new services may be introduced incrementally, but Phase 1, Phase 2, and Phase 3 behaviour must already be protected by tests before moving calls.

The refactor is intentionally not a microservice split. New modules remain in the backend process and receive explicit dependencies rather than importing global state where practical. If a dependency cannot yet be injected without broad unrelated changes, preserve its current access pattern and record it as follow-up work rather than expanding the refactor.

#### Solution

Use `OrchestrationService` as a thin controller with explicit stages: prepare request context, invoke the model/tool stream, and dispatch post-turn work. Read prompt-safe hot context through the Phase 1 boundary, move the trusted cold-memory ingestion call introduced in Phase 2 into its own service boundary, keep ComPeer scheduling behind its scheduler/mailbox APIs from Phase 3, and extract other cohesive work only where an existing method boundary already exists. The conversation-context boundary must supply verified learner-state signals, if any, separately from raw memory candidates; prompts must instruct the model to use conditional language when no evidence confirms understanding. This keeps execution ordering visible while making memory and mailbox behaviour independently testable.

Maintain the current SSE payload sequence through the existing adapter. The refactor should be performed as behaviour-preserving moves with tests at each move, not as a rewrite of `execute`.

#### Implementation

> Context: Add Google-style module and public-service docstrings for the new context and post-turn services, and update `OrchestrationService` documentation to state its controller-only role. Comments must explain why verified learner state is distinct from memory candidates, why unverified propositions cannot support mastery claims, and why the existing SSE sequence is a compatibility boundary. Add inline rationale only around delegation order, cancellation, non-critical post-turn failure handling, and phase-level structured-log emission; avoid comments that merely paraphrase stream or dependency-injection code. The resulting documentation must make it clear which service owns each side effect.

Update `backend/services/orchestration_service.py` so its user-message path delegates to `backend/services/memory_ingestion_service.py` rather than directly owning memory gate details. Extract prompt/context preparation into a newly added `backend/services/conversation_context_service.py`, with a narrow interface that returns the finalized model messages, verified learner-state signals, and any retrieval context needed by the existing stream node. It must exclude unverified GUM propositions from profile-memory and learner-mastery prompt fields, and express absent mastery evidence as unknown rather than confirmed. Extract post-turn job dispatch, including reflection scheduling and suggestions, into a newly added `backend/services/post_turn_service.py`; it must not write user profile memory itself.

Keep `_node_llm_stream` and the SSE adapter as stable interfaces until their current stream tests pass through the new collaborators. Pass dependencies through the `OrchestrationService` constructor where the current constructor already accepts services; preserve temporary adapters only where needed to avoid changing endpoints. Remove duplicate direct imports of memory, mailbox, and GUM behaviour from the controller after the delegated paths are verified. Document the resulting ownership in module docstrings and keep the controller responsible only for ordering, cancellation, and SSE completion.

Emit safe request-stage events at controller delegation boundaries: context prepared, stream started/completed/cancelled, memory ingestion dispatched, and post-turn dispatch succeeded or failed. Reuse request and conversation correlation IDs so terminal output links controller stages to the memory and ComPeer events emitted by delegated services. Do not log streamed tokens, prompts, or user content.

#### Expected File Tree After Phase 4

This tree is cumulative: Phases 1 through 3 remain in place, while Phase 4 adds the controller boundaries below.

```text
backend/
├── gum_integration.py                                      [modified in Phases 1, 2]
├── mailbox_store.py                                        [modified in Phase 3]
├── memory_gate.py                                          [modified in Phase 2]
├── memory_store.py                                         [modified in Phases 1, 2]
└── services/
    ├── compeer_scheduler.py                                [modified in Phases 1, 3]
    ├── conversation_context_service.py                     [new]
    ├── hot_memory_service.py                               [new in Phase 1]
    ├── memory_ingestion_service.py                         [new in Phase 2]
    ├── orchestration_service.py                            [modified]
    └── post_turn_service.py                                [new]
tests/backend/
├── test_compeer_scheduler.py                               [modified in Phase 3]
├── test_memory_source_boundaries.py                        [modified in Phase 2]
├── test_orchestration_service.py                           [modified]
└── test_stream_endpoint.py                                 [modified]
```

#### Work List

1. [ ] Create `backend/services/conversation_context_service.py`.
   - [ ] Add the proposed `build_conversation_context()` interface that returns finalized model messages, retrieval context, and verified learner-state signals.
   - [ ] Read prompt-safe, non-expired working context through the Phase 1 hot-memory service rather than assembling raw Redis hot-memory values in the controller.
   - [ ] Exclude unverified GUM propositions from profile-memory and learner-mastery prompt fields; represent absent mastery evidence as unknown.
2. [ ] Create `backend/services/post_turn_service.py`.
   - [ ] Add the proposed `dispatch_post_turn_work()` method and move reflection scheduling and suggestion dispatch out of the controller.
   - [ ] Ensure the new service cannot call profile-memory persistence directly; it must use the Phase 2 memory-ingestion boundary where applicable.
3. [ ] Reduce `backend/services/orchestration_service.py` to controller responsibilities.
   - [ ] Update `OrchestrationService.execute` to delegate user evidence to `memory_ingestion_service.py`, context preparation to `conversation_context_service.py`, and post-turn work to `post_turn_service.py`.
   - [ ] Keep `_node_llm_stream` and the existing SSE adapter stable while collaborators are introduced through the current constructor/dependency pattern.
   - [ ] Remove duplicate direct memory, mailbox, and GUM imports only after the delegated paths are covered.
   - [ ] Emit safe `orchestration.*` request-stage events with request/conversation correlation IDs, without prompts, tokens, or raw user messages.
4. [ ] Extend `tests/backend/test_orchestration_service.py` and `test_stream_endpoint.py`.
   - [ ] Assert the existing SSE event order, payload shape, cancellation behavior, and terminal event.
   - [ ] Add a first-time Newton request case proving no learner-understanding claim is supplied without verified evidence.
   - [ ] Re-run the Phase 2 preference-query and Phase 3 ComPeer paths through the orchestration entry point.

#### Test Plan

Extend `tests/backend/test_orchestration_service.py` and `tests/backend/test_stream_endpoint.py` to assert that the SSE event order and terminal event remain unchanged while hot-context retrieval, memory ingestion, and post-turn work are mocked independently. Add a response-context test for a first-time Newton question that asserts no verified learner-understanding signal is provided, and that the generated instruction/context does not claim the user already understands inertia. Assert that `orchestration.*` stage events retain request/conversation correlation without prompt or token data. Re-run the Phase 1 hot-snapshot regression, the Phase 2 preference-question regression, and the Phase 3 ComPeer trigger through the orchestration entry point. Include import/compile validation for the moved modules and the full backend test suite:

```bash
./backend/.venv/bin/python -m compileall -q backend
./backend/.venv/bin/python -m pytest -q \
  tests/backend/test_orchestration_service.py \
  tests/backend/test_stream_endpoint.py \
  tests/backend/test_memory_source_boundaries.py \
  tests/backend/test_compeer_scheduler.py
npm run test:backend
```

#### Expected Output / Result

`OrchestrationService` acts only as the streaming controller: it orders request preparation, model/tool streaming, and post-turn dispatch without directly owning memory policy or background-job implementation. Context construction supplies only verified learner-state signals, so a first-time Newton question is answered without claiming the learner already understands inertia. Existing endpoints and the SSE event sequence, payload semantics, cancellation behaviour, and terminal event remain unchanged while memory ingestion and ComPeer scheduling are independently testable services. Terminal logs show the safe, correlated controller stages without exposing prompts, tokens, or user text.

#### Testing Script

##### Act 01: Preserve the Existing Streaming Contract

Capture the SSE sequence for a normal learning request before the refactor, then replay the same request after the refactor.

Pass condition: event order, names, payload shape, cancellation handling, and terminal semantics are unchanged.

##### Act 02: Do Not Claim Understanding Without Evidence

Use a new user with no verified learner-state signal and ask: `請教我牛頓第一運動定律。`

Pass condition: the context identifies learner understanding as unknown, and the reply does not state or imply that the user already understands inertia.

##### Act 03: The Controller Delegates Without Breaking Protected Flows

Run `OrchestrationService.execute` with independently mocked hot-context, memory-ingestion, and post-turn services. Then repeat the Phase 2 preference-question path and the Phase 3 ComPeer trigger through the orchestration entry point.

Pass condition: the controller preserves stream completion when a non-critical post-turn job fails, the question does not become memory, and the ComPeer task remains durable and traceable.

#### Gate to Enter the Next Phase

This is the final implementation phase. All listed checks must pass, the SSE contract tests must show no changed event ordering or terminal semantics, and the complete backend suite must pass. Record the module ownership change and test results in the worklog. Any failure requires returning to the responsible extracted service or controller adapter and rerunning the entire Phase 4 gate; do not change stream assertions merely to match a regression.

### Cross-Phase Regression and Final Acceptance

The final acceptance run must execute `npm run test:backend`, together with the focused Phase 1, Phase 2, and Phase 3 commands if the full suite does not include a newly added worker test. Run the July 16 experiment script again in an environment with the mailbox database and Redis enabled. The acceptance record must show the following observable outcomes: no hot-memory model inference, behavior signal, learner-state value, or scheduler flag is exported to cold or profile memory; no visible or stored profile memory after the Newton/SpaceX one-off questions, including no promoted GUM proposition about learner ability, anxiety, or SpaceX context; no profile memory created from `"我偏好什麼學習方法？"`; one passive preference stored as a 90-day candidate and promoted only after two distinct conversations containing matching explicit user evidence; semantically equivalent low-risk preference declarations may join the same candidate only after a validated Gemini result, while `uncertain`, timeout, invalid-schema, cross-user, expired, or category-mismatched results do not add corroboration; a temporary goal removed on completion or after 30 days; no automatic cold/profile record for sensitive information; no unsupported assertion that the learner has already understood Newton's first law or inertia; and one ComPeer task with correlated scheduled, claimed, and delivered records followed by a mailbox message at approximately 120 seconds, with an explicit failure record if delivery has not completed by 150 seconds. The terminal evidence must show a safe, correlated event trail for hot-memory policy decisions, memory ingestion/semantic-analysis/promotion outcomes, controller stages, and the ComPeer task lifecycle without raw user content or prompt data.

The principal risks are missing message provenance in the current transport schema, legacy untyped hot-memory entries, OpenRouter/provider data-policy drift, semantic false matches, a Redis-only deployment, and migration of legacy candidates that lack complete evidence. These are mitigated by failing closed for cold export and automatic promotion, treating untyped hot entries as non-exportable, pinning Gemini semantic analysis behind strict schema, same-user/category validation, shadow rollout, unavailable-result fallback, and verified provider privacy controls, treating durable mailbox storage as a deployment prerequisite, and requiring explicit confirmation for legacy candidates. Embeddings are not required for correctness; they may later reduce candidate-retrieval cost, but must remain behind the same deterministic safety boundary and cannot authorize a profile write.
