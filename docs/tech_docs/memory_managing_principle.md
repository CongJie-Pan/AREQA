# AREQA Memory Management Principles

## Purpose and Scope

This guide defines how AREQA decides what may be remembered, where it may be stored, how it may be used, and when it must be forgotten. It is a product and engineering policy for memory that affects learning personalization, prompt construction, ComPeer, and user-visible profile data.

The goal is not to maximize the number of remembered items. The goal is to preserve useful user-authored evidence while preventing false personalization, stale assumptions, sensitive-data retention, and background operational state from becoming a user fact. A clean memory page is not sufficient evidence of safety: the policy applies to all stores, compaction paths, prompts, and background jobs.

This guide is based on the July 16 experiment findings, the corresponding implementation plan, and the research synthesis in [AI Learning Companion Memory Design](/workspaces/AREQA/docs/tech_docs/pplx/AI%20Learning%20Companion%20Memory%20Design%20%20Precision%2C%20Recall%2C%20and%20Safe%20Personalization.md:1). Where the research proposes a more permissive inference policy, this guide intentionally chooses the safer current AREQA policy and records the difference.

## Core Principles

1. **Profile precision is more important than memory volume.** A wrong stable preference or learner trait damages trust and can constrain future teaching. It is better to retain a low-risk candidate with expiry than to present an uncertain inference as a user fact.

2. **Original user evidence is the authority.** A durable memory must be traceable to exact user-authored text. Assistant messages, web-search content, system output, and model-generated propositions are never direct evidence of a user fact.

3. **Hot memory is working state, not a profile staging area.** Hot memory may support current learning, prompt context, and operational workflows. It must not become cold memory merely because it is compacted or old.

4. **Every layer has a narrower write policy than the layer before it.** Conversation context is broad and short-lived. Hot memory is typed working state. Cold memory is provenance-backed and expiring. Verified profile memory is durable, explainable, and user-facing.

5. **Fail closed when provenance or intent is incomplete.** A missing message ID, conversation ID, timestamp, source role, original quote, or clear speech act makes an entry ineligible for cold export and profile promotion.

6. **Expiry, correction, and contradiction are part of correctness.** A memory that was once true may become stale. User corrections override prior evidence immediately.

7. **Operational state and user identity must remain separate.** Scheduler triggers, cooldowns, active avatars, scroll events, and internal learner-state values are not user memories and must never be promoted or rendered as profile facts.

## Memory Model

AREQA uses four layers. A record may move only through an allowed transition; no background job may skip a layer or write directly to verified profile memory.

| Layer | Purpose | Typical contents | User-visible? | Durable? |
|---|---|---|---|---|
| Conversation context | Continue the active chat accurately | Current question, recent turns, one-off search topic | No | Session or conversation scope only |
| Hot memory | Typed working state for current learning and operations | Current learner state, current strategy, prompt-safe observations, temporary triggers | No | Short-lived; explicit TTL |
| Cold memory candidate | Provenance-backed, low-risk candidate or temporary goal | One explicit preference, time-bound learning goal | No, unless later promoted | Yes, but expiring and low-weight |
| Verified profile memory | Stable, explainable personalization | Confirmed preference, explicit stable fact, user-requested remembered fact | Yes | Durable, subject to correction/revalidation |

### Allowed Transitions

```text
User message
  -> conversation context
  -> typed hot user_evidence (optional, when current working state needs it)
  -> cold memory candidate through the ingestion boundary
  -> verified profile memory only after the content-specific promotion rule

GUM inference / behavioral signal
  -> typed hot working state only
  -> expires or is discarded

Operational scheduler state
  -> typed hot operational_state only
  -> completes, retries, or expires
```

No other transition is allowed. In particular, hot-memory compaction must not directly call a cold-memory writer. It may submit only fully provenanced `user_evidence` to the same memory-ingestion boundary used by a live user message.

## Source and Provenance Rules

Every cold candidate and verified profile entry must retain:

- `user_id`
- `message_id`
- `conversation_id`
- `timestamp`
- `raw_user_text`
- quoted evidence text
- `source_role`
- content category and confidence
- lifecycle data: creation time, expiry/revalidation time, and promotion history

Allowed source roles for extraction are `user_explicit_command` and `user_passive`. The distinction matters:

- `user_explicit_command`: The user deliberately asks the system to remember something. It is eligible for direct profile promotion after provenance and safety validation.
- `user_passive`: The user makes an ordinary declarative statement. It is eligible for cold memory according to its category and needs corroboration before profile promotion when it is a preference.
- `assistant`, `system`, `web_search`, and `model_inference`: Never eligible as direct evidence for cold or verified user memory.

