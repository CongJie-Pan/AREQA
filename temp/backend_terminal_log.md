2026-07-31T17:00:10.442564618Z 2026-07-31 17:00:10 [INFO] main: background.worker_task_started name=reflection_loop
2026-07-31T17:00:10.442634089Z 2026-07-31 17:00:10 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-07-31T17:00:10.470494517Z 2026-07-31 17:00:10 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-b84157eebb8945be97d723a9de13cc41
2026-07-31T17:00:10.470548628Z 2026-07-31 17:00:10 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-b84157eebb8945be97d723a9de13cc41
2026-07-31T17:00:10.684733455Z INFO:     Application startup complete.
2026-07-31T17:00:10.684878909Z 2026-07-31 17:00:10 [WARNING] main: background.worker_task_stopped name=delayed_mail_worker
2026-07-31T17:00:10.685301779Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-07-31T17:00:11.156450522Z Memory Store initialized successfully.
2026-07-31T17:00:11.156485423Z Mailbox Store initialized successfully.
2026-07-31T17:00:11.156490633Z Agent Job Store initialized successfully.
2026-07-31T17:00:11.156494743Z Redis RAG Cache initialized successfully.
2026-07-31T17:00:11.156502414Z INFO:     127.0.0.1:36792 - "HEAD / HTTP/1.1" 404 Not Found
2026-07-31T17:00:18.823175216Z ==> Your service is live 🎉
2026-07-31T17:00:19.094565403Z ==> 
2026-07-31T17:00:19.100298735Z ==> ///////////////////////////////////////////////////////////
2026-07-31T17:00:19.104051408Z ==> 
2026-07-31T17:00:19.107619568Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-07-31T17:00:19.112283968Z ==> 
2026-07-31T17:00:19.116386799Z ==> ///////////////////////////////////////////////////////////
2026-07-31T17:00:31.401445814Z INFO:     1.165.59.33:0 - "OPTIONS /api/v1/mailbox HTTP/1.1" 200 OK
2026-07-31T17:00:31.936147345Z 2026-07-31 17:00:31 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:00:32.28331163Z INFO:     1.165.59.33:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK
2026-07-31T17:00:36.38337257Z INFO:     1.165.59.33:0 - "OPTIONS /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-31T17:00:36.468586093Z 2026-07-31 17:00:36 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:00:36.55358185Z INFO:     1.165.59.33:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-31T17:00:36.827053695Z INFO:     1.165.59.33:0 - "WebSocket /api/v1/ws/notifications?ticket=42merlIExgYBVvzFnm5MjU2Ui1eG4nsZ_41Qv8kc8xA" [accepted]
2026-07-31T17:00:36.827081486Z INFO:     connection open
2026-07-31T17:00:36.827135207Z 2026-07-31 17:00:36 [INFO] services.connection_manager: WebSocket connected for user: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:00:42.964909044Z 2026-07-31 17:00:42 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:00:43.054838745Z INFO:     1.165.59.33:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK
2026-07-31T17:00:43.086440758Z 2026-07-31 17:00:43 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:00:43.257731913Z INFO:     74.220.52.32:0 - "POST /api/v1/stream HTTP/1.1" 200 OK
2026-07-31T17:00:45.969387213Z 2026-07-31 17:00:45 [WARNING] agents.tutor_agent: Tutor routing fallback: TimeoutError
2026-07-31T17:00:45.969675099Z 2026-07-31 17:00:45 [INFO] services.orchestration_service: orchestration.turn_plan_selected run_id=ae891ac2018840b5b9f2f61ad5b5bdbd conversation_id=51c1c50d-3dc1-44e5-a28c-247ee56826ad route=STATIC_GREETING enabled=True reason=LOW_INFORMATION_MESSAGE max_foreground_model_calls=2
2026-07-31T17:00:45.987335544Z 2026-07-31 17:00:45 [INFO] services.memory_ingestion_service: memory.ingestion_decided user_id=2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0 message_id=655a850e0350b924d292e76a conversation_id=51c1c50d-3dc1-44e5-a28c-247ee56826ad candidate_id=none state=working_context_only reason=low_information_greeting category=smalltalk promoted=False
2026-07-31T17:00:45.987355624Z 2026-07-31 17:00:45 [INFO] services.turn_intake_service: orchestration.memory_ingestion_dispatched run_id=ae891ac2018840b5b9f2f61ad5b5bdbd conversation_id=51c1c50d-3dc1-44e5-a28c-247ee56826ad outcome=working_context_only reason=low_information_greeting
2026-07-31T17:00:45.992263987Z 2026-07-31 17:00:45 [INFO] services.orchestration_service: orchestration.turn_trace_completed run_id=ae891ac2018840b5b9f2f61ad5b5bdbd conversation_id=51c1c50d-3dc1-44e5-a28c-247ee56826ad trace={'run_id': 'ae891ac2018840b5b9f2f61ad5b5bdbd', 'conversation_id': '51c1c50d-3dc1-44e5-a28c-247ee56826ad', 'elapsed_ms': 2734, 'phases': [{'name': 'request_accepted', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_started', 'elapsed_ms': 0, 'occurrence': 1}, {'name': 'search_routing_finished', 'elapsed_ms': 2712, 'occurrence': 1}, {'name': 'turn_plan_static_greeting', 'elapsed_ms': 2712, 'occurrence': 1}, {'name': 'turn_intake_started', 'elapsed_ms': 2712, 'occurrence': 1}, {'name': 'turn_intake_finished', 'elapsed_ms': 2734, 'occurrence': 1}, {'name': 'first_answer_delta', 'elapsed_ms': 2734, 'occurrence': 1}, {'name': 'terminal_sent', 'elapsed_ms': 2734, 'occurrence': 1}], 'model_calls': {'search_routing': 1}, 'tool_calls': {}, 'cache_statuses': {}}
2026-07-31T17:00:45.992297638Z 2026-07-31 17:00:45 [INFO] services.orchestration_service: orchestration.turn_trace_summary run_id=ae891ac2018840b5b9f2f61ad5b5bdbd conversation_id=51c1c50d-3dc1-44e5-a28c-247ee56826ad summary={"cache_statuses": {}, "conversation_id": "51c1c50d-3dc1-44e5-a28c-247ee56826ad", "elapsed_ms": 2734, "is_slow": false, "main_model_started_ms": null, "model_calls": {"search_routing": 1}, "phase_durations_ms": {"search_routing": 2712, "turn_intake": 22}, "provider_first_token_ms": null, "run_id": "ae891ac2018840b5b9f2f61ad5b5bdbd", "slow_reasons": [], "terminal_sent_ms": 2734, "time_to_first_answer_ms": 2734, "tool_calls": {}, "top_phase_durations": [{"duration_ms": 2712, "name": "search_routing"}, {"duration_ms": 22, "name": "turn_intake"}]}
2026-07-31T17:00:46.194869568Z INFO:     74.220.52.32:0 - "POST /api/v1/generate-title HTTP/1.1" 200 OK
2026-07-31T17:00:55.416080395Z 2026-07-31 17:00:55 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:00:55.507809265Z INFO:     1.165.59.33:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-31T17:00:55.738259394Z INFO:     1.165.59.33:0 - "WebSocket /api/v1/ws/notifications?ticket=xmuzQkeY50GLuqWI1ZbbxjvNQ9LuxsYY6giCR8GUTUs" [accepted]
2026-07-31T17:00:55.738288685Z INFO:     connection open
2026-07-31T17:00:55.738335686Z 2026-07-31 17:00:55 [INFO] services.connection_manager: WebSocket connected for user: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:01:13.382751387Z 2026-07-31 17:01:13 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:01:13.484273042Z INFO:     1.165.59.33:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK
2026-07-31T17:01:43.52736814Z 2026-07-31 17:01:43 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:01:43.693710901Z INFO:     1.165.59.33:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK
2026-07-31T17:02:31.428190456Z 2026-07-31 17:02:31 [INFO] auth: JWT successfully verified for user_id: 2cca1a29-8a6f-478a-a2af-fbc57ae5d3c0
2026-07-31T17:02:31.531612521Z INFO:     1.165.59.33:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK