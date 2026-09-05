## Overview
AREQA currently runs two parallel generation paths: a text chat path backed by `/stream` (AREQA's RAG pipeline with citations, memory, and conversation context) and a voice path backed by OpenAI's Realtime API, where `gpt-realtime` independently generates both the spoken answer and its transcript. Because the Realtime model produces its own answer directly from audio input rather than routing through AREQA's retrieval-augmented pipeline, the two paths can diverge in content, citations, and even factual accuracy — the voice answer is not guaranteed to be the "same" answer the text system would have given. This report compares three candidate architectures for unifying the two paths and recommends a migration path with an event flow diagram.[^1][^2]
## How the Underlying APIs Behave
Three OpenAI primitives are relevant to this decision:

- **Realtime API**: A persistent WebSocket/WebRTC session supporting full-duplex audio in and out, native speech-to-speech generation, function/tool calling mid-conversation, and automatic barge-in — the server-side voice activity detector (VAD) emits `input_audio_buffer.speech_started` when the user starts talking, and the client is expected to call `response.cancel` to stop the in-flight response. Realtime sessions can also be configured for text-only modality, and function tools let the model call out to external code and incorporate results into a "second" response.[^3][^4][^5][^6][^7]
- **Speech (TTS) API**: A stateless `audio/speech` endpoint (`gpt-4o-mini-tts`) that converts arbitrary input text into streamed audio (SSE or chunked PCM/WAV), with the first audio chunk arriving in well under a second and support for "speak this way" style instructions. It has no memory of prior turns — it is a pure text-to-audio renderer.[^8][^9][^10]
- **Streaming text generation (SSE/FastAPI)**: The established pattern for AREQA's `/stream` is unidirectional SSE token streaming with disconnect handling and explicit error events — this is the same mechanism many production RAG chat backends use.[^11][^12][^13]

This matters because Realtime and TTS are architecturally distinct products: Realtime is a full conversational engine with its own state and generation, while TTS is a dumb renderer that takes whatever text you feed it. Architecture B and C exploit this separation; Architecture A does not.
## Architecture A: Realtime Generates the Answer Itself (Current)
In this design, `gpt-realtime` receives the user's audio, forms its own understanding of the request, and generates both a spoken answer and a transcript in one pass, with no mandatory pass through AREQA's RAG stack. Barge-in is native: the VAD detects overlapping speech and the client cancels the response.[^14][^2][^15][^6]

The core weakness is that the model's world knowledge, not AREQA's retrieved context, drives the answer content unless every fact is force-fed into the session's tool or system context beforehand. This makes citation fidelity and RAG grounding structurally unreliable — the model can "know" things beyond what was retrieved, or omit citations entirely, since Realtime responses are not designed to emit structured citation metadata the way a RAG completion is. Language behavior (e.g., matching the user's Traditional Chinese register, formality, or terminology conventions) also has to be re-specified in Realtime instructions, separate from whatever prompt engineering already governs `/stream`, creating two divergent behavior surfaces to maintain.
## Architecture B: AREQA `/stream` First, Then TTS
Here, voice mode reuses the exact `/stream` pipeline used by text chat — same retrieval, same memory, same prompt template, same citations — and only after (or incrementally as) text is produced does a separate TTS call render it to audio. Because `gpt-4o-mini-tts` supports low-latency streaming with sub-second first-chunk latency, the perceived responsiveness gap versus Realtime is manageable, especially if TTS is invoked sentence-by-sentence rather than after the full answer completes.[^8][^16][^9][^10]

This is the only architecture that guarantees answer identity between text and voice: since both modes call the same generation code path, citation fidelity, RAG context, memory, and language behavior are byproducts of using one system rather than a re-implementation. The frontend can also drive text fade-in directly from the same SSE token stream already used for chat, rather than deriving cadence from a separate transcript, which simplifies sentence-by-sentence sync with audio playback. Interruption handling requires custom engineering, though: cancelling an in-flight `/stream` request and an in-flight TTS stream are two separate operations that must be coordinated so partial text and partial audio playback end in a consistent state (e.g., truncating displayed text to the last spoken sentence boundary, not the last generated token).

