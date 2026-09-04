# AREQA Backend Service Split Construction Plan

This plan modularizes the long backend files identified by the user while preserving existing runtime behavior and import compatibility. The phase order starts with type/model extraction and the largest visual service, then moves through PDF/paper visual planning, query policy, memory/GUM boundaries, and finally orchestration. This sequence keeps each intermediate commit buildable, gives high-risk public contracts a compatibility layer, and lets focused tests prove that moved code still behaves the same before the next layer depends on it.

Confirmed line-count targets at planning time:

```text
backend/gum_integration.py                         1221
backend/memory_store.py                             903
backend/services/memory_ingestion_service.py        864
backend/services/orchestration_service.py          1693
backend/services/paper_visual_planner_service.py    823
backend/services/pdf_visual_extraction_service.py  1098
backend/services/query_policy_service.py            915
backend/services/visual_answer_service.py          3015
```

The target state is that no single production Python file in this requested group remains above 600 lines unless a phase explicitly documents an unavoidable residual risk and a follow-up split. Existing public imports such as `from services.visual_answer_service import ImageBlock, VisualAnswerService`, `from memory_store import MemoryStore`, and `from gum_integration import run_reflection` must continue to work during and after the refactor.

### Phase 1: Extract Visual Answer Models, Cache, and Layout

#### Problem

`backend/services/visual_answer_service.py` currently owns dataclasses, cache serialization, safety checks, layout helpers, provider calls, scoring, and orchestration in one 3015-line file. Tests and callers import both public service APIs and several static/private helpers from the service class, so a naive split would break compatibility even if behavior remains unchanged. The target state is a smaller service facade with moved model/cache/layout code and compatibility aliases for existing imports and static method usage.

#### Assumptions

`ImageBlock`, `ImageCandidate`, `PlannedImageSlot`, and `VisualPreflightDecision` are data contracts used outside the service and must remain importable from `backend.services.visual_answer_service`. Existing tests may patch or call `VisualAnswerService._cache_key()`, `_image_block_from_frontend()`, `_interleave_blocks()`, and related helpers, so this phase must preserve those attributes as forwarding static/class methods. If this assumption is false and downstream code imports the new modules directly only after refactor, the compatibility layer is still harmless but can be removed in a later cleanup.

#### Solution

Move visual dataclasses into a model module, move cache key/serialization helpers into a cache module, and move paragraph/interleave helpers into a layout module. Keep `VisualAnswerService` as the behavior facade and re-export the model classes from `visual_answer_service.py`. This phase intentionally avoids moving provider HTTP code or candidate scoring so the first commit has a narrow blast radius and proves the compatibility approach.

#### Implementation

> Context: Add Google-style docstrings to every new public module and public helper class/function introduced in this phase. Document why the facade re-exports symbols, which frontend/cache fields are compatibility contracts, and which helpers must not include raw user text in logs. Inline comments are allowed only around non-obvious compatibility forwarding and cache safety invariants; do not comment simple assignments or moved control flow.

Add `backend/services/visual_answer_models.py` with the four dataclasses currently defined in `visual_answer_service.py`. Preserve field names, defaults, slots/frozen settings, `ImageBlock.to_frontend()`, and metadata semantics exactly. Add `backend/services/visual_answer_cache.py` for cache constants, cache key generation, cache payload validation, frontend payload restoration, safe string coercion, and optional integer parsing. Add `backend/services/visual_answer_layout.py` for paragraph splitting and block interleaving. Update `visual_answer_service.py` to import these modules, keep the existing class-level helper names as forwarding methods, and remove the moved definitions from the original file.

#### Expected File Tree After Phase 1

This tree is cumulative for Phase 1 only.

```text
backend/
└── services/
    ├── visual_answer_cache.py          [new]
    ├── visual_answer_layout.py         [new]
    ├── visual_answer_models.py         [new]
    └── visual_answer_service.py        [modified]
tests/
└── backend/
    └── test_visual_answer_service.py   [modified]
```

#### Work List

1. [ ] Create `backend/services/visual_answer_models.py`.
   - [ ] Move proposed `VisualPreflightDecision`, `ImageBlock`, `ImageCandidate`, and `PlannedImageSlot` without field or method behavior changes.
   - [ ] Keep `ImageBlock.to_frontend()` output keys identical to the current frontend contract.
2. [ ] Create `backend/services/visual_answer_cache.py`.
   - [ ] Add proposed `VisualAnswerCacheCodec.cache_key()` using the current `_VISUAL_CACHE_VERSION` and capability fingerprint behavior.
   - [ ] Add proposed `VisualAnswerCacheCodec.image_block_from_frontend()` with the current payload safety checks and coercion behavior.
   - [ ] Add proposed `VisualAnswerCacheCodec.is_safe_cached_image_block()` preserving the current allowlist semantics.
3. [ ] Create `backend/services/visual_answer_layout.py`.
   - [ ] Add proposed `split_paragraphs()`, `pending_block()`, `interleave_pending_slots()`, `interleave_blocks_at_planned_slots()`, and `interleave_blocks()` using the current algorithms.
4. [ ] Modify `backend/services/visual_answer_service.py`.
   - [ ] Import and re-export `VisualPreflightDecision`, `ImageBlock`, `ImageCandidate`, and `PlannedImageSlot`.
   - [ ] Replace the moved static helper bodies on `VisualAnswerService` with forwarding methods to the new cache/layout modules.
   - [ ] Update internal references in `VisualAnswerService.build_answer_blocks()`, `prepare_preflight_image_blocks()`, cache reads/writes, and layout calls to use the new modules or the compatibility forwards.
5. [ ] Modify `tests/backend/test_visual_answer_service.py`.
   - [ ] Add import compatibility assertions for `ImageBlock`, `ImageCandidate`, `PlannedImageSlot`, and `VisualPreflightDecision` from `backend.services.visual_answer_service`.
   - [ ] Add a focused regression assertion that `VisualAnswerService._cache_key()` equals the new cache helper output.

#### Test Plan

Run the visual answer tests because they cover cache keys, cached block restoration, safety filtering, search query rewriting, planned slots, and provider candidate parsing. Use existing fake Redis fixtures in `tests/backend/test_visual_answer_service.py`. Assertions must prove that public imports from `visual_answer_service.py` still work and that cache/layout outputs are byte-for-byte equivalent for representative payloads.

Executable commands:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_visual_answer_service.py
./backend/.venv/bin/python -m pytest tests/backend/test_output_image_service.py tests/backend/test_output_image_service_visual_retry.py
```

#### Expected Output / Result

The visual answer service still returns the same answer block shapes, cache keys remain stable for existing positive and negative cache records, and frontend image block payloads keep the same field names. No API, SSE, Redis key, or frontend behavior changes are expected.

#### Testing Script

##### Act 01: Import Compatibility

Import `ImageBlock`, `ImageCandidate`, `PlannedImageSlot`, `VisualPreflightDecision`, and `VisualAnswerService` from `backend.services.visual_answer_service`.

Pass condition: every import succeeds and the imported model classes are the same objects used by `VisualAnswerService`.

##### Act 02: Cache Key Stability

Call `VisualAnswerService._cache_key("meta analysis", "diagram")` before and after the extraction using the same capability settings.

Pass condition: the cache key prefix and digest are unchanged.

##### Act 03: Frontend Payload Round Trip

Build an `ImageBlock`, call `to_frontend()`, restore it through `VisualAnswerService._image_block_from_frontend()`, and compare all public fields.

Pass condition: restored values match the original compatibility payload.

#### Gate to Enter the Next Phase

Run:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_visual_answer_service.py tests/backend/test_output_image_service.py tests/backend/test_output_image_service_visual_retry.py
git diff --check
```

Success requires all tests to pass with no diff whitespace errors. Retain the pytest command output and line-count evidence from `wc -l backend/services/visual_answer_service.py backend/services/visual_answer_*.py`. If any test fails, stop in this phase, inspect whether the failure is caused by moved behavior or missing compatibility forwarding, and fix without weakening assertions.

#### Phase Commit

Commit message:

```text
refactor(visual): extract visual answer models cache and layout
```

Before committing, run `git status --short` and preserve unrelated user changes. Stage only `backend/services/visual_answer_service.py`, `backend/services/visual_answer_models.py`, `backend/services/visual_answer_cache.py`, `backend/services/visual_answer_layout.py`, and the specific hunks in `tests/backend/test_visual_answer_service.py`. Run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "refactor(visual): extract visual answer models cache and layout"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 2: Extract Visual Providers and Scoring

#### Problem

After Phase 1, `visual_answer_service.py` will still contain provider-specific HTTP clients, candidate conversion, domain safety, source quality scoring, and selection logic. These responsibilities are independent from high-level answer block orchestration but are mixed with it, making the service hard to review and keeping the file above the target line range. The target state is provider and scoring ownership in dedicated modules while `VisualAnswerService` controls workflow and observability.

#### Assumptions

Provider behavior depends on settings, HTTP headers, timeout handling, and fail-soft logging, but it does not need mutable state from `VisualAnswerService` except configuration and Redis-domain safety helpers. Existing tests call private provider helpers such as `_serpapi_image_candidate()` and candidate safety/scoring helpers, so `VisualAnswerService` must retain forwarding compatibility. If some helper relies on instance attributes discovered during implementation, keep that helper on the service until a clean dependency injection boundary is available.

#### Solution

Create a provider client module for external image search providers and a scoring module for candidate safety, source quality, pedagogical scoring, and display URL choice. Keep network retry/fail-soft semantics and structured log names stable. The service will call the provider client to gather `ImageCandidate` values and call scoring functions to select `ImageBlock` values. Forwarding methods on `VisualAnswerService` preserve test and caller expectations.

#### Implementation

> Context: Add Google-style docstrings to new provider/scoring modules and any public provider class or function. Document provider ownership, timeout/fail-soft behavior, safe structured-log fields, and why raw query/prompt/image URLs must not be logged. Use inline comments only where provider-specific behavior differs for compatibility, such as Wikimedia error classification or SerpAPI thumbnail fallback.

Add `backend/services/visual_answer_providers.py` with provider query functions or a `VisualImageProviderClient` that owns `_query_perplexity_images()`, `_query_wikimedia()`, `_query_openverse()`, `_query_tavily_images()`, `_query_serpapi_images()`, provider headers, candidate parsers, and provider error helpers. Add `backend/services/visual_answer_scoring.py` with domain filtering, inaccessible-domain checks, display URL selection, dimensions checks, source quality, pedagogical scoring, and heuristic scoring. Update `visual_answer_service.py` to delegate `_query_provider_candidates()`, `_resolve_paid_provider_image()`, `_select_image_block()`, and `_select_image_blocks()` to the new modules where possible while keeping orchestration and cache commitment in the service.

#### Expected File Tree After Phase 2

This tree is cumulative for Phase 2.

```text
backend/
└── services/
    ├── visual_answer_providers.py      [new]
    ├── visual_answer_scoring.py        [new]
    └── visual_answer_service.py        [modified]
tests/
└── backend/
    └── test_visual_answer_service.py   [modified]
```

#### Work List

1. [ ] Create `backend/services/visual_answer_providers.py`.
   - [ ] Add proposed `VisualImageProviderClient.query_provider_candidates()` and provider-specific methods for Perplexity, Wikimedia, Openverse, Tavily, and SerpAPI.
   - [ ] Move proposed `perplexity_image_candidate()`, `tavily_image_candidates()`, `tavily_image_candidate()`, and `serpapi_image_candidate()` without parsing changes.
2. [ ] Create `backend/services/visual_answer_scoring.py`.
   - [ ] Add proposed `VisualCandidateScorer.heuristic_score()`, `source_quality_score()`, `pedagogical_score()`, `is_safe_candidate()`, `display_image_url()`, and `has_useful_dimensions()`.
   - [ ] Preserve inaccessible-domain TTL and safe-domain behavior currently exposed through `VisualAnswerService.mark_inaccessible_image_domain()`.
3. [ ] Modify `backend/services/visual_answer_service.py`.
   - [ ] Initialize the proposed provider client and scorer in `VisualAnswerService.__init__()`.
   - [ ] Replace moved private method bodies with delegating wrappers for `_query_perplexity_images()`, `_query_wikimedia()`, `_query_openverse()`, `_query_tavily_images()`, `_query_serpapi_images()`, `_serpapi_image_candidate()`, `_is_safe_candidate()`, `_source_quality_score()`, `_display_image_url()`, and related helpers.
   - [ ] Keep `_resolve_images()`, `_resolve_preflight_parallel_images()`, `_select_image_blocks()`, and `commit_positive_cache()` behavior-compatible.
4. [ ] Modify `tests/backend/test_visual_answer_service.py`.
   - [ ] Add focused compatibility assertions for provider parser forwarding methods.
   - [ ] Add one direct test of the new scorer for trusted-domain and rejected-domain behavior while keeping existing service-level tests.

#### Test Plan

Run provider/scoring-focused tests from `tests/backend/test_visual_answer_service.py`, including SerpAPI candidate parsing, unsafe-domain rejection, source quality scoring, display URL fallback, planned image block selection, and cache commitment. Where tests mock network calls, verify the new provider client receives the same payloads and returns the same candidate ordering.

