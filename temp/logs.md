2026-08-25T07:24:32.211657227Z ==> Deploying...
2026-08-25T07:24:32.409468308Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-08-25T07:24:52.610118883Z ==> Running 'python -m uvicorn main:app --host 0.0.0.0 --port $PORT'
2026-08-25T07:24:58.237952167Z INFO:     Started server process [62]
2026-08-25T07:24:58.237974347Z INFO:     Waiting for application startup.
2026-08-25T07:24:58.249025124Z 2026-08-25 07:24:58 [INFO] redis_client: Successfully connected to Redis.
2026-08-25T07:24:58.352992561Z 2026-08-25 07:24:58 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-08-25T07:24:58.35982749Z 2026-08-25 07:24:58 [INFO] main: background.worker_task_started name=proactive_scheduler_loop
2026-08-25T07:24:58.359856141Z 2026-08-25 07:24:58 [INFO] main: background.worker_task_started name=daily_scheduler_loop
2026-08-25T07:24:58.359916272Z 2026-08-25 07:24:58 [INFO] main: background.worker_task_started name=delayed_mail_worker
2026-08-25T07:24:58.359930403Z 2026-08-25 07:24:58 [INFO] main: background.worker_task_started name=agent_job_worker
2026-08-25T07:25:01.028875025Z 2026-08-25 07:25:01 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-08-25T07:25:01.031427444Z 2026-08-25 07:25:01 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-08-25T07:25:01.038951319Z 2026-08-25 07:25:01 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-08-25T07:25:01.039329608Z 2026-08-25 07:25:01 [INFO] main: background.worker_task_started name=reflection_loop
2026-08-25T07:25:01.03940902Z 2026-08-25 07:25:01 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-08-25T07:25:01.039507712Z 2026-08-25 07:25:01 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-50dd5eca71d8426fa89a03abf0088a87
2026-08-25T07:25:01.039538113Z 2026-08-25 07:25:01 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-50dd5eca71d8426fa89a03abf0088a87
2026-08-25T07:25:01.411390536Z INFO:     Application startup complete.
2026-08-25T07:25:01.411422187Z 2026-08-25 07:25:01 [WARNING] main: background.worker_task_stopped name=delayed_mail_worker
2026-08-25T07:25:01.411586051Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-08-25T07:25:02.298687883Z Memory Store initialized successfully.
2026-08-25T07:25:02.298707003Z Mailbox Store initialized successfully.
2026-08-25T07:25:02.298710273Z Agent Job Store initialized successfully.
2026-08-25T07:25:02.298712783Z Redis RAG Cache initialized successfully.
2026-08-25T07:25:02.298715403Z INFO:     127.0.0.1:51956 - "HEAD / HTTP/1.1" 404 Not Found
2026-08-25T07:25:03.578110106Z ==> Your service is live 🎉
2026-08-25T07:28:52.601712032Z 2026-08-25 07:28:52 [INFO] main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-08-25T07:28:52.602114271Z INFO:     114.42.249.125:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-08-25T07:29:25.765423637Z 2026-08-25 07:29:25 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-25T07:29:26.02510576Z INFO:     74.220.52.34:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-08-25T07:29:27.996454754Z 2026-08-25 07:29:27 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:28.19038523Z 2026-08-25 07:29:28 [INFO] services.orchestration_service: orchestration.turn_plan_selected run_id=723b3c0dd458427b8bcaa90f1d91dd49 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 route=WEB_REQUIRED enabled=True reason=EXTERNAL_SEARCH_REQUIRED max_foreground_model_calls=3
2026-08-25T07:29:28.44603166Z 2026-08-25 07:29:28 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['current_focus', 'current_focus_conversation_id']
2026-08-25T07:29:28.446059851Z 2026-08-25 07:29:28 [INFO] services.memory_ingestion_service: memory.ingestion_decided user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 message_id=b109fc3268d698ef0dcf1f34 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 candidate_id=none state=working_context_only reason=ordinary_user_message_for_current_turn category=current_focus promoted=False
2026-08-25T07:29:28.446129372Z 2026-08-25 07:29:28 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=723b3c0dd458427b8bcaa90f1d91dd49 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 outcome=working_context_only reason=ordinary_user_message_for_current_turn
2026-08-25T07:29:28.449822828Z 2026-08-25 07:29:28 [INFO] services.orchestration_service: orchestration.web_search_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 user_id=39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-25T07:29:29.108603005Z 2026-08-25 07:29:29 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:29.161584786Z 2026-08-25 07:29:29 [INFO] services.query_policy_service: orchestration.response_policy_selected metadata={"answer_depth": "SCAFFOLDED", "followup_mode": "OPTIONAL", "legacy_policy": "PROBE_UNDERSTANDING", "structure": "STEP_BY_STEP", "task_intent": "EXPLAIN_TEXT", "tone": "TUTORING"}
2026-08-25T07:29:29.227136389Z 2026-08-25 07:29:29 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:29.428396435Z 2026-08-25 07:29:29 [INFO] services.orchestration_service: orchestration.web_query_ready conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 elapsed_ms=976 max_results=10 context_size=high rewritten=True
2026-08-25T07:29:29.80562375Z 2026-08-25 07:29:29 [ERROR] services.orchestration_service: orchestration.web_search_failed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 reason=HTTPStatusError
2026-08-25T07:29:29.80563484Z Traceback (most recent call last):
2026-08-25T07:29:29.80563832Z   File "/opt/render/project/src/backend/services/orchestration_service.py", line 1044, in _node_perplexity_search
2026-08-25T07:29:29.80564191Z     tool_result = await self.tool_registry.execute(
2026-08-25T07:29:29.80564524Z   File "/opt/render/project/src/backend/tools/registry.py", line 55, in execute
2026-08-25T07:29:29.805648191Z     result = await definition.handler(arguments)
2026-08-25T07:29:29.805651541Z   File "/opt/render/project/src/backend/tools/web_search.py", line 79, in execute
2026-08-25T07:29:29.805654861Z     response.raise_for_status()
2026-08-25T07:29:29.805657651Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/httpx/_models.py", line 829, in raise_for_status
2026-08-25T07:29:29.805660521Z     raise HTTPStatusError(message, request=request, response=self)
2026-08-25T07:29:29.805663731Z httpx.HTTPStatusError: Client error '401 Unauthorized' for url 'https://api.perplexity.ai/search'
2026-08-25T07:29:29.805669451Z For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401
2026-08-25T07:29:29.805921177Z 2026-08-25 07:29:29 [INFO] services.orchestration_service: orchestration.dialogue_policy_selected conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 policy=PROBE_UNDERSTANDING
2026-08-25T07:29:29.805987768Z 2026-08-25 07:29:29 [INFO] services.orchestration_service: orchestration.response_policy_applied conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 source=classifier metadata={"answer_depth": "SCAFFOLDED", "followup_mode": "OPTIONAL", "legacy_policy": "PROBE_UNDERSTANDING", "structure": "STEP_BY_STEP", "task_intent": "EXPLAIN_TEXT", "tone": "TUTORING"}
2026-08-25T07:29:30.467762275Z 2026-08-25 07:29:30 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:31.164585405Z 2026-08-25 07:29:31 [INFO] services.parts_context_service: parts_context.rewrite_selected route=WEB_REQUIRED metadata={"confidence": "high", "has_act": true, "has_composed_instruction": true, "has_persona": true, "has_recipient": true, "has_structure": true, "has_theme": true, "missing_field_count": 1}
2026-08-25T07:29:31.172151491Z 2026-08-25 07:29:31 [INFO] services.conversation_context_service: orchestration.long_term_memory_skipped reason=EXTERNAL_SEARCH_REQUIRED memory_reason=SUBSTANTIVE_QUERY
2026-08-25T07:29:31.172188392Z 2026-08-25 07:29:31 [INFO] services.orchestration_service: orchestration.context_prepared conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 learner_understanding=unknown retrieved_memory=False
2026-08-25T07:29:31.815997601Z 2026-08-25 07:29:31 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:32.442473026Z 2026-08-25 07:29:32 [INFO] services.visual_grounding_agent: visual.brief_planned conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 visual_type=infographic source=agent reject_count=5 task_intent=explain_text answer_depth=scaffolded turn_route=web_required
2026-08-25T07:29:32.442498727Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.preflight_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 slot_count=1 visual_type=infographic brief_source=agent
2026-08-25T07:29:32.442572089Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.slot_resolution_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 slot_id=img_1
2026-08-25T07:29:32.443747086Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.cache_scope_selected conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 scope=preflight visual_type=infographic
2026-08-25T07:29:32.498920468Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.cache_miss conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14
2026-08-25T07:29:32.501218062Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.parallel_provider_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider_count=5
2026-08-25T07:29:32.535391325Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.provider_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=perplexity_images timeout_seconds=4.5
2026-08-25T07:29:32.609458497Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.provider_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=wikimedia timeout_seconds=3.0
2026-08-25T07:29:32.638963872Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.provider_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=openverse timeout_seconds=3.0
2026-08-25T07:29:32.721139941Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.provider_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=tavily_images timeout_seconds=3.0
2026-08-25T07:29:32.808212064Z 2026-08-25 07:29:32 [INFO] services.visual_answer_service: visual.provider_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=serpapi_images timeout_seconds=3.0
2026-08-25T07:29:33.076946308Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=openverse candidate_count=0
2026-08-25T07:29:33.07701917Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.parallel_provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=openverse candidate_count=0
2026-08-25T07:29:33.07702539Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.parallel_candidates_merged conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider_count=1 candidate_count=0 pending_provider_count=4
2026-08-25T07:29:33.084896573Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.provider_failed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=perplexity_images reason=HTTPStatusError status_code=401
2026-08-25T07:29:33.085222051Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.parallel_provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=perplexity_images candidate_count=0
2026-08-25T07:29:33.085233941Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.parallel_candidates_merged conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider_count=2 candidate_count=0 pending_provider_count=3
2026-08-25T07:29:33.440232809Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=wikimedia candidate_count=2
2026-08-25T07:29:33.44025432Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.parallel_provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=wikimedia candidate_count=2
2026-08-25T07:29:33.44025818Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.parallel_candidates_merged conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider_count=3 candidate_count=2 pending_provider_count=2
2026-08-25T07:29:33.44026256Z 2026-08-25 07:29:33 [INFO] services.visual_answer_service: visual.candidate_top_scored conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=wikimedia candidate_count=2 safe_candidate_count=2 top_score=0.58 threshold=0.40 source_domain=commons.wikimedia.org license=Public domain dimension_bucket=large
2026-08-25T07:29:33.933697085Z 2026-08-25 07:29:33 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:34.176715991Z 2026-08-25 07:29:34 [INFO] services.visual_grounding_agent: visual.grounding_checked conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 accepted=False expected_type=infographic candidate_type=document_scan reason=document_scan_mismatch
2026-08-25T07:29:34.176729632Z 2026-08-25 07:29:34 [INFO] services.visual_answer_service: visual.candidate_rejected conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=wikimedia reason=grounding_document_scan_mismatch expected_type=infographic candidate_type=document_scan
2026-08-25T07:29:34.808138662Z 2026-08-25 07:29:34 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:34.81923471Z 2026-08-25 07:29:34 [INFO] services.visual_grounding_agent: visual.grounding_checked conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 accepted=False expected_type=infographic candidate_type=document_scan reason=document_scan_not_infographic
2026-08-25T07:29:34.819289931Z 2026-08-25 07:29:34 [INFO] services.visual_answer_service: visual.candidate_rejected conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=wikimedia reason=grounding_document_scan_not_infographic expected_type=infographic candidate_type=document_scan
2026-08-25T07:29:34.819353723Z 2026-08-25 07:29:34 [INFO] services.visual_answer_service: visual.image_omitted conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 reason=grounding_rejected provider=wikimedia checked_candidate_count=2 threshold=0.40
2026-08-25T07:29:34.852738339Z 2026-08-25 07:29:34 [INFO] services.visual_answer_service: visual.provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=tavily_images candidate_count=40
2026-08-25T07:29:34.852975434Z 2026-08-25 07:29:34 [INFO] services.visual_answer_service: visual.parallel_provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=tavily_images candidate_count=40
2026-08-25T07:29:34.852983574Z 2026-08-25 07:29:34 [INFO] services.visual_answer_service: visual.parallel_candidates_merged conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider_count=4 candidate_count=42 pending_provider_count=1
2026-08-25T07:29:34.854651433Z 2026-08-25 07:29:34 [INFO] services.visual_answer_service: visual.candidate_top_scored conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=tavily_images candidate_count=40 safe_candidate_count=25 top_score=1.00 threshold=0.40 source_domain=pharmaceutical-journal.com license=unknown dimension_bucket=unknown
2026-08-25T07:29:35.851997436Z 2026-08-25 07:29:35 [INFO] services.visual_answer_service: visual.provider_failed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=serpapi_images reason=ReadTimeout status_code=unknown
2026-08-25T07:29:36.355376852Z 2026-08-25 07:29:36 [INFO] services.visual_grounding_agent: visual.grounding_failed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 reason=TimeoutError
2026-08-25T07:29:36.355568547Z 2026-08-25 07:29:36 [INFO] services.visual_answer_service: visual.candidate_rejected conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=tavily_images reason=grounding_model_unavailable expected_type=unknown candidate_type=unknown
2026-08-25T07:29:37.002919938Z 2026-08-25 07:29:37 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:37.027384596Z 2026-08-25 07:29:37 [INFO] services.visual_grounding_agent: visual.grounding_checked conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 accepted=False expected_type=infographic candidate_type=diagram reason=mismatched_process_focus
2026-08-25T07:29:37.027407937Z 2026-08-25 07:29:37 [INFO] services.visual_answer_service: visual.candidate_rejected conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=tavily_images reason=grounding_mismatched_process_focus expected_type=infographic candidate_type=diagram
2026-08-25T07:29:37.027458178Z 2026-08-25 07:29:37 [INFO] services.visual_answer_service: visual.image_omitted conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 reason=grounding_rejected provider=tavily_images checked_candidate_count=2 threshold=0.40
2026-08-25T07:29:37.027575951Z 2026-08-25 07:29:37 [INFO] services.visual_answer_service: visual.parallel_provider_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider=serpapi_images candidate_count=0
2026-08-25T07:29:37.027585321Z 2026-08-25 07:29:37 [INFO] services.visual_answer_service: visual.parallel_candidates_merged conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 provider_count=5 candidate_count=42 pending_provider_count=0
2026-08-25T07:29:37.086583432Z 2026-08-25 07:29:37 [INFO] services.visual_answer_service: visual.slot_resolution_failed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 slot_id=img_1 reason=no_verified_image
2026-08-25T07:29:37.086610992Z 2026-08-25 07:29:37 [INFO] services.visual_answer_service: visual.preflight_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 resolved_image_count=0
2026-08-25T07:29:37.086763566Z 2026-08-25 07:29:37 [INFO] services.conversation_stream_service: orchestration.stream_started conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 model=google/gemini-3.7-flash attachment_parser=False
2026-08-25T07:29:39.454984224Z 2026-08-25 07:29:39 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:42.757939722Z 2026-08-25 07:29:42 [INFO] services.conversation_stream_service: orchestration.stream_completed conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 elapsed_ms=5671
2026-08-25T07:29:42.758327141Z 2026-08-25 07:29:42 [INFO] services.visual_answer_service: visual.slots_planned conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 slot_count=2 reason=policy_or_explicit_visual
2026-08-25T07:29:42.758336821Z 2026-08-25 07:29:42 [INFO] services.visual_answer_service: visual.preverified_unused conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 available_image_count=0
2026-08-25T07:29:43.321062132Z 2026-08-25 07:29:43 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:43.567333912Z 2026-08-25 07:29:43 [INFO] services.orchestration_service: orchestration.post_turn_queued run_id=723b3c0dd458427b8bcaa90f1d91dd49 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14
2026-08-25T07:29:43.567496146Z 2026-08-25 07:29:43 [INFO] services.orchestration_service: orchestration.turn_trace_completed run_id=723b3c0dd458427b8bcaa90f1d91dd49 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 trace={'run_id': '723b3c0dd458427b8bcaa90f1d91dd49', 'conversation_id': '22faffaf-9453-4e75-a549-a49d377a7b14', 'elapsed_ms': 17542, 'phases': [{'name': 'request_accepted', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_started', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_finished', 'elapsed_ms': 2164, 'occurrence': 1}, {'name': 'turn_plan_web_required', 'elapsed_ms': 2165, 'occurrence': 1}, {'name': 'turn_intake_started', 'elapsed_ms': 2166, 'occurrence': 1}, {'name': 'turn_intake_finished', 'elapsed_ms': 2424, 'occurrence': 1}, {'name': 'policy_classifier_started', 'elapsed_ms': 2424, 'occurrence': 1}, {'name': 'rag_skipped', 'elapsed_ms': 2424, 'occurrence': 1}, {'name': 'web_search_started', 'elapsed_ms': 2425, 'occurrence': 1}, {'name': 'policy_classifier_finished', 'elapsed_ms': 3781, 'occurrence': 1}, {'name': 'prompt_assembly_started', 'elapsed_ms': 3781, 'occurrence': 1}, {'name': 'parts_context_started', 'elapsed_ms': 3781, 'occurrence': 1}, {'name': 'parts_context_finished', 'elapsed_ms': 5139, 'occurrence': 1}, {'name': 'hot_memory_snapshot_started', 'elapsed_ms': 5141, 'occurrence': 1}, {'name': 'hot_memory_snapshot_finished', 'elapsed_ms': 5145, 'occurrence': 1}, {'name': 'prompt_assembly_finished', 'elapsed_ms': 5147, 'occurrence': 1}, {'name': 'visual_preflight_started', 'elapsed_ms': 5147, 'occurrence': 1}, {'name': 'visual_preflight_finished', 'elapsed_ms': 11061, 'occurrence': 1}, {'name': 'main_model_started', 'elapsed_ms': 11061, 'occurrence': 1}, {'name': 'first_answer_delta', 'elapsed_ms': 13996, 'occurrence': 1}, {'name': 'main_model_finished', 'elapsed_ms': 16733, 'occurrence': 1}, {'name': 'suggestions_started', 'elapsed_ms': 16733, 'occurrence': 1}, {'name': 'suggestions_finished', 'elapsed_ms': 17541, 'occurrence': 1}, {'name': 'post_turn_queued', 'elapsed_ms': 17542, 'occurrence': 1}, {'name': 'terminal_sent', 'elapsed_ms': 17542, 'occurrence': 1}], 'model_calls': {'main_answer': 1, 'parts_context_rewrite': 1, 'policy_classifier': 1, 'search_routing': 1, 'suggestions': 1, 'web_query_rewrite': 1}, 'tool_calls': {'hot_memory': 1}, 'cache_statuses': {'hot_memory:not_applicable': 1}}
2026-08-25T07:29:43.567597988Z 2026-08-25 07:29:43 [INFO] services.orchestration_service: orchestration.turn_trace_summary run_id=723b3c0dd458427b8bcaa90f1d91dd49 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 summary={"cache_statuses": {"hot_memory:not_applicable": 1}, "conversation_id": "22faffaf-9453-4e75-a549-a49d377a7b14", "elapsed_ms": 17542, "is_slow": true, "main_model_started_ms": 11061, "model_calls": {"main_answer": 1, "parts_context_rewrite": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1, "web_query_rewrite": 1}, "phase_durations_ms": {"hot_memory_snapshot": 4, "main_model": 5672, "parts_context": 1358, "policy_classifier": 1357, "prompt_assembly": 1366, "search_routing": 2164, "suggestions": 808, "turn_intake": 258, "visual_preflight": 5914}, "provider_first_token_ms": 2935, "run_id": "723b3c0dd458427b8bcaa90f1d91dd49", "slow_reasons": ["total_elapsed", "time_to_first_answer", "top_phase:visual_preflight"], "terminal_sent_ms": 17542, "time_to_first_answer_ms": 13996, "tool_calls": {"hot_memory": 1}, "top_phase_durations": [{"duration_ms": 5914, "name": "visual_preflight"}, {"duration_ms": 5672, "name": "main_model"}, {"duration_ms": 2164, "name": "search_routing"}, {"duration_ms": 1366, "name": "prompt_assembly"}, {"duration_ms": 1358, "name": "parts_context"}]}
2026-08-25T07:29:43.567710431Z 2026-08-25 07:29:43 [WARNING] services.orchestration_service: orchestration.turn_trace_slow run_id=723b3c0dd458427b8bcaa90f1d91dd49 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 summary={"cache_statuses": {"hot_memory:not_applicable": 1}, "conversation_id": "22faffaf-9453-4e75-a549-a49d377a7b14", "elapsed_ms": 17542, "is_slow": true, "main_model_started_ms": 11061, "model_calls": {"main_answer": 1, "parts_context_rewrite": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1, "web_query_rewrite": 1}, "phase_durations_ms": {"hot_memory_snapshot": 4, "main_model": 5672, "parts_context": 1358, "policy_classifier": 1357, "prompt_assembly": 1366, "search_routing": 2164, "suggestions": 808, "turn_intake": 258, "visual_preflight": 5914}, "provider_first_token_ms": 2935, "run_id": "723b3c0dd458427b8bcaa90f1d91dd49", "slow_reasons": ["total_elapsed", "time_to_first_answer", "top_phase:visual_preflight"], "terminal_sent_ms": 17542, "time_to_first_answer_ms": 13996, "tool_calls": {"hot_memory": 1}, "top_phase_durations": [{"duration_ms": 5914, "name": "visual_preflight"}, {"duration_ms": 5672, "name": "main_model"}, {"duration_ms": 2164, "name": "search_routing"}, {"duration_ms": 1366, "name": "prompt_assembly"}, {"duration_ms": 1358, "name": "parts_context"}]}
2026-08-25T07:29:43.567980387Z 2026-08-25 07:29:43 [INFO] services.post_turn_service: orchestration.post_turn_dispatched run_id=723b3c0dd458427b8bcaa90f1d91dd49 conversation_id=22faffaf-9453-4e75-a549-a49d377a7b14 reflection_durable=False evaluation_durable=False
2026-08-25T07:29:43.570021934Z 2026-08-25 07:29:43 [WARNING] persistqueue.queue: Default tempdir '/tmp/tmpv2w4fch5' is not on the same filesystem with queue path '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue',defaulting to '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue'.
2026-08-25T07:29:43.817135294Z [GUM] Initializing new GUM instance for user 39bcc4a1-6be9-4817-80ae-9f5257721717...
2026-08-25T07:29:43.817191835Z INFO:     74.220.52.34:0 - "POST /api/v1/generate-title HTTP/1.1" 200 OK
2026-08-25T07:29:44.407871035Z 2026-08-25 07:29:44 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:44.476027828Z 2026-08-25 07:29:44 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:44.577206828Z 2026-08-25 07:29:44 [INFO] memory_store: [MemoryStore] Published learner state snapshot v303 for user 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-25T07:29:47.645415634Z 2026-08-25 07:29:47 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:29:47.896341303Z 2026-08-25 07:29:47,896 - INFO - [STITCH] No substantial entities/scopes selected. Fallback to pure BM25 search.
2026-08-25T07:29:47.896353963Z 2026-08-25 07:29:47 [INFO] gum: [STITCH] No substantial entities/scopes selected. Fallback to pure BM25 search.
2026-08-25T07:29:49.663001167Z 2026-08-25 07:29:49 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:30:12.363743132Z ==> Detected service running on port 10000
2026-08-25T07:30:12.747886493Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-08-25T07:30:14.687724511Z 2026-08-25 07:30:14 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:30:19.753110762Z 2026-08-25 07:30:19 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:30:21.267417404Z 2026-08-25 07:30:21 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-08-25T07:31:09.62951367Z [EDF-LOG] evaluate_student_state: LLM returned state: TINKERING, strategy: 提供具體步驟與機制解釋，運用類比法將mRNA疫苗機制與刺突蛋白的角色拆解為邏輯流程，並引導學習者建立因果連結。, trigger_proactive: False
2026-08-25T07:31:09.629534201Z INFO:     114.42.249.125:0 - "OPTIONS /api/v1/memory/summary?t=1787643037113 HTTP/1.1" 200 OK
2026-08-25T07:31:09.780387495Z INFO:     114.42.249.125:0 - "OPTIONS /api/v1/memory?t=1787643037113 HTTP/1.1" 200 OK
2026-08-25T07:31:09.913696712Z 2026-08-25 07:31:09 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-25T07:31:10.004487781Z 2026-08-25 07:31:10 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-25T07:31:10.418123381Z INFO:     114.42.249.125:0 - "GET /api/v1/memory/summary?t=1787643037113 HTTP/1.1" 200 OK
2026-08-25T07:31:10.419471702Z INFO:     114.42.249.125:0 - "GET /api/v1/memory?t=1787643037113 HTTP/1.1" 200 OK
2026-08-25T07:51:12.558176783Z 2026-08-25 07:51:12 [INFO] main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-08-25T07:51:12.558537931Z INFO:     114.42.249.125:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-08-25T07:51:20.031181406Z ==> Deploying...
2026-08-25T07:51:20.230874649Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-08-25T07:51:43.813613845Z 2026-08-25 07:51:43 [INFO] main: background.worker_task_started name=daily_scheduler_loop
2026-08-25T07:51:43.813626706Z 2026-08-25 07:51:43 [INFO] main: background.worker_task_started name=delayed_mail_worker
2026-08-25T07:51:43.813657668Z 2026-08-25 07:51:43 [INFO] main: background.worker_task_started name=agent_job_worker
2026-08-25T07:51:46.677658684Z 2026-08-25 07:51:46 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-08-25T07:51:46.68070351Z 2026-08-25 07:51:46 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-08-25T07:51:46.690054535Z 2026-08-25 07:51:46 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-08-25T07:51:46.690484027Z 2026-08-25 07:51:46 [INFO] main: background.worker_task_started name=reflection_loop
2026-08-25T07:51:46.690597685Z 2026-08-25 07:51:46 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-08-25T07:51:46.690728415Z 2026-08-25 07:51:46 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-59280f11582e486eb76f3265ad25d80c
2026-08-25T07:51:46.690763177Z 2026-08-25 07:51:46 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-59280f11582e486eb76f3265ad25d80c
2026-08-25T07:51:46.879435693Z INFO:     Application startup complete.
2026-08-25T07:51:46.879460285Z 2026-08-25 07:51:46 [WARNING] main: background.worker_task_stopped name=delayed_mail_worker
2026-08-25T07:51:46.879464215Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-08-25T07:51:47.683260126Z Memory Store initialized successfully.
2026-08-25T07:51:47.683297189Z Mailbox Store initialized successfully.
2026-08-25T07:51:47.683302719Z Agent Job Store initialized successfully.
2026-08-25T07:51:47.683306379Z Redis RAG Cache initialized successfully.
2026-08-25T07:51:47.68331028Z INFO:     127.0.0.1:47748 - "HEAD / HTTP/1.1" 404 Not Found
2026-08-25T07:51:50.920868343Z ==> Your service is live 🎉
2026-08-25T07:51:51.040922078Z INFO:     35.197.80.206:0 - "GET / HTTP/1.1" 404 Not Found
2026-08-25T07:51:51.130708799Z ==> 
2026-08-25T07:51:51.140750043Z ==> ///////////////////////////////////////////////////////////
2026-08-25T07:51:51.148668025Z ==> 
2026-08-25T07:51:51.160579405Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-08-25T07:51:51.168218513Z ==> 
2026-08-25T07:51:51.172809561Z ==> ///////////////////////////////////////////////////////////
2026-08-25T07:52:50.279362577Z INFO:     Shutting down
2026-08-25T07:52:50.379827621Z INFO:     Waiting for application shutdown.
2026-08-25T07:52:50.380148269Z INFO:     Application shutdown complete.
2026-08-25T07:52:50.380433695Z INFO:     Finished server process [62]
2026-08-25T07:53:26.255758425Z 2026-08-25 07:53:26 [INFO] main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-08-25T07:53:26.2560996Z INFO:     114.42.249.125:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-08-25T07:56:58.629817725Z ==> Detected service running on port 10000
2026-08-25T07:56:58.999954541Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding