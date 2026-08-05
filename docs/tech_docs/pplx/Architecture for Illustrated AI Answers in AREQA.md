## Overview
Gemini-like "illustrated answers" combine three subsystems that are decoupled but tightly coordinated: a planning/generation layer that decides *where* images belong and *why*, a retrieval layer that finds and ranks candidate web images, and a verification/rendering layer that confirms match quality before the frontend displays anything. Google's own AI Mode implements this as a "visual search fan-out" — the model decomposes the query/image into sub-queries run in parallel, then recombines results that best match intent. Bing/Copilot and Google's Gemini Enterprise Answer API return images as separate structured objects tied to citations rather than inline Markdown. This pattern — structured plan → parallel retrieval → grounded recombination — is the direct model for AREQA.[^1][^2][^3][^4][^5]
## Should the LLM Emit a Structured Plan with Visual Slots?
Yes — an explicit plan-with-slots step is the architecturally correct choice, not just an optimization. Google's Search Generative Experience and AI Mode already operate this way internally: the model does not free-form emit "![img]" tokens; it issues discrete internal queries (fan-out) tied to detected concepts, then a separate layer resolves and places the visual results. The Gemini Enterprise "answer" API formalizes this further — the answer method explicitly separates the generated text from an `imageSource` field describing whether an image should be pulled from the corpus or generated, and images are attached to specific citations rather than embedded in text.[^6][^7][^2][^3]

Reasons to keep IMAGE_SLOT(topic, purpose, search_query) as a first-class structured object rather than inline Markdown:

- **Determinism and safety**: a slot object can be validated, filtered, and rejected without re-parsing free text or risking a broken Markdown image tag reaching the user.
- **Decoupled retrieval timing**: slots can be dispatched to the image pipeline asynchronously while text generation continues streaming.
- **Purpose-awareness**: tagging each slot with a purpose (e.g., "diagram", "example-photo", "historical-figure-portrait") lets the ranker apply different scoring rules per purpose.
- **Retry and fallback control**: if retrieval fails, the backend can drop, retry with a rewritten query, or substitute a caption-only card — impossible to do cleanly with inline Markdown image syntax embedded in generated prose.
- **Multimodal RAG grounding research** shows structured retrieval requests ("query decoupling," reformulating a query into an explicit retrieval object) consistently outperform ad hoc embedded references for cross-modal grounding accuracy.[^8]

Free-form Markdown image insertion should be avoided as the primary mechanism because the LLM cannot verify a URL exists, is safe, or is licensed at generation time — it can only hallucinate plausible-looking image markdown. The slot-based plan defers the actual URL resolution to a deterministic backend stage that has real search results in hand.
## When Should Image Retrieval Happen?
A hybrid "plan-then-parallel-resolve" timing works best, mirroring Gemini/AI Mode's fan-out design and Gemini API's Google Search grounding tool, which runs search calls before finalizing the grounded response:[^2][^9]

| Timing option | Behavior | Trade-off |
|---|---|---|
| Before generation | Retrieve images from the raw query, then generate text around them | Fast but risks mismatched images if the answer's actual explanatory structure diverges from the initial query |
| During generation (plan-driven) | Model emits IMAGE_SLOT objects mid-stream as it drafts each paragraph; slots dispatch to image search concurrently with continued text streaming | Best balance — matches Gemini/AI Mode fan-out pattern; images resolve in parallel with minimal added latency[^7][^2] |
| After full draft | Generate complete text, then a second pass extracts slot candidates and retrieves images | Highest matching accuracy (full context available) but adds latency since retrieval is fully serialized after generation |

Recommended approach for AREQA: emit the structured plan (paragraphs + slot placeholders) in one first LLM pass, then fire all IMAGE_SLOT retrieval calls concurrently while the text-to-speech/stream rendering of the final answer proceeds — this is functionally what Google's fan-out technique does, issuing "multiple queries about the image... in parallel" and recombining results that best match intent.[^7][^2]
## Structured Backend-to-Frontend Schema
The backend should never send raw Markdown with embedded image URLs. Instead it should stream a JSON structure similar to Gemini Enterprise's answer object, which separates `answerText`, `citations`, and `references` (including image references) into distinct arrays:[^3]