Executable commands:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_visual_answer_service.py
./backend/.venv/bin/python -m pytest tests/backend/test_visual_grounding_agent.py tests/backend/test_visual_pipeline_integration.py
```

#### Expected Output / Result

Provider search, candidate ranking, safety rejection, and visual block selection remain behavior-compatible. Logs continue to use safe metadata only. `visual_answer_service.py` should be within or close to the `500-600` line target after Phase 2; if it remains above target, the remaining lines must be high-level orchestration or explicitly scheduled for Phase 3/6 cleanup.

#### Testing Script

##### Act 01: Provider Parser Compatibility

Pass a representative SerpAPI image result payload to `VisualAnswerService._serpapi_image_candidate()`.

Pass condition: the returned `ImageCandidate` fields match the pre-refactor behavior and existing assertions.

##### Act 02: Safety Rejection

Create an `ImageCandidate` with an unsafe or inaccessible domain and call `VisualAnswerService._is_safe_candidate()`.

Pass condition: the candidate is rejected without logging raw image URL content.

##### Act 03: Trusted Source Ranking

Score a trusted-source candidate and an unrelated low-quality candidate for the same query.

Pass condition: the trusted-source candidate has a higher final score.

#### Gate to Enter the Next Phase

Run:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_visual_answer_service.py tests/backend/test_visual_grounding_agent.py tests/backend/test_visual_pipeline_integration.py
wc -l backend/services/visual_answer_service.py backend/services/visual_answer_*.py
git diff --check
```

Success requires all tests to pass, no whitespace errors, and `backend/services/visual_answer_service.py` at or below 600 lines unless the exact remaining extraction is documented in this plan before proceeding. On failure, keep fixes within Phase 2-owned files.

#### Phase Commit

Commit message:

```text
refactor(visual): extract image providers and scoring
```

Inspect `git status --short`, stage only Phase 2 files or identified hunks, and preserve unrelated changes. Run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "refactor(visual): extract image providers and scoring"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 3: Split PDF and Paper Visual Planning

#### Problem

`backend/services/pdf_visual_extraction_service.py` and `backend/services/paper_visual_planner_service.py` mix dataclasses, PDF geometry, render/downscale helpers, caption heuristics, fallback ranking, and model planning. Both files exceed the target size and are coupled through `PaperVisualPlanItem` and PDF extraction plans. The target state is small service classes that orchestrate planning/extraction while models, heuristics, and geometry are separately testable.

#### Assumptions

`PdfVisualCandidate`, `PdfVisualExtractionService`, `PaperVisualPlanItem`, and `PaperVisualPlannerService` are the public imports used by tests and orchestration. `PdfVisualCandidate.to_image_block()` depends on `ImageBlock` from the visual answer model contract and must preserve frontend payload fields. If PyMuPDF shape APIs vary in tests, geometry helpers must retain the current defensive behavior rather than tightening validation.

#### Solution

Extract PDF and paper dataclasses into model modules, extract caption/page/fallback heuristics into pure helper modules, and extract PDF rectangle/rendering utilities into dedicated modules. Keep the service classes as facades and re-export public model classes from their original service modules. This lowers file length while improving test targeting for crop selection and paper fallback planning.

#### Implementation

> Context: Add Google-style docstrings to all new PDF/paper modules and public helpers. Document PyMuPDF coordinate invariants, crop-quality thresholds, image-size safety limits, attachment provenance, and fail-soft behavior for corrupt or unsupported PDF/image data. Inline comments should explain non-obvious geometry choices, not basic rectangle math.

Add `backend/services/paper_visual_models.py` for `PaperVisualPlanItem` and private page context if appropriate. Add `backend/services/paper_visual_heuristics.py` for section/caption constants, fallback plan ranking, caption normalization, and fallback teaching captions. Add `backend/services/pdf_visual_models.py` for `PdfVisualCandidate` and `_PdfCropChoice`. Add `backend/services/pdf_visual_geometry.py` for rectangle normalization, union, padding, crop usability, caption adjacency, and table/figure crop selection helpers. Add `backend/services/pdf_visual_rendering.py` for PNG validation, downscaling, dimension reading, and render data URI handling where it can be moved without changing instance configuration.

#### Expected File Tree After Phase 3

This tree is cumulative for Phase 3.

```text
backend/
└── services/
    ├── paper_visual_heuristics.py          [new]
    ├── paper_visual_models.py              [new]
    ├── paper_visual_planner_service.py     [modified]
    ├── pdf_visual_geometry.py              [new]
    ├── pdf_visual_models.py                [new]
    ├── pdf_visual_rendering.py             [new]
    └── pdf_visual_extraction_service.py    [modified]
tests/
└── backend/
    ├── test_paper_visual_planner_service.py [modified]
    └── test_pdf_visual_extraction_service.py [modified]
```

#### Work List

1. [ ] Create `backend/services/paper_visual_models.py`.
   - [ ] Move proposed `PaperVisualPlanItem` with unchanged constructor fields and defaults.
   - [ ] Move proposed `_PaperPageContext` only if it does not create a public dependency leak.
2. [ ] Create `backend/services/paper_visual_heuristics.py`.
   - [ ] Move proposed `fallback_plan()`, `fallback_candidate_rank()`, `fallback_fill_rank()`, `best_fallback_visual()`, and caption/section normalization helpers.
3. [ ] Modify `backend/services/paper_visual_planner_service.py`.
   - [ ] Re-export `PaperVisualPlanItem`.
   - [ ] Keep `PaperVisualPlannerService.plan_visuals()` and `_plan_with_model()` as service-owned orchestration.
   - [ ] Delegate fallback ranking and caption heuristics to `paper_visual_heuristics.py`.
4. [ ] Create `backend/services/pdf_visual_models.py`.
   - [ ] Move proposed `PdfVisualCandidate` and `_PdfCropChoice` with unchanged fields and `to_image_block()` semantics.
5. [ ] Create `backend/services/pdf_visual_geometry.py`.
   - [ ] Move proposed geometry helpers currently named `_find_figure_crop_rect()`, `_select_crop_choice()`, `_crop_quality_score()`, `_expanded_crop_rect()`, `_nearest_caption_visuals()`, `_table_caption_visuals()`, `_union_rects()`, `_pad_rect()`, `_is_usable_crop_rect()`, and `_dedupe_rects()`.
6. [ ] Create `backend/services/pdf_visual_rendering.py`.
   - [ ] Move proposed `_is_valid_png()`, `_downscale_png()`, and `_png_dimensions()` helpers.
7. [ ] Modify `backend/services/pdf_visual_extraction_service.py`.
   - [ ] Re-export `PdfVisualCandidate`.
   - [ ] Keep `PdfVisualExtractionService.extract_candidates()` as the public orchestration method.
   - [ ] Delegate geometry/rendering helpers while preserving existing private method forwarding where tests call them.
