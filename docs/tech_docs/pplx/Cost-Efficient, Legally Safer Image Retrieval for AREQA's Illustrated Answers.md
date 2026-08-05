## Recommendation Summary
A three-tier hybrid retrieval strategy — Wikimedia Commons/Openverse first, a paid general image-search API second, og:image extraction last — combined with cheap heuristic ranking and selective CLIP/VLM verification, delivers the best balance of success rate, cost, legal safety, and cache-ability for AREQA's `image_block` schema. The critical architectural decision is to decouple "find candidates" (cheap, cacheable, provider-agnostic) from "verify match" (expensive, invoked only when heuristics disagree), rather than running multimodal reranking on every request.
## 1–2. Provider Comparison and Recommendation
Provider economics differ sharply, and licensing terms diverge just as much, which matters as much as raw cost for an educational product exposing `sourceUrl` and `license` fields to users.

| Provider | Cost | License clarity | Fit for AREQA |
|---|---|---|---|
| Wikimedia Commons / Wikidata | Free, no rate-limited paid tier | Explicit `extmetadata.UsageTerms`/CC0/PD per file via `imageinfo` API[^1][^2][^3] | Best default for factual, historical, scientific, biographical topics — matches AREQA's classical-literature and educational focus |
| Openverse | Free API, optional OAuth token only raises rate limits[^4][^5] | Aggregates CC0/BY/BY-SA/PDM across 800M+ works from Flickr, Smithsonian, NASA, Europeana, etc., with license filter built into the query[^6][^4][^5] | Excellent second open-source tier — much broader coverage than Commons alone, still fully attributable |
| Google Custom Search JSON API (image mode) | 100 free/day; $5 per 1,000 queries beyond that, capped at 10k/day; being discontinued for new customers Jan 2027[^7][^8][^9] | No license metadata returned; results are general web images of unknown rights status | Usable as paid fallback today, but sunset risk makes it a poor long-term bet for a new product |
| Bing Image Search (Azure) | Free tier ~1,000 transactions/month; paid tiers roughly $7–$25 per 1,000 transactions depending on plan (S1/S3/S7 tiers bundle image search)[^10][^11][^12] | No structured license field; same general-web-rights ambiguity as Google | Reasonable paid general-search fallback with clearer transactional pricing than Google's tiered model |
| SerpAPI (Google Images via SERP scraping) | Free 250 searches/month; $25/month for 1,000, $75/month for 5,000[^13][^14] | Inherits whatever rights info the underlying Google result exposes (usually none) | Convenient developer experience but materially more expensive per-query than Bing/Google direct APIs at low volume |
| DataForSEO Google Images SERP API | $0.0006–$0.002 per SERP page depending on turnaround priority (~$600–$2,000 per 1M)[^15][^16] | Same as above — no license metadata | Cheapest general-image-search-via-scraping option at scale; good backend fallback if cost is the binding constraint |
| Brave Search API / Tavily / Exa | Not surfaced with public image-search pricing in this research pass; Tavily and Exa are primarily text/web-content retrieval APIs, not image-search specialized | N/A | Not recommended as a primary image source; better suited to the existing text `web_search` tool AREQA already has |

For a small team building an educational assistant, Wikimedia Commons + Openverse should be the primary path, not a "nice-to-have," because they are simultaneously the cheapest, most legally documented, and most topically aligned with textbook/encyclopedic explanations. A single paid general-search API (Bing Image Search is recommended over Google CSE given Google's stated Jan 2027 sunset for new customers) should be reserved for the residual queries — pop-culture references, brand-name products, or very recent events — that open datasets don't cover.[^7][^10]
## 3. Hybrid Retrieval Pipeline
A staged fallback chain minimizes cost while maximizing both hit rate and legal safety:

1. **Tier 1 — Open educational sources**: query Wikimedia Commons search API and Openverse (filtered to `cc0,by,by-sa,pdm`) using the slot's `topic`/`search_query`. Both return explicit license metadata per result, which populates the schema's `license` field with confidence rather than "unknown".[^1][^4][^5]
2. **Tier 2 — Paid general image search**: if Tier 1 returns zero or low-relevance candidates, fall back to Bing Image Search (or DataForSEO at scale) for a broader web image pool, explicitly marking `license: "unknown"` on results.
3. **Tier 3 — og:image extraction**: keep the existing og:image/twitter:image scraper as the last-resort fallback only for slots where both prior tiers fail, since it is the least reliable and carries no license signal at all.

This ordering means most educational explanations — the bulk of AREQA's actual traffic given its classical-literature and STEM tutoring use cases — get resolved for free with clean attribution, and paid API calls are only spent on the harder residual queries.
## 4. Metadata to Store per Candidate
Store enough per candidate to support ranking, caching, and later re-verification without re-querying the provider:

- `provider` (wikimedia / openverse / bing / og_image)
- `image_url`, `thumbnail_url`, `source_url`, `source_domain`
- `title`/`alt_text`/`caption_raw` (from provider metadata or og:title)
- `license`, `license_url`, `attribution_string`, `creator` (from Openverse/Commons `extmetadata`/`creator` fields)[^1][^4]
- `width`, `height`, `filesize`, `filetype`
- `retrieved_at`, `query_used` (the exact search string that returned this candidate)
- `heuristic_score` (from cheap ranking, see below) and, if computed, `match_confidence` from a later CLIP/VLM pass
- `cache_key` (normalized slot query + provider) for the caching layer
## 5. Cheap Ranking Without CLIP/VLM
Most candidates can be ranked well using signals that cost nothing beyond the initial API call:

- **Lexical overlap**: score title/alt-text/caption token overlap against the slot's `topic` and `purpose` using simple TF-IDF or fuzzy string matching — cheap and surprisingly effective for encyclopedic image metadata.
- **Source authority tier**: hard-rank Wikimedia/Openverse/museum-and-institution domains above generic stock or social domains, since provenance quality correlates strongly with educational relevance.
- **Aspect ratio / resolution filters**: discard thumbnails below a minimum resolution or with extreme aspect ratios unsuitable for a caption card.
- **Purpose-based heuristics**: if `purpose == "diagram"`, prefer filenames/alt-text containing "diagram," "chart," "schematic"; if `purpose == "portrait"`, prefer results tagged as photographs of a named person from a biographical source.
- **Negative filtering**: exclude known low-relevance patterns (logos, icons, watermarked stock previews, generic placeholder images) via filename/domain blocklists.

This composite heuristic score should be sufficient to auto-approve high-confidence matches (e.g., Wikimedia result with strong lexical overlap and correct purpose tag) without ever invoking a model.
## 6. When to Use CLIP or VLM Verification
Reserve embedding-based or VLM verification for the ambiguous middle band, not every request:

- Trigger CLIP-based cosine similarity scoring only when the heuristic score falls in an uncertain range (e.g., no result clears a high-confidence threshold, or top-2 candidates are close in score) — this keeps the expensive path to a minority of slots.
- Trigger a full VLM verification pass (image + paragraph text passed to a vision-capable model) only for a further-narrowed subset: slots flagged `purpose: "portrait"` or `"historical-figure"` where a wrong-person mismatch would be a serious factual error, or slots where CLIP similarity itself is borderline.
- Cache the verification result alongside the candidate so a repeated slot query never re-pays the VLM cost.
- This two-tier gating (heuristics → CLIP-only-if-ambiguous → VLM-only-if-still-ambiguous-and-high-stakes) mirrors the general design principle from multimodal RAG literature of applying cross-encoder/VLM reranking only after a cheaper retrieval stage narrows the candidate pool, rather than scoring every candidate with the expensive model.[^17][^18]
## 7. Caching by Visual Slot Query
Cache at the level of the normalized `(topic, purpose, search_query)` tuple, not the raw user question, since many different user questions will generate the same underlying visual need (e.g., "explain photosynthesis" and "how do plants make energy" should hit the same cached slot for a chloroplast diagram):

- Use a normalized, lowercased, stop-word-stripped version of `search_query` plus `purpose` as the cache key.
- Cache the full resolved `image_block` (including chosen candidate, license, caption, and any CLIP/VLM confidence score) with a TTL — long TTL (weeks/months) for stable educational topics, shorter TTL for anything time-sensitive.
- Cache negative results too ("no good image found for this slot") to avoid repeatedly re-querying paid APIs for topics that reliably fail.
- Because Wikimedia/Openverse are free, only paid-tier (Bing/DataForSEO) and any VLM calls need aggressive caching to control cost — but caching all tiers uniformly simplifies the implementation and improves latency across the board.
## 8. Avoiding Misleading or Mismatched Images
Layer defenses so a single ranking mistake cannot reach the user as a confident-looking illustration:

- Never auto-render a candidate below the heuristic/CLIP confidence threshold; drop the image block instead of showing a weak guess.
- For `purpose: "portrait"` or named-entity slots, require an exact or near-exact name match in the source metadata/title before rendering — a diagram mismatch is embarrassing, but a wrong-person portrait is a factual error.
- Surface `match_confidence` internally to logging/analytics even when not shown to the user, so weak matches can be audited and heuristics retuned over time.
- Prefer "no image" over "plausible-looking but unverified image" as the default failure mode, consistent with the broader illustrated-answers architecture principle of gating on confidence rather than forcing a visual into every slot.
## 9. UI Attribution and Licensing Practices
- Always render `sourceDomain` and a clickable link to `sourceUrl` directly on the image card, not buried in a tooltip — this is standard practice for citation-style attribution in AI answer UIs.[^19][^20]
- Display `attribution_string`/`creator` when available (Wikimedia/Openverse both return this field explicitly), since CC-BY and CC-BY-SA licenses require attribution to remain compliant.[^1][^4]
- Add a visible license badge (e.g., "CC BY-SA," "Public Domain," "Unknown source") so users can distinguish freely reusable Commons/Openverse images from unknown-rights web images pulled via the paid-search or og:image fallback tiers.
- For `license: "unknown"` results (typical of Bing/Google/og:image fallback), keep the card thumbnail-only with a clear source link rather than implying reuse rights — this keeps AREQA's own liability exposure low while still crediting the source.
- Never strip or reformat the original attribution text required by CC-BY/BY-SA licenses when displaying Wikimedia/Openverse-sourced images.
## 10. Implementation Path for a Small Team
A staged rollout keeps engineering cost low while improving hit rate incrementally:

1. **Phase 1 (days)**: implement Wikimedia Commons + Openverse clients returning normalized candidate objects with license metadata; wire into the existing `image_block` schema; keep the current og:image scraper as the only fallback.
2. **Phase 2 (1–2 weeks)**: add the heuristic ranking layer (lexical overlap, source-authority tiering, purpose-based filters) and the slot-level cache (key = normalized topic+purpose+query) with negative-result caching.
3. **Phase 3 (1–2 weeks)**: add one paid general-image-search fallback (Bing Image Search recommended over Google CSE given its sunset timeline) gated strictly behind Tier 1 failure, with a hard monthly budget cap and per-request logging.[^7][^10]
4. **Phase 4 (as needed)**: introduce CLIP similarity scoring only for the ambiguous-confidence band identified from Phase 2/3 production logs; add VLM verification only for the narrower named-entity/portrait subset if error audits show it's needed.
5. **Ongoing**: monitor cache hit rate, per-tier success rate, and paid-API spend; retune heuristic thresholds and blocklists based on logged low-confidence and rejected slots rather than guessing upfront.

This path defers the most expensive component (VLM verification) until real usage data justifies it, keeps legal risk low by defaulting to explicitly licensed sources, and reuses the existing `image_block`/citation schema without structural changes.

---

## References

1. [Retrieving image license and author information in wiki commons](https://stackoverflow.com/questions/7453654/retrieving-image-license-and-author-information-in-wiki-commons) - I am trying to use the wikimedia API for wiki commons at: http://commons.wikimedia.org/w/api.php It ...

2. [API:Licensing - MediaWiki](https://www.mediawiki.org/wiki/API:Licensing)

3. [Wikimedia API Reference — 35 Endpoints | openapi.city](https://openapi.city/providers/wikimedia) - Wikimedia API reference with 35 endpoints. Wikipedia and Wikimedia projects API

4. [Openverse API](https://api.openverse.org/v1/)

5. [Openverse API (Creative Commons Catalog) | Jentic](https://jentic.com/apis/api.openverse.org/openverse)

6. [Openverse API — Documentation, OpenAPI](https://apis.io/apis/openverse/openverse-api/) - Openverse API is published by Openverse on the APIs.io network, described by a machine-readable Open...

7. [Custom Search JSON API | Google for Developers](https://developers.google.com/custom-search/v1/overview) - Custom Search JSON API provides 100 search queries per day for free. If you need more, you may sign ...

8. [Google Image Search API: Pricing Guide](https://ccgit.crown.edu/cyber-reels/google-image-search-api-pricing-guide-1764802123) - Google Image Search API: Pricing Guide Hey everyone! Let’s dive into the nitty-gritty of the Google ...

9. [Overview | Programmable Search Engine](https://developers.google.com/custom-search/docs/overview) - Read an overview of Programmable Search Engine, which lets you create a search engine for your websi...

10. [Pricing - Bing Search API - Bing Entity Search](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/bing-entity-search-api/) - With Bing Search APIs, pay only for what you use. View and compare pricing options for Bing Entity S...

11. [Bing Images API 2025: I Turned Boring Project into Goldmine](https://freerdps.com/blog/bing-images-api/) - Discover the power of the Bing Images API! Learn my secrets to transforming a mundane project into a...

12. [Bing Search API Pricing | Microsoft Bing](https://www.microsoft.com/en-us/bing/apis/pricing?msockid=020902aac9ed66f732401727c8d567e8) - Compare Bing API pricing to find the right fit to suit your needs. Our API pricing options allow you...

13. [Pricing](https://serpapi.com/pricing) - Choose your plan. Month to month contract. Cancel anytime. SerpApi provides simple pricing to suit y...

14. [7 Best Google Image API Providers in 2026 Guide](https://www.serphouse.com/blog/best-google-image-api-providers/) - Compare Google Image API Providers by pricing speed reliability location targeting and image search ...

15. [Google Images SERP API - DataForSEO](https://dataforseo.com/pricing/serp/google-images-serp-api) - The cost of DataForSEO SERP API varies based on the method and priority of a set task. In addition t...

16. [Google Images SERP API by DataForSEO](https://dataforseo.com/apis/serp-api/google-images-api) - Scrape data from Google Image search using API and collect results in JSON. Track image rankings or ...

17. [A Comprehensive Survey on Multimodal Retrieval- ...](https://openreview.net/pdf/371ce5eb217f4167e792883aeb958c38b5400e5c.pdf)

18. [A Practical Guide to Multi‑Modal RAG: Images Plus Text, End‑to‑End ...](https://asoasis.tech/articles/2026-04-11-0853-multi-modal-rag-images-text-tutorial/) - Build a practical multi‑modal RAG system that retrieves from images and text using OCR, captions, CL...

19. [Bing AI Search (Copilot) Answers](https://apify.com/practicaltools/bing-ai-copilot) - Structured Citations: Parses source citations into a dedicated, easy-to-use array of objects (index,...

20. [Get answers and follow-ups (Legacy) | Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/answer)