```json
{
  "answer_id": "string",
  "blocks": [
    { "type": "paragraph", "text": "string", "citation_ids": ["c1", "c2"] },
    {
      "type": "image_block",
      "slot_id": "string",
      "topic": "string",
      "purpose": "diagram | photo | portrait | chart",
      "search_query": "string",
      "image_url": "string",
      "thumbnail_url": "string",
      "source_url": "string",
      "source_domain": "string",
      "caption": "string",
      "license": "string | unknown",
      "safety_status": "pass | flagged | unavailable",
      "match_confidence": 0.0
    },
    { "type": "paragraph", "text": "string", "citation_ids": ["c3"] }
  ],
  "citations": [ { "id": "c1", "url": "string", "title": "string" } ]
}
```

This mirrors the Bing/Copilot pattern of parsing citations into "a dedicated, easy-to-use array of objects (index, URL)" rather than inlining them into the answer text, and Gemini Enterprise's rule that "citations can contain multiple images" as discrete reference objects. Key fields worth keeping non-optional: `source_url` (for attribution/click-through), `match_confidence` (drives frontend fallback logic), and `safety_status` (drives whether the block renders at all).[^1][^3]
## Selecting Image Candidates from Web/Image Search
A ranking pipeline should combine lexical, semantic, and provenance signals rather than relying on top-1 search results:

- **Query construction**: derive the `search_query` from the slot's topic + purpose, not the raw user question — e.g., for "explain Bayes' theorem," use "Bayes theorem diagram explained" not the literal question.
- **Semantic re-ranking with CLIP-style scoring**: compute a CLIPScore between the slot's caption/topic text and each candidate image (cosine similarity between text and image embeddings in a shared space) to filter out visually irrelevant but keyword-matching results.[^10][^8]
- **Source quality filtering**: prefer educational domains, Wikimedia Commons, official documentation, or textbook publishers over generic stock/social sites, similar to how multimodal RAG pipelines index provenance metadata alongside embeddings.[^11]
- **Diversity/de-duplication**: avoid returning near-identical images across multiple slots in the same answer using perceptual hashing.
- **License-aware filtering**: prioritize images with identifiable licensing (Creative Commons, public domain) and mark unknown-license images distinctly in the schema's `license` field, since AREQA will display source links directly to users.
## Verifying Image-to-Explanation Match
Treat this as a grounding verification step, not just retrieval ranking — this is the core weakness multimodal RAG research explicitly targets. The recommended verification stack:

1. **Embed-and-score**: use a CLIP-style dual encoder to embed the drafted paragraph (or slot topic) and each candidate image into the same space, then compute cosine similarity as a numeric `match_confidence`.[^10][^8]
2. **VLM secondary check**: for high-stakes or ambiguous slots, pass the top-2–3 candidates plus the paragraph text to a vision-language model and ask it to confirm/deny relevance and flag factual mismatches (e.g., wrong historical figure, wrong diagram version) — this "cross-encoder VLM" reranking step is standard in production multimodal RAG stacks.[^11]
3. **Threshold gating**: only render an image block if `match_confidence` exceeds a calibrated threshold; otherwise fall back to a text-only card (see failure modes below).
4. **Citation-image consistency**: verify the image's source domain is consistent with or complementary to the paragraph's cited sources, reducing the risk of an image implying an unsupported claim.

This layered check follows the "retrieve-then-verify" or "generate-then-ground" idea seen across MuRAG-style multimodal retrieval-augmented generation, where retrieved multimodal memory augments — but does not blindly override — the generation step.[^12][^13]
## Frontend Rendering of Image Blocks
Render image blocks as discrete cards, not inline `<img>` tags dropped into flowing prose, so provenance stays legible:

