2026-09-06T06:28:09.932289061Z ==> Deploying...
2026-09-06T06:28:10.131823422Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-06T06:28:30.578592047Z ==> Running 'python -m uvicorn main:app --host 0.0.0.0 --port $PORT'
2026-09-06T06:28:38.829343589Z INFO:     Started server process [61]
2026-09-06T06:28:38.829373949Z INFO:     Waiting for application startup.
2026-09-06T06:28:38.869312683Z 2026-09-06 06:28:38 [INFO] redis_client: Successfully connected to Redis.
2026-09-06T06:28:38.980264277Z 2026-09-06 06:28:38 [INFO] redis_client: system.redis_open_status status=open endpoint=rediss://ace-moray-116600.upstash.io:6379/0
2026-09-06T06:28:39.009780363Z 2026-09-06 06:28:39 [INFO] backend.main: background.worker_task_started name=proactive_scheduler_loop
2026-09-06T06:28:39.009819374Z 2026-09-06 06:28:39 [INFO] backend.main: background.worker_task_started name=daily_scheduler_loop
2026-09-06T06:28:39.009900176Z 2026-09-06 06:28:39 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-06T06:28:39.009943237Z 2026-09-06 06:28:39 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-06T06:28:45.178216057Z 2026-09-06 06:28:45 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-06T06:28:45.180849204Z 2026-09-06 06:28:45 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-06T06:28:45.188687815Z 2026-09-06 06:28:45 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-06T06:28:45.198978899Z 2026-09-06 06:28:45 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-06T06:28:45.199097882Z 2026-09-06 06:28:45 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-06T06:28:45.199283877Z 2026-09-06 06:28:45 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-5878eedce27648788d0e47575ba337a2
2026-09-06T06:28:45.199295917Z 2026-09-06 06:28:45 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-5878eedce27648788d0e47575ba337a2
2026-09-06T06:28:45.464860633Z INFO:     Application startup complete.
2026-09-06T06:28:45.464901934Z 2026-09-06 06:28:45 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-06T06:28:45.465093699Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-06T06:28:46.414107342Z Memory Store initialized successfully.
2026-09-06T06:28:46.414162524Z Mailbox Store initialized successfully.
2026-09-06T06:28:46.414168924Z Agent Job Store initialized successfully.
2026-09-06T06:28:46.414171724Z Redis RAG Cache initialized successfully.
2026-09-06T06:28:46.414174564Z INFO:     127.0.0.1:54994 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-06T06:28:50.764503132Z ==> Your service is live 🎉
2026-09-06T06:28:50.992466175Z ==> 
2026-09-06T06:28:50.995874627Z ==> ///////////////////////////////////////////////////////////
2026-09-06T06:28:50.998751932Z ==> 
2026-09-06T06:28:51.001176723Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-06T06:28:51.003945441Z ==> 
2026-09-06T06:28:51.006929662Z ==> ///////////////////////////////////////////////////////////
2026-09-06T06:33:55.357853229Z ==> Detected service running on port 10000
2026-09-06T06:33:55.745834088Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-06T06:33:57.526205739Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-06T06:33:57.52625204Z 2026-09-06 06:33:57 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-06T06:34:37.208465949Z 2026-09-06 06:34:37 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-06T06:34:37.208787167Z INFO:     223.143.33.88:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-06T06:36:35.837281075Z 2026-09-06 06:36:35 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T06:36:35.928011091Z 2026-09-06 06:36:35 [INFO] backend.main: realtime.session_create_started conversation_id=f420de88-bd87-43e7-9fb3-a3aaca55580b authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-06T06:36:36.859674859Z 2026-09-06 06:36:36 [INFO] backend.main: realtime.session_create_completed conversation_id=f420de88-bd87-43e7-9fb3-a3aaca55580b model=gpt-realtime-2.1-mini elapsed_ms=931
2026-09-06T06:36:36.860071669Z INFO:     74.220.52.216:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-06T06:37:22.884756091Z 2026-09-06 06:37:22 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-06T06:37:22.884787592Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK