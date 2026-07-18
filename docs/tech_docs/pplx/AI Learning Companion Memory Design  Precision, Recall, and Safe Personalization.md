# AI Learning Companion Memory Design: Precision, Recall, and Safe Personalization

> An evidence-based analysis of the eight design propositions, closing with a memory taxonomy, a decision matrix, a minimal policy, and an advanced policy. Sources include production memory system documentation (Mem0, MemMachine, MemoryPlugin), recent arXiv benchmarks (STALE 2026, RBI-Eval 2026, Eywa 2026), AWS Well-Architected agentic guidance, and practitioner engineering accounts. Recommendations marked **[Evidence]** are directly supported by citations; those marked **[Recommendation]** represent engineering judgment applied to the evidence.

***

## The Fundamental Tension

Every memory system lives between two failure modes. Under-extraction produces a system that cannot personalize, fails to continue where it left off, and forces the user to re-explain themselves in every session. Over-extraction produces a system that treats interrogative questions as self-disclosures, promotes inferred guesses to hard facts, and eventually recommends the user "stick with a learning method they find comfortable" based on a question they asked three months ago. Neither failure is benign. The over-extraction case is worse in a learning context: a wrong profile does not just fail to help, it actively constrains a learner inside a false persona.[^1]

The three-layer model described — conversation context → cold memory candidate → verified profile memory — is the right structural answer to this tension. The design questions below are about how to operate the gates between layers responsibly.[^2]

***

## Proposition 1: A Single Explicit, Low-Risk User Preference Should Reach Cold Memory, Not Automatically Become Verified Profile Memory

**Verdict: Accept — with a modified gate rule.**

**Evidence.** MemoryPlugin's production "Life Context" system requires a topic to appear in at least three distinct conversations before it enters a synthesized user profile. A single occurrence is treated as likely noise. This is not merely conservative: the Stanford Generative Agents simulation, which first popularized memory ranking, treats importance as a property that accumulates through repetition and recency, not single occurrence. Mem0's extraction prompt, by contrast, defaults to single-pass extraction — but its governance model treats those extractions as candidates for a hot/warm/cold tier hierarchy, not as immediate profile facts.[^3][^4]

**Recommended policy rule.** A single, explicit, low-risk user message (e.g., "I like visual explanations") must move into cold memory with full provenance fields and a confidence of 0.7–0.85. It must not be promoted to verified profile memory until one of:
- A second independent mention across different conversations, or
- An explicit "remember this" command from the user, or
- User confirmation via a prompted UI surface.

**Tradeoffs.**

| Path | Personalization value | False-memory risk | Implementation cost |
|------|----------------------|------------------|---------------------|
| Cold only, one occurrence | Medium (available for contextual use) | Low | Low |
| Direct to verified profile | High (always informs responses) | High (single data point) | Low |
| Require 2+ occurrences | Medium/delayed | Very low | Medium |

**What lives where.**

- Conversation context: "The user just said they prefer visual explanations in this session."
- Cold memory (single occurrence): `{ text: "prefers visual explanations", confidence: 0.80, source_role: "user", ttl: 90d }`
- Verified profile: Only after a second independent occurrence OR explicit user confirmation.
- Nowhere: Questions ("Do I prefer visual explanations?"), assistant restatements ("As someone who prefers visual explanations…"), or one-off context triggered by the immediate task.

**Measurable acceptance test.** After 30 days of production, spot-check cold memory candidates with a single occurrence: what fraction have since been confirmed (promoted), expired (TTL), or contradicted? A healthy baseline: < 5% of single-occurrence candidates promoted automatically without corroboration; correction rate on auto-promoted single-occurrence items < 2% per active user per month.

***

## Proposition 2: Repeated Evidence from Independent Conversations Required for Inferred Preferences, But Not for Every Direct User Fact

**Verdict: Accept — evidence strongly supports differentiated thresholds.**