- Each image card should show: thumbnail, caption, and a visible source attribution (domain name + link), consistent with how Bing/Copilot expose citations as a distinct array rather than burying them in text.[^1]
- Clicking/tapping the card should reveal the full-size image and its `source_url`, matching the click-through pattern used in Gemini Enterprise's reference model where "citations can contain multiple images".[^3]
- Keep image cards visually distinct from generated citation chips for text claims — different card styling avoids conflating "this image illustrates the concept" with "this fact is sourced from here."
- Show `license`/safety status as a small badge when known, and omit or clearly mark cards as "unverified source" when license metadata is missing.
- Preserve streaming behavior: render the paragraph text immediately and let the image card populate asynchronously with a loading skeleton once the parallel image retrieval resolves, rather than blocking text rendering on image availability.
## Failure Modes and Fallback Strategies
| Failure mode | Fallback |
|---|---|
| No image passes match-confidence threshold | Render paragraph without an image block; do not force a low-confidence image |
| Search API returns zero/blocked results | Retry once with a rewritten, more generic search query derived from the topic; if still empty, drop the slot |
| Image license unknown or restrictive | Still show if `safety_status: pass`, but mark license as "unknown" and keep the card clickable to source only (no local re-hosting/embedding beyond a thumbnail preview) |
| VLM verification flags mismatch | Discard the candidate and try the next-ranked candidate before giving up on the slot entirely |
| Source page returns 404 / hotlinking blocked | Cache a thumbnail at retrieval time so the card still renders even if the origin later removes the image, but keep `source_url` for attribution |
| Sensitive/explicit content detected | Suppress the entire image block; do not substitute an AI-generated image without explicit user opt-in, especially given policies restricting photorealistic faces and notable individuals in generative substitutes[^14][^15] |
| Latency exceeds streaming budget | Timeout the image slot after a fixed window (e.g., 2–3s) and render text-only, with the image quietly appended later if it resolves |
## Comparable Architectures
| System | Planning mechanism | Retrieval timing | Match verification |
|---|---|---|---|
| Google AI Mode / SGE | "Visual search fan-out": query decomposed into parallel sub-queries | During generation, parallel | Recombination step selects results best matching intent[^7][c2cite:22] |
| Gemini Enterprise Answer API | Explicit `imageSource` field (`CORPUS_IMAGE_ONLY`/`ALL_AVAILABLE_SOURCES`) separate from answer text | Backend-controlled, one image max per answer, multiple in citations | Data-store-scoped retrieval limits mismatch risk[^3] |
| Gemini API Google Search grounding | Model auto-generates search queries as an explicit tool-call step | During generation | Inline `annotations`/citations tied to search results[^9] |
| Bing/Copilot | Structured citation array separate from prose | Not fully documented publicly, but citations parsed as discrete objects | Citation-object structure implies backend-side verification before exposure[^1] |
| Multimodal RAG (CLIP + VLM rerank) | Query decoupling into structured retrieval requests | Before/during generation | CLIPScore + cross-encoder VLM reranking[^8][^11] |
| MuRAG | Non-parametric multimodal memory retrieval via MIPS | Before generation (retrieval-augmented) | Retrieved evidence conditions generation directly[^13] |

All of these converge on the same principle relevant to AREQA: **separate the "what to show" decision (structured plan) from the "how to get it" mechanism (retrieval), and verify relevance before exposing anything to the user** — never let free-text generation directly emit final image URLs.
## Implementation Checklist for AREQA
- Define an `IMAGE_SLOT(topic, purpose, search_query)` object in the LLM's structured output schema (e.g., via function-calling / JSON mode) instead of relying on Markdown image syntax in free text.
- Modify the answer-planning prompt so the model interleaves paragraph blocks and image-slot blocks in a single structured plan before/while streaming.
- Build an async image-retrieval microservice that takes a slot's `search_query`, queries an image search API, and returns top-N candidates with metadata (url, source domain, license if available).
- Add a CLIP-based (or equivalent) re-ranking step scoring candidates against the slot's topic/paragraph text.
- Add an optional VLM verification pass for low-confidence or high-stakes slots before finalizing a `match_confidence`.
- Extend the existing citation JSON schema with an `image_block` type carrying `image_url`, `thumbnail_url`, `source_url`, `caption`, `license`, `safety_status`, `match_confidence`.
- Implement threshold-based gating in the backend so only sufficiently confident image blocks reach the frontend payload.
- Update the frontend renderer to display image cards as distinct components (thumbnail + caption + source link + license badge) separate from text-citation chips, with async population and loading skeletons.
- Implement retry/rewrite logic for empty search results and a hard timeout to avoid blocking the text stream.
- Add explicit content-safety filtering and a policy to never substitute an unverified image with a generated one without clear labeling and opt-in, consistent with SGE's photorealistic-face and notable-person restrictions.[^14][^15]
- Log slot-level outcomes (found/rejected/timeout) to tune ranking thresholds over time.

