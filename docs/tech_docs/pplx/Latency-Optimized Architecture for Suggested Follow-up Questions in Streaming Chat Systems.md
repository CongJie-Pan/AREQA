## Overview

The 1-2 second delay before the final SSE `done` event is a well-documented pattern in production chat systems: a synchronous, blocking second LLM call inserted between "answer complete" and "turn complete." Every production system reviewed (Open WebUI, LibreChat, Perplexity-style answer engines, Microsoft Copilot Studio agent flows, and OpenAI community implementations) either decouples this call from the critical path, uses a small/cheap model with a timeout, or moves it out of the synchronous request entirely.[^1][^2][^3]

## How Production Systems Generate Suggestions

**Separate small/cheap model, not the main model.** Open WebUI explicitly generates follow-ups via a distinct "task model" (a lighter model configured separately from the main chat model) run after the main response. LibreChat's follow-up feature proposal specifies a dedicated `followUpModel` (e.g., `gpt-4o-mini`) distinct from the primary answer model, with a configurable count and temperature. This mirrors LibreChat's existing pattern for conversation-title generation, which already runs as a separate lightweight background call. The rationale is consistent across sources: the main model is optimized (and often prompted/tuned) for answer quality and long-context reasoning, while suggestion generation is a short, low-stakes, high-volume task better suited to a fast, cheap model.[^2][^1]

**Single-call generation is used mainly in prompt-hacked consumer setups, not production backends.** Community "custom instruction" tricks for ChatGPT ask the *same* main model to append follow-up questions to its own answer, formatted with delimiters for later parsing. This is popular among individual users but is explicitly flagged in engineering discussions as fragile: it mixes concerns in one prompt, risks the model bleeding formatting into the visible answer, and makes suggestion quality dependent on the main model's context/instructions rather than a dedicated, tunable prompt. No production system reviewed uses this as its primary backend architecture — Open WebUI and LibreChat both explicitly separate it out.[^4][^5][^6][^1][^2]

**Multi-agent answer engines dedicate a distinct pipeline stage to "related questions."** The open-source Perplexity-style implementations describe "related questions" as a discrete pipeline agent/stage that runs alongside or after synthesis, separate from citation and answer-generation stages. This reflects the general architecture pattern in RAG/answer-engine systems: retrieval → synthesis → (parallel) related-question generation, rather than folding suggestion generation into the main generation call.[^7][^8]

## Synchronous vs. Asynchronous Delivery

No source found describes suggestions being generated synchronously *before* `done` as a deliberate best practice — every credible engineering writeup treats this as the anti-pattern to be fixed. The SSE protocol design described in a detailed engineering postmortem on building streaming AI chat explicitly separates event types (`session`, `status`, `token`, `citations`, `done`, `error`) and treats `done` as a lifecycle signal for completion/analytics, sent as soon as the model's output is finalized — additional payloads (like citations) are appended as their own event type without blocking `done`. The same source's core lesson generalizes directly to suggestions: "any operation over one second needs visible, specific feedback" rather than a silent block, and operations that aren't essential to the primary answer should not gate the completion signal.[^9]

Microsoft's Copilot Studio agent flow documentation formalizes the general pattern for exactly this problem: an "asynchronous response" mode lets the primary response return immediately while a secondary flow (analogous to suggestion generation) completes in the background and delivers results via a callback once finished, rather than making the user's turn wait on it. This is the direct architectural analogy for decoupling suggestion generation from the `done` event.[^3]

Fallback-and-timeout design is also well established outside pure chat UX: enterprise RAG fallback architectures use rule-based/deterministic short-circuits for non-critical tasks and cascade to smaller, faster models when a primary call is slow or degraded — a pattern directly transferable to "generate 3 follow-ups, or fall back to a template/cache after N ms".[^10]

## SSE Delivery Patterns

The dominant pattern is **typed SSE events over a single connection**, where the answer stream, citations, and suggestions are distinct event types multiplexed on one response: `token` events for streamed answer text, then discrete non-token event types (e.g., `citations`, `suggestions`) sent once available, followed by a terminal `done` event carrying only completion metadata (timing, status). Because `EventSource` does not support POST bodies or custom headers, production implementations commonly use `fetch` with manual chunk parsing rather than the native browser API, which also gives more control over how/when to emit additional event types like suggestions.[^9]

Two viable event sequencing options emerge from the sources:

1. **`done`-then-suggestions**: emit `done` immediately after the answer stream ends, then push a separate `suggestions` event afterward (fire-and-forget or short background job), letting the frontend render the answer as "complete" instantly and progressively fill in suggestion chips.[^3][^9]
2. **Timeout-gated suggestions before `done`**: keep the current event order but cap the suggestion call at a strict budget (e.g., 300-500 ms) and fall back to cached/template suggestions if the model doesn't respond in time, so `done` is delayed by a bounded, small amount rather than an open-ended 1-2 seconds.[^10]

## Comparison of Approaches

| Approach | Perceived latency | Answer quality impact | UI/SSE consistency | Backend complexity | Failure mode |
|---|---|---|---|---|---|
| Separate LLM call, synchronous before `done` (current design) | Poor — full suggestion latency added to critical path[^9] | None — fully decoupled prompt/model[^1][^2] | High — suggestions always present before `done` | Low | Slow/failed call blocks entire turn |
| Main model generates suggestions in same response | Adds to *first* response latency (single call, but longer output)[^4][^5] | Risk — mixes formatting/instructions with main answer prompt, parsing fragility[^5] | Medium — must parse combined output; formatting can leak into visible answer[^4] | Low (no second call) but fragile parsing | Malformed delimiter breaks both answer and suggestions |
| Background async generation after `done` | Best — `done` fires as soon as answer completes; suggestions arrive as a later event[^9][^3] | None — separate, tunable prompt/model[^1][^2] | Requires frontend to handle late-arriving `suggestions` event and a "pending" state for chips | Medium — needs background job/callback plumbing[^3] | Suggestions may never arrive; needs a UI timeout/empty state |
| Cached/template fallback suggestions | Excellent — near-zero added latency | Lower relevance/specificity, generic phrasing | High — always available, simple to render | Low | Suggestions feel generic or repetitive |
| Small/cheap model with timeout budget | Good — bounded worst case (e.g., ≤500 ms) | Slightly lower quality/specificity than main model, generally acceptable for short suggestion text[^1][^2] | High — consistent event ordering preserved | Medium — needs timeout + fallback wiring[^10] | Timeout triggers fallback; degrades gracefully |

## Recommended Architecture

The pattern that best satisfies "suggestions remain a feature, main answer quality must not degrade, SSE compatibility matters" is a **hybrid of async delivery + small model + timeout fallback**, mirroring what Open WebUI, LibreChat, and Copilot Studio's async-flow model already implement in production:[^1][^2][^3]

- Use a distinct, small/cheap "task model" for suggestions, separate from the main answer model, following the Open WebUI/LibreChat pattern.[^2][^1]
- Fire the suggestion call the moment the main answer stream finishes (or even earlier, once enough context is available), running concurrently rather than strictly after full completion.
- Send `done` as soon as the answer text is finalized, without waiting on suggestions — treat suggestions as a non-blocking, best-effort enrichment, consistent with the SSE lifecycle design where `done` signals turn completion and other payload types are appended independently.[^9]
- Deliver suggestions via a dedicated `suggestions` SSE event pushed after `done` (or via a short follow-up request/poll), with the frontend showing a lightweight loading state for the chip row that resolves when the event arrives.[^9]
- Enforce a hard timeout budget (roughly 300-800 ms is a reasonable target given suggestion text is short) and fall back to cached/template suggestions derived from the query category or a static bank when the model misses the budget, following the fallback-cascade pattern used in resilient RAG systems.[^10]

## Risks and Mitigations

- **Frontend expects suggestions before `done`.** Changing event order requires a client contract change; mitigate by versioning the SSE protocol (e.g., an explicit `suggestions_pending: true` flag in `done`) so older clients degrade gracefully.[^9]
- **Suggestions never arrive (background job fails silently).** Mitigate with a client-side timeout that swaps in template fallbacks if no `suggestions` event arrives within a set window, and server-side logging of failure/timeout rate.[^10]
- **Small model produces lower-quality or repetitive suggestions.** Mitigate with prompt tuning specific to the suggestion task (as LibreChat does with a dedicated model/temperature config) and periodic quality sampling against the main model's suggestions.[^1]
- **Increased backend complexity from async/background jobs.** Mitigate by starting with the lowest-risk phase (timeout + fallback only) before introducing full async delivery.