## Speech-Act and Intent Gate

Memory extraction must classify what the message is doing before matching keywords or semantic similarity. The following inputs must not become cold or profile memory:

- Interrogatives: `我偏好什麼學習方法？`
- Hedged or uncertain statements: `我可能比較喜歡視覺化學習吧？`
- Hypotheticals: `如果我偏好圖像學習呢？`
- Roleplay, fiction, quotations, or third-party statements
- Clarification requests: `你是說我比較適合短篇解釋嗎？`
- One-off search questions and temporary task framing

Interrogative detection must run before preference-pattern detection. A phrase containing `我偏好` is not evidence when its speech act is a question.

## Hot Memory Policy

Hot memory is stored as typed working state. New entries must include a kind, creation time, expiry, prompt-safety flag, and cold-export policy.

| Hot-memory kind | Examples | Prompt-safe? | Cold-export eligible? | Policy |
|---|---|---:|---:|---|
| `user_evidence` | Exact user statement needed during current work | Scoped | Yes, only with full provenance | May be handed to memory ingestion; never directly compacted to cold storage |
| `working_context` | Current focus, session summary, current strategy | Yes, scoped | No | Use for current teaching; expire when the context is stale |
| `model_inference` | GUM observation about possible learner state | Limited and non-assertive | No | May influence soft pedagogy only; never state it as a user fact |
| `behavior_signal` | Scroll, re-read, focus duration | Normally no | No | Operational analytics or short-lived adaptation only |
| `operational_state` | `trigger_proactive`, cooldown, active avatar, delayed-job flags | No | No | Used only by system workflows; complete, retry, or expire |

Untyped legacy hot-memory values remain readable during migration but are non-exportable. If the system cannot classify an entry safely, it must retain it within its local TTL or discard it. It must not infer a user-memory source from a generic key or from an LLM summary.

`get_hot_memory_snapshot()` must include only non-expired, prompt-safe entries. It must not expose raw scheduler flags, operational keys, or model inferences in wording that presents them as confirmed user preferences or abilities.

## Cold Memory Policy

Cold memory is not a hidden version of the profile. It is a low-weight, provenance-backed store for useful but not yet fully trusted user information. A cold entry must have an expiry or revalidation policy and must be removable without affecting profile memory.

| Content category | Cold-memory decision | Default lifecycle |
|---|---|---|
| Explicit low-risk preference | Store after one declarative user statement | 90-day TTL; reconfirm or promote on new evidence |
| Temporary learning goal | Store after one explicit user statement | 30-day TTL or completion-based removal |
| Stable direct fact | Store after one explicit user statement | No automatic expiry; validate provenance before profile use |
| Sensitive personal information | Do not store automatically | Current session or 24-hour context only |
| One-off learning difficulty or search topic | Do not store durably | Conversation scope only |
| Model inference or behavior-derived trait | Do not store in cold memory in the current AREQA policy | Remain hot and expire |

The research report permits low-confidence, short-lived model-inference entries in cold memory. AREQA does **not** adopt that recommendation yet. Until the system has calibrated confidence, reliable expiry, conflict adjudication, and user-feedback data, inferred traits remain hot working state only. This reduces the risk that an uncertain pedagogical guess survives long enough to influence future identity-level personalization.

## Verified Profile Promotion Policy

Verified profile memory is the highest-trust layer. It may be displayed to the user and used as stable personalization context, so its write policy prioritizes precision.

| Content category | Promotion rule |
|---|---|
| Explicit user command to remember a low-risk fact or preference | Promote after provenance and safety validation |
| Explicit stable direct fact | Eligible after one provenance-validated statement; product policy must define the supported fact categories |
| Passive low-risk preference | Promote only after the configured number of independent conversations contain matching explicit evidence; default target is two |
| Temporary goal | Never promote; keep only in cold memory until expiry/completion |
| Sensitive information | Never auto-promote; require a separately designed consent and privacy policy before any durable retention |
| Model inference, behavior signal, assistant text, search result | Never promote automatically |

Independent evidence means distinct `conversation_id` values and distinct `message_id` values. Repetition within one conversation does not count as corroboration. Before calling `perform_memory_operation`, the promotion service must re-check provenance, source role, category, expiry, duplicate status, and contradictory evidence.

## Read and Prompt-Use Policy