8. [ ] Modify `tests/backend/test_paper_visual_planner_service.py` and `tests/backend/test_pdf_visual_extraction_service.py`.
   - [ ] Add import compatibility assertions from the original service modules.
   - [ ] Add direct helper-module tests only where they reduce service test duplication.

#### Test Plan

Run PDF and paper visual test files because they cover generated PDF fixtures, page scoring, figure/table caption matching, crop selection, image dimensions, and planned page extraction. Also run output-image PDF attachment tests to protect `PdfVisualCandidate.to_image_block()` compatibility.

Executable commands:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_pdf_visual_extraction_service.py tests/backend/test_paper_visual_planner_service.py tests/backend/test_output_image_service_pdf_attachment.py
```

#### Expected Output / Result

PDF attachment image extraction returns the same number and shape of `PdfVisualCandidate` values for existing fixtures. Paper visual planning keeps the same fallback required sections, target captions, and plan metadata. Original service-module imports continue to work.

#### Testing Script

##### Act 01: PDF Candidate Extraction

Run the existing PDF visual extraction fixture through `PdfVisualExtractionService.extract_candidates()`.

Pass condition: candidate count, page number, provider, and image block conversion match existing test expectations.

##### Act 02: Paper Fallback Plan

Run `PaperVisualPlannerService.plan_visuals()` with a PDF fixture and model planning disabled or timed out.

Pass condition: fallback plan includes the required teaching sections and selected page metadata.

##### Act 03: Planned Crop Selection

Provide a `PaperVisualPlanItem` with a caption hint to `PdfVisualExtractionService.extract_candidates()`.

Pass condition: the candidate crop follows the intended page and caption matching behavior.

#### Gate to Enter the Next Phase

Run:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_pdf_visual_extraction_service.py tests/backend/test_paper_visual_planner_service.py tests/backend/test_output_image_service_pdf_attachment.py
wc -l backend/services/pdf_visual_extraction_service.py backend/services/paper_visual_planner_service.py backend/services/pdf_visual_*.py backend/services/paper_visual_*.py
git diff --check
```

Success requires all tests to pass, no whitespace errors, and both original service files at or below 600 lines. If a file remains above target, stop and extract the remaining pure helper group before committing.

#### Phase Commit

Commit message:

```text
refactor(pdf): split visual extraction and paper planning helpers
```

Inspect `git status --short`, stage only Phase 3 paths or exact hunks, and preserve unrelated changes. Run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "refactor(pdf): split visual extraction and paper planning helpers"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 4: Split Query Policy and Memory Ingestion Helpers

#### Problem

`backend/services/query_policy_service.py` mixes policy enums/dataclass contracts, PDF auto-explain guardrails, legacy coercion, and model classification. `backend/services/memory_ingestion_service.py` mixes ingestion workflow with normalization, provenance validation, temporary-goal matching, and learning-preference promotion. Both files are above target and contain contracts used by multiple backend services. The target state is stable policy and ingestion facades with contracts and deterministic helpers extracted.

#### Assumptions

Callers import `ResponsePolicy`, enums, `default_response_policy()`, and classifier functions from `query_policy_service.py`, so that module must re-export the public contract. Callers import `MemoryIngestionService`, `MemoryIngestionResult`, `UserEvidence`, and `create_memory_ingestion_service()` from `memory_ingestion_service.py`, so those names must remain available. If tests rely on private helper names, forwarding wrappers are required until tests are migrated intentionally.

#### Solution

Extract query policy contracts to `query_policy_models.py`, PDF guardrail logic to `query_policy_pdf_guardrails.py`, and keep LLM parsing/classification wrappers in `query_policy_service.py`. Extract memory ingestion dataclasses/enums to `memory_ingestion_models.py`, text normalization/provenance helpers to `memory_ingestion_normalization.py`, and preference/goal helper logic to `memory_ingestion_rules.py`. Keep `MemoryIngestionService.ingest_user_evidence()` as the workflow owner.

#### Implementation

> Context: Add Google-style docstrings to new policy and memory ingestion modules. Document policy compatibility with `ConversationContextService`, `PartsContextService`, and orchestration; document memory provenance invariants, source validation, sensitive-context filtering, promotion/rejection semantics, and safe logging. Inline comments should explain privacy or provenance decisions only.

Create `backend/services/query_policy_models.py` for `TaskIntent`, `AnswerDepth`, `ResponseTone`, `ResponseStructure`, `FollowupMode`, `VisualSupport`, `VisualReason`, `AttachmentTask`, `AttachmentReason`, `ResponsePolicy`, and `default_response_policy()`. Create `backend/services/query_policy_pdf_guardrails.py` for PDF attachment counting, paper auto-explain instruction, broad request detection, guardrail application, and semantic fallback. Create `backend/services/memory_ingestion_models.py` for `MemoryEligibilityState`, `UserEvidence`, and `MemoryIngestionResult`. Create `backend/services/memory_ingestion_normalization.py` and `backend/services/memory_ingestion_rules.py` for deterministic helper methods currently implemented as private service methods. Update original service files to import and re-export public contracts.

#### Expected File Tree After Phase 4

This tree is cumulative for Phase 4.

```text
backend/
└── services/
    ├── memory_ingestion_models.py           [new]
    ├── memory_ingestion_normalization.py    [new]
    ├── memory_ingestion_rules.py            [new]
    ├── memory_ingestion_service.py          [modified]
    ├── query_policy_models.py               [new]
    ├── query_policy_pdf_guardrails.py       [new]
    └── query_policy_service.py              [modified]
tests/
└── backend/
    ├── test_memory_ingestion_service.py     [modified]
    ├── test_response_policy_service.py      [modified]
    ├── test_conversation_context_service.py [modified if needed]
    └── test_parts_context_service.py        [modified if needed]
```

#### Work List

1. [ ] Create `backend/services/query_policy_models.py`.
   - [ ] Move proposed policy enums, `ResponsePolicy.safe_log_metadata()`, and `default_response_policy()`.
   - [ ] Keep enum string values and dataclass defaults unchanged.
2. [ ] Create `backend/services/query_policy_pdf_guardrails.py`.
   - [ ] Move proposed `count_pdf_attachments()`, `paper_auto_explain_instruction()`, `apply_pdf_auto_explain_guardrail()`, and semantic fallback helpers.
3. [ ] Modify `backend/services/query_policy_service.py`.
   - [ ] Re-export all public policy contracts from `query_policy_models.py`.
   - [ ] Keep `parse_and_decompose_query_impl()`, `classify_dialogue_policy_impl()`, and `classify_response_policy_impl()` as the model-facing API.
   - [ ] Preserve legacy policy coercion behavior through imported helpers or local forwarding functions.
4. [ ] Create `backend/services/memory_ingestion_models.py`.
   - [ ] Move proposed `MemoryEligibilityState`, `UserEvidence`, and `MemoryIngestionResult`.
5. [ ] Create `backend/services/memory_ingestion_normalization.py`.
   - [ ] Move proposed normalization, canonicalization, passive preference rewrite, goal topic normalization, and provenance validation helpers.
6. [ ] Create `backend/services/memory_ingestion_rules.py`.
   - [ ] Move proposed learning-preference rejection and active-candidate helper logic if it can remain pure or accept explicit dependencies.
7. [ ] Modify `backend/services/memory_ingestion_service.py`.
   - [ ] Re-export public ingestion contracts.
   - [ ] Delegate deterministic helper methods while keeping service workflow and store writes unchanged.
   - [ ] Keep private method forwarding wrappers for tests that reference class helpers.
8. [ ] Modify `tests/backend/test_response_policy_service.py` and `tests/backend/test_memory_ingestion_service.py`.
   - [ ] Add public import compatibility tests from original modules.
   - [ ] Add helper-module tests for PDF guardrail and provenance validation where direct coverage is clearer.

#### Test Plan

Run policy, context, parts context, and memory ingestion tests. They protect classifier fallback, PDF attachment guardrails, response structure instructions, memory eligibility, preference promotion, temporary goal completion, candidate rejection, and provenance validation.

Executable commands:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_response_policy_service.py tests/backend/test_conversation_context_service.py tests/backend/test_parts_context_service.py
./backend/.venv/bin/python -m pytest tests/backend/test_memory_ingestion_service.py tests/backend/test_memory_source_boundaries.py tests/backend/test_compaction_flow.py
```

#### Expected Output / Result

Policy classifiers and PDF auto-explain behavior produce the same sanitized `ResponsePolicy` values. Memory ingestion writes, promotes, rejects, or ignores evidence exactly as before, with no change to Redis keys, user profile shape, or cold candidate shape.

#### Testing Script

##### Act 01: Policy Contract Re-export

Import `ResponsePolicy`, `TaskIntent`, `VisualSupport`, `count_pdf_attachments()`, and `classify_response_policy_impl()` from `backend.services.query_policy_service`.

Pass condition: imports succeed and returned policy values match existing enum types.

##### Act 02: PDF Auto Explain Guardrail

Pass a broad "explain this paper" style user message with one PDF attachment to the guardrail path.

Pass condition: the resulting policy requests the paper overview behavior expected by existing tests.

##### Act 03: Memory Ingestion Preference Promotion

Ingest deterministic user evidence representing a learning preference using the existing fake store fixture.

Pass condition: the same profile or candidate writes occur as before refactor.

#### Gate to Enter the Next Phase

Run:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_response_policy_service.py tests/backend/test_conversation_context_service.py tests/backend/test_parts_context_service.py tests/backend/test_memory_ingestion_service.py tests/backend/test_memory_source_boundaries.py tests/backend/test_compaction_flow.py
wc -l backend/services/query_policy_service.py backend/services/memory_ingestion_service.py backend/services/query_policy_*.py backend/services/memory_ingestion_*.py
git diff --check
```

Success requires all tests to pass, no whitespace errors, and both original service files at or below 600 lines. Stop and fix compatibility or helper extraction failures before proceeding.

#### Phase Commit

Commit message:

```text
refactor(memory): split query policy and ingestion helpers
```

Inspect `git status --short`, stage only Phase 4 paths or exact hunks, and preserve unrelated changes. Run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "refactor(memory): split query policy and ingestion helpers"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 5: Split Memory Store and GUM Integration

#### Problem

`backend/memory_store.py` combines hot memory, working memory, learner state snapshots, behavior signals, cold candidate lifecycle, pending alerts, and global singleton setup. `backend/gum_integration.py` combines GUM singleton lifecycle, observation batching, reflection, compaction scheduling, cold-memory querying, EDF update, proactive event detection, care-letter generation, and delayed reply writing. These files are central integration surfaces used by `main.py`, background jobs, mailbox, ComPeer scheduler, and tests, so the target state must reduce file length while preserving all existing import paths.

#### Assumptions

The root modules `memory_store.py` and `gum_integration.py` are public compatibility modules. Callers import many functions directly from `gum_integration.py`, and tests import `MemoryStore`, `init_global_store()`, `get_global_store()`, `gum_instance`, and `gum_instances`. If any direct global variable mutation exists in tests, the compatibility modules must retain those variables or expose proxy variables with identical behavior.

#### Solution

Split `MemoryStore` by responsibility using mixins or helper modules only where behavior can be moved safely without changing method names. Keep the `MemoryStore` class importable from `memory_store.py`. Split GUM integration into lifecycle, observation, reflection/compaction, cold query, and LLM message helper modules while keeping `gum_integration.py` as the public API facade that re-exports direct functions and globals. This phase should favor compatibility wrappers over aggressive class redesign.

#### Implementation

> Context: Add Google-style docstrings to every new memory/GUM module and public function. Document Redis key ownership, user-id isolation, memory source validation, cold candidate lifecycle states, singleton lifecycle, background job idempotency, debounce behavior, and fail-soft semantics for missing GUM/database/LLM dependencies. Structured logs must use safe IDs and reason codes only; no raw memory content, prompts, user messages, or generated letters should be logged.

Create `backend/memory_store_errors.py` for exceptions. Create `backend/memory_store_keys.py` for key builders if duplicated key construction can be centralized without behavior changes. Create `backend/memory_store_candidates.py` for cold candidate normalization, promotion, rejection, and temporary goal completion helpers or a mixin. Create `backend/memory_store_behavior.py` for behavior signal append/consume helpers. Update `memory_store.py` to keep `MemoryStore` public and delegate or inherit helper behavior. Create `backend/gum_lifecycle.py`, `backend/gum_observations.py`, `backend/gum_reflection.py`, `backend/gum_compaction.py`, and `backend/gum_llm_messages.py` where responsibilities can be moved without import cycles. Keep root `gum_integration.py` as the stable facade.

#### Expected File Tree After Phase 5

This tree is cumulative for Phase 5.

```text
backend/
├── gum_compaction.py                 [new]
├── gum_integration.py                [modified]
├── gum_lifecycle.py                  [new]
├── gum_llm_messages.py               [new]
├── gum_observations.py               [new]
├── gum_reflection.py                 [new]
├── memory_store.py                   [modified]
├── memory_store_behavior.py          [new]
├── memory_store_candidates.py        [new]
├── memory_store_errors.py            [new]
└── memory_store_keys.py              [new]
tests/
├── backend/
│   ├── test_gum_integration.py       [modified if needed]
│   ├── test_gum_integration_compeer.py [modified if needed]
│   ├── test_memory_store.py          [modified if needed]
│   ├── test_memory_store_compeer.py  [modified if needed]
│   └── test_memory_source_boundaries.py [modified if needed]
└── unit/
    ├── test_gum_singleton.py         [modified if needed]
    └── test_memory_store.py          [modified if needed]
```

