# Legacy service imports

These files preserve the old flat `services.<name>` and
`backend.services.<name>` imports. The service package adds this directory to
its module search path; callers do not import `_compat` directly.

Each alias resolves to its canonical module object, so monkeypatches, locks,
mutable globals and singletons remain shared. Add implementation only to the
owning domain. Migrate internal callers to canonical paths; remove an alias
only after external callers and documented test patch paths have migrated.

The normal import loader handles discovery. No provider is imported merely by
importing `services`.

| Legacy name (under `services`) | Canonical module (under `services`) |
| --- | --- |
| `answer_style_service` | `conversation.answer_style` |
| `attachment_image_storage_service` | `attachments.storage` |
| `attachment_service` | `attachments.parsing` |
| `cache_service` | `retrieval.cache` |
| `compeer_scheduler` | `compeer.runtime` |
| `connection_manager` | `notifications.connections` |
| `conversation_context_service` | `conversation.context` |
| `conversation_stream_service` | `conversation.stream` |
| `explicit_memory_cache` | `memory.recall_cache` |
| `generated_image_quota` | `visual.generation_quota` |
| `generated_image_service` | `visual.generation` |
| `hot_memory_service` | `memory.hot` |
| `memory_extraction_agent` | `memory.extraction` |
| `memory_ingestion_service` | `memory.ingestion.service` |
| `memory_retrieval_trace` | `memory.retrieval_trace` |
| `memory_semantic_analyzer` | `memory.semantic_analysis` |
| `message_intent_service` | `orchestration.message_intent` |
| `orchestration_service` | `orchestration.service` |
| `output_image_service` | `visual.output` |
| `paper_visual_planner_service` | `paper_visual.planner` |
| `parts_context_service` | `conversation.parts` |
| `pdf_visual_extraction_service` | `pdf_visual.extraction` |
| `post_turn_service` | `orchestration.post_turn` |
| `query_policy_service` | `query_policy.classifier` |
| `response_boundary_validator` | `conversation.response_boundary` |
| `speaking_material_service` | `realtime.speaking_material` |
| `turn_intake_service` | `orchestration.intake` |
| `turn_latency_trace` | `orchestration.trace` |
| `turn_plan_service` | `orchestration.turn_plan` |
| `tutor_profile_service` | `conversation.tutor_profile` |
| `visual_affordance_registry` | `visual.affordance` |
| `visual_answer_service` | `visual_answer.service` |
| `visual_grounding_agent` | `visual.grounding` |
| `visual_input_service` | `visual.input` |
| `visual_understanding_agent` | `visual.understanding` |