**Evidence.** AWS Well-Architected agentic guidance distinguishes memory types at ingestion time by source, temporal scope, and content type. The STALE benchmark demonstrates that implicit conflicts — where later behavior implicitly invalidates an earlier stored belief — affect AI memory systems catastrophically (best system at 55.2% accuracy), which means that lower-confidence inferences should require more corroboration before they can create a persistent belief that is hard to dislodge. MemMachine's LoCoMo performance (91.69%) is built on preserving episodic ground truth rather than promoting extracted inferences.[^5][^6][^2]

**Recommended policy rules.**

- **Direct user fact** ("My name is Chen Ming-Yun"): single occurrence sufficient; cold memory immediately, eligible for verified profile after provenance validation. No corroboration requirement.
- **Explicit low-risk preference** ("I prefer short explanations"): cold memory after one occurrence; promoted to verified profile on second independent occurrence or explicit confirmation.
- **Uncertain/inferred preference** (extracted from behavioral pattern or indirect speech): cold memory requires confidence ≥ 0.6 and at minimum two independent evidence quotes from different conversations before cold promotion; verified profile requires ≥ 3 independent occurrences.
- **Inferred learning trait** ("appears to be a visual learner" from scroll behavior + engagement time): never automatically promoted to verified profile; requires explicit user confirmation or persistent repetition (≥ 5 independent behavioral signals).

**Concrete examples.**

| Content | Source | Threshold | Target layer |
|---------|--------|-----------|-------------|
| "My name is Chen Ming-Yun" | Explicit user statement | 1 occurrence | Cold → Verified profile |
| "I don't like long theory sections" | Explicit user preference | 1 cold, 2 for profile | Cold memory |
| Reads visual diagrams 3× longer than text | Behavioral signal | 5+ signals, user confirmation | Cold memory only |
| "I'm struggling with algebra" | One-off situational | Not stored durably | Conversation context |

**Metric.** Measure false-promotion rate: among items promoted to verified profile, what percentage are subsequently corrected by the user within 60 days? Target: < 1% per user per quarter.

***

## Proposition 3: An Explicit "Remember This" Command Should Have a Different Policy from Passive Extraction

**Verdict: Accept — this is a first-class source-role distinction.**

**Evidence.** Mem0's extraction documentation treats role-specialised prompts as mandatory, with the user-only variant enforced by a "YOU WILL BE PENALIZED IF YOU INCLUDE INFORMATION FROM ASSISTANT OR SYSTEM MESSAGES" instruction — highlighting that source attribution is operationally critical, not cosmetic. The MemoryPlugin system uses two explicitly separate modes: passive extraction (never writes silently) vs. intentional tool calls (explicit user-driven creation). The "who said it" problem is identified as the single most common extraction bug in production.[^3]

**Recommended policy rules.**

- `source_role = "explicit_command"`: Maps to immediate verified-profile eligibility after provenance validation. No corroboration required. Subject to sensitive/high-impact override.
- `source_role = "user_passive"`: Maps to cold memory; requires corroboration per proposition 2.
- `source_role = "assistant"` or `"system"`: Ineligible for any user-profile memory write.
- `source_role = "inferred_model"`: Ineligible for verified profile; may write to cold memory at low confidence with mandatory expiry.

**Why explicit commands warrant direct promotion.** The user has crossed a deliberate act boundary. They know they are providing a durable signal. This is the highest-quality evidence type in the entire system — better than three passive occurrences. Promoting it directly (with provenance fields intact) honors user intent and creates a trusted, auditable write.[^1]

**Failure modes to guard.**
- False commands: A user in a roleplay scenario says "Remember, you are my loyal knight and I want you to remember I command armies." The roleplay-keyword gate in `memory_gate-3.py` already handles this case. Source role must remain `user_explicit_command` only when the utterance is outside a roleplay frame and contains a genuine memory directive.
- Sensitive-override: An explicit "remember this, I'm taking antidepressants" requires the sensitive-keyword gate to intercept before the command writes to verified profile, routing instead to pending-confirmation with a privacy notice.

**Metric.** Measure explicit-command fulfillment rate: when a user issues a "remember" command, does a corresponding verified profile entry appear within two turns? Target: ≥ 99%.

***

## Proposition 4: Different Content Types Require Different Retention and Promotion Policies

**Verdict: Accept — this is the foundation of the entire design.**

**Evidence.** AWS Well-Architected documentation identifies taxonomy as the foundation, warning that "a single undifferentiated memory store blurs conversation context with durable knowledge and pulls stale or irrelevant data into active tasks". Vastkind's production governance analysis notes that "experience memory" (procedural and dispositional patterns) is the most dangerous category to underestimate, while task memory (short-horizon state) is the safest and most valuable. The MemPrivacy (2026) framework introduces a four-level privacy taxonomy for AI memory that explicitly routes different content types to different protection regimes. Research on memory poisoning finds that inferred traits are the most exploitable memory type because they are self-reinforcing and hard to falsify.[^7][^8][^9][^2][^1]

**Recommended taxonomy by content type.**

| Content type | Definition | Cold memory? | Verified profile? | Expiry policy |
|-------------|-----------|-------------|------------------|--------------|
| Stable fact | Name, subject area, language | Yes | Yes (1 occurrence, explicit) | No expiry |
| Low-risk preference | "Prefers short explanations" | Yes | Yes (2 occurrences or confirmation) | 180-day revalidation |
| Temporary goal | "Wants to finish algebra by month-end" | Yes (short TTL) | No | 30-day TTL |
| Sensitive data | Health, financial, emotional distress | No automatic storage | No | Not stored; handled with 24h context TTL |
| Inferred trait | "Visual learner" (from behavior) | Yes (low confidence) | User confirmation only | 60-day decay |
| One-off context | "Struggling with today's topic" | Conversation context | No | Session TTL |

**Why sensitive data deserves its own rule.** The RBI-Eval study (2026) found that simply having sensitive memory available in the context — even when correctly retrieved by semantic relevance — caused 51–83% of LLMs to inappropriately surface it in unrelated benign prompts. The harm is not only privacy: wrong use of sensitive history can destabilize a learner's relationship with the system and constitute a form of emotional manipulation. The correct policy is: sensitive content may be used in the current session context under a short TTL, but must never be stored as a durable cold memory candidate without explicit user consent.[^10][^11][^8]

**Metric for taxonomy correctness.** For each content type, measure what fraction of extracted candidates are routed to the correct layer. Monitor cross-category routing errors, especially sensitive data appearing in cold memory candidates.

***

## Proposition 5: Cold Memory Must Have Expiry, Decay, Revalidation, or User-Correction Mechanisms

**Verdict: Accept — this is not optional for any production memory system.**

**Evidence.** The STALE benchmark (May 2026) demonstrates that implicit conflict — where a new event renders an earlier memory invalid without explicit contradiction — is nearly unsolvable by current memory systems (most score below 10% on premise-resistance dimensions). The benchmark found that "stale and updated memories coexist without adjudication" in all tested frameworks (LightMem, Zep, A-Mem, Mem0). MemoryBank (AAAI 2024) introduced Ebbinghaus-curve-inspired decay: each memory carries a strength value `S`; retention follows `R = e^(-t/S)`, and every recall reinforces strength by 1. The Sparsion system implements a lifecycle: `Events → Salience Scoring → Hot → Warm → Cold → Forgotten` with configurable half-lives.[^6][^12][^4]

**Recommended mechanisms by content type.**

| Content type | Decay/Expiry policy | Revalidation trigger |
|-------------|---------------------|---------------------|
| Stable fact | No automatic expiry | Contradiction detection or user update |
| Low-risk preference | Soft decay after 90d inactivity; hard expiry at 180d | New evidence in same category |
| Temporary goal | Hard TTL 30d | Goal-completion detection |
| Inferred trait | 60d half-life; drops below promotion threshold | New behavioral signals |
| One-off context | Session TTL only | N/A |