#### Work List

1. [ ] Create `backend/memory_store_errors.py`.
   - [ ] Move proposed `MemoryBudgetExceeded` and `InvalidMemorySource`.
2. [ ] Create `backend/memory_store_keys.py`.
   - [ ] Add proposed key-builder helpers for hot memory, user profile, working memory, learner state, behavior signals, cold candidates, and pending alerts only if they preserve exact Redis key strings.
3. [ ] Create `backend/memory_store_behavior.py`.
   - [ ] Move proposed behavior signal append, consume, and filtering logic used by `MemoryStore.append_behavior_signal()` and `MemoryStore.consume_behavior_signals()`.
4. [ ] Create `backend/memory_store_candidates.py`.
   - [ ] Move proposed cold candidate update, append, promote, complete temporary goal, and reject helper logic used by `MemoryStore`.
5. [ ] Modify `backend/memory_store.py`.
   - [ ] Re-export `MemoryBudgetExceeded` and `InvalidMemorySource`.
   - [ ] Keep `MemoryStore` method names, return values, Redis writes, and global store functions unchanged.
   - [ ] Delegate extracted behavior through helper functions or mixins without changing caller-visible behavior.
6. [ ] Create `backend/gum_lifecycle.py`.
   - [ ] Move proposed GUM singleton setup, `TextObserver`, `get_gum_instance()`, `stop_gum_instance()`, `clear_gum_memory()`, and `is_real_gum_batcher()` if global state can remain shared.
7. [ ] Create `backend/gum_observations.py`.
   - [ ] Move proposed `ObservationQueueWorker`, `push_text_to_gum()`, `push_observation()`, `push_reflection_observation()`, and batch observation processing helpers.
8. [ ] Create `backend/gum_reflection.py` and `backend/gum_compaction.py`.
   - [ ] Move proposed `run_reflection()`, `schedule_session_reflection()`, `run_reflection_loop()`, `schedule_compaction()`, and `run_compaction()` while keeping job-store integration unchanged.
9. [ ] Create `backend/gum_llm_messages.py`.
   - [ ] Move proposed ZPD query generation, EDF state evaluation, proactive event detection, scaffolding message generation, epistolary letter generation, AREQA care letter generation, and delayed reply writer helpers where they do not introduce cycles.
10. [ ] Modify `backend/gum_integration.py`.
   - [ ] Re-export all existing public functions and globals used by `main.py`, `job_store.py`, `mailbox_store.py`, `compeer_scheduler.py`, and tests.
   - [ ] Add forwarding wrappers only where direct imports require the original module path.
11. [ ] Modify memory/GUM tests only for compatibility assertions.
   - [ ] Update `tests/unit/test_gum_singleton.py` only if global state access requires a compatibility shim.
   - [ ] Add direct tests for exact Redis key preservation if `memory_store_keys.py` is introduced.

#### Test Plan

Run focused memory and GUM tests plus ComPeer/mailbox tests that import the root modules. These protect singleton behavior, observation batching, reflection scheduling, memory source boundaries, cold candidate lifecycle, behavior signal flow, learner state snapshot updates, and background job integration.

Executable commands:

```bash
./backend/.venv/bin/python -m pytest tests/unit/test_gum_singleton.py tests/unit/test_memory_store.py
./backend/.venv/bin/python -m pytest tests/backend/test_memory_store.py tests/backend/test_memory_store_compeer.py tests/backend/test_memory_source_boundaries.py tests/backend/test_gum_integration.py tests/backend/test_gum_integration_compeer.py tests/backend/test_gum_batcher.py tests/backend/test_compeer_behavior_signal_flow.py
./backend/.venv/bin/python -m pytest tests/backend/test_mailbox_store.py tests/backend/test_compeer_scheduler.py
```

#### Expected Output / Result

All root-module imports remain valid. Memory Redis keys and values remain stable. GUM singleton startup/shutdown behavior, observation debounce, reflection scheduling, compaction scheduling, and ComPeer/mailbox integrations continue to pass existing tests. `memory_store.py` and `gum_integration.py` are at or below 600 lines after extraction.

#### Testing Script

##### Act 01: Memory Store Global Compatibility

Call `init_global_store()` and `get_global_store()` through `memory_store.py`, then perform a hot-memory update with the fake Redis fixture.

Pass condition: the returned object is a `MemoryStore` and Redis state matches the existing test contract.

##### Act 02: GUM Singleton Compatibility

Call `get_gum_instance()`, inspect the exported singleton state expected by tests, and call `stop_gum_instance()`.

Pass condition: lifecycle state transitions match existing singleton tests.

##### Act 03: Observation and Reflection Flow

Push an observation through `gum_integration.push_observation()` with deterministic fake dependencies and schedule reflection.

Pass condition: the same queued observation count and reflection job behavior are observed as before.

#### Gate to Enter the Next Phase

Run:

```bash
./backend/.venv/bin/python -m pytest tests/unit/test_gum_singleton.py tests/unit/test_memory_store.py tests/backend/test_memory_store.py tests/backend/test_memory_store_compeer.py tests/backend/test_memory_source_boundaries.py tests/backend/test_gum_integration.py tests/backend/test_gum_integration_compeer.py tests/backend/test_gum_batcher.py tests/backend/test_compeer_behavior_signal_flow.py tests/backend/test_mailbox_store.py tests/backend/test_compeer_scheduler.py
wc -l backend/gum_integration.py backend/gum_*.py backend/memory_store.py backend/memory_store_*.py
git diff --check
```

Success requires all tests to pass, no whitespace errors, and both original root modules at or below 600 lines. If global state compatibility fails, stop and repair the facade before proceeding.

#### Phase Commit

Commit message:

```text
refactor(memory): split memory store and gum integration
```

Inspect `git status --short`, stage only Phase 5 paths or exact hunks, and preserve unrelated changes. Run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "refactor(memory): split memory store and gum integration"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Phase 6: Split Orchestration Nodes and Verify End-to-End Streaming

#### Problem

`backend/services/orchestration_service.py` is a 1693-line streaming coordinator that mixes request intake, roleplay handling, attachment grounding, RAG retrieval, web search, prompt assembly, visual extraction, LLM streaming, and post-generation side effects. It imports many services and has public behavior tested through streaming endpoint, RAG, Perplexity, visual pipeline, and orchestration tests. The target state is a compact `OrchestrationService` facade whose `execute()` method delegates node responsibilities to focused modules without changing SSE/API behavior.

