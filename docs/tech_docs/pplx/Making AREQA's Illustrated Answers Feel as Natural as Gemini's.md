## Why Gemini's Illustrated Answers Feel Natural
The gap between AREQA's current image card and Gemini's illustrated answer is not primarily a retrieval-quality gap — it is an integration gap across five dimensions: selection criteria, placement logic, captioning depth, viewer UX, and attribution polish. Google's own visual-search architecture treats image relevance as a fan-out and recombination problem, issuing multiple parallel sub-queries and selecting results that "best match intent," not just keyword overlap. Bing/Copilot and Gemini Enterprise both keep image and citation metadata as structured objects distinct from the prose flow, which is what allows their frontends to render clean, non-clunky attribution. AREQA already has the retrieval and schema; what's missing is (1) an instructional-value layer on top of keyword ranking, (2) a placement/explanation contract between the LLM and the image pipeline, and (3) a lightbox-based frontend instead of link-out image cards.[^1][^2][^3][^4]
## 1. Image Retrieval: From Keyword Match to Pedagogical Match
### Query rewriting for educational images
Rewrite the visual query in two stages instead of one. First, extract the *concept* and *diagram type* the paragraph is teaching (e.g., "meta-analysis" → "forest plot," "photosynthesis" → "chloroplast light reaction diagram") using the LLM's own paragraph draft, not the user's raw question — for a bilingual product like AREQA, generate the query rewrite in English regardless of the source-language question (統合分析 → "forest plot diagram"), since Wikimedia/Openverse coverage and captioning quality are strongest in English. Second, append a "canonical diagram" qualifier (diagram, labeled, annotated, schematic) when `purpose` is diagram/chart, since forest plots, chloroplast diagrams, and similar teaching visuals are reliably tagged this way on Wikimedia Commons and in academic sources.[^5][^6]
### Choosing pedagogically useful images, not just keyword matches
Instructional value is a distinct axis from topical relevance. A forest plot image that is annotated with labeled axes, legend, and diamond/box elements teaches more than a bare, unlabeled chart pulled from a random paper — Gemini's apparent preference for "images that directly support explanation" reflects ranking on these visual-pedagogy signals, not just caption-text similarity. Concretely, score candidates on:[^7][^8][^5]

- **Label density**: does the image contain visible axis labels, legends, or annotations (approximable via alt-text/caption mentioning "labeled," "annotated," or via a lightweight OCR/text-detection pass on the image)
- **Canonical-source bonus**: images from textbook publishers, Cochrane/Wikipedia's own forest-plot exemplar (`en.wikipedia.org/wiki/Forest_plot`), or university teaching guides outrank random paper figures[^9][^5]
- **Complexity match**: prefer a simpler illustrative diagram for an intro-level explanation over a dense real-study figure with dozens of rows, unless the paragraph explicitly discusses a specific study
- **Caption informativeness**: candidates whose existing caption/alt-text already explains what the visual elements mean (e.g., "diamond represents pooled effect") should rank above visually similar but uncaptioned images, since that caption text can be reused/adapted for the in-app explanation
### Provider mix (unchanged core, refined weighting)
Keep the existing Wikimedia Commons → Openverse → og:image hybrid, but re-weight Wikimedia's own canonical topic pages (like the Forest Plot Wikipedia article's lead image) higher than generic Commons search results, since canonical article images are curated specifically for explanatory clarity. Only fall through to Bing/Google paid search when the topic has no strong open-education presence.[^5]
## 2. Image Placement: Slot Planning, Not Post-Hoc Insertion
### Structured visual slot schema
The answer planner should emit visual slots as first-class structured objects during the planning pass, before final prose is finalized:

```json
{
  "slot_id": "vs_1",
  "topic": "forest plot",
  "purpose": "diagram",
  "explanation_goal": "show how individual study effects and the pooled diamond are visually combined",
  "placement_after_paragraph": 2,
  "visual_query": "forest plot diagram meta-analysis labeled",
  "expected_elements": ["study rows", "confidence interval lines", "pooled diamond", "line of no effect"]
}
```

The `explanation_goal` and `expected_elements` fields are the key upgrade over a bare `IMAGE_SLOT(topic, purpose, search_query)`: they let the caption/explanation generator later verify the retrieved image actually contains what the paragraph is about to describe, and they let the ranker score candidates against *what the image needs to show*, not just what it needs to be *about*.
### Placement logic
- Only insert a slot immediately after the paragraph that introduces the concept the image supports — never before, since the reader needs context before the image is useful.
- Cap slot density: one image per 2–4 paragraphs on a single sub-topic; avoid clustering multiple images on the same concept.
- If the answer plan doesn't naturally build to a paragraph that "needs" a visual (e.g., a purely definitional one-liner), skip the slot rather than forcing one — awkward placement usually stems from inserting a slot the content doesn't structurally support.
- Validate placement against paragraph boundaries at render time: `placement_after_paragraph` should reference the *final* paragraph index after any mid-generation edits, requiring the planner to finalize paragraph structure before or alongside slot emission (a single planning pass covering both, rather than two independently timed passes).
## 3. Image Explanation: Hybrid Metadata + Generated Caption
### Caption sourcing strategy
Use both sources, but for different purposes — a two-caption pattern:

- **Attribution caption** (short, factual): sourced from the image's own metadata (Wikimedia `ImageDescription`/title, Openverse title) — this is what appears directly under/beside the image as its formal caption, tying to the license/source card.
- **Explanatory caption** (pedagogical): generated by the LLM using the slot's `explanation_goal` and `expected_elements`, written to explicitly reference visible parts of the image (e.g., "Each horizontal line represents one study; the diamond at the bottom is the pooled result across all studies"). This is the sentence immediately before/after the image in the answer flow — exactly the "tight explanation" AREQA is currently missing.[^7][^8][^5]
### Explaining diagrams like forest plots
For diagram-purpose slots, prompt the explanation generator with the `expected_elements` list and require it to map each visible element to its meaning in one or two sentences, mirroring how domain guides describe forest plots element-by-element (study rows → point estimate boxes → confidence-interval whiskers → pooled diamond → line of no effect). This produces text like: "Each row is one included study, with the square showing its effect size and the horizontal line its confidence interval; the diamond at the bottom shows the combined result of the meta-analysis," which reads exactly like the explanatory pattern used in teaching guides for this figure type.[^7][^8][^5][^6]
## 4. UI/UX: Lightbox, Not Link-Out Card
### Inline rendering pattern
Render the image inline at a moderate size (not a small thumbnail card) directly within the answer flow, immediately preceded and followed by the explanatory text — this contiguous text-image-text flow is a major contributor to Gemini's "natural" feel versus a separated card. Keep the card visually light: image, one-line caption, and a minimal attribution strip (small text, not a bordered box).
### In-app lightbox instead of external link
Replace "click opens the source website" with an in-app enlarged viewer: clicking opens a modal/lightbox showing the full-resolution image, its full caption, and the source/license info as an overlay panel — the source link becomes a secondary "View source" action inside the lightbox, not the default click behavior. This is standard practice in modern React/Next.js image galleries, typically implemented with a lightbox library (e.g., `lightGallery`, `yet-another-react-lightbox`, or a custom Radix/Headless UI dialog) supporting pinch-zoom, keyboard navigation, and a caption/attribution overlay.[^10]
### Attribution without visual heaviness
- Default state: small caption line + tiny source-domain text (e.g., "commons.wikimedia.org") with a small license badge icon — no large boxed "citation card."
- Expanded state (in lightbox only): full attribution string, creator name, license name and link, and "View original source" button.
- This two-tier disclosure (light inline, full detail on demand) is how Bing/Copilot's citation objects are described — parsed into a structured array but rendered progressively rather than dumped inline.[^1]
### How Gemini's presentation differs from a simple image card
The differences are less about the image itself and more about integration: image sits inline in reading flow (not sidebar/card), explanatory text directly frames it, clicking enlarges in-place rather than navigating away, and attribution is minimized until requested — all of which are UI/orchestration decisions AREQA can adopt without needing better retrieval.
## 5. Safety/Legal Handling
- **Wikimedia/Openverse**: always display the license name (e.g., "CC BY-SA 4.0") and creator/attribution string sourced directly from `extmetadata`/Openverse metadata; link the license name to its canonical license page.[^11][^12]
- **CC-BY / CC-BY-SA display**: attribution text must remain visible and unmodified per license terms — show it in the lightbox's expanded panel at minimum, and ideally as small text under the inline image too, since BY/BY-SA require attribution wherever the work is displayed.
- **Unknown-license images (Google/Bing/og:image)**: mark clearly as "Source: [domain] · License: unknown" and avoid implying reuse rights; keep these images functioning purely as illustrative aids with a visible source link rather than a license badge, consistent with treating them as lower-trust fallback content.
- **Fallback tiering should be visible in the UI**, not just internal: a Wikimedia-sourced image can show a green "Open license" indicator, while an og:image fallback shows a neutral "Source only" indicator, giving users an honest signal about reuse rights.
## 6. End-to-End System Design
### Pipeline
```
User question
  → Answer planner (LLM): drafts paragraph plan + visual slot list
      { paragraphs[], visual_slots[] with topic/purpose/explanation_goal/expected_elements/placement }
  → Visual query rewriter: slot.topic + slot.purpose → optimized English visual_query
  → Candidate retrieval (parallel per slot):
        Tier 1: Wikimedia Commons + Openverse
        Tier 2: Bing/Google paid image search (fallback)
        Tier 3: og:image extraction (last resort)
  → Ranking: lexical + source-authority + pedagogical-value heuristics
      (label density, canonical-source bonus, complexity match, caption informativeness)
  → [Ambiguous cases only] CLIP similarity → VLM verification against expected_elements
  → Explanation generator: attribution_caption (from metadata) + explanatory_caption (from LLM, using expected_elements)
  → Image block assembly → Redis cache write (key: normalized topic+purpose+visual_query)
  → Frontend rendering: inline image + explanatory text + lightbox on click
```
### Data schemas
**Visual slot (planner output):**

