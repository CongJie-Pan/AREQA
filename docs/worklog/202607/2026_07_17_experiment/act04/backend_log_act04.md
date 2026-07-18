2026-07-17T13:25:45.292433937Z 2026-07-17 13:25:45 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:25:45.50898979Z 2026-07-17 13:25:45 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:25:46.047364885Z 2026-07-17 13:25:46 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:25:46.081145832Z INFO:     74.220.48.219:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-07-17T13:25:46.220331164Z 2026-07-17 13:25:46 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:25:46.222138783Z [EDF-LOG] log_action endpoint received: [User Action] Type: scroll, Context: {'scrollY': 10.399999618530273}
2026-07-17T13:25:46.222151723Z INFO:     114.42.247.248:0 - "POST /api/v1/log_action HTTP/1.1" 200 OK
2026-07-17T13:25:47.584138392Z 2026-07-17 13:25:47 [WARNING] agents.tutor_agent: Tutor routing fallback: TimeoutError
2026-07-17T13:25:48.111449677Z 2026-07-17 13:25:48 [INFO] memory_store: [MemoryStore] Updated working memory for user f263565b-f38f-4d3d-b33f-4ee01d528041: ['current_focus', 'current_focus_conversation_id']
2026-07-17T13:25:48.811266228Z 2026-07-17 13:25:48 [INFO] memory_store: memory.candidate_created user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 candidate_id=f7b8f1524533d02359894ab3 category=passive_preference expires=True
2026-07-17T13:25:49.160833214Z 2026-07-17 13:25:49 [WARNING] memory_store: memory.promotion_blocked user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 candidate_id=f7b8f1524533d02359894ab3 reason=insufficient_independent_evidence
2026-07-17T13:25:49.336035724Z 2026-07-17 13:25:49 [INFO] services.memory_ingestion_service: memory.ingestion_decided user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 message_id=d7a8dfd2c55367941a5a7ded state=candidate reason=candidate_created_or_updated category=passive_preference
2026-07-17T13:25:49.336088335Z 2026-07-17 13:25:49 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=f8f3173308994fecb4d06f81abbabf9d conversation_id=52e7edc7-5732-4dc1-8b67-cc63e21345be outcome=candidate reason=candidate_created_or_updated
2026-07-17T13:25:50.840016351Z 2026-07-17 13:25:50 [WARNING] services.orchestration_service: orchestration.dialogue_policy_timeout conversation_id=52e7edc7-5732-4dc1-8b67-cc63e21345be fallback=NORMAL
2026-07-17T13:25:51.720687936Z 2026-07-17 13:25:51,720 - INFO - [STITCH] Intent Cache Miss. Querying LLM for intent prediction...
2026-07-17T13:25:51.720715497Z 2026-07-17 13:25:51 [INFO] gum: [STITCH] Intent Cache Miss. Querying LLM for intent prediction...
2026-07-17T13:25:52.686791412Z 2026-07-17 13:25:52 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:25:53.10415128Z 2026-07-17 13:25:53 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/embeddings "HTTP/1.1 200 OK"
2026-07-17T13:25:53.647263205Z 2026-07-17 13:25:53 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:25:54.121007075Z 2026-07-17 13:25:54,120 - INFO - [STITCH] Predicted Labels: {"selected_context_scopes": ["個人特質與學習行為", "學習動機與溝通風格"], "selected_event_types": ["自我探索", "溝通模式"], "selected_targets": [], "selected_functional_type_seeds": ["interest_profiling"]}
2026-07-17T13:25:54.121025405Z 2026-07-17 13:25:54 [INFO] gum: [STITCH] Predicted Labels: {"selected_context_scopes": ["個人特質與學習行為", "學習動機與溝通風格"], "selected_event_types": ["自我探索", "溝通模式"], "selected_targets": [], "selected_functional_type_seeds": ["interest_profiling"]}
2026-07-17T13:25:56.358783987Z 2026-07-17 13:25:56 [INFO] services.orchestration_service: orchestration.context_prepared conversation_id=52e7edc7-5732-4dc1-8b67-cc63e21345be learner_understanding=unknown retrieved_memory=False
2026-07-17T13:25:56.359097105Z 2026-07-17 13:25:56 [INFO] services.conversation_stream_service: orchestration.stream_started conversation_id=52e7edc7-5732-4dc1-8b67-cc63e21345be model=google/gemini-3.1-flash-lite attachment_parser=False
2026-07-17T13:25:57.438772927Z 2026-07-17 13:25:57 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:25:58.661499774Z 2026-07-17 13:25:58 [INFO] services.conversation_stream_service: orchestration.stream_completed conversation_id=52e7edc7-5732-4dc1-8b67-cc63e21345be elapsed_ms=2302
2026-07-17T13:26:00.456663472Z 2026-07-17 13:26:00 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:01.206803931Z 2026-07-17 13:26:01 [INFO] services.orchestration_service: orchestration.post_turn_queued run_id=f8f3173308994fecb4d06f81abbabf9d conversation_id=52e7edc7-5732-4dc1-8b67-cc63e21345be
2026-07-17T13:26:01.207041057Z 2026-07-17 13:26:01 [INFO] services.post_turn_service: orchestration.post_turn_dispatched run_id=f8f3173308994fecb4d06f81abbabf9d conversation_id=52e7edc7-5732-4dc1-8b67-cc63e21345be reflection_durable=False evaluation_durable=False
2026-07-17T13:26:01.844787493Z 2026-07-17 13:26:01 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:01.973426527Z INFO:     74.220.48.219:0 - "POST /api/v1/generate-title HTTP/1.1" 200 OK
2026-07-17T13:26:02.597575383Z 2026-07-17 13:26:02 [INFO] services.hot_memory_service: hot_memory.created key=current_learner_state kind=model_inference export_eligible=False
2026-07-17T13:26:02.597766559Z 2026-07-17 13:26:02 [INFO] services.hot_memory_service: hot_memory.created key=current_strategy kind=model_inference export_eligible=False
2026-07-17T13:26:02.597910272Z 2026-07-17 13:26:02 [INFO] services.hot_memory_service: hot_memory.created key=trigger_proactive kind=operational_state export_eligible=False
2026-07-17T13:26:02.598038806Z 2026-07-17 13:26:02 [INFO] services.hot_memory_service: hot_memory.created key=learner_state_version kind=operational_state export_eligible=False
2026-07-17T13:26:02.598155939Z 2026-07-17 13:26:02 [INFO] services.hot_memory_service: hot_memory.created key=learner_state_evaluated_at kind=operational_state export_eligible=False
2026-07-17T13:26:02.70715438Z 2026-07-17 13:26:02 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:02.773510983Z 2026-07-17 13:26:02 [INFO] memory_store: [MemoryStore] Published learner state snapshot v4 for user f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:26:04.56387074Z 2026-07-17 13:26:04,563 - INFO - [STITCH] Intent Cache Miss. Querying LLM for intent prediction...
2026-07-17T13:26:04.563897271Z 2026-07-17 13:26:04 [INFO] gum: [STITCH] Intent Cache Miss. Querying LLM for intent prediction...
2026-07-17T13:26:05.258676576Z 2026-07-17 13:26:05 [INFO] services.hot_memory_service: hot_memory.created key=last_reflection_attempt_at kind=working_context export_eligible=False
2026-07-17T13:26:05.433542557Z 2026-07-17 13:26:05 [INFO] memory_store: [MemoryStore] Updated hot memory for user u1, key: last_reflection_attempt_at
2026-07-17T13:26:05.456389727Z 2026-07-17 13:26:05 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:05.930767106Z 2026-07-17 13:26:05,930 - INFO - [STITCH] Predicted Labels: {"selected_context_scopes": ["個人特質與學習行為", "學習動機與溝通風格"], "selected_event_types": ["溝通模式", "Self-disclosure", "需求獲取"], "selected_targets": [], "selected_functional_type_seeds": ["interest_profiling"]}
2026-07-17T13:26:05.930795057Z 2026-07-17 13:26:05 [INFO] gum: [STITCH] Predicted Labels: {"selected_context_scopes": ["個人特質與學習行為", "學習動機與溝通風格"], "selected_event_types": ["溝通模式", "Self-disclosure", "需求獲取"], "selected_targets": [], "selected_functional_type_seeds": ["interest_profiling"]}
2026-07-17T13:26:10.028141119Z 2026-07-17 13:26:10 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:16.663653422Z 2026-07-17 13:26:16,663 - INFO - Processing batch of 1 observations from observers: TextChatObserver_f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:26:16.663675282Z 2026-07-17 13:26:16 [INFO] gum: Processing batch of 1 observations from observers: TextChatObserver_f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:26:17.798824064Z 2026-07-17 13:26:17 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:21.020159156Z 2026-07-17 13:26:21 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:21.315718676Z 2026-07-17 13:26:21,315 - INFO - Applying proposition updates for batch...
2026-07-17T13:26:21.315745296Z 2026-07-17 13:26:21 [INFO] gum: Applying proposition updates for batch...
2026-07-17T13:26:23.409899838Z 2026-07-17 13:26:23 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:26:25.621228733Z 2026-07-17 13:26:25,620 - INFO - Completed processing batch of 1 observations
2026-07-17T13:26:25.621268654Z 2026-07-17 13:26:25 [INFO] gum: Completed processing batch of 1 observations
2026-07-17T13:27:09.802818222Z 2026-07-17 13:27:09 [INFO] services.hot_memory_service: hot_memory.created key=last_reflection_attempt_at kind=working_context export_eligible=False
2026-07-17T13:27:09.977778555Z 2026-07-17 13:27:09 [INFO] memory_store: [MemoryStore] Updated hot memory for user u1, key: last_reflection_attempt_at
2026-07-17T13:28:14.344921777Z 2026-07-17 13:28:14 [INFO] services.hot_memory_service: hot_memory.created key=last_reflection_attempt_at kind=working_context export_eligible=False
2026-07-17T13:28:14.520824506Z 2026-07-17 13:28:14 [INFO] memory_store: [MemoryStore] Updated hot memory for user u1, key: last_reflection_attempt_at