#### Assumptions

`OrchestrationService.execute()` is the primary public API and must retain its signature, yielded event sequence, and fail-soft behavior. Tests may patch private methods such as `_node_perplexity_search()`, so compatibility wrappers should remain on `OrchestrationService` or tests must be adjusted only where the patch target intentionally moves. If a node helper needs direct access to many instance attributes, keep it as a small method until dependency boundaries are clear.

#### Solution

Extract pure utility helpers first, then move node-level responsibilities into modules that accept explicit dependencies or the service instance as a compatibility bridge. Keep `execute()` in `orchestration_service.py`, along with constructor wiring and high-level turn flow. Move visual attachment handling, retrieval/search nodes, prompt assembly, and stream/post-generation node helpers into focused modules. Preserve structured log names, latency trace calls, and emitted SSE event shapes.

#### Implementation

> Context: Add Google-style docstrings to new orchestration modules and any public helper class/function. Document control-flow ownership, event emission contracts, cancellation/fail-soft semantics, latency trace points, attachment privacy boundaries, and structured-log safe metadata. Inline comments should explain non-obvious order dependencies such as why visual extraction happens before prompt assembly or why post-turn side effects are delayed.

Create `backend/services/orchestration_utils.py` for localized greeting, source validation, query decomposition wrappers if still needed, route naming, and recent conversation context formatting. Create `backend/services/orchestration_visuals.py` for attachment grounding instructions, paper auto-explain instruction attachment, PDF visual candidate extraction, and verified visual instruction generation. Create `backend/services/orchestration_retrieval.py` for RAG retrieval and Perplexity search node helpers. Create `backend/services/orchestration_prompting.py` for prompt assembly and parts-context rewrite decisions. Update `orchestration_service.py` to keep `execute()`, `_node_llm_stream()`, and `_node_post_generation()` if they remain tightly coupled, while delegating extracted helpers and keeping wrapper methods for existing patch targets.

#### Expected File Tree After Phase 6

This tree is cumulative for Phase 6.

```text
backend/
└── services/
    ├── orchestration_prompting.py       [new]
    ├── orchestration_retrieval.py       [new]
    ├── orchestration_service.py         [modified]
    ├── orchestration_utils.py           [new]
    └── orchestration_visuals.py         [new]
tests/
├── backend/
│   ├── test_orchestration_service.py    [modified if needed]
│   ├── test_perplexity_node.py          [modified if needed]
│   ├── test_stream_endpoint.py          [modified if needed]
│   └── test_visual_pipeline_integration.py [modified if needed]
└── unit/
    └── test_orchestration_service.py    [modified if needed]
```

#### Work List

1. [ ] Create `backend/services/orchestration_utils.py`.
   - [ ] Move proposed `_localized_greeting_reply()`, `reorder_for_attention()`, `_build_valid_web_sources()`, `_turn_plan_route_name()`, and `_recent_conversation_context()` with unchanged behavior.
2. [ ] Create `backend/services/orchestration_visuals.py`.
   - [ ] Move proposed attachment methods `_attach_to_latest_user_message()`, `_add_attachment_grounding_instruction()`, `_add_paper_auto_explain_instruction()`, `_extract_attachment_visual_candidates()`, and `_add_verified_visual_instruction()`.
3. [ ] Create `backend/services/orchestration_retrieval.py`.
   - [ ] Move proposed RAG and web search node bodies from `_node_rag_retrieval()` and `_node_perplexity_search()` into dependency-explicit helper functions.
4. [ ] Create `backend/services/orchestration_prompting.py`.
   - [ ] Move proposed prompt assembly logic from `_node_prompt_assembly()` and `_should_run_parts_llm_rewrite()`.
5. [ ] Modify `backend/services/orchestration_service.py`.
   - [ ] Keep `OrchestrationService.__init__()` and `OrchestrationService.execute()` as the public workflow owner.
   - [ ] Keep compatibility wrapper methods for patched private node names used by tests.
   - [ ] Delegate visual, retrieval, and prompting work to the new modules without changing yielded SSE events or `TurnLatencyTrace` calls.
6. [ ] Modify orchestration and stream tests only if patch targets need compatibility assertions.
   - [ ] Update `tests/backend/test_perplexity_node.py` to assert `_node_perplexity_search()` wrapper behavior if the implementation moved.
   - [ ] Update `tests/backend/test_stream_endpoint.py` only when mock paths must account for wrappers.

#### Test Plan

Run orchestration, stream endpoint, RAG, Perplexity, visual pipeline, and avatar-rule tests. These protect yielded events, prompt assembly, attachment injection, PDF visual path, web search source handling, roleplay state, budget behavior, and post-generation side effects.

Executable commands:

```bash
./backend/.venv/bin/python -m pytest tests/unit/test_orchestration_service.py tests/backend/test_orchestration_service.py tests/backend/test_perplexity_node.py
./backend/.venv/bin/python -m pytest tests/backend/test_stream_endpoint.py tests/backend/test_stream_api_perplexity.py tests/backend/test_rag_service.py tests/backend/test_visual_pipeline_integration.py tests/backend/test_orchestration_avatar_rules.py
```

#### Expected Output / Result

The streaming endpoint emits the same event sequence and payload shapes. Prompt assembly includes the same memory, RAG, web, visual, paper, and attachment instructions. Web search and RAG nodes continue to fail soft where they did before. `orchestration_service.py` is at or below 600 lines.

#### Testing Script

##### Act 01: Basic Stream Execution

Call the chat streaming endpoint with a simple text-only user message and deterministic mocked model output.

Pass condition: the stream completes with the same public answer event shape and no unexpected internal errors.

##### Act 02: Perplexity Node Wrapper

Invoke or patch `OrchestrationService._node_perplexity_search()` using the existing Perplexity test fixture.

Pass condition: the wrapper delegates to the extracted helper and yields the same search events/results.

##### Act 03: Attachment Visual Flow

Run an attachment/PDF visual pipeline test through orchestration with planned visual slots.

Pass condition: verified image instructions and answer blocks are assembled exactly as existing tests expect.

#### Gate to Enter the Next Phase

Run:

```bash
./backend/.venv/bin/python -m pytest tests/unit/test_orchestration_service.py tests/backend/test_orchestration_service.py tests/backend/test_perplexity_node.py tests/backend/test_stream_endpoint.py tests/backend/test_stream_api_perplexity.py tests/backend/test_rag_service.py tests/backend/test_visual_pipeline_integration.py tests/backend/test_orchestration_avatar_rules.py
wc -l backend/services/orchestration_service.py backend/services/orchestration_*.py
git diff --check
```