```json
{
  "slot_id": "string",
  "topic": "string",
  "purpose": "diagram | photo | portrait | chart",
  "explanation_goal": "string",
  "expected_elements": ["string"],
  "placement_after_paragraph": 0,
  "visual_query": "string"
}
```

**Final image block (rendered to frontend, extending AREQA's existing schema):**

```json
{
  "type": "image_block",
  "slot_id": "string",
  "imageUrl": "string",
  "thumbnailUrl": "string",
  "sourceUrl": "string",
  "sourceDomain": "string",
  "attributionCaption": "string",
  "explanatoryCaption": "string",
  "license": "string | unknown",
  "licenseUrl": "string | null",
  "creator": "string | null",
  "safetyStatus": "pass | flagged | unavailable",
  "matchConfidence": 0.0,
  "pedagogicalScore": 0.0,
  "tier": "wikimedia | openverse | paid_search | og_image"
}
```
### Logging/debug signals
Log per-slot: `visual_query` used, all candidates considered with their heuristic/pedagogical scores, the chosen candidate's `tier` and `matchConfidence`/`pedagogicalScore`, whether CLIP/VLM verification was triggered and its result, cache hit/miss, and final render outcome (shown / dropped / fallback-to-og-image). This lets the team audit why a "meta-analysis" query surfaced a mediocre Commons image versus a better one, and retune the pedagogical-scoring heuristics from real data rather than guesswork.
### MVP vs. advanced roadmap (FastAPI + React/Next.js + Redis + Supabase)
**Low-cost MVP (1–2 weeks):**
- Add `explanation_goal`/`expected_elements` fields to the existing visual-slot LLM output.
- Add a pedagogical-scoring heuristic layer (label-density keyword check, canonical-source domain list, caption-length/informativeness score) on top of existing lexical ranking — no new API calls needed.
- Generate the two-caption pattern (metadata attribution + LLM explanatory caption using `expected_elements`) in the existing answer-generation call.
- Build a React/Next.js lightbox component (e.g., wrapping `yet-another-react-lightbox` or a Radix Dialog) replacing the current link-out click behavior; store full-res image references and Supabase-cached thumbnails for fast lightbox load.
- Redesign the inline card to be visually light (small caption + tiny source/license line), moving full attribution into the lightbox.

**Advanced follow-up:**
- Add CLIP similarity scoring gated to ambiguous heuristic-score cases, verifying candidate images against `expected_elements` text.
- Add VLM verification for portrait/named-entity slots and any diagram slot where CLIP confidence is borderline.
- Expand Redis caching to store full ranked candidate lists (not just the winner) per normalized slot key, enabling instant re-ranking if pedagogical-scoring weights change without re-querying providers.
- Build an internal review dashboard from the logging signals to continuously tune pedagogical-scoring weights per subject domain (STEM diagrams vs. historical photographs vs. literary portraits — relevant given AREQA's classical-literature focus).

---

## References

1. [Bing AI Search (Copilot) Answers](https://apify.com/practicaltools/bing-ai-copilot) - Structured Citations: Parses source citations into a dedicated, easy-to-use array of objects (index,...

2. [Google adds eyes to AI Mode with new visual search features](https://www.techradar.com/ai-platforms-assistants/gemini/google-adds-eyes-to-ai-mode-with-new-visual-search-features) - Like a conversational Pinterest with some online shopping thrown in

3. [AI Mode Knows When You Want Images Instead Of Text, And It ...](https://www.bgr.com/1982477/google-ai-mode-visual-search/) - Google's new AI Mode update lets you perform visual searches in Google Search, as Gemini will know w...

4. [Get answers and follow-ups (Legacy) | Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs/answer)

5. [Forest plot](https://en.wikipedia.org/wiki/Forest_plot) - A forest plot, also known as a blobbogram, is a graphical display of estimated results from a number...

6. [Meta-analysis - interpretation of forest plots: A wood for the trees](https://pmc.ncbi.nlm.nih.gov/articles/PMC11878362/) - A forest plot is a graphical tool to visualise and interpret the summary of estimated results in a m...

7. [How to Interpret a Meta-Analysis Forest Plot - PMC - NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC8119923/) - by JR Dettori · 2021 · Cited by 148 — A forest plot is a useful graphical display of findings from a...

8. [How to Read a Forest Plot](https://metricgate.com/blogs/reading-a-forest-plot/) - Learn to read a forest plot in meta-analysis: decode each study's effect size and CI, the diamond po...

9. [Forest Plots - Statistics - explanations and formulas](https://libguides.und.edu/c.php?g=1333878&p=10080492) - Research Guides: Statistics - explanations and formulas: Forest Plots

10. [Step 2: Create the Masonry...](https://www.fullstackfoundations.com/blog/nextjs-masonry-image-gallery-lightbox) - Build a masonry layout of images that are clickable and open into a beautiful lightbox with the Next...

11. [Retrieving image license and author information in wiki commons](https://stackoverflow.com/questions/7453654/retrieving-image-license-and-author-information-in-wiki-commons) - I am trying to use the wikimedia API for wiki commons at: http://commons.wikimedia.org/w/api.php It ...

12. [Openverse API](https://api.openverse.org/v1/)