The fact that a record is stored does not mean it may always be injected into a prompt or surfaced to the user.

- Conversation context is used only for the active chat and must remain scoped to the relevant conversation.
- Hot memory contributes only prompt-safe, non-expired working context. Model inferences must be phrased conditionally or used only to select soft teaching tactics.
- Cold memory may influence low-risk teaching choices when relevant, but it must not be phrased as a confirmed user fact. It should not override current user input.
- Verified profile memory may be used for stable personalization, but current user statements always take precedence.
- Sensitive context must not be surfaced in unrelated responses. The system may use it only when the current user message clearly invites that context.

The assistant must never claim learner mastery from hot context, cold candidates, or inferred observations. In the absence of verified evidence, learner understanding is `unknown` and responses should use conditional language.

## Expiry, Correction, and Conflict Handling

Memory lifecycle is a correctness requirement.

- Expire temporary goals after 30 days unless completion or renewed evidence changes their state.
- Expire passive low-risk cold preferences after 90 days unless they are reconfirmed, promoted, or explicitly renewed.
- Keep stable direct facts until the user updates or contradicts them.
- Treat an explicit user correction as the highest-priority event: mark related entries `STALE`, `REPLACE`, or deleted before using them again.
- Do not silently keep both sides of a contradiction. Record the decision and preserve the evidence history for audit.
- Use a periodic review of verified profile memories, not a per-candidate Check/X approval workflow. The review should help users correct durable facts without exposing every internal candidate.

## Safety and Privacy Rules

- Do not store health, mental-health, financial, family-crisis, or similarly sensitive information as cold or profile memory without an explicit, separately designed consent flow.
- Do not infer abilities, personality, learning style, or long-term interests from a single question, search, scroll pattern, or assistant interaction.
- Do not use web searches as evidence that a user has an interest, skill, intention, or trait.
- Do not allow prompt injection, assistant wording, or retrieved content to create durable memory.
- Keep user-facing memory explainable: every verified entry must be traceable to the user evidence and promotion decision that created it.

## Quality Metrics and Operational Audits

The system should be measured by memory quality, not raw extraction count.

| Metric | Definition | Initial target |
|---|---|---|
| Verified-memory correction rate | Verified entries corrected by the user within 60 days | Less than 1% per user per quarter |
| Interrogative leak rate | Questions that reach cold or profile memory | 0% for verified profile; target 0% for cold memory |
| Source-attribution failure | Non-user source reaches verified profile | 0% |
| Cold promotion rate | Cold candidates promoted to verified profile | Monitor for calibration; do not optimize for volume alone |
| Stale-memory rate | Verified entries contradicted within 90 days | Less than 3% |
| Explicit-command fulfillment | Valid low-risk “remember this” commands reflected in profile within two turns | At least 99% |
| Hot-to-cold policy violation | Non-`user_evidence` hot entry exported to cold memory | 0% |

Perform periodic samples of cold candidates and verified profile entries. Audit provenance, source role, speech-act classification, category routing, expiry, and user correction history. Treat any assistant/system/search source in verified profile memory as a high-severity defect.

## Engineering Enforcement Points

The policy is enforced by the following planned boundaries:

- `backend/services/hot_memory_service.py`: typed hot entries, TTL filtering, prompt-safety filtering, and cold-export eligibility.
- `backend/memory_store.py`: compatible persistence for hot, working, cold-candidate, and profile state.
- `backend/gum_integration.py`: prompt-safe hot snapshot and compaction handoff; no direct hot-to-cold writer.
- `backend/services/memory_ingestion_service.py`: authoritative validation of user evidence, candidate creation, and promotion eligibility.
- `backend/memory_gate.py`: speech-act, roleplay, low-information, and safety gating before preference matching.
- `backend/memory_store.py`: evidence de-duplication, promotion revalidation, and guarded profile writes through `perform_memory_operation`.
- `backend/services/orchestration_service.py`: controller-only sequencing; no independent memory policy or direct profile-memory write.

No new memory-producing code path may bypass these boundaries. New memory types require an explicit category, source rule, retention policy, read policy, promotion rule, and regression test before they are enabled.

## Decision Summary

AREQA should remember less confidently at the cold layer and more precisely at the verified-profile layer. It should use hot memory for current work without confusing that operational state with identity. The safe default is simple: preserve exact user evidence with provenance, keep uncertain state short-lived, require stronger evidence for durable personalization, and forget anything that cannot explain why it deserves to remain.