Success requires all tests to pass, no whitespace errors, and `backend/services/orchestration_service.py` at or below 600 lines. Any changed SSE or API payload requires an explicit decision and additional frontend/backward-compatibility tests before proceeding.

#### Phase Commit

Commit message:

```text
refactor(orchestration): split streaming orchestration nodes
```

Inspect `git status --short`, stage only Phase 6 paths or exact hunks, and preserve unrelated changes. Run:

```bash
git diff --cached --check
git diff --cached --stat
git commit -m "refactor(orchestration): split streaming orchestration nodes"
git show --stat --oneline --summary HEAD
```

Do not commit if the phase gate fails.

### Cross-Phase Regression and Final Acceptance

After all phase gates and commits pass, run the full backend regression suite:

```bash
npm run test:backend
```

Also run the focused commands from each phase if the full suite fails before identifying the affected area:

```bash
./backend/.venv/bin/python -m pytest tests/backend/test_visual_answer_service.py tests/backend/test_pdf_visual_extraction_service.py tests/backend/test_paper_visual_planner_service.py tests/backend/test_response_policy_service.py tests/backend/test_memory_ingestion_service.py tests/backend/test_memory_store.py tests/backend/test_gum_integration.py tests/backend/test_orchestration_service.py tests/backend/test_stream_endpoint.py
```

Manual or end-to-end rerun scenario:

1. Start the backend and frontend with `npm run dev` using the existing development environment.
2. Send a normal chat message with no attachments.
3. Send a PDF attachment and ask for a broad paper explanation.
4. Send a visual-support request that triggers image preflight.
5. Trigger or simulate a memory-worthy user statement and confirm the memory ingestion path remains nonblocking.

Final acceptance outcomes:

- Every requested original file is at or below 600 lines:

```bash
wc -l backend/gum_integration.py backend/memory_store.py backend/services/memory_ingestion_service.py backend/services/orchestration_service.py backend/services/paper_visual_planner_service.py backend/services/pdf_visual_extraction_service.py backend/services/query_policy_service.py backend/services/visual_answer_service.py
```

- Existing public imports from original modules continue to work.
- No API response, SSE event, Redis key, cache key, database record, or frontend answer-block shape changes unless explicitly approved in a later plan.
- Critical paths still use safe structured logging and do not log raw user text, prompts, model output, image URLs, credentials, or sensitive memory content.
- `npm run test:backend` passes from a clean checkout plus the phase commits.

Final Git review:

```bash
git status --short
git log --oneline -6
```

`git status --short` must show no uncommitted planned changes except unrelated user-owned work that was intentionally preserved. `git log --oneline -6` must show the six phase commits in order:

```text
refactor(visual): extract visual answer models cache and layout
refactor(visual): extract image providers and scoring
refactor(pdf): split visual extraction and paper planning helpers
refactor(memory): split query policy and ingestion helpers
refactor(memory): split memory store and gum integration
refactor(orchestration): split streaming orchestration nodes
```

Remaining risks and mitigations:

- Private helper compatibility is the largest risk because existing tests and callers may patch private service methods. Mitigation: keep wrapper methods through this refactor and remove them only in a later cleanup.
- Circular imports are likely around `visual_answer_service.py`, `pdf_visual_extraction_service.py`, `memory_store.py`, and `gum_integration.py`. Mitigation: move dataclasses/contracts first, keep dependency direction from facade to helper modules, and preserve local imports where the project already uses them to avoid cycles.
- Full backend tests may require services such as Redis, database, or API keys depending on environment. Mitigation: run focused deterministic tests first, then full suite; document environment-caused skips or failures without weakening assertions.
- The line target may require a second extraction pass if wrappers remain verbose. Mitigation: treat wrappers as temporary compatibility code and measure line counts at every phase gate.

## Implementation Status

Status as of 2026-09-04: implemented with the updated user-approved ceiling of 657 lines for a single file.

Completed work:

- [x] Split visual answer internals into `backend/services/visual_answer/`.
- [x] Split PDF visual extraction internals into `backend/services/pdf_visual/`.
- [x] Split paper visual planner contracts/constants into `backend/services/paper_visual/`.
- [x] Split query policy contracts and PDF guardrails into `backend/services/query_policy/`.
- [x] Split memory ingestion contracts, rules, and factory helpers into `backend/services/memory_ingestion/`.
- [x] Split memory store behavior and candidate logic into `backend/memory_store_parts/`.
- [x] Split GUM observation and LLM context helpers into `backend/gum_parts/`.
- [x] Split orchestration execution, visual, retrieval, prompting, streaming, intake, and utility logic into `backend/services/orchestration/`.
- [x] Preserve facade modules and legacy import/patch points for existing tests.

Verification performed:

```bash
python -m py_compile backend/gum_integration.py backend/gum_parts/*.py backend/memory_store.py backend/memory_store_parts/*.py backend/services/memory_ingestion_service.py backend/services/memory_ingestion/*.py backend/services/orchestration_service.py backend/services/orchestration/*.py backend/services/paper_visual_planner_service.py backend/services/paper_visual/*.py backend/services/pdf_visual_extraction_service.py backend/services/pdf_visual/*.py backend/services/query_policy_service.py backend/services/query_policy/*.py backend/services/visual_answer_service.py backend/services/visual_answer/*.py backend/services/turn_intake_service.py
./backend/.venv/bin/python -m pytest tests/unit/test_orchestration_service.py tests/unit/test_gum_singleton.py -q
./backend/.venv/bin/python -m pytest tests/backend/test_visual_answer_service.py tests/backend/test_output_image_service.py tests/backend/test_output_image_service_visual_retry.py tests/backend/test_pdf_visual_extraction_service.py tests/backend/test_paper_visual_planner_service.py tests/backend/test_output_image_service_pdf_attachment.py tests/backend/test_response_policy_service.py tests/backend/test_conversation_context_service.py tests/backend/test_parts_context_service.py tests/backend/test_memory_ingestion_service.py tests/backend/test_memory_source_boundaries.py tests/backend/test_compaction_flow.py tests/backend/test_memory_store.py tests/backend/test_memory_store_compeer.py tests/backend/test_compeer_behavior_signal_flow.py tests/backend/test_gum_integration.py tests/backend/test_gum_integration_compeer.py tests/backend/test_gum_batcher.py tests/backend/test_orchestration_service.py tests/backend/test_perplexity_node.py tests/backend/test_stream_endpoint.py tests/backend/test_stream_api_perplexity.py tests/backend/test_rag_service.py tests/backend/test_visual_pipeline_integration.py tests/backend/test_orchestration_avatar_rules.py -q
```

Observed result:

- `py_compile` passed.
- Unit focused suite passed: `2 passed, 1 warning`.
- Backend focused suite passed: `287 passed, 5 skipped, 8 warnings`.
