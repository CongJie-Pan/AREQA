2026-09-27T03:41:33.139310067Z ==> Deploying...
2026-09-27T03:41:33.432580391Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-27T03:42:05.275232945Z 2026-09-27 03:42:05 [INFO] redis_client: Successfully connected to Redis.
2026-09-27T03:42:05.405083263Z 2026-09-27 03:42:05 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-27T03:42:05.416503517Z 2026-09-27 03:42:05 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-27T03:42:05.416526299Z 2026-09-27 03:42:05 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-27T03:42:05.416566061Z 2026-09-27 03:42:05 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-27T03:42:05.416580862Z 2026-09-27 03:42:05 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-27T03:42:08.783937228Z 2026-09-27 03:42:08 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-27T03:42:08.786649131Z 2026-09-27 03:42:08 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-27T03:42:08.794822593Z 2026-09-27 03:42:08 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-27T03:42:08.799331807Z 2026-09-27 03:42:08 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-27T03:42:08.79954803Z 2026-09-27 03:42:08 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-27T03:42:08.799663646Z 2026-09-27 03:42:08 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-3bf3e6405a284a8ca40f6ea3d8b24a8d
2026-09-27T03:42:08.799670306Z 2026-09-27 03:42:08 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-3bf3e6405a284a8ca40f6ea3d8b24a8d
2026-09-27T03:42:08.988029126Z INFO:     Application startup complete.
2026-09-27T03:42:08.988077549Z 2026-09-27 03:42:08 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-27T03:42:08.988242368Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-27T03:42:09.500768673Z Memory Store initialized successfully.
2026-09-27T03:42:09.500790154Z Mailbox Store initialized successfully.
2026-09-27T03:42:09.500793364Z Agent Job Store initialized successfully.
2026-09-27T03:42:09.500795924Z Redis RAG Cache initialized successfully.
2026-09-27T03:42:09.500798525Z INFO:     127.0.0.1:50276 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-27T03:42:14.257327845Z ==> Your service is live 🎉
2026-09-27T03:42:14.556356195Z ==> 
2026-09-27T03:42:14.558994185Z ==> ///////////////////////////////////////////////////////////
2026-09-27T03:42:14.561218197Z ==> 
2026-09-27T03:42:14.563382163Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-27T03:42:14.565136035Z ==> 
2026-09-27T03:42:14.566933131Z ==> ///////////////////////////////////////////////////////////
2026-09-27T03:45:19.113069816Z 2026-09-27 03:45:19 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False conversation_history_debug_logs=True
2026-09-27T03:45:19.113473509Z INFO:     116.59.49.3:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-27T03:45:20.858760785Z INFO:     116.59.49.3:0 - "OPTIONS /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:20.863787048Z INFO:     116.59.49.3:0 - "OPTIONS /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:20.870030791Z INFO:     116.59.49.3:0 - "OPTIONS /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:21.421465435Z 2026-09-27 03:45:21 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:21.489285001Z 2026-09-27 03:45:21 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:21.542443019Z 2026-09-27 03:45:21 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:21.67649396Z 2026-09-27 03:45:21 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selected context={"activeConversationId": null, "component": "ConversationList", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae"}
2026-09-27T03:45:21.676760456Z 2026-09-27 03:45:21 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_requested context={"component": "chatService", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae", "previousActiveConversationId": null}
2026-09-27T03:45:21.676972097Z 2026-09-27 03:45:21 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_load_started context={"clearBeforeLoad": false, "component": "chatService", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae"}
2026-09-27T03:45:21.677437034Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:21.677591862Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:21.67773065Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:22.806714122Z 2026-09-27 03:45:22 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:22.85489351Z 2026-09-27 03:45:22 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:22.907021371Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:22.907042482Z 2026-09-27 03:45:22 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_completed context={"activeConversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae", "component": "chatService", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae", "displayMessageCount": 51, "durationMs": 1187}
2026-09-27T03:45:22.935875628Z 2026-09-27 03:45:22 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selection_finished context={"activeConversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae", "component": "ConversationList", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae"}
2026-09-27T03:45:22.936185686Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:23.365869533Z 2026-09-27 03:45:23 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:23.404429568Z 2026-09-27 03:45:23 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:23.475192279Z 2026-09-27 03:45:23 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_messages_committed context={"assistantMessageCount": 23, "component": "chatService", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae", "deletionMarkerCount": 0, "displayMessageCount": 51, "durationMs": 653, "latestMessageUpdatedAt": "2026-09-25T13:43:21.314Z", "latestQueuedAt": null, "messageCount": 51, "pendingSyncCount": 0, "userMessageCount": 28}
2026-09-27T03:45:23.476331964Z 2026-09-27 03:45:23 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:45:23.500672517Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:23.536322367Z 2026-09-27 03:45:23 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_cloud_hydration_finished context={"assistantMessageCount": 23, "component": "chatService", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae", "deletionMarkerCount": 0, "durationMs": 648, "latestMessageUpdatedAt": "2026-09-25T13:43:21.314Z", "latestQueuedAt": null, "messageCount": 51, "pendingSyncCount": 0, "userMessageCount": 28}
2026-09-27T03:45:23.536664977Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:45:23.543265339Z 2026-09-27 03:45:23 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_local_messages_read context={"assistantMessageCount": 23, "component": "chatService", "conversationId": "05517cf4-4c97-4800-9838-0e03a0a39cae", "deletionMarkerCount": 0, "durationMs": 652, "latestMessageUpdatedAt": "2026-09-25T13:43:21.314Z", "latestQueuedAt": null, "messageCount": 51, "pendingSyncCount": 0, "userMessageCount": 28}
2026-09-27T03:45:23.566723492Z INFO:     116.59.49.3:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-27T03:46:25.070223635Z 2026-09-27 03:46:25 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:46:25.145993227Z 2026-09-27 03:46:25 [INFO] backend.main: realtime.debug.session_config_built conversation_id=0bb2fd3a-6579-4d6d-b24c-bee636f02249 model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=semantic_vad tool_count=1 tool_names=get_areqa_context
2026-09-27T03:46:25.146016829Z 2026-09-27 03:46:25 [INFO] backend.main: realtime.session_create_started conversation_id=0bb2fd3a-6579-4d6d-b24c-bee636f02249 authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en tutor_profile=general
2026-09-27T03:46:25.146050961Z 2026-09-27 03:46:25 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=0bb2fd3a-6579-4d6d-b24c-bee636f02249 authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-27T03:46:26.046276972Z 2026-09-27 03:46:26 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=0bb2fd3a-6579-4d6d-b24c-bee636f02249 status=200 elapsed_ms=900
2026-09-27T03:46:26.046383388Z 2026-09-27 03:46:26 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=0bb2fd3a-6579-4d6d-b24c-bee636f02249 expires_at_present=True client_secret_present=True
2026-09-27T03:46:26.046479013Z 2026-09-27 03:46:26 [INFO] backend.main: realtime.session_create_completed conversation_id=0bb2fd3a-6579-4d6d-b24c-bee636f02249 model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=900
2026-09-27T03:46:26.046858284Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-27T03:47:19.040114755Z ==> Detected service running on port 10000
2026-09-27T03:47:19.643906989Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-27T03:47:47.521641002Z 2026-09-27 03:47:47 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:47:47.775452299Z 2026-09-27 03:47:47 [INFO] backend.main: stream.request_accepted conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 response_mode=text tutor_profile=english message_count=3 upload_count=1
2026-09-27T03:47:47.792407566Z 2026-09-27 03:47:47 [INFO] backend.services.attachment_service: attachment.processing_started count=1
2026-09-27T03:47:47.793750772Z 2026-09-27 03:47:47 [INFO] backend.services.attachment_service: attachment.processed filename=Software with Taste with Geoffrey Litt AM Podcast _7 _English _auto-generated__ _DownloadYoutubeSubtitles.com_ _1_.txt declared_type=text/plain media_type=text/plain size_bucket=lt_100kb sha256_prefix=e0f3084a2e48
2026-09-27T03:47:47.799281904Z 2026-09-27 03:47:47 [INFO] services.speaking_material_service: speaking_material.saved chars=40000
2026-09-27T03:47:47.987099228Z INFO:     74.220.52.33:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-09-27T03:47:47.989719046Z 2026-09-27 03:47:47 [INFO] backend.services.orchestration_service: orchestration.turn_plan_selected run_id=94f824699d4d4fe5b6c5a53caa3c6f29 conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 route=ATTACHMENT_GROUNDED enabled=True reason=ATTACHMENT_CONTEXT_PRIORITY max_foreground_model_calls=3
2026-09-27T03:47:48.014651502Z 2026-09-27 03:47:48 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['current_focus', 'current_focus_conversation_id']
2026-09-27T03:47:48.014678254Z 2026-09-27 03:47:48 [INFO] services.memory_ingestion.rules: memory.ingestion_decided user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 message_id=804f57e963a313f3aef7c50e conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 candidate_id=none state=working_context_only reason=ordinary_user_message_for_current_turn category=current_focus promoted=False
2026-09-27T03:47:48.014682334Z 2026-09-27 03:47:48 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=94f824699d4d4fe5b6c5a53caa3c6f29 conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 outcome=working_context_only reason=ordinary_user_message_for_current_turn
2026-09-27T03:47:48.717220143Z 2026-09-27 03:47:48 [WARNING] backend.services.orchestration_service: orchestration.dialogue_policy_timeout conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 fallback=NORMAL
2026-09-27T03:47:48.71751554Z 2026-09-27 03:47:48 [INFO] backend.services.orchestration_service: orchestration.response_policy_applied conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 source=timeout_fallback metadata={"answer_depth": "SCAFFOLDED", "attachment_reason": "NO_ATTACHMENT", "attachment_task": "NONE", "evidence_mode": "NONE", "followup_mode": "OPTIONAL", "learning_mode": "LEARN", "learning_technique": "NONE", "legacy_policy": "NORMAL", "pedagogical_action": "EXPLAIN_PREREQ", "structure": "STEP_BY_STEP", "task_intent": "GENERAL_QA", "tone": "TUTORING", "visual_reason": "NOT_NEEDED", "visual_support": "NONE"}
2026-09-27T03:47:48.71787372Z 2026-09-27 03:47:48 [INFO] services.orchestration.prompting: parts_context.rewrite_gate conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 enabled=True route=ATTACHMENT_GROUNDED grounded=True allow_ungrounded=False
2026-09-27T03:47:49.34082648Z 2026-09-27 03:47:49 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-27T03:47:49.790717108Z 2026-09-27 03:47:49 [INFO] services.conversation.parts: parts_context.rewrite_selected route=ATTACHMENT_GROUNDED metadata={"confidence": "high", "has_act": true, "has_composed_instruction": true, "has_persona": true, "has_recipient": true, "has_structure": true, "has_theme": true, "missing_field_count": 1}
2026-09-27T03:47:51.300052668Z 2026-09-27 03:47:51 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:47:51.398323681Z 2026-09-27 03:47:51 [INFO] backend.main: realtime.debug.session_config_built conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=semantic_vad tool_count=1 tool_names=get_areqa_context
2026-09-27T03:47:51.398377684Z 2026-09-27 03:47:51 [INFO] backend.main: realtime.session_create_started conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en tutor_profile=english
2026-09-27T03:47:51.398403976Z 2026-09-27 03:47:51 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-27T03:47:52.159395383Z 2026-09-27 03:47:52 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 status=200 elapsed_ms=761
2026-09-27T03:47:52.159513129Z 2026-09-27 03:47:52 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 expires_at_present=True client_secret_present=True
2026-09-27T03:47:52.159536231Z 2026-09-27 03:47:52 [INFO] backend.main: realtime.session_create_completed conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=761
2026-09-27T03:47:52.159944403Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-27T03:49:03.990213047Z 2026-09-27 03:49:03 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-27T03:49:04.081334704Z 2026-09-27 03:49:04 [INFO] backend.main: realtime.debug.session_config_built conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=semantic_vad tool_count=1 tool_names=get_areqa_context
2026-09-27T03:49:04.081383686Z 2026-09-27 03:49:04 [INFO] backend.main: realtime.session_create_started conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en tutor_profile=english
2026-09-27T03:49:04.081416448Z 2026-09-27 03:49:04 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-27T03:49:04.50538751Z 2026-09-27 03:49:04 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 status=200 elapsed_ms=424
2026-09-27T03:49:04.505544479Z 2026-09-27 03:49:04 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 expires_at_present=True client_secret_present=True
2026-09-27T03:49:04.505573471Z 2026-09-27 03:49:04 [INFO] backend.main: realtime.session_create_completed conversation_id=e72c0e43-abbc-4142-a0f2-0a282c583f97 model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=424
2026-09-27T03:49:04.506010945Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK