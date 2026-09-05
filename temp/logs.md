2026-09-05T08:02:13.06458191Z 2026-09-05 08:02:13 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=baaa14e9f468442587fd2f6134d30081 conversation_id=be7dbb6b-66ef-4666-92f6-3c2ed4e24456 outcome=working_context_only reason=interrogative_not_memory_evidence
2026-09-05T08:02:13.065171922Z 2026-09-05 08:02:13 [INFO] services.orchestration.retrieval: orchestration.web_search_started conversation_id=be7dbb6b-66ef-4666-92f6-3c2ed4e24456 user_id=39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:02:14.130315949Z 2026-09-05 08:02:14 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T08:02:14.549379796Z 2026-09-05 08:02:14 [INFO] services.query_policy_service: orchestration.response_policy_selected metadata={"answer_depth": "SCAFFOLDED", "attachment_reason": "NO_ATTACHMENT", "attachment_task": "NONE", "followup_mode": "OPTIONAL", "legacy_policy": "NORMAL", "structure": "STEP_BY_STEP", "task_intent": "EXPLAIN_TEXT", "tone": "TUTORING", "visual_reason": "KNOWLEDGE_EXPLANATION", "visual_support": "OPTIONAL"}
2026-09-05T08:02:15.428141146Z 2026-09-05 08:02:15 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:02:15.512027047Z INFO:     74.220.52.216:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-09-05T08:02:16.514152882Z 2026-09-05 08:02:16 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T08:02:16.687517531Z 2026-09-05 08:02:16 [INFO] backend.services.orchestration_service: orchestration.turn_plan_selected run_id=82c3faf74d114886b9a3cc63cbb53838 conversation_id=be7dbb6b-66ef-4666-92f6-3c2ed4e24456 route=WEB_REQUIRED enabled=True reason=EXTERNAL_SEARCH_REQUIRED max_foreground_model_calls=3
2026-09-05T08:02:16.690364795Z 2026-09-05 08:02:16 [INFO] memory_store: [MemoryStore] Updated working memory for user 39bcc4a1-6be9-4817-80ae-9f5257721717: ['current_focus', 'current_focus_conversation_id']
2026-09-05T08:02:16.690387655Z 2026-09-05 08:02:16 [INFO] services.memory_ingestion.rules: memory.ingestion_decided user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 message_id=b920dfd1a6080d381dd2364d conversation_id=be7dbb6b-66ef-4666-92f6-3c2ed4e24456 candidate_id=none state=working_context_only reason=interrogative_not_memory_evidence category=current_focus promoted=False
2026-09-05T08:02:16.690427226Z 2026-09-05 08:02:16 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=82c3faf74d114886b9a3cc63cbb53838 conversation_id=be7dbb6b-66ef-4666-92f6-3c2ed4e24456 outcome=working_context_only reason=interrogative_not_memory_evidence
2026-09-05T08:02:16.690884295Z 2026-09-05 08:02:16 [INFO] services.orchestration.retrieval: orchestration.web_search_started conversation_id=be7dbb6b-66ef-4666-92f6-3c2ed4e24456 user_id=39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:02:17.638036681Z 2026-09-05 08:02:17 [INFO] httpx2: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-09-05T08:02:18.041856017Z 2026-09-05 08:02:18 [INFO] services.query_policy_service: orchestration.response_policy_selected metadata={"answer_depth": "SCAFFOLDED", "attachment_reason": "NO_ATTACHMENT", "attachment_task": "NONE", "followup_mode": "OPTIONAL", "legacy_policy": "NORMAL", "structure": "STEP_BY_STEP", "task_intent": "EXPLAIN_TEXT", "tone": "TUTORING", "visual_reason": "NOT_NEEDED", "visual_support": "NONE"}
2026-09-05T08:03:52.363616989Z 2026-09-05 08:03:52 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-05T08:03:52.364062168Z INFO:     140.112.25.1:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-05T08:06:31.098663286Z ==> Deploying...
2026-09-05T08:06:31.304934069Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-05T08:06:52.115188391Z ==> Running 'python -m uvicorn main:app --host 0.0.0.0 --port $PORT'
2026-09-05T08:07:00.039840009Z INFO:     Started server process [60]
2026-09-05T08:07:00.03985955Z INFO:     Waiting for application startup.
2026-09-05T08:07:00.101555914Z 2026-09-05 08:07:00 [INFO] redis_client: Successfully connected to Redis.
2026-09-05T08:07:00.206449357Z 2026-09-05 08:07:00 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-05T08:07:00.218249088Z 2026-09-05 08:07:00 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-05T08:07:00.218266168Z 2026-09-05 08:07:00 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-05T08:07:00.21833028Z 2026-09-05 08:07:00 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-05T08:07:00.218367401Z 2026-09-05 08:07:00 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-05T08:07:03.908951436Z 2026-09-05 08:07:03 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-05T08:07:03.909789895Z 2026-09-05 08:07:03 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-05T08:07:03.912018676Z 2026-09-05 08:07:03 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-05T08:07:03.917009721Z 2026-09-05 08:07:03 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-05T08:07:03.917137334Z 2026-09-05 08:07:03 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-05T08:07:03.917269607Z 2026-09-05 08:07:03 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-6a1a4139700f49bbb7673259ef4ab12a
2026-09-05T08:07:03.917286417Z 2026-09-05 08:07:03 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-6a1a4139700f49bbb7673259ef4ab12a
2026-09-05T08:07:04.204678523Z INFO:     Application startup complete.
2026-09-05T08:07:04.204736765Z 2026-09-05 08:07:04 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-05T08:07:04.204917959Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-05T08:07:04.32758761Z Memory Store initialized successfully.
2026-09-05T08:07:04.327620601Z Mailbox Store initialized successfully.
2026-09-05T08:07:04.327625401Z Agent Job Store initialized successfully.
2026-09-05T08:07:04.327628421Z Redis RAG Cache initialized successfully.
2026-09-05T08:07:04.327631341Z INFO:     127.0.0.1:60016 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-05T08:07:11.829023968Z ==> Your service is live 🎉
2026-09-05T08:07:12.044348094Z ==> 
2026-09-05T08:07:12.047710192Z ==> ///////////////////////////////////////////////////////////
2026-09-05T08:07:12.050213383Z ==> 
2026-09-05T08:07:12.052596007Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-05T08:07:12.05550088Z ==> 
2026-09-05T08:07:12.058238402Z ==> ///////////////////////////////////////////////////////////
2026-09-05T08:07:12.315418861Z INFO:     35.197.80.206:0 - "GET / HTTP/1.1" 404 Not Found
2026-09-05T08:08:11.230947965Z INFO:     Shutting down
2026-09-05T08:08:11.331473492Z INFO:     Waiting for application shutdown.
2026-09-05T08:08:11.331999312Z INFO:     Application shutdown complete.
2026-09-05T08:08:11.332035623Z INFO:     Finished server process [61]
2026-09-05T08:12:09.806815612Z ==> Detected service running on port 10000
2026-09-05T08:12:10.22254997Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-05T08:18:04.662701266Z [ComPeer] Proactive trigger needed: {'learner_state': 'RUN_REPEAT', 'pedagogical_strategy': '打破重複迴圈，採用降維打擊策略，將論文核心概念轉化為極簡的類比（例如：AI家教就像是教練，而非答案機），並透過提問引導其聚焦於特定細節，而非重複要求概括說明。', 'trigger_proactive': True}
2026-09-05T08:18:04.662707316Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:04.711952584Z 2026-09-05 08:18:04 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:04.813311065Z 2026-09-05 08:18:04 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.auth_header_present context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:04.813607072Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:04.96771119Z 2026-09-05 08:18:04 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:05.039099165Z 2026-09-05 08:18:05 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.authenticated context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:05.039450893Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:05.065785786Z 2026-09-05 08:18:05 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:05.133878555Z 2026-09-05 08:18:05 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.payload_received context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "hasConversationPayload": true, "messageCount": 14, "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:05.134124531Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:05.163935223Z 2026-09-05 08:18:05 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:05.253124666Z 2026-09-05 08:18:05 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.conversation_upsert_started context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a", "titleLength": 3}
2026-09-05T08:18:05.253389672Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:05.380769588Z 2026-09-05 08:18:05 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:05.459696946Z 2026-09-05 08:18:05 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.conversation_upsert_succeeded context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:05.459967322Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:05.48302947Z 2026-09-05 08:18:05 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:05.552342147Z 2026-09-05 08:18:05 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.messages_validated context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "messageCount": 14, "shareDebugId": "d5dd43b0f28a", "validMessageCount": 14}
2026-09-05T08:18:05.552669924Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:05.573101282Z 2026-09-05 08:18:05 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:05.664993316Z 2026-09-05 08:18:05 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.messages_upsert_started context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a", "validMessageCount": 14}
2026-09-05T08:18:05.665294593Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:05.803674272Z 2026-09-05 08:18:05 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:05.903857276Z 2026-09-05 08:18:05 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.messages_minimal_upsert_started context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a", "validMessageCount": 14}
2026-09-05T08:18:05.904128872Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:06.000801546Z 2026-09-05 08:18:06 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:06.085499845Z 2026-09-05 08:18:06 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.messages_upsert_succeeded context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a", "validMessageCount": 14}
2026-09-05T08:18:06.085908294Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:06.115137044Z 2026-09-05 08:18:06 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:06.18658047Z 2026-09-05 08:18:06 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.conversation_lookup_started context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:06.186835965Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:06.258271811Z 2026-09-05 08:18:06 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:06.330370702Z 2026-09-05 08:18:06 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.conversation_lookup_succeeded context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:06.33073585Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:06.35952683Z 2026-09-05 08:18:06 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:06.46435645Z 2026-09-05 08:18:06 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.existing_lookup_started context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:06.464603096Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:06.54910403Z 2026-09-05 08:18:06 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:06.622279216Z 2026-09-05 08:18:06 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.insert_started context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:06.622522592Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK
2026-09-05T08:18:06.707201091Z 2026-09-05 08:18:06 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-05T08:18:06.778464672Z 2026-09-05 08:18:06 [INFO] backend.main: share.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=share.create.created context={"component": "share-conversation-route", "conversationId": "be7dbb6b-66ef-4666-92f6-3c2ed4e24456", "shareDebugId": "d5dd43b0f28a"}
2026-09-05T08:18:06.778749929Z INFO:     74.220.52.217:0 - "POST /api/v1/share/debug-log HTTP/1.1" 200 OK