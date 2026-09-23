2026-09-23T06:06:39.858866159Z ==> 
2026-09-23T06:06:39.860534169Z ==> ///////////////////////////////////////////////////////////
2026-09-23T06:07:39.055920686Z INFO:     Shutting down
2026-09-23T06:07:39.155548707Z INFO:     Waiting for application shutdown.
2026-09-23T06:07:39.155876585Z INFO:     Application shutdown complete.
2026-09-23T06:07:39.155936076Z INFO:     Finished server process [64]
2026-09-23T06:07:51.819543964Z 2026-09-23 06:07:51 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False conversation_history_debug_logs=True
2026-09-23T06:07:51.82332387Z INFO:     140.112.25.30:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-23T06:11:39.991718266Z ==> Detected service running on port 10000
2026-09-23T06:11:40.37172697Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-23T06:20:27.232627249Z 2026-09-23 06:20:27 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False conversation_history_debug_logs=True
2026-09-23T06:20:27.233035688Z INFO:     140.112.25.30:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-23T06:27:07.432356573Z INFO:     20.192.21.55:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 404 Not Found
2026-09-23T06:27:27.737727902Z INFO:     20.192.21.55:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 404 Not Found
2026-09-23T06:27:47.907095632Z INFO:     20.192.21.55:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 404 Not Found
2026-09-23T06:28:08.173634397Z INFO:     20.192.21.55:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 404 Not Found
2026-09-23T06:28:19.225297578Z ==> Deploying...
2026-09-23T06:28:19.466210743Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-23T06:28:28.455326586Z INFO:     20.192.21.55:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 404 Not Found
2026-09-23T06:28:48.655135196Z INFO:     20.192.21.55:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 404 Not Found
2026-09-23T06:28:48.752106946Z 2026-09-23 06:28:48 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-23T06:28:48.769956804Z 2026-09-23 06:28:48 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-23T06:28:48.769972104Z 2026-09-23 06:28:48 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-23T06:28:48.769976105Z 2026-09-23 06:28:48 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-23T06:28:48.769979125Z 2026-09-23 06:28:48 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-23T06:28:51.35366852Z 2026-09-23 06:28:51 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-23T06:28:51.356247471Z 2026-09-23 06:28:51 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-23T06:28:51.366653625Z 2026-09-23 06:28:51 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-23T06:28:51.371674362Z 2026-09-23 06:28:51 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-23T06:28:51.371829646Z 2026-09-23 06:28:51 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-23T06:28:51.37195168Z 2026-09-23 06:28:51 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-55176f3f360346f091eb15ff8d91f771
2026-09-23T06:28:51.371982621Z 2026-09-23 06:28:51 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-55176f3f360346f091eb15ff8d91f771
2026-09-23T06:28:51.472143509Z INFO:     Application startup complete.
2026-09-23T06:28:51.472351285Z 2026-09-23 06:28:51 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-23T06:28:51.472558011Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-23T06:28:52.136525283Z Memory Store initialized successfully.
2026-09-23T06:28:52.136551143Z Mailbox Store initialized successfully.
2026-09-23T06:28:52.136554433Z Agent Job Store initialized successfully.
2026-09-23T06:28:52.136557644Z Redis RAG Cache initialized successfully.
2026-09-23T06:28:52.136560404Z INFO:     127.0.0.1:37404 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-23T06:29:00.375983228Z ==> Your service is live 🎉
2026-09-23T06:29:00.458438729Z INFO:     35.233.144.17:0 - "GET / HTTP/1.1" 404 Not Found
2026-09-23T06:29:08.801934463Z 2026-09-23 06:29:08 [INFO] backend.main: conversation_history.backend_debug user_id=anonymous event=chat_history_probe context={"component": "codex", "conversationId": "deploy-probe", "status": "poll"}
2026-09-23T06:29:08.802291633Z INFO:     20.192.21.55:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:29:59.640307137Z INFO:     Shutting down
2026-09-23T06:29:59.740842804Z INFO:     Waiting for application shutdown.
2026-09-23T06:29:59.741188201Z INFO:     Application shutdown complete.
2026-09-23T06:29:59.741291693Z INFO:     Finished server process [61]
2026-09-23T06:30:09.94191272Z 2026-09-23 06:30:09 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False conversation_history_debug_logs=True
2026-09-23T06:30:09.943477623Z INFO:     140.112.25.30:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-23T06:30:29.306982269Z 2026-09-23 06:30:29 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False conversation_history_debug_logs=True
2026-09-23T06:30:29.307604486Z INFO:     140.112.25.30:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-23T06:30:30.410560712Z INFO:     140.112.25.30:0 - "OPTIONS /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:30.418974803Z INFO:     140.112.25.30:0 - "OPTIONS /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:30.858811816Z 2026-09-23 06:30:30 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:30.885588021Z INFO:     140.112.25.30:0 - "OPTIONS /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:30.888916483Z 2026-09-23 06:30:30 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:30.941421404Z 2026-09-23 06:30:30 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:30.970899963Z 2026-09-23 06:30:30 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:31.048369049Z 2026-09-23 06:30:31 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:31.075371011Z 2026-09-23 06:30:31 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:31.162528773Z 2026-09-23 06:30:31 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:31.25094385Z 2026-09-23 06:30:31 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:31.38211163Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_load_started context={"clearBeforeLoad": false, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:31.382542352Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:31.40358391Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_completed context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "displayMessageCount": 0, "durationMs": 243}
2026-09-23T06:30:31.405013429Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selected context={"activeConversationId": null, "component": "ConversationList", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:31.405272726Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:31.405704388Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:31.408788893Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selection_finished context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "ConversationList", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:31.40903898Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:31.414308954Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_cloud_hydration_finished context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "durationMs": 216, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:31.415096576Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_requested context={"component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "previousActiveConversationId": null}
2026-09-23T06:30:31.415324222Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:31.415717973Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:31.417270146Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_messages_committed context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "displayMessageCount": 0, "durationMs": 218, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:31.417718968Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:31.419823556Z 2026-09-23 06:30:31 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_local_messages_read context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "durationMs": 218, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:31.420018771Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.04913221Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.084784299Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.140477418Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.232063231Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_load_started context={"clearBeforeLoad": false, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:32.23273857Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_requested context={"component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "previousActiveConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:32.232979006Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selected context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "ConversationList", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:32.233389148Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.233819349Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.233994314Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.260572614Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.294436124Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.355690085Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.43382929Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.492635654Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_cloud_hydration_finished context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "durationMs": 211, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:32.494169556Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_completed context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "displayMessageCount": 0, "durationMs": 235}
2026-09-23T06:30:32.494407243Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.494958018Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.528350874Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selection_finished context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "ConversationList", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:32.530205005Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_messages_committed context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "displayMessageCount": 0, "durationMs": 213, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:32.530457562Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.530986747Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.561997178Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:32.646550379Z 2026-09-23 06:30:32 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_local_messages_read context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "durationMs": 212, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:32.646926089Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:32.976841035Z 2026-09-23 06:30:32 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.016560306Z 2026-09-23 06:30:33 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.054836076Z 2026-09-23 06:30:33 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.173199085Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selected context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "ConversationList", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:33.173607436Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:33.188556477Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_load_started context={"clearBeforeLoad": false, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:33.188753482Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:33.202401887Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_requested context={"component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "previousActiveConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:33.202824268Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:33.241947862Z 2026-09-23 06:30:33 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.275332359Z 2026-09-23 06:30:33 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.34202533Z 2026-09-23 06:30:33 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.371810317Z 2026-09-23 06:30:33 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.449934882Z 2026-09-23 06:30:33 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-23T06:30:33.558015539Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_sidebar_selection_finished context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "ConversationList", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091"}
2026-09-23T06:30:33.558401869Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:33.5729866Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_cloud_hydration_finished context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "durationMs": 217, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:33.573300608Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:33.582538402Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_local_messages_read context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "durationMs": 220, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:33.58281729Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:33.589406291Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_messages_committed context={"assistantMessageCount": 0, "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "deletionMarkerCount": 0, "displayMessageCount": 0, "durationMs": 221, "latestMessageUpdatedAt": null, "latestQueuedAt": null, "messageCount": 0, "pendingSyncCount": 0, "userMessageCount": 0}
2026-09-23T06:30:33.589780981Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK
2026-09-23T06:30:33.601085031Z 2026-09-23 06:30:33 [INFO] backend.main: conversation_history.backend_debug user_id=39bcc4a1-6be9-4817-80ae-9f5257721717 event=chat_history_switch_completed context={"activeConversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "component": "chatService", "conversationId": "ec2522c3-f05e-4c8e-a21f-3b32b538c091", "displayMessageCount": 0, "durationMs": 246}
2026-09-23T06:30:33.601431151Z INFO:     140.112.25.30:0 - "POST /api/v1/conversation-history/debug-log HTTP/1.1" 200 OK