## Phased Implementation

**Phase 1 — Lowest-risk fix (no protocol change):** Keep the current event order (suggestions before `done`), but switch the suggestion call to a smaller/cheaper model and impose a strict timeout (e.g., 500 ms) with an immediate template/cached fallback if exceeded. This directly attacks the 1-2 second delay without touching the frontend contract, following the fallback-cascade approach used in production LLM resilience patterns and the dedicated-task-model pattern from Open WebUI/LibreChat.[^2][^1][^10]

**Phase 2 — Improved architecture (protocol change):** Emit `done` immediately after the answer stream completes; run suggestion generation concurrently/asynchronously and deliver it via a separate `suggestions` SSE event (or a lightweight follow-up poll), matching the async-response callback pattern documented for agent flows and the typed multi-event SSE protocol design seen in production streaming chat implementations. Update the frontend to render answer completion instantly and show a brief loading state for suggestion chips.[^3][^9]

**Phase 3 — Optional experiment:** A/B test whether pre-fetching/pre-generating likely suggestions *during* answer streaming (using partial context, before the answer fully completes) further reduces the suggestion event's arrival latency, and measure whether quality holds up versus post-completion generation. Log suggestion-call latency, timeout-fallback rate, click-through rate on suggestions, and answer-vs-suggestion model disagreement to guide whether Phase 3 optimizations are worth the added complexity.[^10][^9]

## Telemetry to Log

Suggestion-call latency (p50/p95/p99), timeout/fallback trigger rate, suggestion-model error rate, time between answer-stream-end and `done`, time between `done` and `suggestions` event (if async), click-through rate on suggestion chips vs. fallback chips, and any user-visible "answer felt slow" signals tied to the suggestion stage specifically rather than the main answer stream.[^9]

---

## References

1. [Enhancement: Auto generate suggested follow-up questions · Issue #4132 · danny-avila/LibreChat](https://github.com/danny-avila/LibreChat/issues/4132) - What features would you like to see added? Similar to how the title generation is done, it'd be cool...

2. [Follow-Up Prompts - Open WebUI](https://docs.openwebui.com/features/chat-conversations/chat-features/follow-up-prompts/) - Open WebUI can automatically generate follow-up question suggestions after each model response. Thes...

3. [Asynchronous response support for agent flows - Microsoft Learn](https://learn.microsoft.com/en-us/microsoft-copilot-studio/flow-asynchronous-response) - Learn how to enable asynchronous responses for agent flows so that long-running flows can continue b...

4. [Add one-click follow-up prompts - Feature requests](https://community.openai.com/t/add-one-click-follow-up-prompts/1254567) - To reduce the amount of typing and speed up using ChatGPT, have each prompt end with a few suggestio...

5. [Suggested follow up questions - Prompting](https://community.openai.com/t/suggested-follow-up-questions/121278) - We’re using chat GPT-3-turbo with the API and have just started playing with the concept of a UI tha...

6. [Unlock ChatGPT's Full Potential: Auto-Suggest Brilliant Questions!](https://www.youtube.com/watch?v=S6BiZQpAcD8) - Discover how to make ChatGPT automatically suggest great questions to ask next! 

Imagine ChatGPT su...

7. [What It Does](https://devpost.com/software/perplexity-oss-by-lyzr) - Open-source,self-hosted AI search engine combining web search with Bedrock's Nova models via special...

8. [How Perplexity AI Answers Work: Retrieval, Ranking, and ...](https://ziptie.dev/blog/how-perplexity-ai-answers-work/) - Perplexity AI generates cited answers through a multi-stage Retrieval-Augmented Generation (RAG) pip...

9. [Building streaming AI chat with Server-Sent Events](https://neuralsummary.com/en/blog/building-streaming-ai-chat-with-sse) - Why we chose SSE over WebSocket for AI chat streaming, how citation buffering eliminated visual arti...

10. [Implementing LLM Fallback Mechanisms with LangGraph - C# Corner](https://www.c-sharpcorner.com/article/building-resilient-enterprise-rag-implementing-llm-fallback-mechanisms-with-lan/) - By leveraging LangGraph, we can elegantly orchestrate complex fallback mechanisms. We bypass the LLM...

