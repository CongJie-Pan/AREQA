2026-09-04T14:13:59.934081722Z ==> Deploying...
2026-09-04T14:14:00.173788393Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-09-04T14:14:28.411388724Z 2026-09-04 14:14:28 [INFO] backend.main: background.worker_task_started name=delayed_mail_worker
2026-09-04T14:14:28.411448416Z 2026-09-04 14:14:28 [INFO] backend.main: background.worker_task_started name=agent_job_worker
2026-09-04T14:14:32.608591802Z 2026-09-04 14:14:32 [INFO] persistqueue.serializers.pickle: Selected pickle protocol: '4'
2026-09-04T14:14:32.609329149Z 2026-09-04 14:14:32 [INFO] persistqueue: Async queues not available, may need to install aiofiles and aiosqlite: No module named 'aiofiles'
2026-09-04T14:14:32.611589881Z 2026-09-04 14:14:32 [INFO] persistqueue: DBUtils may not be installed, install via 'pip install persist-queue[extra]'
2026-09-04T14:14:32.660963657Z 2026-09-04 14:14:32 [INFO] backend.main: background.worker_task_started name=reflection_loop
2026-09-04T14:14:32.661088689Z 2026-09-04 14:14:32 [INFO] services.compeer_scheduler: compeer.scheduler_started
2026-09-04T14:14:32.661206202Z 2026-09-04 14:14:32 [INFO] mailbox_store: mailbox.worker_starting worker_id=mailbox-75eee22c29a245949657a4e142294f34
2026-09-04T14:14:32.661215532Z 2026-09-04 14:14:32 [INFO] mailbox_store: mailbox.worker_disabled worker_id=mailbox-75eee22c29a245949657a4e142294f34
2026-09-04T14:14:32.808076591Z INFO:     Application startup complete.
2026-09-04T14:14:32.808157633Z 2026-09-04 14:14:32 [WARNING] backend.main: background.worker_task_stopped name=delayed_mail_worker
2026-09-04T14:14:32.808313666Z INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
2026-09-04T14:14:32.963560978Z Memory Store initialized successfully.
2026-09-04T14:14:32.963583818Z Mailbox Store initialized successfully.
2026-09-04T14:14:32.963588528Z Agent Job Store initialized successfully.
2026-09-04T14:14:32.963592508Z Redis RAG Cache initialized successfully.
2026-09-04T14:14:32.963597499Z INFO:     127.0.0.1:38558 - "HEAD / HTTP/1.1" 404 Not Found
2026-09-04T14:14:41.195728059Z ==> Your service is live 🎉
2026-09-04T14:14:41.436062701Z ==> 
2026-09-04T14:14:41.438748353Z ==> ///////////////////////////////////////////////////////////
2026-09-04T14:14:41.441156307Z ==> 
2026-09-04T14:14:41.444211438Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-04T14:14:41.446971402Z ==> 
2026-09-04T14:14:41.44913565Z ==> ///////////////////////////////////////////////////////////
2026-09-04T14:19:37.828456187Z ==> Detected service running on port 10000
2026-09-04T14:19:38.192284935Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-04T14:20:18.443490073Z 2026-09-04 14:20:18 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-04T14:20:18.443844001Z INFO:     116.59.49.139:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-04T14:20:47.579989515Z 2026-09-04 14:20:47 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-04T14:20:47.580300322Z INFO:     116.59.49.139:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-04T14:23:06.361092704Z 2026-09-04 14:23:06 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-04T14:23:06.361404871Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-04T14:23:23.456477296Z 2026-09-04 14:23:23 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-04T14:23:23.594829608Z 2026-09-04 14:23:23 [INFO] backend.main: realtime.session_create_started conversation_id=96081d0f-b390-4967-b66e-6eb9322065da authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-04T14:23:24.613571279Z 2026-09-04 14:23:24 [INFO] backend.main: realtime.session_create_completed conversation_id=96081d0f-b390-4967-b66e-6eb9322065da model=gpt-realtime-2.1-mini elapsed_ms=1018
2026-09-04T14:23:24.613854405Z INFO:     74.220.52.215:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-04T14:23:49.638960569Z 2026-09-04 14:23:49 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-04T14:23:49.798248851Z 2026-09-04 14:23:49 [INFO] backend.main: realtime.session_create_started conversation_id=96081d0f-b390-4967-b66e-6eb9322065da authenticated=True model=gpt-realtime-2.1-mini voice=marin
2026-09-04T14:23:50.195576782Z 2026-09-04 14:23:50 [INFO] backend.main: realtime.session_create_completed conversation_id=96081d0f-b390-4967-b66e-6eb9322065da model=gpt-realtime-2.1-mini elapsed_ms=397
2026-09-04T14:23:50.195879729Z INFO:     74.220.52.215:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-04T14:23:58.398308002Z 2026-09-04 14:23:58 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-04T14:23:58.426435077Z 2026-09-04 14:23:58 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-04T14:23:58.524795162Z 2026-09-04 14:23:58 [WARNING] persistqueue.queue: Default tempdir '/tmp/tmp22wyutnu' is not on the same filesystem with queue path '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue',defaulting to '/opt/render/project/src/data/gum_data/39bcc4a1-6be9-4817-80ae-9f5257721717/batches/queue'.
2026-09-04T14:23:58.811109838Z 2026-09-04 14:23:58 [INFO] backend.main: realtime.context_served conversation_id=96081d0f-b390-4967-b66e-6eb9322065da authenticated=True message_count=1 memory_count=2
2026-09-04T14:23:58.811583759Z [GUM] Initializing new GUM instance for user 39bcc4a1-6be9-4817-80ae-9f5257721717...
2026-09-04T14:23:58.811596039Z INFO:     74.220.52.215:0 - "POST /api/v1/realtime/context HTTP/1.1" 200 OK
2026-09-04T14:23:58.865544336Z 2026-09-04 14:23:58 [INFO] backend.main: realtime.context_served conversation_id=96081d0f-b390-4967-b66e-6eb9322065da authenticated=True message_count=1 memory_count=2
2026-09-04T14:23:58.865896015Z INFO:     74.220.52.215:0 - "POST /api/v1/realtime/context HTTP/1.1" 200 OK