The main cost is latency at the front end of the turn: the user hears nothing until the first sentence of the RAG answer is generated, whereas Realtime can start "talking" before an equivalent RAG answer would even be retrieved. This gap narrows considerably if `/stream` emits sentence-level chunks and TTS synthesis for sentence 1 starts while sentence 2 is still being generated (pipelined streaming), but a first-audio delay of roughly 1-3 seconds (retrieval + first LLM tokens) versus Realtime's near-instant start is a real UX trade-off.
## Architecture C: Hybrid — Realtime Orchestration + Forced AREQA Tool Call
This design keeps a Realtime session open for low-latency turn-taking (VAD, interruption, natural backchannel), but configures the AREQA answer as a mandatory function tool that the model must call on every substantive turn before producing its final spoken response, using the standard Realtime function-calling lifecycle: model emits `function_call` arguments, client executes the tool (calls `/stream` or an equivalent AREQA endpoint), and returns `function_call_output`, after which the model is prompted to speak from that result. Realtime's tool schema can be scoped at the session or per-response level, so "always call AREQA" can be enforced with `tool_choice` forcing the tool on each turn.[^3][^17][^4][^18]

This preserves Realtime's native interruption handling and natural audio cadence while nominally grounding answers in AREQA's retrieval. But it introduces a subtle citation-fidelity risk: Realtime's spoken response is a paraphrase of the tool output, not a verbatim recitation, so the model can still drop, mangle, or hallucinate around citations when converting the AREQA answer into speech, since audio generation models are not trained to preserve inline citation markers faithfully. It also doubles latency contributors — RAG retrieval/generation time, plus a full model turn to convert that result into spoken audio — and requires two separate logs/traces (Realtime session events and the /stream backend) that can drift out of sync, complicating text-audio consistency and failure recovery.
## Comparative Analysis
| Dimension | A: Realtime-native | B: Text-first + TTS | C: Hybrid (Realtime + forced tool) |
|---|---|---|---|
| First-audio latency | Lowest — near-instant[^5] | Higher — waits for first RAG sentence[^11] | Medium — RAG call + Realtime paraphrase turn[^4] |
| Context consistency (text vs. voice) | Poor — two independent generations | Excellent — single generation path | Good but not guaranteed — paraphrase step can drift |
| Citation fidelity | Very weak — no structured citation path | Strong — citations carried through unchanged | Weak-to-moderate — citations may be dropped/altered in paraphrase |
| Language consistency (zh-Hant behavior) | Requires duplicate prompt engineering | Single source of truth | Requires syncing two prompt layers |
| Cost | Realtime audio tokens are expensive per exchange[^19] | RAG LLM cost + cheap TTS ($0.60/$12 per 1M tokens class)[^19] | Realtime session cost + RAG cost — highest combined cost |
| Interruptibility | Native, built-in VAD + `response.cancel`[^6][^14] | Must be custom-built (cancel /stream + cancel TTS) | Native at the Realtime layer, but AREQA call itself isn't interruptible mid-retrieval |
| Frontend state mgmt | Two divergent state machines (voice vs. text) | One state machine reused for both modes | Three state machines: Realtime session, tool call, and TTS/synthesis if further split |
| Failure recovery | Silent divergence — hard to detect | Isolated: failure surfaces in one shared pipeline | Two systems must agree on failure semantics |
| Testing strategy | Must test Realtime prompt separately from text prompt | Test once (backend), reuse across modes | Must test tool-forcing reliability + paraphrase accuracy |
## Recommendation
Architecture B — AREQA `/stream` generates the authoritative text first, with a thin TTS layer converting that same text to audio — is the most elegant and safest architecture because it is the only design where citation fidelity, RAG grounding, memory, and language behavior are structurally guaranteed rather than re-validated per mode. It is also the most incrementally migratable: it requires zero changes to AREQA's core RAG/memory/citation logic, and voice mode simply becomes a new consumer of the existing `/stream` endpoint plus a new TTS microservice, rather than a parallel prompt-engineering surface that must be kept in sync with text chat indefinitely.

The two real risks in B — perceived latency and custom interruption handling — are both solvable with engineering rather than requiring a different foundational architecture: pipelining TTS synthesis per sentence as `/stream` emits sentence boundaries closes most of the latency gap versus Realtime, and a shared "turn state" object (below) resolves interruption consistency. Architecture C is worth revisiting later only if user testing shows the latency of B is unacceptable for casual conversational turns (e.g., "yes/no" clarifications) — in that narrow case, a lightweight Realtime layer could handle only short deterministic acknowledgments while all substantive Q&A still flows through B's `/stream`-first path, but this should be a targeted optimization, not the default architecture.
### Incremental Migration Path
1. Keep Realtime voice mode (A) live for existing users; build a parallel "Voice v2" behind a feature flag.
2. Add a `POST /stream` mode flag or a companion `/stream/voice` endpoint that segments AREQA's SSE output into sentence-complete chunks (already implicit in token streaming; add sentence-boundary detection).
3. Introduce a TTS microservice that consumes each completed sentence chunk and streams back PCM/WAV via `gpt-4o-mini-tts` streaming, buffering just enough to avoid audio gaps.[^8][^10]
4. Build a unified frontend "turn" state machine (see below) shared by text and voice UI, so text fade-in timing is driven by TTS playback position (via Web Audio API playback clock) rather than a second independent timer.
5. Implement interruption by exposing a single `cancelTurn()` action that aborts the `/stream` SSE connection (if still generating) and stops/discards buffered TTS audio, then snaps the displayed text to the last fully-spoken sentence boundary.
6. A/B test v2 against the Realtime baseline on latency-to-first-audio and answer-fidelity metrics before fully deprecating A.
### Event Flow Diagram (Recommended Architecture B)
```
User speaks / types
        │
        ▼
Frontend: send query to /stream  (existing RAG entry point)
        │
        ▼
AREQA /stream (RAG + memory + citations)
        │  emits SSE token deltas, tagged with sentence-boundary markers
        ▼
Frontend Sentence Buffer
   ├─► on sentence complete → POST sentence text to TTS microservice
   │        │
   │        ▼
   │   TTS (gpt-4o-mini-tts, streaming PCM/WAV)
   │        │  streams audio chunks back
   │        ▼
   │   Audio Player queue (Web Audio API) ── plays chunk, exposes playback clock
   │
   └─► Text renderer: fades in text in sync with audio playback clock
              (character/sentence reveal rate = f(playback position))

        ┌─────────────── If user starts speaking / clicks stop ───────────────┐
        │  cancelTurn()                                                      │
        │   1. Abort /stream SSE connection (if still generating)            │
        │   2. Flush/stop TTS audio queue immediately                        │
        │   3. Snap displayed text to last fully-spoken sentence boundary    │
        │   4. Mark turn as "interrupted" in conversation history            │
        │   5. New user turn appended to SAME conversation (no new chat)     │
        └─────────────────────────────────────────────────────────────────────┘
```
### Testing Strategy Notes
Validation should cover the seams unique to B: sentence-boundary detection accuracy against streamed RAG tokens (avoiding TTS synthesis of incomplete/broken sentences), audio-text sync drift under variable network conditions, and interruption correctness (verifying text state and audio state never disagree after `cancelTurn()`). Regression tests should replay the same benchmark question set through both text-only and voice-enabled paths and diff citations, RAG context, and final answer text to confirm true content parity — the property that Architecture A structurally cannot guarantee.[^4][^2]

---

## References

1. [Realtime and audio | OpenAI API](https://developers.openai.com/api/docs/guides/realtime) - Learn which realtime and audio guide to use for each speech application.

2. [Realtime API | OpenAI Help Center](https://help.openai.com/en/articles/9949624-realtime-api)

3. [Realtime with tools | OpenAI API](https://developers.openai.com/api/docs/guides/realtime-mcp) - Learn how to configure function tools, MCP tools, and connectors in a Realtime session.

4. [Realtime conversations | OpenAI API](https://developers.openai.com/api/docs/guides/realtime-conversations) - Learn how to manage Realtime speech-to-speech conversations.

5. [Introducing the Realtime API](https://openai.com/index/introducing-the-realtime-api/) - Developers can now build fast speech-to-speech experiences into their applications

6. [Barge-in & Interruption | howie/voice-lab | DeepWiki](https://deepwiki.com/howie/voice-lab/5.6-barge-in-and-interruption) - This page documents the barge-in (interruption) functionality in the Voice Interaction Module, which...

7. [How to get text only output from the Realtime API?](https://community.openai.com/t/how-to-get-text-only-output-from-the-realtime-api/967528) - Hi! I'd like to build some UI controls using the Realtime API and I'm not interested in the audio ou...

8. [Text to speech | OpenAI API](https://developers.openai.com/api/docs/guides/text-to-speech) - The Audio API provides a speech endpoint based on our GPT-4o mini TTS (text-to-speech) model. It com...

9. [Updates for developers building with voice](https://developers.openai.com/blog/updates-audio-models) - New audio model snapshots and broader access to Custom Voices for production voice apps.

10. [GPT-4o Mini TTS API Guide - TheRouter.ai](https://therouter.ai/models/openai--gpt-4o-mini-tts/api/) - Pricing, context length, supported parameters, and OpenAI-compatible usage examples for GPT-4o Mini ...

11. [1. Json-Encoded Sse For...](https://www.callmissed.com/en/blog/tutorial-stream-llm-fastapi) - A 2026 production-grade FastAPI streaming tutorial — SSE, async, post-stream usage tracking, client-...

12. [Server-Sent Events (SSE)](https://fastapi.tiangolo.com/tutorial/server-sent-events/) - FastAPI framework, high performance, easy to learn, fast to code, ready for production

13. [Real-time Communication | carlosplanchon/fastapi_ai_assistant | DeepWiki](https://deepwiki.com/carlosplanchon/fastapi_ai_assistant/3-real-time-communication) - This document explains how the FastAPI AI Assistant implements real-time streaming of AI responses u...

14. [Barge-In and Custom Turn Detection - The AI Agent Factory](https://agentfactory.panaversity.org/docs/Building-Realtime-Voice-Agents/openai-realtime-api/barge-in-custom-turn) - Master interruption handling and implement custom turn detection with the OpenAI Realtime API. Learn...

15. [Audio and speech | OpenAI API](https://developers.openai.com/api/docs/guides/audio) - Models such as gpt-realtime-2.1 and gpt-audio-1.5 are natively multimodal, meaning they can understa...

16. [developers.openai.com](https://developers.openai.com/api/docs/guides/text-to-speech.md)

17. [Function calling | OpenAI API](https://developers.openai.com/api/docs/guides/function-calling) - Learn how function calling enables large language models to connect to external data and systems.

18. [Tool Integration | soketlabs/realtime-console | DeepWiki](https://deepwiki.com/soketlabs/realtime-console/2.3-tool-integration) - This document covers the tool (function calling) integration system in the OpenAI Realtime Console, ...

19. [GPT-4o Mini TTS Model | OpenAI API](https://developers.openai.com/api/docs/models/gpt-4o-mini-tts) - GPT-4o Mini TTS is a text-to-speech model built on GPT-4o Mini, a fast and powerful language model. ...

