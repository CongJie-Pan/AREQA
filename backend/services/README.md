# Backend Services Structure

`backend/services` is organized around domain packages plus compatibility
facades. New implementation code should go into a domain package when ownership
is clear. Keep a flat module only when it is a small cross-domain utility or a
compatibility facade for existing imports and test patch paths.

## Domain Packages

- `attachments/`: attachment parsing, validation, and PDF image persistence.
- `compeer/`: ComPeer cooldowns, proactive scheduling, care letters, and worker
  loops.
- `conversation/`: answer-context assembly, LearnLM PARTS context, and provider
  streaming helpers.
- `memory_ingestion/`: memory-ingestion models, rules, constants, and factory
  helpers.
- `orchestration/`: turn intake, prompt assembly, retrieval, execution,
  streaming, visual coordination, and orchestration utilities.
- `paper_visual/`: paper visual planning constants, models, and helper logic.
- `pdf_visual/`: PDF visual extraction constants, geometry, models, and
  rendering helpers.
- `query_policy/`: query-policy models and PDF guardrails.
- `visual/`: visual affordances, grounding, image input preparation, output
  image coordination, and vision understanding.
- `visual_answer/`: visual-answer provider clients, provider helpers, caching,
  scoring, layout, slots, selection, and models.

## Compatibility Facades

These flat modules intentionally re-export package implementations so legacy
imports such as `services.foo` and `backend.services.foo` continue to work:

- `attachment_image_storage_service.py` -> `services.attachments.storage`
- `attachment_service.py` -> `services.attachments.parsing`
- `compeer_scheduler.py` -> `services.compeer`
- `conversation_context_service.py` -> `services.conversation.context`
- `conversation_stream_service.py` -> `services.conversation.stream`
- `memory_ingestion_service.py` -> `services.memory_ingestion`
- `orchestration_service.py` -> `services.orchestration`
- `output_image_service.py` -> `services.visual.output`
- `paper_visual_planner_service.py` -> `services.paper_visual`
- `parts_context_service.py` -> `services.conversation.parts`
- `pdf_visual_extraction_service.py` -> `services.pdf_visual`
- `query_policy_service.py` -> `services.query_policy`
- `visual_affordance_registry.py` -> `services.visual.affordance`
- `visual_answer_service.py` -> `services.visual_answer`
- `visual_grounding_agent.py` -> `services.visual.grounding`
- `visual_input_service.py` -> `services.visual.input`
- `visual_understanding_agent.py` -> `services.visual.understanding`

Do not remove these facades until all runtime imports, tests, and documented
patch paths have migrated to package modules.

## Flat Leaf Utilities

These files remain flat because they are small, broadly shared utilities or
single-purpose services without enough internal structure to justify a package:

- `answer_style_service.py`
- `cache_service.py`
- `connection_manager.py`
- `explicit_memory_cache.py`
- `hot_memory_service.py`
- `memory_extraction_agent.py`
- `memory_retrieval_trace.py`
- `memory_semantic_analyzer.py`
- `post_turn_service.py`
- `response_boundary_validator.py`
- `turn_intake_service.py`
- `turn_latency_trace.py`
- `turn_plan_service.py`

If one of these grows beyond the line ceiling or gains multiple subdomains,
create a focused package first and leave the flat module as a facade.

## Placement Rules

- Put new ComPeer code under `compeer/`.
- Put new attachment parsing or storage code under `attachments/`.
- Put new visual retrieval, grounding, input, or output-image coordination code
  under `visual/` or `visual_answer/`, depending on the existing ownership.
- Put new prompt/context/streaming conversation code under `conversation/`.
- Put new orchestration workflow code under `orchestration/`.
- Put new query-policy logic under `query_policy/`.
- Preserve existing route, SSE, Redis key, mailbox, and test patch contracts
  when changing facades.