---

## References

1. [Bing AI Search (Copilot) Answers](https://apify.com/practicaltools/bing-ai-copilot) - Structured Citations: Parses source citations into a dedicated, easy-to-use array of objects (index,...

2. [AI Mode Knows When You Want Images Instead Of Text, And It ...](https://www.bgr.com/1982477/google-ai-mode-visual-search/) - Google's new AI Mode update lets you perform visual searches in Google Search, as Gemini will know w...

3. [Get answers and follow-ups (Legacy) | Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/answer)

4. [Google AI - X](https://x.com/GoogleAI/status/1973073164210151739)

5. [Google's AI Mode search can now answer questions about images](https://arstechnica.com/gadgets/2025/04/googles-ai-mode-search-can-now-answer-questions-about-images/) - Google's AI Mode can now understand images as part of your searches.

6. [Google’s AI Mode can now see and search with images](https://www.theverge.com/news/644363/google-search-ai-mode-multimodal-lens-image-recognition) - It’s like Google Search, Lens, and Gemini had a baby.

7. [Google adds eyes to AI Mode with new visual search features](https://www.techradar.com/ai-platforms-assistants/gemini/google-adds-eyes-to-ai-mode-with-new-visual-search-features) - Like a conversational Pinterest with some online shopping thrown in

8. [A Comprehensive Survey on Multimodal Retrieval- ...](https://openreview.net/pdf/371ce5eb217f4167e792883aeb958c38b5400e5c.pdf)

9. [Grounding with Google Search | Gemini API | Google AI for Developers](https://ai.google.dev/gemini-api/docs/google-search) - Ground your model's responses in real-time information from Google Search to improve factual accurac...

10. [CLIP embeddings to improve multimodal RAG with GPT-4 ...](https://developers.openai.com/cookbook/examples/custom_image_embedding_search) - Multimodal RAG integrates additional modalities into traditional text-based RAG, enhancing LLMs' que...

11. [A Practical Guide to Multi‑Modal RAG: Images Plus Text, End‑to‑End ...](https://asoasis.tech/articles/2026-04-11-0853-multi-modal-rag-images-text-tutorial/) - Build a practical multi‑modal RAG system that retrieves from images and text using OCR, captions, CL...

12. [RAG Series, Part 4: Multi-Modal RAG — Retrieval with Text ...](https://medium.com/@renswick.d/rag-series-part-4-multi-modal-rag-retrieval-with-text-images-using-clip-gpt-4-1-fdbb2b3e5467) - In the first three parts of this series, we explored the foundational and agentic aspects of Retriev...

13. [MuRAG: Multimodal Retrieval-Augmented Generator for ...](https://aclanthology.org/2022.emnlp-main.375.pdf)

14. [Google’s AI-powered search experience can now generate images](https://www.theverge.com/2023/10/12/23913337/google-ai-powered-search-sge-images-written-drafts) - What horrors await?

15. [Google is rolling out AI image generator to Search Generative Experience](https://gadgetsnow.indiatimes.com/tech-news/google-is-rolling-out-ai-image-generator-to-search-generative-experience/articleshow/104731108.cms) - Google has introduced an AI image generator and text generation feature in its Search Generative Exp...

