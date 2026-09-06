2026-09-05T13:12:11.132600559Z 2026-09-05 13:12:11 [WARNING] backend.services.orchestration_service: orchestration.dialogue_policy_timeout conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 fallback=NORMAL
2026-09-05T13:12:11.132798435Z 2026-09-05 13:12:11 [INFO] backend.services.orchestration_service: orchestration.response_policy_applied conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 source=timeout_fallback metadata={"answer_depth": "SCAFFOLDED", "attachment_reason": "NO_ATTACHMENT", "attachment_task": "NONE", "followup_mode": "OPTIONAL", "legacy_policy": "NORMAL", "structure": "STEP_BY_STEP", "task_intent": "GENERAL_QA", "tone": "TUTORING", "visual_reason": "NOT_NEEDED", "visual_support": "NONE"}
2026-09-05T13:12:11.133242958Z 2026-09-05 13:12:11 [INFO] services.orchestration.prompting: parts_context.rewrite_gate conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 enabled=False route=GENERAL_CHAT grounded=False allow_ungrounded=False
2026-09-05T13:12:11.133435903Z 2026-09-05 13:12:11 [INFO] services.conversation.parts: parts_context.rewrite_skipped route=GENERAL_CHAT reason=disabled_or_unavailable metadata={"confidence": "medium", "has_act": true, "has_composed_instruction": true, "has_persona": true, "has_recipient": true, "has_structure": true, "has_theme": true, "missing_field_count": 1}
2026-09-05T13:12:11.138555998Z 2026-09-05 13:12:11 [INFO] services.conversation.context: orchestration.long_term_memory_skipped reason=GENERAL_CHAT memory_reason=SUBSTANTIVE_QUERY
2026-09-05T13:12:11.138580489Z 2026-09-05 13:12:11 [INFO] services.orchestration.prompting: orchestration.context_prepared conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 learner_understanding=unknown retrieved_memory=False
2026-09-05T13:12:11.138664901Z 2026-09-05 13:12:11 [INFO] backend.services.orchestration_service: paper.auto_explain_policy_selected conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 enabled=True applied=False task=NONE reason=NO_ATTACHMENT pdf_count=0
2026-09-05T13:12:11.138762324Z 2026-09-05 13:12:11 [INFO] backend.services.orchestration_service: visual.preflight_policy_gate conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 allowed=False blocking_allowed=False trigger=policy_gate visual_support=NONE visual_reason=NOT_NEEDED explicit_visual=False known_affordance=False max_images=2 has_attachment_visual_sources=False
2026-09-05T13:12:11.138805905Z 2026-09-05 13:12:11 [INFO] backend.services.orchestration_service: visual.preflight_blocking_skipped conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 trigger=policy_gate visual_support=NONE explicit_visual=False known_affordance=False
2026-09-05T13:12:11.138832326Z 2026-09-05 13:12:11 [INFO] backend.services.orchestration_service: visual.preverified_inventory_ready conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 available_image_count=0 has_attachment_visual_sources=False
2026-09-05T13:12:11.13896171Z 2026-09-05 13:12:11 [INFO] services.conversation.stream: orchestration.stream_started conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 model=google/gemini-3.8-flash attachment_parser=False image_slot_cap=2 openrouter_session=True latency_routing=True
2026-09-05T13:12:11.796656577Z 2026-09-05 13:12:11 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:13.649736872Z 2026-09-05 13:12:13 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:18.521693673Z 2026-09-05 13:12:18 [INFO] services.conversation.stream: orchestration.stream_completed conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 elapsed_ms=7382
2026-09-05T13:12:18.521860498Z 2026-09-05 13:12:18 [INFO] backend.services.orchestration_service: visual.answer_blocks_skipped conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 planned_image_slot_count=0 preverified_image_count=0
2026-09-05T13:12:18.522012882Z 2026-09-05 13:12:18 [INFO] services.suggestion_service: suggestions.requested language=繁體中文 model=google/gemini-2.5-flash-lite context_count=0
2026-09-05T13:12:19.401535919Z 2026-09-05 13:12:19 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:19.522892034Z 2026-09-05 13:12:19 [WARNING] services.post_turn_service: orchestration.suggestions_failed run_id=6e0d2afe5d5746c886500f2c42f2148d conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 language=en reason=TimeoutError
2026-09-05T13:12:19.523329487Z 2026-09-05 13:12:19 [INFO] backend.services.orchestration_service: orchestration.post_turn_queued run_id=6e0d2afe5d5746c886500f2c42f2148d conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031
2026-09-05T13:12:19.52347084Z 2026-09-05 13:12:19 [INFO] backend.services.orchestration_service: orchestration.turn_trace_completed run_id=6e0d2afe5d5746c886500f2c42f2148d conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 trace={'run_id': '6e0d2afe5d5746c886500f2c42f2148d', 'conversation_id': 'a3d0aa61-612f-4201-87f9-135851ec8031', 'elapsed_ms': 10600, 'phases': [{'name': 'request_accepted', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_started', 'elapsed_ms': 2, 'occurrence': 1}, {'name': 'search_routing_finished', 'elapsed_ms': 1503, 'occurrence': 1}, {'name': 'turn_plan_general_chat', 'elapsed_ms': 1503, 'occurrence': 1}, {'name': 'turn_intake_started', 'elapsed_ms': 1504, 'occurrence': 1}, {'name': 'turn_intake_finished', 'elapsed_ms': 1508, 'occurrence': 1}, {'name': 'policy_classifier_started', 'elapsed_ms': 1508, 'occurrence': 1}, {'name': 'rag_skipped', 'elapsed_ms': 1508, 'occurrence': 1}, {'name': 'policy_classifier_timeout', 'elapsed_ms': 2209, 'occurrence': 1}, {'name': 'prompt_assembly_started', 'elapsed_ms': 2210, 'occurrence': 1}, {'name': 'parts_context_started', 'elapsed_ms': 2210, 'occurrence': 1}, {'name': 'parts_context_finished', 'elapsed_ms': 2210, 'occurrence': 1}, {'name': 'hot_memory_snapshot_started', 'elapsed_ms': 2210, 'occurrence': 1}, {'name': 'hot_memory_snapshot_finished', 'elapsed_ms': 2213, 'occurrence': 1}, {'name': 'prompt_assembly_finished', 'elapsed_ms': 2215, 'occurrence': 1}, {'name': 'visual_preflight_started', 'elapsed_ms': 2215, 'occurrence': 1}, {'name': 'visual_preflight_finished', 'elapsed_ms': 2215, 'occurrence': 1}, {'name': 'main_model_started', 'elapsed_ms': 2215, 'occurrence': 1}, {'name': 'main_model_provider_request_started', 'elapsed_ms': 2215, 'occurrence': 1}, {'name': 'main_model_provider_stream_received', 'elapsed_ms': 4726, 'occurrence': 1}, {'name': 'first_answer_delta', 'elapsed_ms': 7417, 'occurrence': 1}, {'name': 'main_model_finished', 'elapsed_ms': 9598, 'occurrence': 1}, {'name': 'suggestions_started', 'elapsed_ms': 9598, 'occurrence': 1}, {'name': 'suggestions_failed', 'elapsed_ms': 10599, 'occurrence': 1}, {'name': 'post_turn_queued', 'elapsed_ms': 10600, 'occurrence': 1}, {'name': 'terminal_sent', 'elapsed_ms': 10600, 'occurrence': 1}], 'model_calls': {'main_answer': 1, 'policy_classifier': 1, 'search_routing': 1, 'suggestions': 1}, 'tool_calls': {'hot_memory': 1}, 'cache_statuses': {'hot_memory:not_applicable': 1}}
2026-09-05T13:12:19.523533662Z 2026-09-05 13:12:19 [INFO] backend.services.orchestration_service: orchestration.turn_trace_summary run_id=6e0d2afe5d5746c886500f2c42f2148d conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 summary={"cache_statuses": {"hot_memory:not_applicable": 1}, "conversation_id": "a3d0aa61-612f-4201-87f9-135851ec8031", "elapsed_ms": 10600, "is_slow": true, "main_model_started_ms": 2215, "model_calls": {"main_answer": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1}, "phase_durations_ms": {"hot_memory_snapshot": 3, "main_model": 7383, "parts_context": 0, "policy_classifier": 701, "prompt_assembly": 5, "search_routing": 1501, "suggestions": 1001, "turn_intake": 4, "visual_preflight": 0}, "provider_first_token_ms": 5202, "run_id": "6e0d2afe5d5746c886500f2c42f2148d", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 10600, "time_to_first_answer_ms": 7417, "tool_calls": {"hot_memory": 1}, "top_phase_durations": [{"duration_ms": 7383, "name": "main_model"}, {"duration_ms": 1501, "name": "search_routing"}, {"duration_ms": 1001, "name": "suggestions"}, {"duration_ms": 701, "name": "policy_classifier"}, {"duration_ms": 5, "name": "prompt_assembly"}]}
2026-09-05T13:12:19.523602064Z 2026-09-05 13:12:19 [WARNING] backend.services.orchestration_service: orchestration.turn_trace_slow run_id=6e0d2afe5d5746c886500f2c42f2148d conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 summary={"cache_statuses": {"hot_memory:not_applicable": 1}, "conversation_id": "a3d0aa61-612f-4201-87f9-135851ec8031", "elapsed_ms": 10600, "is_slow": true, "main_model_started_ms": 2215, "model_calls": {"main_answer": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1}, "phase_durations_ms": {"hot_memory_snapshot": 3, "main_model": 7383, "parts_context": 0, "policy_classifier": 701, "prompt_assembly": 5, "search_routing": 1501, "suggestions": 1001, "turn_intake": 4, "visual_preflight": 0}, "provider_first_token_ms": 5202, "run_id": "6e0d2afe5d5746c886500f2c42f2148d", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 10600, "time_to_first_answer_ms": 7417, "tool_calls": {"hot_memory": 1}, "top_phase_durations": [{"duration_ms": 7383, "name": "main_model"}, {"duration_ms": 1501, "name": "search_routing"}, {"duration_ms": 1001, "name": "suggestions"}, {"duration_ms": 701, "name": "policy_classifier"}, {"duration_ms": 5, "name": "prompt_assembly"}]}
2026-09-05T13:12:19.52379512Z 2026-09-05 13:12:19 [INFO] services.post_turn_service: orchestration.post_turn_dispatched run_id=6e0d2afe5d5746c886500f2c42f2148d conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 reflection_durable=False evaluation_durable=False
2026-09-05T13:12:19.712038558Z 2026-09-05 13:12:19 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T13:12:19.795933073Z 2026-09-05 13:12:19 [INFO] backend.main: stream.request_accepted conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 response_mode=text message_count=8
2026-09-05T13:12:19.797682993Z INFO:     74.220.52.32:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-09-05T13:12:20.817370467Z 2026-09-05 13:12:20 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:20.991083794Z 2026-09-05 13:12:20 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:21.300785451Z 2026-09-05 13:12:21 [WARNING] agents.tutor_agent: Tutor routing fallback: TimeoutError
2026-09-05T13:12:21.302113119Z 2026-09-05 13:12:21 [INFO] backend.services.orchestration_service: orchestration.turn_plan_selected run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 route=GENERAL_CHAT enabled=True reason=GENERAL_CHAT max_foreground_model_calls=2
2026-09-05T13:12:21.309544469Z 2026-09-05 13:12:21 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['current_focus', 'current_focus_conversation_id']
2026-09-05T13:12:21.309675113Z 2026-09-05 13:12:21 [INFO] services.memory_ingestion.rules: memory.ingestion_decided user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 message_id=ef4950cee29789493b8f4b88 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 candidate_id=none state=working_context_only reason=ordinary_user_message_for_current_turn category=current_focus promoted=False
2026-09-05T13:12:21.309683123Z 2026-09-05 13:12:21 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 outcome=working_context_only reason=ordinary_user_message_for_current_turn
2026-09-05T13:12:21.676692162Z 2026-09-05 13:12:21 [INFO] memory_store: [MemoryStore] Published learner state snapshot v398 for user 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T13:12:22.011133549Z 2026-09-05 13:12:22 [WARNING] backend.services.orchestration_service: orchestration.dialogue_policy_timeout conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 fallback=NORMAL
2026-09-05T13:12:22.011331954Z 2026-09-05 13:12:22 [INFO] backend.services.orchestration_service: orchestration.response_policy_applied conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 source=timeout_fallback metadata={"answer_depth": "SCAFFOLDED", "attachment_reason": "NO_ATTACHMENT", "attachment_task": "NONE", "followup_mode": "OPTIONAL", "legacy_policy": "NORMAL", "structure": "STEP_BY_STEP", "task_intent": "GENERAL_QA", "tone": "TUTORING", "visual_reason": "NOT_NEEDED", "visual_support": "NONE"}
2026-09-05T13:12:22.011661113Z 2026-09-05 13:12:22 [INFO] services.orchestration.prompting: parts_context.rewrite_gate conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 enabled=False route=GENERAL_CHAT grounded=False allow_ungrounded=False
2026-09-05T13:12:22.011764406Z 2026-09-05 13:12:22 [INFO] services.conversation.parts: parts_context.rewrite_skipped route=GENERAL_CHAT reason=disabled_or_unavailable metadata={"confidence": "medium", "has_act": true, "has_composed_instruction": true, "has_persona": true, "has_recipient": true, "has_structure": true, "has_theme": true, "missing_field_count": 1}
2026-09-05T13:12:22.017065226Z 2026-09-05 13:12:22 [INFO] services.conversation.context: orchestration.long_term_memory_skipped reason=GENERAL_CHAT memory_reason=SUBSTANTIVE_QUERY
2026-09-05T13:12:22.017087387Z 2026-09-05 13:12:22 [INFO] services.orchestration.prompting: orchestration.context_prepared conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 learner_understanding=unknown retrieved_memory=False
2026-09-05T13:12:22.017136768Z 2026-09-05 13:12:22 [INFO] backend.services.orchestration_service: paper.auto_explain_policy_selected conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 enabled=True applied=False task=NONE reason=NO_ATTACHMENT pdf_count=0
2026-09-05T13:12:22.01720631Z 2026-09-05 13:12:22 [INFO] backend.services.orchestration_service: visual.preflight_policy_gate conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 allowed=False blocking_allowed=False trigger=policy_gate visual_support=NONE visual_reason=NOT_NEEDED explicit_visual=False known_affordance=False max_images=2 has_attachment_visual_sources=False
2026-09-05T13:12:22.017238271Z 2026-09-05 13:12:22 [INFO] backend.services.orchestration_service: visual.preflight_blocking_skipped conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 trigger=policy_gate visual_support=NONE explicit_visual=False known_affordance=False
2026-09-05T13:12:22.017265102Z 2026-09-05 13:12:22 [INFO] backend.services.orchestration_service: visual.preverified_inventory_ready conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 available_image_count=0 has_attachment_visual_sources=False
2026-09-05T13:12:22.017352674Z 2026-09-05 13:12:22 [INFO] services.conversation.stream: orchestration.stream_started conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 model=google/gemini-3.8-flash attachment_parser=False image_slot_cap=2 openrouter_session=True latency_routing=True
2026-09-05T13:12:23.740113091Z 2026-09-05 13:12:23 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:24.543654537Z 2026-09-05 13:12:24 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:25.665702259Z 2026-09-05 13:12:25 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:31.311440273Z 2026-09-05 13:12:31 [INFO] services.conversation.stream: orchestration.stream_completed conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 elapsed_ms=9293
2026-09-05T13:12:31.311648879Z 2026-09-05 13:12:31 [INFO] backend.services.orchestration_service: visual.answer_blocks_skipped conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 planned_image_slot_count=0 preverified_image_count=0
2026-09-05T13:12:31.311817253Z 2026-09-05 13:12:31 [INFO] services.suggestion_service: suggestions.requested language=繁體中文 model=google/gemini-2.5-flash-lite context_count=0
2026-09-05T13:12:32.186348529Z 2026-09-05 13:12:32 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:32.312623413Z 2026-09-05 13:12:32 [WARNING] services.post_turn_service: orchestration.suggestions_failed run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 language=en reason=TimeoutError
2026-09-05T13:12:32.313072486Z 2026-09-05 13:12:32 [INFO] backend.services.orchestration_service: orchestration.post_turn_queued run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031
2026-09-05T13:12:32.313300412Z 2026-09-05 13:12:32 [INFO] backend.services.orchestration_service: orchestration.turn_trace_completed run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 trace={'run_id': 'e570f73de63942ef80017f77ea895cd9', 'conversation_id': 'a3d0aa61-612f-4201-87f9-135851ec8031', 'elapsed_ms': 12515, 'phases': [{'name': 'request_accepted', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_started', 'elapsed_ms': 2, 'occurrence': 1}, {'name': 'search_routing_finished', 'elapsed_ms': 1504, 'occurrence': 1}, {'name': 'turn_plan_general_chat', 'elapsed_ms': 1504, 'occurrence': 1}, {'name': 'turn_intake_started', 'elapsed_ms': 1506, 'occurrence': 1}, {'name': 'turn_intake_finished', 'elapsed_ms': 1512, 'occurrence': 1}, {'name': 'policy_classifier_started', 'elapsed_ms': 1513, 'occurrence': 1}, {'name': 'rag_skipped', 'elapsed_ms': 1513, 'occurrence': 1}, {'name': 'policy_classifier_timeout', 'elapsed_ms': 2213, 'occurrence': 1}, {'name': 'prompt_assembly_started', 'elapsed_ms': 2214, 'occurrence': 1}, {'name': 'parts_context_started', 'elapsed_ms': 2214, 'occurrence': 1}, {'name': 'parts_context_finished', 'elapsed_ms': 2214, 'occurrence': 1}, {'name': 'hot_memory_snapshot_started', 'elapsed_ms': 2214, 'occurrence': 1}, {'name': 'hot_memory_snapshot_finished', 'elapsed_ms': 2218, 'occurrence': 1}, {'name': 'prompt_assembly_finished', 'elapsed_ms': 2219, 'occurrence': 1}, {'name': 'visual_preflight_started', 'elapsed_ms': 2219, 'occurrence': 1}, {'name': 'visual_preflight_finished', 'elapsed_ms': 2220, 'occurrence': 1}, {'name': 'main_model_started', 'elapsed_ms': 2220, 'occurrence': 1}, {'name': 'main_model_provider_request_started', 'elapsed_ms': 2220, 'occurrence': 1}, {'name': 'main_model_provider_stream_received', 'elapsed_ms': 4746, 'occurrence': 1}, {'name': 'first_answer_delta', 'elapsed_ms': 9173, 'occurrence': 1}, {'name': 'main_model_finished', 'elapsed_ms': 11514, 'occurrence': 1}, {'name': 'suggestions_started', 'elapsed_ms': 11514, 'occurrence': 1}, {'name': 'suggestions_failed', 'elapsed_ms': 12515, 'occurrence': 1}, {'name': 'post_turn_queued', 'elapsed_ms': 12515, 'occurrence': 1}, {'name': 'terminal_sent', 'elapsed_ms': 12515, 'occurrence': 1}], 'model_calls': {'main_answer': 1, 'policy_classifier': 1, 'search_routing': 1, 'suggestions': 1}, 'tool_calls': {'hot_memory': 1}, 'cache_statuses': {'hot_memory:not_applicable': 1}}
2026-09-05T13:12:32.313349464Z 2026-09-05 13:12:32 [INFO] backend.services.orchestration_service: orchestration.turn_trace_summary run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 summary={"cache_statuses": {"hot_memory:not_applicable": 1}, "conversation_id": "a3d0aa61-612f-4201-87f9-135851ec8031", "elapsed_ms": 12515, "is_slow": true, "main_model_started_ms": 2220, "model_calls": {"main_answer": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1}, "phase_durations_ms": {"hot_memory_snapshot": 4, "main_model": 9294, "parts_context": 0, "policy_classifier": 700, "prompt_assembly": 5, "search_routing": 1502, "suggestions": 1001, "turn_intake": 6, "visual_preflight": 1}, "provider_first_token_ms": 6953, "run_id": "e570f73de63942ef80017f77ea895cd9", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 12515, "time_to_first_answer_ms": 9173, "tool_calls": {"hot_memory": 1}, "top_phase_durations": [{"duration_ms": 9294, "name": "main_model"}, {"duration_ms": 1502, "name": "search_routing"}, {"duration_ms": 1001, "name": "suggestions"}, {"duration_ms": 700, "name": "policy_classifier"}, {"duration_ms": 6, "name": "turn_intake"}]}
2026-09-05T13:12:32.313433106Z 2026-09-05 13:12:32 [WARNING] backend.services.orchestration_service: orchestration.turn_trace_slow run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 summary={"cache_statuses": {"hot_memory:not_applicable": 1}, "conversation_id": "a3d0aa61-612f-4201-87f9-135851ec8031", "elapsed_ms": 12515, "is_slow": true, "main_model_started_ms": 2220, "model_calls": {"main_answer": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1}, "phase_durations_ms": {"hot_memory_snapshot": 4, "main_model": 9294, "parts_context": 0, "policy_classifier": 700, "prompt_assembly": 5, "search_routing": 1502, "suggestions": 1001, "turn_intake": 6, "visual_preflight": 1}, "provider_first_token_ms": 6953, "run_id": "e570f73de63942ef80017f77ea895cd9", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 12515, "time_to_first_answer_ms": 9173, "tool_calls": {"hot_memory": 1}, "top_phase_durations": [{"duration_ms": 9294, "name": "main_model"}, {"duration_ms": 1502, "name": "search_routing"}, {"duration_ms": 1001, "name": "suggestions"}, {"duration_ms": 700, "name": "policy_classifier"}, {"duration_ms": 6, "name": "turn_intake"}]}
2026-09-05T13:12:32.313664763Z 2026-09-05 13:12:32 [INFO] services.post_turn_service: orchestration.post_turn_dispatched run_id=e570f73de63942ef80017f77ea895cd9 conversation_id=a3d0aa61-612f-4201-87f9-135851ec8031 reflection_durable=False evaluation_durable=False
2026-09-05T13:12:33.796689053Z 2026-09-05 13:12:33 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:34.659219098Z 2026-09-05 13:12:34 [INFO] memory_store: [MemoryStore] Published learner state snapshot v399 for user 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T13:12:37.130509893Z 2026-09-05 13:12:37 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:38.705247329Z 2026-09-05 13:12:38 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:48.030725875Z 2026-09-05 13:12:48 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:51.387250648Z 2026-09-05 13:12:51 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:12:54.035588824Z 2026-09-05 13:12:54 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T13:37:19.00573644Z ==> Deploying...
2026-09-05T13:37:19.215793861Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-05T13:37:45.339340198Z INFO:     Started server process [62]
2026-09-05T13:37:45.339522933Z INFO:     Waiting for application startup.
2026-09-05T13:37:45.358667567Z 2026-09-05 13:37:45 [INFO] redis_client: Successfully connected to Redis.
2026-09-05T13:37:45.507088959Z 2026-09-05 13:37:45 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-05T13:37:45.528301462Z 2026-09-05 13:37:45 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-05T13:37:45.528318282Z 2026-09-05 13:37:45 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-05T13:37:45.528329572Z 2026-09-05 13:37:45 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-05T13:37:45.528345773Z 2026-09-05 13:37:45 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-05T13:37:48.453032579Z 2026-09-05 13:37:48 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-05T13:37:48.455789116Z 2026-09-05 13:37:48 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-05T13:37:48.514293939Z 2026-09-05 13:37:48 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-05T13:37:48.519284128Z 2026-09-05 13:37:48 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-05T13:37:48.519390671Z 2026-09-05 13:37:48 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-05T13:37:48.519492384Z 2026-09-05 13:37:48 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-a2308af1671e457fb04fd6d44295f354
2026-09-05T13:37:48.519514685Z 2026-09-05 13:37:48 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-a2308af1671e457fb04fd6d44295f354
2026-09-05T13:37:48.726871702Z INFO:     Application startup complete.
2026-09-05T13:37:48.726895352Z 2026-09-05 13:37:48 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-05T13:37:48.727039116Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-05T13:37:48.98300597Z Memory Store initialized successfully.
2026-09-05T13:37:48.983024521Z Mailbox Store initialized successfully.
2026-09-05T13:37:48.983028021Z Agent Job Store initialized successfully.
2026-09-05T13:37:48.983031141Z Redis RAG Cache initialized successfully.
2026-09-05T13:37:48.983034071Z INFO:     127.0.0.1:58886 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-05T13:37:49.875333052Z ==> Your service is live 🎉
2026-09-05T13:37:50.079310644Z ==> 
2026-09-05T13:37:50.081497834Z ==> ///////////////////////////////////////////////////////////
2026-09-05T13:37:50.083605819Z ==> 
2026-09-05T13:37:50.085668619Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-05T13:37:50.087732022Z ==> 
2026-09-05T13:37:50.091931526Z ==> ///////////////////////////////////////////////////////////
2026-09-05T13:37:50.307522446Z INFO:     35.230.76.60:0 - "GET / HTTP/1.1" 404 Not Found
2026-09-05T13:38:49.200161275Z INFO:     Shutting down
2026-09-05T13:38:49.300657546Z INFO:     Waiting for application shutdown.
2026-09-05T13:38:49.300985355Z INFO:     Application shutdown complete.
2026-09-05T13:38:49.301061157Z INFO:     Finished server process [62]
2026-09-05T13:42:56.448225147Z ==> Detected service running on port 10000
2026-09-05T13:42:56.812833802Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-05T13:43:18.947983223Z 2026-09-05 13:43:18 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-05T13:43:18.948289442Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-05T13:43:40.98936868Z 2026-09-05 13:43:40 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T13:43:41.072902811Z 2026-09-05 13:43:41 [INFO] backend.main: realtime.session_create_started conversation_id=25b6dfa5-f078-4fa9-8038-636c5eedc473 authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-05T13:43:42.140732147Z 2026-09-05 13:43:42 [INFO] backend.main: realtime.session_create_completed conversation_id=25b6dfa5-f078-4fa9-8038-636c5eedc473 model=gpt-realtime-2.1-mini elapsed_ms=1067
2026-09-05T13:43:42.144161252Z INFO:     74.220.52.215:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-05T14:04:30.9896443Z ==> Deploying...
2026-09-05T14:04:31.200761263Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-05T14:05:01.280636272Z 2026-09-05 14:05:01 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-05T14:05:01.281592746Z 2026-09-05 14:05:01 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-05T14:05:01.284104059Z 2026-09-05 14:05:01 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-05T14:05:01.289236477Z 2026-09-05 14:05:01 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-05T14:05:01.289431082Z 2026-09-05 14:05:01 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-05T14:05:01.289567756Z 2026-09-05 14:05:01 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-f4ffc5da2d7f4155b9f0e0671ea26faa
2026-09-05T14:05:01.289577676Z 2026-09-05 14:05:01 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-f4ffc5da2d7f4155b9f0e0671ea26faa
2026-09-05T14:05:01.768296797Z INFO:     Application startup complete.
2026-09-05T14:05:01.768330388Z 2026-09-05 14:05:01 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-05T14:05:01.768335798Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-05T14:05:02.036988928Z Memory Store initialized successfully.
2026-09-05T14:05:02.037012079Z Mailbox Store initialized successfully.
2026-09-05T14:05:02.037015399Z Agent Job Store initialized successfully.
2026-09-05T14:05:02.037018469Z Redis RAG Cache initialized successfully.
2026-09-05T14:05:02.037021039Z INFO:     127.0.0.1:43688 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-05T14:05:12.123639017Z ==> Your service is live 🎉
2026-09-05T14:05:12.403292511Z ==> 
2026-09-05T14:05:12.406001297Z ==> ///////////////////////////////////////////////////////////
2026-09-05T14:05:12.40803735Z ==> 
2026-09-05T14:05:12.410014436Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-05T14:05:12.412278186Z ==> 
2026-09-05T14:05:12.414496634Z ==> ///////////////////////////////////////////////////////////
2026-09-05T14:05:12.53071718Z INFO:     35.197.117.9:0 - "GET / HTTP/1.1" 404 Not Found
2026-09-05T14:05:46.338692623Z 2026-09-05 14:05:46 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-05T14:05:46.339167115Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-05T14:05:55.077611625Z 2026-09-05 14:05:55 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T14:05:55.191172083Z 2026-09-05 14:05:55 [INFO] backend.main: realtime.session_create_started conversation_id=0680b66b-3af7-4713-998b-d24f40993eeb authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-05T14:05:55.580952536Z 2026-09-05 14:05:55 [INFO] backend.main: realtime.session_create_completed conversation_id=0680b66b-3af7-4713-998b-d24f40993eeb model=gpt-realtime-2.1-mini elapsed_ms=389
2026-09-05T14:05:55.581361206Z INFO:     74.220.52.215:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-05T14:06:11.223751151Z INFO:     Shutting down
2026-09-05T14:06:11.324313488Z INFO:     Waiting for application shutdown.
2026-09-05T14:06:11.324523984Z INFO:     Application shutdown complete.
2026-09-05T14:06:11.324593775Z INFO:     Finished server process [62]
2026-09-05T14:07:34.12865053Z 2026-09-05 14:07:34 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T14:07:34.576474682Z 2026-09-05 14:07:34 [INFO] backend.main: realtime.session_create_started conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-05T14:07:34.976197209Z 2026-09-05 14:07:34 [INFO] backend.main: realtime.session_create_completed conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 model=gpt-realtime-2.1-mini elapsed_ms=399
2026-09-05T14:07:34.976534158Z INFO:     74.220.52.215:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-05T14:10:11.963657945Z ==> Detected service running on port 10000
2026-09-05T14:10:12.332419328Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-05T14:31:03.499711882Z INFO:     111.80.45.81:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-05T14:31:03.499779263Z 2026-09-05 14:31:03 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-05T14:31:52.618839777Z 2026-09-05 14:31:52 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T14:31:52.977147268Z 2026-09-05 14:31:52 [INFO] backend.main: realtime.session_create_started conversation_id=b8e4a0b8-e0db-4766-aea5-ce1a443bba77 authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-05T14:31:54.305303213Z 2026-09-05 14:31:54 [INFO] backend.main: realtime.session_create_completed conversation_id=b8e4a0b8-e0db-4766-aea5-ce1a443bba77 model=gpt-realtime-2.1-mini elapsed_ms=1328
2026-09-05T14:31:54.305688853Z INFO:     74.220.52.217:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-05T14:33:12.789745136Z 2026-09-05 14:33:12 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-05T14:33:12.790065164Z INFO:     111.80.45.81:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-05T14:33:38.313242126Z 2026-09-05 14:33:38 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T14:33:38.633901178Z 2026-09-05 14:33:38 [INFO] backend.main: realtime.session_create_started conversation_id=5647b2c3-dacf-4872-94a4-792dd6b33f72 authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-05T14:33:39.043824045Z 2026-09-05 14:33:39 [INFO] backend.main: realtime.session_create_completed conversation_id=5647b2c3-dacf-4872-94a4-792dd6b33f72 model=gpt-realtime-2.1-mini elapsed_ms=409
2026-09-05T14:33:39.044194045Z INFO:     74.220.52.217:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-05T14:54:58.89428893Z INFO:     Shutting down
2026-09-05T14:54:58.99473995Z INFO:     Waiting for application shutdown.
2026-09-05T14:54:58.994964986Z INFO:     Application shutdown complete.
2026-09-05T14:54:58.994990217Z INFO:     Finished server process [59]
2026-09-06T00:21:14.172219712Z ==> Deploying...
2026-09-06T00:21:14.374583542Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-06T00:21:33.703659554Z ==> Running 'python -m uvicorn main:app --host 0.0.0.0 --port $PORT'
2026-09-06T00:21:38.41104347Z INFO:     Started server process [62]
2026-09-06T00:21:38.411069011Z INFO:     Waiting for application startup.
2026-09-06T00:21:38.423646667Z 2026-09-06 00:21:38 [INFO] redis_client: Successfully connected to Redis.
2026-09-06T00:21:38.550478481Z 2026-09-06 00:21:38 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-06T00:21:38.560774578Z 2026-09-06 00:21:38 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-06T00:21:38.560793179Z 2026-09-06 00:21:38 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-06T00:21:38.560829309Z 2026-09-06 00:21:38 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-06T00:21:38.560868361Z 2026-09-06 00:21:38 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-06T00:21:41.530632668Z 2026-09-06 00:21:41 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-06T00:21:41.533061751Z 2026-09-06 00:21:41 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-06T00:21:41.5407579Z 2026-09-06 00:21:41 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-06T00:21:41.596071203Z 2026-09-06 00:21:41 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-06T00:21:41.596201796Z 2026-09-06 00:21:41 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-06T00:21:41.59633079Z 2026-09-06 00:21:41 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-e712e87c60a541b187b931547b56e7ae
2026-09-06T00:21:41.59635585Z 2026-09-06 00:21:41 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-e712e87c60a541b187b931547b56e7ae
2026-09-06T00:21:41.713691989Z INFO:     Application startup complete.
2026-09-06T00:21:41.713779071Z 2026-09-06 00:21:41 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-06T00:21:41.713960456Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-06T00:21:42.134945708Z Memory Store initialized successfully.
2026-09-06T00:21:42.134964959Z Mailbox Store initialized successfully.
2026-09-06T00:21:42.134993919Z Agent Job Store initialized successfully.
2026-09-06T00:21:42.13500354Z Redis RAG Cache initialized successfully.
2026-09-06T00:21:42.13500771Z INFO:     127.0.0.1:47366 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-06T00:21:44.874685784Z ==> Your service is live 🎉
2026-09-06T00:21:45.083255029Z ==> 
2026-09-06T00:21:45.086560455Z ==> ///////////////////////////////////////////////////////////
2026-09-06T00:21:45.089132259Z ==> 
2026-09-06T00:21:45.091570816Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-06T00:21:45.093931528Z ==> 
2026-09-06T00:21:45.096687903Z ==> ///////////////////////////////////////////////////////////