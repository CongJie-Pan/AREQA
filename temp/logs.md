2026-09-13T09:56:38.64579044Z 2026-09-13 09:56:38 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-13T09:56:38.645808771Z 2026-09-13 09:56:38 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-13T09:56:38.645823801Z 2026-09-13 09:56:38 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-13T09:56:38.645830082Z 2026-09-13 09:56:38 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-13T09:56:41.760153114Z 2026-09-13 09:56:41 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-13T09:56:41.76117953Z 2026-09-13 09:56:41 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-13T09:56:41.76422633Z 2026-09-13 09:56:41 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-13T09:56:41.775504735Z 2026-09-13 09:56:41 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-13T09:56:41.775525045Z 2026-09-13 09:56:41 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-13T09:56:41.775529385Z 2026-09-13 09:56:41 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-bbfdfa83fde04210a7329339491aae61
2026-09-13T09:56:41.775532015Z 2026-09-13 09:56:41 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-bbfdfa83fde04210a7329339491aae61
2026-09-13T09:56:42.165348959Z INFO:     Application startup complete.
2026-09-13T09:56:42.165458922Z 2026-09-13 09:56:42 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-13T09:56:42.165634807Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-13T09:56:42.748075873Z Memory Store initialized successfully.
2026-09-13T09:56:42.748118224Z Mailbox Store initialized successfully.
2026-09-13T09:56:42.748121934Z Agent Job Store initialized successfully.
2026-09-13T09:56:42.748124624Z Redis RAG Cache initialized successfully.
2026-09-13T09:56:42.748126994Z INFO:     127.0.0.1:56400 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-13T09:56:49.797457804Z ==> Your service is live 🎉
2026-09-13T09:56:49.938286223Z [EDF-LOG] evaluate_student_state: LLM returned state: TINKERING, strategy: 引導反思與概念釐清，透過對比統計研究與質性研究的差異，協助學習者建立對研究方法的分類架構。, trigger_proactive: False
2026-09-13T09:56:49.938325234Z INFO:     35.197.36.229:0 - "GET / HTTP/1.1" 404 Not Found
2026-09-13T09:56:50.015526397Z ==> 
2026-09-13T09:56:50.018760345Z ==> ///////////////////////////////////////////////////////////
2026-09-13T09:56:50.021342477Z ==> 
2026-09-13T09:56:50.023982811Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-13T09:56:50.026724247Z ==> 
2026-09-13T09:56:50.02934344Z ==> ///////////////////////////////////////////////////////////
2026-09-13T09:57:37.184111225Z 2026-09-13 09:57:37 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-13T09:57:37.184494295Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-13T09:57:49.143325711Z INFO:     Shutting down
2026-09-13T09:57:49.243849698Z INFO:     Waiting for application shutdown.
2026-09-13T09:57:49.244265917Z INFO:     Application shutdown complete.
2026-09-13T09:57:49.244317228Z INFO:     Finished server process [59]
2026-09-13T09:58:07.942036901Z 2026-09-13 09:58:07 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-13T09:58:08.019879441Z 2026-09-13 09:58:08 [INFO] backend.main: realtime.debug.session_config_built conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-13T09:58:08.019907272Z 2026-09-13 09:58:08 [INFO] backend.main: realtime.session_create_started conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-13T09:58:08.019918822Z 2026-09-13 09:58:08 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-13T09:58:09.179451106Z 2026-09-13 09:58:09 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 status=200 elapsed_ms=1159
2026-09-13T09:58:09.179528178Z 2026-09-13 09:58:09 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 expires_at_present=True client_secret_present=True
2026-09-13T09:58:09.179536358Z 2026-09-13 09:58:09 [INFO] backend.main: realtime.session_create_completed conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=1159
2026-09-13T09:58:09.179892668Z INFO:     74.220.52.217:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-13T09:58:19.662872804Z 2026-09-13 09:58:19 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-13T09:58:19.756039699Z 2026-09-13 09:58:19 [INFO] backend.main: stream.request_accepted conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 response_mode=text message_count=29
2026-09-13T09:58:19.991318206Z 2026-09-13 09:58:19 [INFO] backend.services.orchestration_service: orchestration.auto_web_search_disabled conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953
2026-09-13T09:58:19.991970363Z Internal RAG disabled. Set ENABLE_INTERNAL_RAG=true to enable local retrieval.
2026-09-13T09:58:19.991979733Z INFO:     74.220.52.217:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-09-13T09:58:20.043478766Z 2026-09-13 09:58:20 [INFO] backend.services.orchestration_service: orchestration.turn_plan_selected run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 route=RAG_EXPLICIT enabled=True reason=RAG_EXPLICIT_REQUEST max_foreground_model_calls=3
2026-09-13T09:58:20.06708071Z 2026-09-13 09:58:20 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['current_focus', 'current_focus_conversation_id']
2026-09-13T09:58:20.067115911Z 2026-09-13 09:58:20 [INFO] services.memory_ingestion.rules: memory.ingestion_decided user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 message_id=3b22e4804e1f3db762ad96fd conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 candidate_id=none state=working_context_only reason=interrogative_not_memory_evidence category=current_focus promoted=False
2026-09-13T09:58:20.067176433Z 2026-09-13 09:58:20 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 outcome=working_context_only reason=interrogative_not_memory_evidence
2026-09-13T09:58:21.765013738Z 2026-09-13 09:58:21 [WARNING] backend.services.orchestration_service: orchestration.dialogue_policy_timeout conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 fallback=NORMAL
2026-09-13T09:58:21.765183373Z 2026-09-13 09:58:21 [INFO] backend.services.orchestration_service: orchestration.response_policy_applied conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 source=timeout_fallback metadata={"answer_depth": "SCAFFOLDED", "attachment_reason": "NO_ATTACHMENT", "attachment_task": "NONE", "evidence_mode": "NONE", "followup_mode": "OPTIONAL", "learning_technique": "NONE", "legacy_policy": "NORMAL", "structure": "STEP_BY_STEP", "task_intent": "GENERAL_QA", "tone": "TUTORING", "visual_reason": "NOT_NEEDED", "visual_support": "NONE"}
2026-09-13T09:58:21.765698066Z 2026-09-13 09:58:21 [INFO] services.orchestration.prompting: parts_context.rewrite_gate conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 enabled=True route=RAG_EXPLICIT grounded=True allow_ungrounded=False
2026-09-13T09:58:23.329184765Z 2026-09-13 09:58:23 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:24.061316467Z 2026-09-13 09:58:24 [INFO] services.conversation.parts: parts_context.rewrite_selected route=RAG_EXPLICIT metadata={"confidence": "high", "has_act": true, "has_composed_instruction": true, "has_persona": true, "has_recipient": true, "has_structure": true, "has_theme": true, "missing_field_count": 1}
2026-09-13T09:58:24.071891774Z 2026-09-13 09:58:24 [WARNING] persistqueue.queue: Default tempdir '/tmp/tmpn_powrt3' is not on the same filesystem with queue path '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue',defaulting to '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue'.
2026-09-13T09:58:24.808108163Z 2026-09-13 09:58:24 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:25.229905776Z 2026-09-13 09:58:25 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:26.122188263Z 2026-09-13 09:58:26 [INFO] services.conversation.context: orchestration.long_term_memory_retrieval_summary conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 summary={"cache_status": "not_applicable", "elapsed_ms": 2054, "outcome": "retrieved", "result_count_bucket": "1", "route_reason": "substantive_query", "steps": [{"duration_ms": 4, "name": "cold_memory_learner_state", "outcome": "completed"}, {"duration_ms": 891, "name": "cold_memory_zpd_query", "outcome": "completed"}, {"duration_ms": 68, "name": "cold_memory_table_availability", "outcome": "completed"}, {"duration_ms": 1683, "name": "working_memory", "outcome": "completed"}, {"duration_ms": 904, "name": "cold_memory_embedding", "outcome": "completed"}, {"duration_ms": 112, "name": "cold_memory_vector_search", "outcome": "completed"}, {"duration_ms": 62, "name": "cold_memory_bm25_search", "outcome": "completed"}, {"duration_ms": 0, "name": "cold_memory_rrf_fusion", "outcome": "count_0"}, {"duration_ms": 6, "name": "cold_memory_fetch_documents", "outcome": "count_0"}, {"duration_ms": 1156, "name": "cold_memory_search", "outcome": "completed"}, {"duration_ms": 2054, "name": "cold_memory", "outcome": "completed"}], "top_steps": [{"duration_ms": 2054, "name": "cold_memory", "outcome": "completed"}, {"duration_ms": 1683, "name": "working_memory", "outcome": "completed"}, {"duration_ms": 1156, "name": "cold_memory_search", "outcome": "completed"}, {"duration_ms": 904, "name": "cold_memory_embedding", "outcome": "completed"}, {"duration_ms": 891, "name": "cold_memory_zpd_query", "outcome": "completed"}], "truncated": false}
2026-09-13T09:58:26.122220604Z 2026-09-13 09:58:26 [INFO] services.orchestration.prompting: orchestration.context_prepared conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 learner_understanding=unknown retrieved_memory=False
2026-09-13T09:58:26.122325507Z 2026-09-13 09:58:26 [INFO] backend.services.orchestration_service: paper.auto_explain_policy_selected conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 enabled=True applied=False task=NONE reason=NO_ATTACHMENT pdf_count=0
2026-09-13T09:58:26.122559913Z 2026-09-13 09:58:26 [INFO] backend.services.orchestration_service: visual.preflight_policy_gate conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 allowed=False blocking_allowed=False trigger=policy_gate visual_support=NONE visual_reason=NOT_NEEDED explicit_visual=False known_affordance=False max_images=2 has_attachment_visual_sources=False
2026-09-13T09:58:26.122586974Z 2026-09-13 09:58:26 [INFO] backend.services.orchestration_service: visual.preflight_blocking_skipped conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 trigger=policy_gate visual_support=NONE explicit_visual=False known_affordance=False
2026-09-13T09:58:26.122620575Z 2026-09-13 09:58:26 [INFO] backend.services.orchestration_service: visual.preverified_inventory_ready conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 available_image_count=0 has_attachment_visual_sources=False
2026-09-13T09:58:26.122766679Z 2026-09-13 09:58:26 [INFO] services.conversation.stream: orchestration.stream_started conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 model=google/gemini-3.8-flash attachment_parser=False image_slot_cap=2 openrouter_session=True latency_routing=True
2026-09-13T09:58:28.389870564Z 2026-09-13 09:58:28 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:40.830049074Z 2026-09-13 09:58:40 [INFO] services.conversation.stream: orchestration.stream_completed conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 elapsed_ms=14707
2026-09-13T09:58:40.830346692Z 2026-09-13 09:58:40 [INFO] backend.services.orchestration_service: visual.answer_blocks_skipped conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 planned_image_slot_count=0 preverified_image_count=0
2026-09-13T09:58:40.830544957Z 2026-09-13 09:58:40 [INFO] services.suggestion_service: suggestions.requested language=繁體中文 model=google/gemini-2.5-flash-lite context_count=0
2026-09-13T09:58:41.660276747Z 2026-09-13 09:58:41 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:41.831941688Z 2026-09-13 09:58:41 [WARNING] services.post_turn_service: orchestration.suggestions_failed run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 language=en reason=TimeoutError
2026-09-13T09:58:41.832321368Z 2026-09-13 09:58:41 [INFO] backend.services.orchestration_service: orchestration.post_turn_queued run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953
2026-09-13T09:58:41.832562324Z 2026-09-13 09:58:41 [INFO] backend.services.orchestration_service: orchestration.turn_trace_completed run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 trace={'run_id': 'f925500e660449f4b0b793da03c6fb69', 'conversation_id': 'b94e83a5-81d7-44c0-8db6-1712947b6953', 'elapsed_ms': 21841, 'phases': [{'name': 'request_accepted', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_started', 'elapsed_ms': 51, 'occurrence': 1}, {'name': 'search_routing_finished', 'elapsed_ms': 51, 'occurrence': 1}, {'name': 'turn_plan_rag_explicit', 'elapsed_ms': 51, 'occurrence': 1}, {'name': 'turn_intake_started', 'elapsed_ms': 52, 'occurrence': 1}, {'name': 'turn_intake_finished', 'elapsed_ms': 78, 'occurrence': 1}, {'name': 'policy_classifier_started', 'elapsed_ms': 79, 'occurrence': 1}, {'name': 'rag_skipped', 'elapsed_ms': 79, 'occurrence': 1}, {'name': 'policy_classifier_timeout', 'elapsed_ms': 1773, 'occurrence': 1}, {'name': 'prompt_assembly_started', 'elapsed_ms': 1774, 'occurrence': 1}, {'name': 'parts_context_started', 'elapsed_ms': 1774, 'occurrence': 1}, {'name': 'parts_context_finished', 'elapsed_ms': 4069, 'occurrence': 1}, {'name': 'hot_memory_snapshot_started', 'elapsed_ms': 4071, 'occurrence': 1}, {'name': 'hot_memory_snapshot_finished', 'elapsed_ms': 4074, 'occurrence': 1}, {'name': 'long_term_memory_started', 'elapsed_ms': 4075, 'occurrence': 1}, {'name': 'long_term_memory_finished', 'elapsed_ms': 6130, 'occurrence': 1}, {'name': 'prompt_assembly_finished', 'elapsed_ms': 6130, 'occurrence': 1}, {'name': 'visual_preflight_started', 'elapsed_ms': 6130, 'occurrence': 1}, {'name': 'visual_preflight_finished', 'elapsed_ms': 6131, 'occurrence': 1}, {'name': 'main_model_started', 'elapsed_ms': 6131, 'occurrence': 1}, {'name': 'main_model_provider_request_started', 'elapsed_ms': 6131, 'occurrence': 1}, {'name': 'main_model_provider_stream_received', 'elapsed_ms': 8398, 'occurrence': 1}, {'name': 'first_answer_delta', 'elapsed_ms': 16454, 'occurrence': 1}, {'name': 'main_model_finished', 'elapsed_ms': 20838, 'occurrence': 1}, {'name': 'suggestions_started', 'elapsed_ms': 20838, 'occurrence': 1}, {'name': 'suggestions_failed', 'elapsed_ms': 21840, 'occurrence': 1}, {'name': 'post_turn_queued', 'elapsed_ms': 21840, 'occurrence': 1}, {'name': 'terminal_sent', 'elapsed_ms': 21840, 'occurrence': 1}], 'model_calls': {'main_answer': 1, 'parts_context_rewrite': 1, 'policy_classifier': 1, 'suggestions': 1}, 'tool_calls': {'hot_memory': 1, 'memory_query': 1}, 'cache_statuses': {'hot_memory:not_applicable': 1, 'memory_query:not_applicable': 1}}
2026-09-13T09:58:41.832628136Z 2026-09-13 09:58:41 [INFO] backend.services.orchestration_service: orchestration.turn_trace_summary run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 summary={"cache_statuses": {"hot_memory:not_applicable": 1, "memory_query:not_applicable": 1}, "conversation_id": "b94e83a5-81d7-44c0-8db6-1712947b6953", "elapsed_ms": 21840, "is_slow": true, "main_model_started_ms": 6131, "model_calls": {"main_answer": 1, "parts_context_rewrite": 1, "policy_classifier": 1, "suggestions": 1}, "phase_durations_ms": {"hot_memory_snapshot": 3, "long_term_memory": 2055, "main_model": 14707, "parts_context": 2295, "policy_classifier": 1694, "prompt_assembly": 4356, "search_routing": 0, "suggestions": 1002, "turn_intake": 26, "visual_preflight": 1}, "provider_first_token_ms": 10323, "run_id": "f925500e660449f4b0b793da03c6fb69", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 21840, "time_to_first_answer_ms": 16454, "tool_calls": {"hot_memory": 1, "memory_query": 1}, "top_phase_durations": [{"duration_ms": 14707, "name": "main_model"}, {"duration_ms": 4356, "name": "prompt_assembly"}, {"duration_ms": 2295, "name": "parts_context"}, {"duration_ms": 2055, "name": "long_term_memory"}, {"duration_ms": 1694, "name": "policy_classifier"}]}
2026-09-13T09:58:41.832692098Z 2026-09-13 09:58:41 [WARNING] backend.services.orchestration_service: orchestration.turn_trace_slow run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 summary={"cache_statuses": {"hot_memory:not_applicable": 1, "memory_query:not_applicable": 1}, "conversation_id": "b94e83a5-81d7-44c0-8db6-1712947b6953", "elapsed_ms": 21840, "is_slow": true, "main_model_started_ms": 6131, "model_calls": {"main_answer": 1, "parts_context_rewrite": 1, "policy_classifier": 1, "suggestions": 1}, "phase_durations_ms": {"hot_memory_snapshot": 3, "long_term_memory": 2055, "main_model": 14707, "parts_context": 2295, "policy_classifier": 1694, "prompt_assembly": 4356, "search_routing": 0, "suggestions": 1002, "turn_intake": 26, "visual_preflight": 1}, "provider_first_token_ms": 10323, "run_id": "f925500e660449f4b0b793da03c6fb69", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 21840, "time_to_first_answer_ms": 16454, "tool_calls": {"hot_memory": 1, "memory_query": 1}, "top_phase_durations": [{"duration_ms": 14707, "name": "main_model"}, {"duration_ms": 4356, "name": "prompt_assembly"}, {"duration_ms": 2295, "name": "parts_context"}, {"duration_ms": 2055, "name": "long_term_memory"}, {"duration_ms": 1694, "name": "policy_classifier"}]}
2026-09-13T09:58:41.832908903Z 2026-09-13 09:58:41 [INFO] services.post_turn_service: orchestration.post_turn_dispatched run_id=f925500e660449f4b0b793da03c6fb69 conversation_id=b94e83a5-81d7-44c0-8db6-1712947b6953 reflection_durable=False evaluation_durable=False
2026-09-13T09:58:42.762946608Z 2026-09-13 09:58:42 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:43.152840099Z 2026-09-13 09:58:43 [INFO] memory_store: [MemoryStore] Published learner state snapshot v463 for user 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-13T09:58:45.722524365Z 2026-09-13 09:58:45 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:47.280520689Z 2026-09-13 09:58:47 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:55.232343827Z 2026-09-13 09:58:55 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:58:57.96821968Z 2026-09-13 09:58:57 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T09:59:01.290760971Z 2026-09-13 09:59:01 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T10:01:48.023298485Z ==> Detected service running on port 10000
2026-09-13T10:01:48.730369032Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-13T10:04:23.711465082Z 2026-09-13 10:04:23 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-13T10:04:23.71177893Z [GUM] Initializing new GUM instance for user 39bcc4a1-6be9-4817-80ae-9f5257721717...
2026-09-13T10:04:23.71179089Z [EDF-LOG] evaluate_student_state: LLM returned state: TINKERING, strategy: 提供具體步驟與結構化分析，將複雜的方法論拆解為輸入層、特徵提取層與校準層，並引導學生建立系統性架構的認知。, trigger_proactive: False
2026-09-13T10:04:23.71179866Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-13T10:31:43.868428221Z 2026-09-13 10:31:43 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-13T10:31:44.969334435Z 2026-09-13 10:31:44 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['session_summary']
2026-09-13T10:31:44.975121717Z 2026-09-13 10:31:44 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['session_summary']
2026-09-13T10:31:44.98024208Z 2026-09-13 10:31:44 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['session_summary']
2026-09-13T10:31:44.985681712Z 2026-09-13 10:31:44 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['session_summary']
2026-09-13T10:31:44.990854027Z 2026-09-13 10:31:44 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['session_summary']
2026-09-13T10:32:36.751013667Z INFO:     Shutting down
2026-09-13T10:32:36.852110048Z INFO:     Waiting for application shutdown.
2026-09-13T10:32:36.852132578Z INFO:     Application shutdown complete.
2026-09-13T10:32:36.852151069Z INFO:     Finished server process [61]
2026-09-14T08:14:08.478032639Z ==> Deploying...
2026-09-14T08:14:08.690285811Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-14T08:14:39.938278503Z INFO:     Started server process [61]
2026-09-14T08:14:39.938318304Z INFO:     Waiting for application startup.
2026-09-14T08:14:39.954674731Z 2026-09-14 08:14:39 [INFO] redis_client: Successfully connected to Redis.
2026-09-14T08:14:40.104641458Z 2026-09-14 08:14:40 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-14T08:14:40.116668673Z 2026-09-14 08:14:40 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-14T08:14:40.116688493Z 2026-09-14 08:14:40 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-14T08:14:40.116704714Z 2026-09-14 08:14:40 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-14T08:14:40.116711254Z 2026-09-14 08:14:40 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-14T08:14:44.152442836Z 2026-09-14 08:14:44 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-14T08:14:44.15566903Z 2026-09-14 08:14:44 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-14T08:14:44.163478594Z 2026-09-14 08:14:44 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-14T08:14:44.168074984Z 2026-09-14 08:14:44 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-14T08:14:44.168180267Z 2026-09-14 08:14:44 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-14T08:14:44.16830272Z 2026-09-14 08:14:44 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-9138a3cad91b48cf9e6582bd373f7347
2026-09-14T08:14:44.16831193Z 2026-09-14 08:14:44 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-9138a3cad91b48cf9e6582bd373f7347
2026-09-14T08:14:44.341012692Z INFO:     Application startup complete.
2026-09-14T08:14:44.341065893Z 2026-09-14 08:14:44 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-14T08:14:44.341282349Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-14T08:14:45.211317446Z Memory Store initialized successfully.
2026-09-14T08:14:45.211346567Z Mailbox Store initialized successfully.
2026-09-14T08:14:45.211371557Z Agent Job Store initialized successfully.
2026-09-14T08:14:45.211380248Z Redis RAG Cache initialized successfully.
2026-09-14T08:14:45.211383798Z INFO:     127.0.0.1:36918 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-14T08:14:49.446380727Z ==> Your service is live 🎉
2026-09-14T08:14:49.668748933Z ==> 
2026-09-14T08:14:49.676656969Z ==> ///////////////////////////////////////////////////////////
2026-09-14T08:14:49.681753506Z ==> 
2026-09-14T08:14:49.687793467Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-14T08:14:49.696331898Z ==> 
2026-09-14T08:14:49.700176285Z ==> ///////////////////////////////////////////////////////////
2026-09-14T08:17:15.636013133Z 2026-09-14 08:17:15 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-14T08:17:15.636345031Z INFO:     140.122.53.14:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-14T08:19:51.443495108Z ==> Detected service running on port 10000
2026-09-14T08:19:51.805633257Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-14T08:40:34.286650205Z 2026-09-14 08:40:34 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-14T08:40:34.29259984Z INFO:     116.59.119.170:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-14T08:42:26.740721535Z 2026-09-14 08:42:26 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-14T08:42:26.915513094Z 2026-09-14 08:42:26 [INFO] backend.main: realtime.debug.session_config_built conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-14T08:42:26.915540375Z 2026-09-14 08:42:26 [INFO] backend.main: realtime.session_create_started conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-14T08:42:26.915569796Z 2026-09-14 08:42:26 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-14T08:42:28.241561543Z 2026-09-14 08:42:28 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a status=200 elapsed_ms=1326
2026-09-14T08:42:28.241616444Z 2026-09-14 08:42:28 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a expires_at_present=True client_secret_present=True
2026-09-14T08:42:28.241646825Z 2026-09-14 08:42:28 [INFO] backend.main: realtime.session_create_completed conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=1326
2026-09-14T08:42:28.241975954Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-14T08:43:01.943851353Z 2026-09-14 08:43:01 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-14T08:43:02.410407312Z 2026-09-14 08:43:02 [WARNING] persistqueue.queue: Default tempdir '/tmp/tmp1v6jk2xp' is not on the same filesystem with queue path '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue',defaulting to '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue'.
2026-09-14T08:43:02.834782588Z 2026-09-14 08:43:02 [INFO] backend.main: livekit.debug.avatar_session_token_created conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a room_name=areqa-live-34c785bde7f48a9a agent_name=areqa-live-tutor authenticated=True ttl_seconds=900 supplied_message_count=4 memory_count=2 elapsed_ms=664
2026-09-14T08:43:02.834814699Z 2026-09-14 08:43:02 [INFO] backend.main: livekit.avatar_session_created conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a room_name=areqa-live-34c785bde7f48a9a agent_name=areqa-live-tutor authenticated=True elapsed_ms=665
2026-09-14T08:43:02.83638396Z [GUM] Initializing new GUM instance for user 39bcc4a1-6be9-4817-80ae-9f5257721717...
2026-09-14T08:43:02.836399811Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/livekit-avatar-session HTTP/1.1" 200 OK
2026-09-14T08:44:42.770188685Z 2026-09-14 08:44:42 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-14T08:44:43.113489422Z 2026-09-14 08:44:43 [INFO] backend.main: realtime.debug.session_config_built conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-14T08:44:43.113521053Z 2026-09-14 08:44:43 [INFO] backend.main: realtime.session_create_started conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-14T08:44:43.113555904Z 2026-09-14 08:44:43 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-14T08:44:44.027419006Z 2026-09-14 08:44:44 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a status=200 elapsed_ms=913
2026-09-14T08:44:44.02755305Z 2026-09-14 08:44:44 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a expires_at_present=True client_secret_present=True
2026-09-14T08:44:44.02757558Z 2026-09-14 08:44:44 [INFO] backend.main: realtime.session_create_completed conversation_id=b0934264-1060-4b16-b95e-52ec20c4262a model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=914
2026-09-14T08:44:44.028006942Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-14T09:03:44.464058716Z INFO:     Shutting down
2026-09-14T09:03:44.564335315Z INFO:     Waiting for application shutdown.
2026-09-14T09:03:44.564734216Z INFO:     Application shutdown complete.
2026-09-14T09:03:44.565006743Z INFO:     Finished server process [61]
2026-09-15T02:33:52.341989213Z ==> Deploying...
2026-09-15T02:33:52.542119205Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-15T02:34:23.186829197Z INFO:     Started server process [62]
2026-09-15T02:34:23.186849838Z INFO:     Waiting for application startup.
2026-09-15T02:34:23.250088121Z 2026-09-15 02:34:23 [INFO] redis_client: Successfully connected to Redis.
2026-09-15T02:34:23.349166751Z 2026-09-15 02:34:23 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-15T02:34:23.36134861Z 2026-09-15 02:34:23 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-15T02:34:23.36136698Z 2026-09-15 02:34:23 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-15T02:34:23.361414092Z 2026-09-15 02:34:23 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-15T02:34:23.361425122Z 2026-09-15 02:34:23 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-15T02:34:25.567480607Z 2026-09-15 02:34:25 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-15T02:34:25.568345851Z 2026-09-15 02:34:25 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-15T02:34:25.571128751Z 2026-09-15 02:34:25 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-15T02:34:25.576775723Z 2026-09-15 02:34:25 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-15T02:34:25.576912837Z 2026-09-15 02:34:25 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-15T02:34:25.577064381Z 2026-09-15 02:34:25 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-7990f80222b14f53bbad6a9c8c083d15
2026-09-15T02:34:25.577075842Z 2026-09-15 02:34:25 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-7990f80222b14f53bbad6a9c8c083d15
2026-09-15T02:34:25.759550012Z INFO:     Application startup complete.
2026-09-15T02:34:25.759576613Z 2026-09-15 02:34:25 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-15T02:34:25.760738906Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-15T02:34:26.893732512Z Memory Store initialized successfully.
2026-09-15T02:34:26.893759703Z Mailbox Store initialized successfully.
2026-09-15T02:34:26.893764533Z Agent Job Store initialized successfully.
2026-09-15T02:34:26.893768233Z Redis RAG Cache initialized successfully.
2026-09-15T02:34:26.893771833Z INFO:     127.0.0.1:57684 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-15T02:34:33.157447372Z ==> Your service is live 🎉
2026-09-15T02:34:33.379668913Z ==> 
2026-09-15T02:34:33.382184067Z ==> ///////////////////////////////////////////////////////////
2026-09-15T02:34:33.384842317Z ==> 
2026-09-15T02:34:33.387027408Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-15T02:34:33.390090553Z ==> 
2026-09-15T02:34:33.392542165Z ==> ///////////////////////////////////////////////////////////
2026-09-15T02:38:37.805814406Z 2026-09-15 02:38:37 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-15T02:38:37.806183097Z INFO:     140.122.53.14:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-15T02:39:34.269571896Z ==> Detected service running on port 10000
2026-09-15T02:39:34.690311599Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding