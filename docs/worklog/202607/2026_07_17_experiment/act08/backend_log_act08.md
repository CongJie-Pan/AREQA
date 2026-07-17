2026-07-17T13:57:56.024448315Z     await app(scope, receive, sender)
2026-07-17T13:57:56.024450645Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
2026-07-17T13:57:56.024452935Z     await self.app(scope, receive, send)
2026-07-17T13:57:56.024455205Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/routing.py", line 660, in __call__
2026-07-17T13:57:56.024457595Z     await self.middleware_stack(scope, receive, send)
2026-07-17T13:57:56.024459895Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 2672, in app
2026-07-17T13:57:56.024462235Z     await route.handle(scope, receive, send)
2026-07-17T13:57:56.024464546Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 1266, in handle
2026-07-17T13:57:56.024466886Z     await super().handle(scope, receive, send)
2026-07-17T13:57:56.024469176Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/routing.py", line 276, in handle
2026-07-17T13:57:56.024471456Z     await self.app(scope, receive, send)
2026-07-17T13:57:56.024473706Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 150, in app
2026-07-17T13:57:56.024476096Z     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
2026-07-17T13:57:56.024478376Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
2026-07-17T13:57:56.024480696Z     raise exc
2026-07-17T13:57:56.024482966Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
2026-07-17T13:57:56.024485246Z     await app(scope, receive, sender)
2026-07-17T13:57:56.024487556Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 136, in app
2026-07-17T13:57:56.024490256Z     response = await f(request)
2026-07-17T13:57:56.024492547Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 690, in app
2026-07-17T13:57:56.024494876Z     raw_response = await run_endpoint_function(
2026-07-17T13:57:56.024497156Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 344, in run_endpoint_function
2026-07-17T13:57:56.024499437Z     return await dependant.call(**values)
2026-07-17T13:57:56.024501737Z   File "/opt/render/project/src/backend/main.py", line 760, in edit_memory_endpoint
2026-07-17T13:57:56.024504037Z     await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))
2026-07-17T13:57:56.024510387Z UnboundLocalError: local variable 'json' referenced before assignment
2026-07-17T13:58:00.976452867Z 2026-07-17 13:58:00 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:01.712171821Z 2026-07-17 13:58:01 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:01.714025052Z [EDF-LOG] log_action endpoint received: [User Action] Type: scroll, Context: {'scrollY': 3.200000047683716}
2026-07-17T13:58:01.714041672Z INFO:     114.42.247.248:0 - "POST /api/v1/log_action HTTP/1.1" 200 OK
2026-07-17T13:58:08.777757779Z 2026-07-17 13:58:08 [INFO] services.compeer_scheduler: compeer.importance_evaluated importance=9.0 passed=True
2026-07-17T13:58:08.77778624Z 2026-07-17 13:58:08 [INFO] services.compeer_scheduler: compeer.legacy_schedule_due user_id=f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:09.476709331Z 2026-07-17 13:58:09 [INFO] gum_integration: hot_memory.snapshot_excluded user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 reason=not_prompt_safe
2026-07-17T13:58:09.476748913Z 2026-07-17 13:58:09 [INFO] gum_integration: hot_memory.snapshot_excluded user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 reason=not_prompt_safe
2026-07-17T13:58:09.476764623Z 2026-07-17 13:58:09 [INFO] gum_integration: hot_memory.snapshot_excluded user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 reason=not_prompt_safe
2026-07-17T13:58:09.476809444Z 2026-07-17 13:58:09 [INFO] gum_integration: hot_memory.snapshot_excluded user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 reason=not_prompt_safe
2026-07-17T13:58:10.353394725Z 2026-07-17 13:58:10 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:58:10.524461222Z 2026-07-17 13:58:10 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/embeddings "HTTP/1.1 200 OK"
2026-07-17T13:58:13.791182758Z 2026-07-17 13:58:13 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:13.978254656Z 2026-07-17 13:58:13 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:14.176178863Z 2026-07-17 13:58:14 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:14.586270059Z 2026-07-17 13:58:14 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:14.916342633Z 2026-07-17 13:58:14 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:14.93003929Z 2026-07-17 13:58:14 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:15.092415098Z INFO:     114.42.247.248:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-17T13:58:15.106341272Z INFO:     114.42.247.248:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-17T13:58:15.28613895Z INFO:     114.42.247.248:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK
2026-07-17T13:58:15.392864497Z 2026-07-17 13:58:15 [INFO] httpx: HTTP Request: POST https://openrouter.ai/api/v1/chat/completions "HTTP/1.1 200 OK"
2026-07-17T13:58:15.818026848Z INFO:     114.42.247.248:0 - "OPTIONS /api/v1/memory/summary?t=1784296684203 HTTP/1.1" 200 OK
2026-07-17T13:58:15.819674953Z INFO:     114.42.247.248:0 - "OPTIONS /api/v1/memory?t=1784296684203 HTTP/1.1" 200 OK
2026-07-17T13:58:15.860465965Z INFO:     114.42.247.248:0 - "WebSocket /api/v1/ws/notifications?ticket=SEmueaVMi51mfVCFK7sVnizKgv6Iu4a3YLlJItBK3yU" [accepted]
2026-07-17T13:58:15.860528997Z INFO:     connection open
2026-07-17T13:58:15.860755483Z 2026-07-17 13:58:15 [INFO] services.connection_manager: WebSocket connected for user: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:15.996331554Z 2026-07-17 13:58:15 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:16.179455474Z 2026-07-17 13:58:16 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:16.551884313Z INFO:     114.42.247.248:0 - "WebSocket /api/v1/ws/notifications?ticket=-HzW9HtHtHXWQz-RF7_HsophS7i6EL55dO7RP0kZehw" [accepted]
2026-07-17T13:58:16.551928025Z INFO:     connection open
2026-07-17T13:58:16.55210587Z 2026-07-17 13:58:16 [INFO] services.connection_manager: WebSocket connected for user: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:16.580693466Z 2026-07-17 13:58:16 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:16.941252659Z 2026-07-17 13:58:16 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:17.289193724Z 2026-07-17 13:58:17 [INFO] mailbox_store: mailbox.scheduled task_id=compeer-12a754c459f6636a1a0667974eece9f0 user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 kind=compeer_care delay_seconds=120
2026-07-17T13:58:17.289243166Z 2026-07-17 13:58:17 [INFO] services.compeer_scheduler: compeer.scheduled task_id=compeer-12a754c459f6636a1a0667974eece9f0 user_id=f263565b-f38f-4d3d-b33f-4ee01d528041 kind=compeer_care delay_seconds=120
2026-07-17T13:58:17.465439695Z INFO:     114.42.247.248:0 - "GET /api/v1/memory?t=1784296684203 HTTP/1.1" 200 OK
2026-07-17T13:58:17.813643357Z 2026-07-17 13:58:17 [INFO] services.hot_memory_service: hot_memory.created key=user_cooldown_until kind=operational_state export_eligible=False
2026-07-17T13:58:17.989442175Z 2026-07-17 13:58:17 [INFO] memory_store: [MemoryStore] Updated hot memory for user f263565b-f38f-4d3d-b33f-4ee01d528041, key: user_cooldown_until
2026-07-17T13:58:18.171568087Z INFO:     114.42.247.248:0 - "GET /api/v1/memory/summary?t=1784296684203 HTTP/1.1" 200 OK
2026-07-17T13:58:18.668423491Z 2026-07-17 13:58:18 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:18.989066335Z 2026-07-17 13:58:18 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:18.99104134Z [EDF-LOG] log_action endpoint received: [User Action] Type: scroll, Context: {'scrollY': 107.19999694824219}
2026-07-17T13:58:18.99105237Z INFO:     114.42.247.248:0 - "POST /api/v1/log_action HTTP/1.1" 200 OK
2026-07-17T13:58:22.096382459Z 2026-07-17 13:58:22 [INFO] services.hot_memory_service: hot_memory.created key=last_reflection_attempt_at kind=working_context export_eligible=False
2026-07-17T13:58:22.270901002Z 2026-07-17 13:58:22 [INFO] memory_store: [MemoryStore] Updated hot memory for user u1, key: last_reflection_attempt_at
2026-07-17T13:58:22.749307658Z 2026-07-17 13:58:22 [INFO] services.connection_manager: WebSocket disconnected for user: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:25.561437079Z 2026-07-17 13:58:25 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:25.866025431Z 2026-07-17 13:58:25 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:26.042454067Z INFO:     114.42.247.248:0 - "PUT /api/v1/memory/profile%3Aexplicit%3A14a9f753689122521073bfc2 HTTP/1.1" 500 Internal Server Error
2026-07-17T13:58:26.044098832Z ERROR:    Exception in ASGI application
2026-07-17T13:58:26.044111342Z   + Exception Group Traceback (most recent call last):
2026-07-17T13:58:26.044115502Z   |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_utils.py", line 85, in create_collapsing_task_group
2026-07-17T13:58:26.044129653Z   |     async with anyio.create_task_group() as tg:
2026-07-17T13:58:26.044132213Z   |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/anyio/_backends/_asyncio.py", line 815, in __aexit__
2026-07-17T13:58:26.044134273Z   |     raise BaseExceptionGroup(
2026-07-17T13:58:26.044136563Z   | exceptiongroup.ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
2026-07-17T13:58:26.044138673Z   +-+---------------- 1 ----------------
2026-07-17T13:58:26.044140593Z     | Traceback (most recent call last):
2026-07-17T13:58:26.044142513Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/uvicorn/protocols/http/h11_impl.py", line 416, in run_asgi
2026-07-17T13:58:26.044144813Z     |     result = await app(  # type: ignore[func-returns-value]
2026-07-17T13:58:26.044146703Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/uvicorn/middleware/proxy_headers.py", line 63, in __call__
2026-07-17T13:58:26.044148583Z     |     return await self.app(scope, receive, send)
2026-07-17T13:58:26.044150493Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/applications.py", line 1163, in __call__
2026-07-17T13:58:26.044152433Z     |     await super().__call__(scope, receive, send)
2026-07-17T13:58:26.044154423Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/applications.py", line 90, in __call__
2026-07-17T13:58:26.044157513Z     |     await self.middleware_stack(scope, receive, send)
2026-07-17T13:58:26.044160543Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/errors.py", line 186, in __call__
2026-07-17T13:58:26.044164334Z     |     raise exc
2026-07-17T13:58:26.044167134Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/errors.py", line 164, in __call__
2026-07-17T13:58:26.044169834Z     |     await self.app(scope, receive, _send)
2026-07-17T13:58:26.044172714Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/cors.py", line 96, in __call__
2026-07-17T13:58:26.044175354Z     |     await self.simple_response(scope, receive, send, request_headers=headers)
2026-07-17T13:58:26.044178484Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/cors.py", line 154, in simple_response
2026-07-17T13:58:26.044181674Z     |     await self.app(scope, receive, send)
2026-07-17T13:58:26.044183734Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 193, in __call__
2026-07-17T13:58:26.044185784Z     |     response = await self.dispatch_func(request, call_next)
2026-07-17T13:58:26.044189064Z     |   File "/opt/render/project/src/backend/main.py", line 243, in db_error_recovery_middleware
2026-07-17T13:58:26.044192234Z     |     response = await call_next(request)
2026-07-17T13:58:26.044194844Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 168, in call_next
2026-07-17T13:58:26.044198284Z     |     raise app_exc from app_exc.__cause__ or app_exc.__context__
2026-07-17T13:58:26.044201215Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 144, in coro
2026-07-17T13:58:26.044204565Z     |     await self.app(scope, receive_or_disconnect, send_no_error)
2026-07-17T13:58:26.044207325Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 193, in __call__
2026-07-17T13:58:26.044210065Z     |     response = await self.dispatch_func(request, call_next)
2026-07-17T13:58:26.044219065Z     |   File "/opt/render/project/src/backend/main.py", line 238, in chat_attachment_size_limit_middleware
2026-07-17T13:58:26.044222205Z     |     return await call_next(request)
2026-07-17T13:58:26.044225065Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 168, in call_next
2026-07-17T13:58:26.044231215Z     |     raise app_exc from app_exc.__cause__ or app_exc.__context__
2026-07-17T13:58:26.044234416Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 144, in coro
2026-07-17T13:58:26.044237256Z     |     await self.app(scope, receive_or_disconnect, send_no_error)
2026-07-17T13:58:26.044240706Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
2026-07-17T13:58:26.044243676Z     |     await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
2026-07-17T13:58:26.044246646Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
2026-07-17T13:58:26.044248556Z     |     raise exc
2026-07-17T13:58:26.044250466Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
2026-07-17T13:58:26.044252496Z     |     await app(scope, receive, sender)
2026-07-17T13:58:26.044263666Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
2026-07-17T13:58:26.044266506Z     |     await self.app(scope, receive, send)
2026-07-17T13:58:26.044271646Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/routing.py", line 660, in __call__
2026-07-17T13:58:26.044274837Z     |     await self.middleware_stack(scope, receive, send)
2026-07-17T13:58:26.044277777Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 2672, in app
2026-07-17T13:58:26.044280817Z     |     await route.handle(scope, receive, send)
2026-07-17T13:58:26.044283737Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 1266, in handle
2026-07-17T13:58:26.044286707Z     |     await super().handle(scope, receive, send)
2026-07-17T13:58:26.044289617Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/routing.py", line 276, in handle
2026-07-17T13:58:26.044292767Z     |     await self.app(scope, receive, send)
2026-07-17T13:58:26.044295947Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 150, in app
2026-07-17T13:58:26.044298047Z     |     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
2026-07-17T13:58:26.044299967Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
2026-07-17T13:58:26.044301877Z     |     raise exc
2026-07-17T13:58:26.044303757Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
2026-07-17T13:58:26.044305767Z     |     await app(scope, receive, sender)
2026-07-17T13:58:26.044307878Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 136, in app
2026-07-17T13:58:26.044309827Z     |     response = await f(request)
2026-07-17T13:58:26.044311807Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 690, in app
2026-07-17T13:58:26.044313718Z     |     raw_response = await run_endpoint_function(
2026-07-17T13:58:26.044315558Z     |   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 344, in run_endpoint_function
2026-07-17T13:58:26.044322318Z     |     return await dependant.call(**values)
2026-07-17T13:58:26.044324308Z     |   File "/opt/render/project/src/backend/main.py", line 760, in edit_memory_endpoint
2026-07-17T13:58:26.044326278Z     |     await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))
2026-07-17T13:58:26.044328528Z     | UnboundLocalError: local variable 'json' referenced before assignment
2026-07-17T13:58:26.044330328Z     +------------------------------------
2026-07-17T13:58:26.044332108Z 
2026-07-17T13:58:26.044334008Z The above exception was the direct cause of the following exception:
2026-07-17T13:58:26.044335778Z 
2026-07-17T13:58:26.044337658Z Traceback (most recent call last):
2026-07-17T13:58:26.044339588Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/uvicorn/protocols/http/h11_impl.py", line 416, in run_asgi
2026-07-17T13:58:26.044341518Z     result = await app(  # type: ignore[func-returns-value]
2026-07-17T13:58:26.044343379Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/uvicorn/middleware/proxy_headers.py", line 63, in __call__
2026-07-17T13:58:26.044345359Z     return await self.app(scope, receive, send)
2026-07-17T13:58:26.044347228Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/applications.py", line 1163, in __call__
2026-07-17T13:58:26.044349119Z     await super().__call__(scope, receive, send)
2026-07-17T13:58:26.044351069Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/applications.py", line 90, in __call__
2026-07-17T13:58:26.044352989Z     await self.middleware_stack(scope, receive, send)
2026-07-17T13:58:26.044354839Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/errors.py", line 186, in __call__
2026-07-17T13:58:26.044356799Z     raise exc
2026-07-17T13:58:26.044358739Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/errors.py", line 164, in __call__
2026-07-17T13:58:26.044360669Z     await self.app(scope, receive, _send)
2026-07-17T13:58:26.044362549Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/cors.py", line 96, in __call__
2026-07-17T13:58:26.044364499Z     await self.simple_response(scope, receive, send, request_headers=headers)
2026-07-17T13:58:26.044366359Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/cors.py", line 154, in simple_response
2026-07-17T13:58:26.044368229Z     await self.app(scope, receive, send)
2026-07-17T13:58:26.044370109Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 193, in __call__
2026-07-17T13:58:26.044371999Z     response = await self.dispatch_func(request, call_next)
2026-07-17T13:58:26.044373849Z   File "/opt/render/project/src/backend/main.py", line 243, in db_error_recovery_middleware
2026-07-17T13:58:26.044375729Z     response = await call_next(request)
2026-07-17T13:58:26.044379909Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 168, in call_next
2026-07-17T13:58:26.04439219Z     raise app_exc from app_exc.__cause__ or app_exc.__context__
2026-07-17T13:58:26.04439435Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 144, in coro
2026-07-17T13:58:26.04439628Z     await self.app(scope, receive_or_disconnect, send_no_error)
2026-07-17T13:58:26.04439828Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 193, in __call__
2026-07-17T13:58:26.04440381Z     response = await self.dispatch_func(request, call_next)
2026-07-17T13:58:26.04440579Z   File "/opt/render/project/src/backend/main.py", line 238, in chat_attachment_size_limit_middleware
2026-07-17T13:58:26.04440773Z     return await call_next(request)
2026-07-17T13:58:26.04440961Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 168, in call_next
2026-07-17T13:58:26.04441148Z     raise app_exc from app_exc.__cause__ or app_exc.__context__
2026-07-17T13:58:26.04441337Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/base.py", line 144, in coro
2026-07-17T13:58:26.04441521Z     await self.app(scope, receive_or_disconnect, send_no_error)
2026-07-17T13:58:26.04441719Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
2026-07-17T13:58:26.044419101Z     await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
2026-07-17T13:58:26.044420961Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
2026-07-17T13:58:26.044422821Z     raise exc
2026-07-17T13:58:26.044424681Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
2026-07-17T13:58:26.044426511Z     await app(scope, receive, sender)
2026-07-17T13:58:26.044428401Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
2026-07-17T13:58:26.044430311Z     await self.app(scope, receive, send)
2026-07-17T13:58:26.044432221Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/routing.py", line 660, in __call__
2026-07-17T13:58:26.044434291Z     await self.middleware_stack(scope, receive, send)
2026-07-17T13:58:26.044436221Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 2672, in app
2026-07-17T13:58:26.044438081Z     await route.handle(scope, receive, send)
2026-07-17T13:58:26.044439911Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 1266, in handle
2026-07-17T13:58:26.044441811Z     await super().handle(scope, receive, send)
2026-07-17T13:58:26.044443661Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/routing.py", line 276, in handle
2026-07-17T13:58:26.044445571Z     await self.app(scope, receive, send)
2026-07-17T13:58:26.044447421Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 150, in app
2026-07-17T13:58:26.044449291Z     await wrap_app_handling_exceptions(app, request)(scope, receive, send)
2026-07-17T13:58:26.044451101Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
2026-07-17T13:58:26.044452951Z     raise exc
2026-07-17T13:58:26.044454782Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
2026-07-17T13:58:26.044456651Z     await app(scope, receive, sender)
2026-07-17T13:58:26.044458492Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 136, in app
2026-07-17T13:58:26.044461142Z     response = await f(request)
2026-07-17T13:58:26.044462992Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 690, in app
2026-07-17T13:58:26.044464822Z     raw_response = await run_endpoint_function(
2026-07-17T13:58:26.044466702Z   File "/opt/render/project/src/.venv/lib/python3.10/site-packages/fastapi/routing.py", line 344, in run_endpoint_function
2026-07-17T13:58:26.044471522Z     return await dependant.call(**values)
2026-07-17T13:58:26.044473432Z   File "/opt/render/project/src/backend/main.py", line 760, in edit_memory_endpoint
2026-07-17T13:58:26.044476992Z     await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))
2026-07-17T13:58:26.044478882Z UnboundLocalError: local variable 'json' referenced before assignment
2026-07-17T13:58:30.419032496Z 2026-07-17 13:58:30 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:30.57321511Z INFO:     114.42.247.248:0 - "OPTIONS /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-17T13:58:30.573635761Z INFO:     114.42.247.248:0 - "OPTIONS /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-17T13:58:30.784626288Z 2026-07-17 13:58:30 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:30.882497382Z 2026-07-17 13:58:30 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:31.177492571Z 2026-07-17 13:58:31 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:31.373743812Z 2026-07-17 13:58:31 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:31.437842897Z INFO:     114.42.247.248:0 - "OPTIONS /api/v1/memory?t=1784296699785 HTTP/1.1" 200 OK
2026-07-17T13:58:31.44848717Z INFO:     114.42.247.248:0 - "OPTIONS /api/v1/memory/summary?t=1784296699785 HTTP/1.1" 200 OK
2026-07-17T13:58:31.549674184Z INFO:     114.42.247.248:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-17T13:58:31.602422366Z 2026-07-17 13:58:31 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:31.772118877Z 2026-07-17 13:58:31 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:31.884268283Z 2026-07-17 13:58:31 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:32.060213316Z INFO:     114.42.247.248:0 - "GET /api/v1/mailbox HTTP/1.1" 200 OK
2026-07-17T13:58:32.147877279Z INFO:     114.42.247.248:0 - "POST /api/v1/ws/ticket HTTP/1.1" 200 OK
2026-07-17T13:58:32.174780699Z 2026-07-17 13:58:32 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:32.355655167Z INFO:     114.42.247.248:0 - "WebSocket /api/v1/ws/notifications?ticket=_GArvQxlz4SkiaCt8-_cSDyfQ7qK2iMbfyRidbsyLOE" [accepted]
2026-07-17T13:58:32.355829522Z INFO:     connection open
2026-07-17T13:58:32.356014107Z 2026-07-17 13:58:32 [INFO] services.connection_manager: WebSocket connected for user: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:32.501437809Z 2026-07-17 13:58:32 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:33.060475996Z INFO:     114.42.247.248:0 - "GET /api/v1/memory?t=1784296699785 HTTP/1.1" 200 OK
2026-07-17T13:58:33.2219594Z INFO:     114.42.247.248:0 - "WebSocket /api/v1/ws/notifications?ticket=DoA8azjzi_O6a5r9a9EXW1qTod07cBhEeVG90M4BTcc" [accepted]
2026-07-17T13:58:33.222098584Z INFO:     connection open
2026-07-17T13:58:33.222258038Z 2026-07-17 13:58:33 [INFO] services.connection_manager: WebSocket connected for user: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:33.731084992Z INFO:     114.42.247.248:0 - "GET /api/v1/memory/summary?t=1784296699785 HTTP/1.1" 200 OK
2026-07-17T13:58:34.244437251Z 2026-07-17 13:58:34 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:34.9042037Z 2026-07-17 13:58:34 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:34.906416481Z [EDF-LOG] log_action endpoint received: [User Action] Type: scroll, Context: {'scrollY': 106.4000015258789}
2026-07-17T13:58:34.906431611Z INFO:     114.42.247.248:0 - "POST /api/v1/log_action HTTP/1.1" 200 OK
2026-07-17T13:58:39.482452225Z 2026-07-17 13:58:39 [INFO] services.connection_manager: WebSocket disconnected for user: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:41.08572244Z 2026-07-17 13:58:41 [INFO] auth: JWT successfully verified for user_id: f263565b-f38f-4d3d-b33f-4ee01d528041
2026-07-17T13:58:41.820576556Z 2026-07-17 13:58:41 [INFO] httpx: HTTP Request: GET https://hualwtskrtbkgvnidckr.supabase.co/auth/v1/user "HTTP/1.1 200 OK"
2026-07-17T13:58:41.822610721Z [EDF-LOG] log_action endpoint received: [User Action] Type: scroll, Context: {'scrollY': 6.400000095367432}
2026-07-17T13:58:41.822624762Z INFO:     114.42.247.248:0 - "POST /api/v1/log_action HTTP/1.1" 200 OK