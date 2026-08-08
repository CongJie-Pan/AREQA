2026-08-08T08:15:48.773120254Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-08-08T08:16:10.532469746Z ==> Running 'python -m uvicorn main:app --host 0.0.0.0 --port $PORT'
2026-08-08T08:16:18.049791767Z INFO:     Started server process [59]
2026-08-08T08:16:18.049809317Z INFO:     Waiting for application startup.
2026-08-08T08:16:18.059986294Z 2026-08-08 08:16:18 [INFO] redis_client: Successfully connected to Redis.
2026-08-08T08:16:18.158488042Z 2026-08-08 08:16:18 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-08-08T08:16:18.20579493Z 2026-08-08 08:16:18 [INFO] main: background.worker_task_started name=proactive_scheduler_loop
2026-08-08T08:16:18.205821691Z 2026-08-08 08:16:18 [INFO] main: background.worker_task_started name=daily_scheduler_loop
2026-08-08T08:16:18.205871962Z 2026-08-08 08:16:18 [INFO] main: background.worker_task_started name=delayed_mail_worker
2026-08-08T08:16:18.205962014Z 2026-08-08 08:16:18 [INFO] main: background.worker_task_started name=agent_job_worker
2026-08-08T08:16:23.554757713Z 2026-08-08 08:16:23 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-08-08T08:16:23.59263562Z 2026-08-08 08:16:23 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-08-08T08:16:23.610378228Z 2026-08-08 08:16:23 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-08-08T08:16:23.611343498Z 2026-08-08 08:16:23 [INFO] main: background.worker_task_started name=reflection_loop
2026-08-08T08:16:23.611548133Z 2026-08-08 08:16:23 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-08-08T08:16:23.611761507Z 2026-08-08 08:16:23 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-30d9db7963c74a45aa38e4d34eabdfde
2026-08-08T08:16:23.61188048Z 2026-08-08 08:16:23 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-30d9db7963c74a45aa38e4d34eabdfde
2026-08-08T08:16:23.954578281Z INFO:     Application startup complete.
2026-08-08T08:16:23.954592132Z 2026-08-08 08:16:23 [WARNING] main: background.worker_task_stopped name=delayed_mail_worker
2026-08-08T08:16:23.954755245Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-08-08T08:16:25.014440742Z Memory Store initialized successfully.
2026-08-08T08:16:25.014492983Z Mailbox Store initialized successfully.
2026-08-08T08:16:25.014497123Z Agent Job Store initialized successfully.
2026-08-08T08:16:25.014500203Z Redis RAG Cache initialized successfully.
2026-08-08T08:16:25.014503063Z INFO:     127.0.0.1:47548 - "HEAD / HTTP/1.1" 404 Not Found
2026-08-08T08:16:29.453149667Z ==> Your service is live 🎉
2026-08-08T08:16:29.565014814Z [EDF-LOG] evaluate_student_state: LLM returned state: STARTING, strategy: 提供基礎定義與概念鷹架，使用淺顯易懂的類比解釋統合分析的核心目的，並引導其思考該方法在研究中的應用情境。, trigger_proactive: False
2026-08-08T08:16:29.565060855Z INFO:     35.233.144.17:0 - "GET / HTTP/1.1" 404 Not Found
2026-08-08T08:16:29.674222675Z ==> 
2026-08-08T08:16:29.676483889Z ==> ///////////////////////////////////////////////////////////
2026-08-08T08:16:29.678749123Z ==> 
2026-08-08T08:16:29.681130648Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-08-08T08:16:29.683616756Z ==> 
2026-08-08T08:16:29.685826079Z ==> ///////////////////////////////////////////////////////////
2026-08-08T08:17:28.871993017Z INFO:     Shutting down
2026-08-08T08:17:28.872076678Z 2026-08-08 08:17:28 [INFO] services.connection_manager: WebSocket disconnected for user: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:17:28.970963195Z INFO:     Waiting for application shutdown.
2026-08-08T08:17:28.971366174Z INFO:     Application shutdown complete.
2026-08-08T08:17:28.971945056Z INFO:     Finished server process [62]
2026-08-08T08:17:31.12414921Z INFO:     1.165.41.32:0 - "OPTIONS /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-08-08T08:17:31.59208398Z 2026-08-08 08:17:31 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:17:31.694952471Z INFO:     1.165.41.32:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-08-08T08:17:31.931570623Z INFO:     1.165.41.32:0 - "WebSocket /api/v1/ws/notifications?ticket=AEZ4u59EezwQA1WhMRdyXkDD8SN24GM81ImW7RocJT0" [accepted]
2026-08-08T08:17:31.931589973Z INFO:     connection open
2026-08-08T08:17:31.931594653Z 2026-08-08 08:17:31 [INFO] services.connection_manager: WebSocket connected for user: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:17:32.167161562Z 2026-08-08 08:17:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:17:32.277972933Z INFO:     1.165.41.32:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-08-08T08:17:32.653514534Z INFO:     1.165.41.32:0 - "WebSocket /api/v1/ws/notifications?ticket=ZYmC6UGUfAnk3OOZAkc-Ya-0TgU4QdepxsxaIAVMhxs" [accepted]
2026-08-08T08:17:32.653600766Z INFO:     connection open
2026-08-08T08:17:32.653629367Z 2026-08-08 08:17:32 [INFO] services.connection_manager: WebSocket connected for user: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:01.335925382Z 2026-08-08 08:18:01 [INFO] services.connection_manager: WebSocket disconnected for user: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:03.849947415Z INFO:     1.165.41.32:0 - "OPTIONS /api/v1/mailbox HTTP/1.1" 200 OK
2026-08-08T08:18:03.851488008Z 2026-08-08 08:18:03 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:03.939978453Z 2026-08-08 08:18:03 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:03.976590933Z INFO:     1.165.41.32:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-08-08T08:18:04.045308078Z INFO:     1.165.41.32:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-08-08T08:18:04.058241293Z 2026-08-08 08:18:04 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:04.276064144Z INFO:     1.165.41.32:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK
2026-08-08T08:18:04.309936056Z INFO:     1.165.41.32:0 - "WebSocket /api/v1/ws/notifications?ticket=-gB-YyVICTno3aY-olY8_AHfmdeJWpXnWEPhlsHZ6BY" [accepted]
2026-08-08T08:18:04.309969556Z INFO:     connection open
2026-08-08T08:18:04.310099619Z 2026-08-08 08:18:04 [INFO] services.connection_manager: WebSocket connected for user: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:04.632917757Z INFO:     1.165.41.32:0 - "WebSocket /api/v1/ws/notifications?ticket=2mhF05omxvT8pEH089QSgadH1mpCx9gTM1Pn0iCO4Sw" [accepted]
2026-08-08T08:18:04.634168964Z INFO:     connection open
2026-08-08T08:18:04.634404219Z 2026-08-08 08:18:04 [INFO] services.connection_manager: WebSocket connected for user: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:18.310950188Z 2026-08-08 08:18:18 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:18.705084086Z INFO:     74.220.52.216:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-08-08T08:18:22.133808527Z 2026-08-08 08:18:22 [INFO] services.orchestration_service: orchestration.turn_plan_selected run_id=065c0384c1cf487ea50706559c678c16 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 route=WEB_REQUIRED enabled=True reason=EXTERNAL_SEARCH_REQUIRED max_foreground_model_calls=3
2026-08-08T08:18:22.159759151Z 2026-08-08 08:18:22 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['current_focus', 'current_focus_conversation_id']
2026-08-08T08:18:22.159778061Z 2026-08-08 08:18:22 [INFO] services.memory_ingestion_service: memory.ingestion_decided user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 message_id=75a7d633a3a551ab87ba4286 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 candidate_id=none state=working_context_only reason=interrogative_not_memory_evidence category=current_focus promoted=False
2026-08-08T08:18:22.159789231Z 2026-08-08 08:18:22 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=065c0384c1cf487ea50706559c678c16 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 outcome=working_context_only reason=interrogative_not_memory_evidence
2026-08-08T08:18:22.167917444Z 2026-08-08 08:18:22 [INFO] services.orchestration_service: orchestration.web_search_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 user_id=39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:23.093541325Z 2026-08-08 08:18:23 [INFO] services.query_policy_service: orchestration.response_policy_selected metadata={"answer_depth": "SCAFFOLDED", "followup_mode": "OPTIONAL", "legacy_policy": "PROBE_UNDERSTANDING", "structure": "STEP_BY_STEP", "task_intent": "EXPLAIN_TEXT", "tone": "PLAIN"}
2026-08-08T08:18:23.411619172Z 2026-08-08 08:18:23 [INFO] services.orchestration_service: orchestration.web_query_ready conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 elapsed_ms=1210 max_results=5 context_size=high rewritten=True
2026-08-08T08:18:24.338056841Z 2026-08-08 08:18:24 [INFO] services.orchestration_service: orchestration.web_search_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 result_count=5 latency_ms=923
2026-08-08T08:18:24.349182598Z 2026-08-08 08:18:24 [INFO] services.orchestration_service: orchestration.web_search_node_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 elapsed_ms=2174
2026-08-08T08:18:24.352717903Z 2026-08-08 08:18:24 [INFO] services.orchestration_service: orchestration.dialogue_policy_selected conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 policy=PROBE_UNDERSTANDING
2026-08-08T08:18:24.353549041Z 2026-08-08 08:18:24 [INFO] services.orchestration_service: orchestration.response_policy_applied conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 source=classifier metadata={"answer_depth": "SCAFFOLDED", "followup_mode": "OPTIONAL", "legacy_policy": "PROBE_UNDERSTANDING", "structure": "STEP_BY_STEP", "task_intent": "EXPLAIN_TEXT", "tone": "PLAIN"}
2026-08-08T08:18:24.364515144Z 2026-08-08 08:18:24 [INFO] services.conversation_context_service: orchestration.long_term_memory_skipped reason=EXTERNAL_SEARCH_REQUIRED memory_reason=SUBSTANTIVE_QUERY
2026-08-08T08:18:24.372049055Z 2026-08-08 08:18:24 [INFO] services.orchestration_service: orchestration.context_prepared conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 learner_understanding=unknown retrieved_memory=False
2026-08-08T08:18:24.372443423Z 2026-08-08 08:18:24 [INFO] services.visual_answer_service: visual.preflight_query_rewritten conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 rule=meta_analysis_forest_plot
2026-08-08T08:18:25.468091997Z 2026-08-08 08:18:25 [INFO] services.visual_grounding_agent: visual.brief_planned conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 visual_type=forest_plot source=agent reject_count=5 task_intent=explain_text answer_depth=scaffolded turn_route=web_required
2026-08-08T08:18:25.468324362Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.preflight_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 slot_count=1 visual_type=forest_plot brief_source=agent
2026-08-08T08:18:25.46918359Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.slot_resolution_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 slot_id=img_1
2026-08-08T08:18:25.470167361Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.cache_scope_selected conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 scope=preflight visual_type=forest_plot
2026-08-08T08:18:25.535172876Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.cache_hit conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 status=hit
2026-08-08T08:18:25.535266158Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.cache_rejected conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 reason=unsafe_cached_image
2026-08-08T08:18:25.536125906Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.parallel_provider_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider_count=5
2026-08-08T08:18:25.605548685Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.provider_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=perplexity_images timeout_seconds=4.5
2026-08-08T08:18:25.645517167Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.provider_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=wikimedia timeout_seconds=3.0
2026-08-08T08:18:25.728767511Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.provider_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=openverse timeout_seconds=3.0
2026-08-08T08:18:25.819742459Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.provider_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=tavily_images timeout_seconds=3.0
2026-08-08T08:18:25.850658138Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.provider_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=serpapi_images timeout_seconds=3.0
2026-08-08T08:18:25.981275711Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.provider_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=openverse candidate_count=0
2026-08-08T08:18:25.981644788Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.parallel_provider_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=openverse candidate_count=0
2026-08-08T08:18:25.981654029Z 2026-08-08 08:18:25 [INFO] services.visual_answer_service: visual.parallel_candidates_merged conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider_count=1 candidate_count=0 pending_provider_count=4
2026-08-08T08:18:26.037915467Z 2026-08-08 08:18:26 [INFO] services.visual_answer_service: visual.provider_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=serpapi_images candidate_count=100
2026-08-08T08:18:26.037933878Z 2026-08-08 08:18:26 [INFO] services.visual_answer_service: visual.parallel_provider_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=serpapi_images candidate_count=100
2026-08-08T08:18:26.037937408Z 2026-08-08 08:18:26 [INFO] services.visual_answer_service: visual.parallel_candidates_merged conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider_count=2 candidate_count=100 pending_provider_count=3
2026-08-08T08:18:26.049196988Z 2026-08-08 08:18:26 [INFO] services.visual_answer_service: visual.candidate_top_scored conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=serpapi_images candidate_count=100 safe_candidate_count=87 top_score=1.00 threshold=0.40 source_domain=nature.com license=unknown dimension_bucket=medium
2026-08-08T08:18:26.634649681Z 2026-08-08 08:18:26 [INFO] services.visual_answer_service: visual.provider_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 provider=wikimedia candidate_count=8
2026-08-08T08:18:27.099279551Z 2026-08-08 08:18:27 [INFO] services.visual_grounding_agent: visual.grounding_checked conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 accepted=True expected_type=forest_plot candidate_type=forest_plot reason=matches_visual_brief_and_intent
2026-08-08T08:18:27.100245071Z 2026-08-08 08:18:27 [INFO] services.visual_answer_service: visual.image_selected conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 source_domain=nature.com provider=serpapi_images confidence_bucket=high
2026-08-08T08:18:27.100327223Z 2026-08-08 08:18:27 [INFO] services.visual_answer_service: visual.image_block_ready conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 stage=serpapi_images provider=serpapi_images source_domain=nature.com has_explanatory_caption=False pedagogical_score=0.20
2026-08-08T08:18:27.155857096Z 2026-08-08 08:18:27 [INFO] services.visual_answer_service: visual.slot_resolution_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 slot_id=img_1 source=provider
2026-08-08T08:18:27.155878066Z 2026-08-08 08:18:27 [INFO] services.visual_answer_service: visual.preflight_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 resolved_image_count=1
2026-08-08T08:18:27.155984989Z 2026-08-08 08:18:27 [INFO] services.visual_understanding_agent: visual.understanding_unavailable conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 model=google/gemini-3.1-flash-lite source_domain=media.springernature.com reason=AttributeError
2026-08-08T08:18:27.15602849Z 2026-08-08 08:18:27 [INFO] services.output_image_service: visual.output_images_prepared conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 image_count=1 understanding_enabled=True
2026-08-08T08:18:27.156180253Z 2026-08-08 08:18:27 [INFO] services.conversation_stream_service: orchestration.stream_started conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 model=google/gemini-3.1-flash-lite attachment_parser=False
2026-08-08T08:18:34.401999061Z 2026-08-08 08:18:34 [INFO] services.conversation_stream_service: visual.slot_marker_detected conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 slot_count=1
2026-08-08T08:18:34.402033951Z 2026-08-08 08:18:34 [INFO] services.conversation_stream_service: orchestration.stream_completed conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 elapsed_ms=7244
2026-08-08T08:18:34.402038762Z 2026-08-08 08:18:34 [INFO] services.orchestration_service: visual.answer_slots_collected conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 slot_count=1
2026-08-08T08:18:34.402042232Z 2026-08-08 08:18:34 [INFO] services.visual_answer_service: visual.slots_planned conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 slot_count=1 reason=model_planned
2026-08-08T08:18:34.402046402Z 2026-08-08 08:18:34 [INFO] services.orchestration_service: visual.answer_blocks_emitted conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 block_count=8 resolved_image_block_count=1 pending_image_slot_count=0
2026-08-08T08:18:35.401393503Z 2026-08-08 08:18:35 [WARNING] services.post_turn_service: orchestration.suggestions_failed reason=TimeoutError
2026-08-08T08:18:35.402385485Z 2026-08-08 08:18:35 [INFO] services.orchestration_service: orchestration.post_turn_queued run_id=065c0384c1cf487ea50706559c678c16 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71
2026-08-08T08:18:35.402707411Z 2026-08-08 08:18:35 [INFO] services.orchestration_service: orchestration.turn_trace_completed run_id=065c0384c1cf487ea50706559c678c16 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 trace={'run_id': '065c0384c1cf487ea50706559c678c16', 'conversation_id': '0541e973-8dc4-4d74-b81b-4fe0b0fa1e71', 'elapsed_ms': 16697, 'phases': [{'name': 'request_accepted', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_started', 'elapsed_ms': 1, 'occurrence': 1}, {'name': 'search_routing_finished', 'elapsed_ms': 3428, 'occurrence': 1}, {'name': 'turn_plan_web_required', 'elapsed_ms': 3429, 'occurrence': 1}, {'name': 'turn_intake_started', 'elapsed_ms': 3432, 'occurrence': 1}, {'name': 'turn_intake_finished', 'elapsed_ms': 3459, 'occurrence': 1}, {'name': 'policy_classifier_started', 'elapsed_ms': 3460, 'occurrence': 1}, {'name': 'rag_skipped', 'elapsed_ms': 3460, 'occurrence': 1}, {'name': 'web_search_started', 'elapsed_ms': 3461, 'occurrence': 1}, {'name': 'web_search_finished', 'elapsed_ms': 5647, 'occurrence': 1}, {'name': 'policy_classifier_finished', 'elapsed_ms': 5648, 'occurrence': 1}, {'name': 'prompt_assembly_started', 'elapsed_ms': 5649, 'occurrence': 1}, {'name': 'hot_memory_snapshot_started', 'elapsed_ms': 5649, 'occurrence': 1}, {'name': 'hot_memory_snapshot_finished', 'elapsed_ms': 5652, 'occurrence': 1}, {'name': 'prompt_assembly_finished', 'elapsed_ms': 5667, 'occurrence': 1}, {'name': 'visual_preflight_started', 'elapsed_ms': 5667, 'occurrence': 1}, {'name': 'visual_preflight_finished', 'elapsed_ms': 8451, 'occurrence': 1}, {'name': 'main_model_started', 'elapsed_ms': 8451, 'occurrence': 1}, {'name': 'first_answer_delta', 'elapsed_ms': 14655, 'occurrence': 1}, {'name': 'main_model_finished', 'elapsed_ms': 15695, 'occurrence': 1}, {'name': 'suggestions_started', 'elapsed_ms': 15696, 'occurrence': 1}, {'name': 'suggestions_failed', 'elapsed_ms': 16696, 'occurrence': 1}, {'name': 'post_turn_queued', 'elapsed_ms': 16697, 'occurrence': 1}, {'name': 'terminal_sent', 'elapsed_ms': 16697, 'occurrence': 1}], 'model_calls': {'main_answer': 1, 'policy_classifier': 1, 'search_routing': 1, 'suggestions': 1, 'web_query_rewrite': 1}, 'tool_calls': {'hot_memory': 1, 'web_search': 1}, 'cache_statuses': {'hot_memory:not_applicable': 1, 'web_search:miss': 1}}
2026-08-08T08:18:35.402932266Z 2026-08-08 08:18:35 [INFO] services.orchestration_service: orchestration.turn_trace_summary run_id=065c0384c1cf487ea50706559c678c16 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 summary={"cache_statuses": {"hot_memory:not_applicable": 1, "web_search:miss": 1}, "conversation_id": "0541e973-8dc4-4d74-b81b-4fe0b0fa1e71", "elapsed_ms": 16697, "is_slow": true, "main_model_started_ms": 8451, "model_calls": {"main_answer": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1, "web_query_rewrite": 1}, "phase_durations_ms": {"hot_memory_snapshot": 3, "main_model": 7244, "policy_classifier": 2188, "prompt_assembly": 18, "search_routing": 3427, "suggestions": 1000, "turn_intake": 27, "visual_preflight": 2784, "web_search": 2186}, "provider_first_token_ms": 6204, "run_id": "065c0384c1cf487ea50706559c678c16", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 16697, "time_to_first_answer_ms": 14655, "tool_calls": {"hot_memory": 1, "web_search": 1}, "top_phase_durations": [{"duration_ms": 7244, "name": "main_model"}, {"duration_ms": 3427, "name": "search_routing"}, {"duration_ms": 2784, "name": "visual_preflight"}, {"duration_ms": 2188, "name": "policy_classifier"}, {"duration_ms": 2186, "name": "web_search"}]}
2026-08-08T08:18:35.40311382Z 2026-08-08 08:18:35 [WARNING] services.orchestration_service: orchestration.turn_trace_slow run_id=065c0384c1cf487ea50706559c678c16 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 summary={"cache_statuses": {"hot_memory:not_applicable": 1, "web_search:miss": 1}, "conversation_id": "0541e973-8dc4-4d74-b81b-4fe0b0fa1e71", "elapsed_ms": 16697, "is_slow": true, "main_model_started_ms": 8451, "model_calls": {"main_answer": 1, "policy_classifier": 1, "search_routing": 1, "suggestions": 1, "web_query_rewrite": 1}, "phase_durations_ms": {"hot_memory_snapshot": 3, "main_model": 7244, "policy_classifier": 2188, "prompt_assembly": 18, "search_routing": 3427, "suggestions": 1000, "turn_intake": 27, "visual_preflight": 2784, "web_search": 2186}, "provider_first_token_ms": 6204, "run_id": "065c0384c1cf487ea50706559c678c16", "slow_reasons": ["total_elapsed", "time_to_first_answer", "provider_first_token", "top_phase:main_model"], "terminal_sent_ms": 16697, "time_to_first_answer_ms": 14655, "tool_calls": {"hot_memory": 1, "web_search": 1}, "top_phase_durations": [{"duration_ms": 7244, "name": "main_model"}, {"duration_ms": 3427, "name": "search_routing"}, {"duration_ms": 2784, "name": "visual_preflight"}, {"duration_ms": 2188, "name": "policy_classifier"}, {"duration_ms": 2186, "name": "web_search"}]}
2026-08-08T08:18:35.403525279Z 2026-08-08 08:18:35 [INFO] services.post_turn_service: orchestration.post_turn_dispatched run_id=065c0384c1cf487ea50706559c678c16 conversation_id=0541e973-8dc4-4d74-b81b-4fe0b0fa1e71 reflection_durable=False evaluation_durable=False
2026-08-08T08:18:35.437612875Z 2026-08-08 08:18:35 [WARNING] persistqueue.queue: Default tempdir '/tmp/tmp40uddvt8' is not on the same filesystem with queue path '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue',defaulting to '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue'.
2026-08-08T08:18:35.720916061Z [GUM] Initializing new GUM instance for user 39bcc4a1-6be9-4817-80ae-9f5257721717...
2026-08-08T08:18:35.720952742Z INFO:     74.220.52.216:0 - "POST /api/v1/generate-title HTTP/1.1" 200 OK
2026-08-08T08:18:36.826340493Z 2026-08-08 08:18:36 [INFO] memory_store: [MemoryStore] Published learner state snapshot v237 for user 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-08T08:18:40.284639175Z 2026-08-08 08:18:40,284 - INFO - [STITCH] Filtering 20 candidates using Label Density Ranking...
2026-08-08T08:18:40.284739627Z 2026-08-08 08:18:40 [INFO] gum: [STITCH] Filtering 20 candidates using Label Density Ranking...
2026-08-08T08:18:40.284774608Z 2026-08-08 08:18:40,284 - INFO - [STITCH] Filtered down to 1 candidates.
2026-08-08T08:18:40.284787878Z 2026-08-08 08:18:40 [INFO] gum: [STITCH] Filtered down to 1 candidates.