**Implicit conflict handling.** STALE's top-performing system (CUPMem) achieved 68% accuracy by implementing write-side state adjudication: when new evidence arrives, an adjudicator explicitly marks related memories as `ACTIVE`, `STALE`, `REPLACE`, or `UNKNOWN` before the new evidence is inserted. For a learning companion, this means: if a learner says "I changed to a new school", the system should flag location-dependent and schedule-dependent cold memories for revalidation — even if neither was explicitly mentioned in the new message. This cascading invalidation (STALE's Type II conflict) is the most common source of harmful stale memory in production.[^6]

**User-correction UX.** A periodic profile review surface ("Here's what I remember about you — is this still accurate?") is the most reliable stale-memory detection mechanism. One production system (MemoryPlugin's "Life Context") only includes a fact after 3+ conversation appearances precisely because single facts age out quickly. User correction signals should be treated as the highest-priority revalidation event: route to a `REPLACE` adjudication immediately and log the correction for pattern analysis.[^3]

**Metric.** Stale-memory rate: fraction of verified profile entries that are contradicted by a subsequent user statement within a 90-day window. Target: < 3%. User-correction rate: number of corrections per active user per month. A rising correction rate is an early warning that extraction is too aggressive or expiry policies are too long.

***

## Proposition 6: Assistant Text, Web-Search Results, and Model Inferences Should Never Be Direct Evidence of a User Fact

**Verdict: Accept — this is among the most empirically well-supported propositions.**

**Evidence.** Mem0's production extraction prompt enforces this with an all-caps penalty line for including assistant or system messages. The attribution rule is not just good practice: the smart-extraction guide states that "attributing a fact to the wrong voice poisons the store" and gives the canonical example: "User was recommended Osteria Francescana" is a different memory from "User stated they love Osteria Francescana". Memory poisoning research (arXiv 2026) shows that assistant-sourced text is the easiest injection vector into a memory store, with success rates above 95% when no source-role gate exists.[^13][^9][^14][^3]

**Recommended source-role gate.**

```
source_role ∈ {user_explicit, user_passive}  → eligible for extraction
source_role ∈ {assistant, system, web_search, model_inference}  → blocked from memory write
```

**Nuanced case: model inferences.** An LLM inference such as "Based on your engagement patterns, I believe you learn best through spaced repetition" carries information that could be useful — but it is a model belief, not a user fact. The correct treatment:
1. Store the inference in cold memory under `source_role = "model_inference"` with `confidence ≤ 0.5` and a short TTL (14 days).
2. Never allow model-inference entries to promote to verified profile without user confirmation.
3. Use model-inference entries only for soft context (e.g., informing pedagogical strategy) not for user-facing personalization claims ("Because you prefer spaced repetition…").

**Web-search context.** Web-search results about a topic the learner asked about must never contribute to the learner's profile. "A user who searched for 'how to solve quadratic equations'" is session context about current focus, not a profile fact about mathematical ability.

**Metric.** Source-attribution audit: monthly sampling of cold memory candidates to verify that source_role is correctly assigned. Any candidate with `source_role != user_*` that passed into cold memory is a gating failure. Target: 0 assistant/system/inference sourced entries in verified profile.

***

## Proposition 7: Questions, Hypotheticals, Roleplay, and Quoted Text Require Speech-Act Detection Before Memory Extraction

**Verdict: Accept — and this is the most frequently missed edge case in production systems.**

**Evidence.** The speech-act problem ("what the utterance is doing, not just what it says") has been studied since Austin (1962) and Searle (1969) and is directly relevant to AI memory extraction. Modern dialogue act classification achieves high accuracy on clear-cut cases (interrogatives vs. declaratives) using rule-based approaches augmented by learned classifiers. The MemoryPlugin smart extraction guide identifies roleplay, external content, and quoted text as the top provenance guard cases: "exclude content the user is merely helping someone else with" and "exclude posts the user is only critiquing". Your own `memory_gate-3.py` already implements a roleplay keyword gate (`扮演`, `假扮`, `飾演`, `角色扮演`) and a question-syntax filter via `EXPLICIT_MEMORY_PATTERNS` — but the question case ("What learning method do I prefer?") currently falls through to `current_focus` rather than being blocked.[^15][^16][^17][^3]

**Recommended speech-act gate.**

A message should be blocked from cold memory extraction if it is classified as:

1. **Interrogative** — ends with `？`, `?`, or contains interrogative markers (`什麼`, `如何`, `怎麼`, `嗎`, `呢`, `哪`, `who`, `what`, `when`, `where`, `why`, `how`, `should I`). The interrogative check should run as the first filter in `classify_user_message`, before any pattern matching.
2. **Hypothetical** — contains hypothesis markers (`如果`, `假設`, `假如`, `想像`, `if`, `suppose`, `imagine`, `what if`, `hypothetically`).
3. **Roleplay or attributed speech** — within a detected roleplay frame, or contains quotation that attributes the content to a third party.
4. **Clarification or correction request** — asking the assistant to verify something ("Are you saying that…?").

**Interaction with confidence scoring.** A message classified as 60% interrogative and 40% declarative (e.g., "I wonder if I prefer visual learning?") should be stored in conversation context only, never cold memory. The doubt embedded in the utterance is itself evidence against durable storage.

**Example.**

| User message | Speech act | Memory action |
|-------------|-----------|--------------|
| "What learning method do I prefer?" | Interrogative | Conversation context only; no extraction |
| "I prefer visual learning" | Declarative preference | Cold memory candidate |
| "I prefer visual learning — or do I?" | Hedged declarative | Conversation context only |
| "Let's pretend I'm a history student who loves essays" | Roleplay initiation | No memory write; activate roleplay frame |
| "You mentioned I prefer visual learning, right?" | Clarification request | No write; retrieve existing memory |

**Metric.** Interrogative-message false-extraction rate: fraction of memory extraction events where the source message contains a question mark or interrogative marker. Target: 0% for verified profile, < 1% for cold memory.

***

## Proposition 8: User-Visible Profile Memory Should Optimize for Precision; Internal Cold Memory May Accept Lower Confidence

**Verdict: Accept — this is the key design insight for balancing personalization value against false-memory risk.**

**Evidence.** Writer.com's engineering team documented how personalized context quietly degrades AI accuracy when the personalization data is wrong or misapplied — the more the wrong context is surfaced in prompts, the more it contaminates answers. The Memory Write Policies guide distinguishes "every write is a tax on every future read" — a denser cold store with lower-confidence items degrades retrieval signal density. However, suppressing all low-confidence extraction is also harmful: the same guide notes that extracting at multiple confidence levels (0.5 for inferences, 0.9 for explicit statements) and weighting by confidence at read time preserves utility without creating profile contamination.[^18][^4]

**Recommended confidence thresholds.**

| Layer | Confidence threshold | Notes |
|-------|---------------------|-------|
| Conversation context | No threshold | All user messages; TTL = session |
| Cold memory | ≥ 0.50 for inferences; ≥ 0.70 for preferences; ≥ 0.85 for direct facts | Strict provenance required regardless |
| Verified profile | ≥ 0.85 + corroboration requirement per content type | User-facing; must be explainable |

**Why precision matters more for verified profile.** Verified profile memory is the layer that surfaces in user-facing UI ("Here's what I remember about you") and informs the system prompt on every turn. False entries here produce visible errors that damage user trust and are hard to diagnose. Cold memory errors, by contrast, expire, and their effects are diffuse (weak context influence rather than hard facts in the system prompt).

**Cold memory utility despite lower precision.** A cold memory candidate with confidence 0.60 — "user seems to learn better after practice examples than before theory" — might be wrong 40% of the time. But it is still worth storing with a short TTL and low weight, because it informs soft pedagogical decisions (ordering content) where a wrong guess has low cost. The cost asymmetry justifies the threshold difference.[^4]

**Metric.** Precision at verified profile tier: among user-facing verified profile entries, what fraction are confirmed as accurate by the user when shown in a profile review? Target: ≥ 95%. Precision at cold memory tier: what fraction of cold memory entries are promoted vs. expired vs. superseded? Monitor promotion rate to detect if cold memory is too permissive.

***

## Memory Taxonomy Table

| Category | Definition | Example | Source eligibility | Cold memory | Verified profile | Default expiry |
|----------|-----------|---------|-------------------|------------|-----------------|---------------|
| **Stable demographic fact** | Fixed background information | Name, age, country | user_explicit | Yes | Yes | No expiry |
| **Stable academic fact** | Academic level, subject area | "Grade 10 student", "studying biology" | user_explicit, user_passive | Yes | Yes (1 occ.) | No expiry |
| **Explicit low-risk preference** | Stated stylistic/approach preference | "I prefer bullet-point explanations" | user_explicit, user_passive | Yes | Yes (2 occ. or confirm) | 180-day revalidation |
| **Explicit preference via command** | User-invoked memory write | "Please remember I prefer voice format" | user_explicit_command | Yes | Yes (1 occ.) | 180-day revalidation |
| **Temporary learning goal** | Time-bound objective | "I want to finish Chapter 5 this week" | user_explicit, user_passive | Yes (short TTL) | No | 30-day TTL |
| **Inferred learning trait** | Trait from behavioral signal or indirect text | "Appears to be a visual learner" | model_inference | Yes (low confidence, short TTL) | User confirmation only | 60-day decay |
| **Situational / one-off context** | Context specific to current session | "Struggling with today's assignment" | user_passive | No | No | Session TTL |
| **Sensitive personal information** | Health, emotional state, financial | Medical condition, family crisis | None | No (24h context only) | No | 24-hour TTL |
| **Question / interrogative** | User seeking information | "What method do I prefer?" | None | No | No | N/A |
| **Roleplay / hypothetical** | Performative or fictional frame | "Pretend I'm a scientist" | None | No | No | N/A |
| **Assistant-generated summary** | Model-produced inference or restatement | "As you mentioned, you prefer…" | Blocked | No | No | N/A |
| **Web-search context** | Retrieved external content | Search result on a topic | Blocked | No | No | N/A |

***

## Decision Matrix

| Content type | Storage layer | Evidence threshold | Confidence required | Expiry | User confirmation required |
|-------------|--------------|-------------------|--------------------|---------|-----------------------------|
| Stable demographic/academic fact | Cold → Verified | 1 occurrence (explicit) | ≥ 0.85 | None | Not required |
| Low-risk preference (passive) | Cold → Verified | 1 cold; 2 for profile | ≥ 0.75 cold; ≥ 0.85 profile | 180d revalidation | Not required for cold; recommended for profile |
| Low-risk preference (explicit command) | Cold → Verified | 1 occurrence | ≥ 0.85 | 180d revalidation | Not required |
| Temporary goal | Cold only | 1 occurrence | ≥ 0.70 | 30-day TTL | Not required |
| Inferred trait (behavioral) | Cold only | ≥ 5 independent signals | ≤ 0.60 | 60-day decay | Required for verified profile |
| Inferred preference (indirect text) | Cold (pending) | ≥ 2 independent occurrences | ≥ 0.60 | 60-day TTL | Required for verified profile |
| Sensitive information | Conversation context (24h) only | N/A | N/A | 24-hour TTL | Explicit consent for any retention |
| Question / interrogative | None | N/A | N/A | N/A | N/A |
| Roleplay / hypothetical | None | N/A | N/A | N/A | N/A |
| Model/assistant inference | Cold only (model_inference role) | 1 occurrence | ≤ 0.50 | 14-day TTL | Required for any profile use |
| One-off situational context | Conversation context only | N/A | N/A | Session TTL | N/A |

***

## Minimal Policy (Early-Stage Product)

Suitable for a system without reliable user feedback loops, low cold memory volume, and no verified provenance infrastructure. Optimizes for trust and precision at the cost of recall.

**Rule set:**

1. **Write to cold memory only from user messages** (`source_role = user_*`). Block all assistant, system, model-inference, and web-search writes.

2. **Block interrogative messages.** If the source message contains `?` or common interrogative markers, do not extract to cold memory.

3. **Block roleplay frames.** Detect roleplay initiation and suppress all memory extraction until the frame is closed.

4. **Block sensitive keywords.** Use a static sensitive-keyword list (health, financial, family crisis, mental health). Route to 24h session context only.

5. **Cold memory requires full provenance.** All six fields — `user_id`, `message_id`, `conversation_id`, `timestamp`, `raw_user_text`, `source_role` — must be present. Fail closed if any are absent.

6. **Cold memory TTL: 90 days.** All cold entries expire unless reconfirmed or promoted.

7. **Verified profile requires explicit user confirmation.** No automatic promotion. Surface candidates to users as "suggested profile facts" and promote only on positive confirmation.

8. **Review every cold memory candidate before promotion.** A human admin or async review job checks candidates weekly.

**What this policy deliberately sacrifices.** Passive preference extraction, inferred trait learning, multi-conversation corroboration logic, and behavioral signal integration. These are expensive to get right; getting them wrong erodes trust faster than not having them.

***

## Advanced Policy (After Reliable Provenance and User Feedback)

Suitable for a system with: full provenance on all writes, user feedback data (correction rate, confirmation rate, profile review engagement), and at least one revalidation cycle.

**Rule set:**

1. All rules from the minimal policy remain in effect.

2. **Tiered confidence gate.** Cold memory accepts confidence ≥ 0.50 for inferred items, ≥ 0.70 for passive preferences. Track confidence calibration monthly; recalibrate extraction prompts if false-positive rate at cold layer exceeds 5%.

3. **Corroboration-based auto-promotion.** Passive preferences with ≥ 2 independent conversation occurrences AND confidence ≥ 0.85 AND no sensitive-keyword match are eligible for automatic promotion to verified profile. Notify the user on promotion with a single in-app card.

4. **Behavioral signal integration.** Behavioral signals (scroll, focus, re-read) accumulate with a configurable decay function. When ≥ 5 high-weight signals support a consistent trait (e.g., repeatedly re-reading visual diagrams), write a cold memory entry under `source_role = model_inference` with confidence ≤ 0.55 and 60-day TTL. Never auto-promote to verified profile.

5. **Implicit conflict adjudication.** When a new user message arrives, run a lightweight conflict checker against the top-10 semantically related cold memory entries. Flag entries where the new message implies an incompatible state (`STALE`) and demote confidence. Follow STALE benchmark guidance on Type I and Type II conflict types.[^6]

6. **Sensitive memory scoping at generation time.** Retrieved sensitive memory entries are tagged with `background_only`. The generation prompt receives a boundary policy instruction: "Do not explicitly reference or surface content tagged `background_only` unless the user's current message explicitly invites it."[^10]

7. **Periodic profile review UX.** Every 30 active days, surface a "profile review" prompt showing verified profile entries and the top-5 cold memory candidates. Treat confirmation as a strong evidence signal (boost confidence to 0.95); treat rejection as a deletion event and a signal to audit similar extraction patterns.

8. **Promotion history log.** Every verified profile entry maintains a `promotion_history` field recording all evidence events, confidence scores, and the decision that triggered promotion. This enables auditability, rollback, and debugging of false personalization patterns.

**Metrics to monitor in the advanced regime.**

| Metric | Definition | Target |
|--------|-----------|--------|
| False-memory rate | Fraction of verified profile entries corrected by user within 60d | < 1% per user per quarter |
| User correction rate | Corrections per active user per month | Trending down; alert if rising |
| Promotion rate | Fraction of cold candidates reaching verified profile | 10–25% (if <10%, extraction too restrictive; if >40%, gate too permissive) |
| Stale-memory rate | Verified profile entries contradicted by new evidence in 90d | < 3% |
| Interrogative leak rate | Cold memory writes from interrogative source messages | 0% target |
| Source-attribution audit failure | Non-user-role entries in cold or verified profile | 0% target |
| Personalization benefit | User-reported answer relevance in sessions with active profile vs. cold start | +15–25% lift target |

---

## References

1. [Memory policy, not UX: who controls AI recall | Vastkind](https://www.vastkind.com/memory-policy-not-ux/) - The moment AI remembers across sessions, memory stops being a UX feature and becomes a power and lia...

2. [AGENTREL03-BP01 Design an information classification model to identify short-term and long-term memories](https://docs.aws.amazon.com/ja_jp/wellarchitected/latest/agentic-ai-lens/agentrel03-bp01.html) - A single undifferentiated memory store blurs conversation context with durable knowledge and pulls s...

3. [Smart Extraction · The Field Guide to AI Memory](https://www.memoryplugin.com/wiki/smart-extraction.html) - How a raw conversation becomes a small set of facts worth keeping, and the design choices that decid...

4. [Memory Write Policies: What's Worth Remembering](https://jatinbansal.com/ai-engineering/memory-write-policies/) - Memory write policies: distillation, write amplification, the journaling-vs-checkpoint trade-off, le...

5. [MemMachine: A Ground-Truth-Preserving Memory System ...](https://arxiv.org/html/2604.04853v1) - MemMachine, an open-source memory system for AI agents that prioritizes ground truth preservation, c...

6. [STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?](https://arxiv.org/pdf/2605.06527v1.pdf)

7. [LONG-TERM MEMORY POISONING IN LLM-BASED ...](https://papers.ssrn.com/sol3/Delivery.cfm/5995215.pdf?abstractid=5995215&mirid=1) - Personal assistants retain memory to enhance personalization. Preferences, habits, and inferred trai...

8. [\titlefont MemPrivacy: Privacy-Preserving Personalized ...](https://arxiv.org/html/2605.09530v3) - MemPrivacy introduces a four-level privacy taxonomy that allows different protection policies to be ...

9. [Memory Poisoning Attacks on Large Language Model Agents](https://arxiv.org/html/2607.06595v1) - This paper studies security vulnerabilities in personal assistant agents that use long-term memory. ...

10. [[PDF] When Should Memory Stay Silent - arXiv](https://arxiv.org/pdf/2606.06055.pdf)

11. [We Are Not Talking About AI Memory Enough](https://www.techpolicy.press/we-are-not-talking-about-ai-memory-enough/) - AI assistants have reportedly made unauthorized financial decisions, encouraged eating disorders, an...

12. [AI memory is broken. We built one that forgets. - DEV Community](https://dev.to/highpass_studio_382ce5641/ai-memory-is-broken-we-built-one-that-forgets-dmc) - Every agent framework has the same problem with memory: it doesn't forget. Context windows reset...

13. [Memory Injection Attacks on AI Agents: How Poisoned Data Creates ...](https://agentmarketcap.ai/blog/2026/04/05/memory-injection-attacks-ai-agents-poisoned-data-persistent-false-beliefs) - How memory injection attacks plant false beliefs in AI agents that persist across sessions, with 95%...

14. [A Systematic Study of Memory Poisoning Attacks in LLM ...](https://arxiv.org/html/2606.04329v1)

15. [Automated Discovery of Speech Act Categories in ...](https://files.eric.ed.gov/fulltext/ED537204.pdf)

16. [[PDF] Intent Classification for a Management Conversational Assistant](https://repository.mdx.ac.uk/download/1828337e9386331e3bf728f418d13e801447d341c6cac9d9e3a757d396acfb72/234395/IntentClassificationForAManagementConversationalAssistant-17_CR%5B2%5D.pdf)

17. [Dialogue Act Classification Methods in Natural Language](https://openreview.net/pdf?id=lSgh1cRVNv)

18. [How personalized context quietly degrades AI accuracy](https://writer.com/engineering/personalized-context-degrades-ai-accuracy/) - Personalization of LLMs with added context can play a significant role in improving the quality of o...

