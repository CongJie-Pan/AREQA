2026-09-06T18:03:03.977534159Z ==> Your service is live 🎉
2026-09-06T18:03:04.235817594Z ==> 
2026-09-06T18:03:04.238242021Z ==> ///////////////////////////////////////////////////////////
2026-09-06T18:03:04.241507119Z ==> 
2026-09-06T18:03:04.243910276Z ==> Available at your primary URL https://areqa-backend-v9ln.onrender.com
2026-09-06T18:03:04.246639878Z ==> 
2026-09-06T18:03:04.249525708Z ==> ///////////////////////////////////////////////////////////
2026-09-06T18:06:23.523790074Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-06T18:06:28.577279248Z 2026-09-06 18:06:28 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:06:28.746525293Z 2026-09-06 18:06:28 [INFO] backend.main: livekit.debug.avatar_session_token_created conversation_id=b676c5f6-908b-40ad-b2cc-0d9ee58d4233 room_name=areqa-live-82db36b2ba00f658-e6489a6c agent_name=areqa-live-tutor authenticated=True ttl_seconds=900 elapsed_ms=99
2026-09-06T18:06:28.746547554Z 2026-09-06 18:06:28 [INFO] backend.main: livekit.avatar_session_created conversation_id=b676c5f6-908b-40ad-b2cc-0d9ee58d4233 room_name=areqa-live-82db36b2ba00f658-e6489a6c agent_name=areqa-live-tutor authenticated=True elapsed_ms=100
2026-09-06T18:06:28.746949884Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/livekit-avatar-session HTTP/1.1" 200 OK
2026-09-06T18:06:40.164986657Z 2026-09-06 18:06:40 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:06:40.253534729Z 2026-09-06 18:06:40 [INFO] backend.main: realtime.debug.session_config_built conversation_id=5319f69a-4ba3-4be2-95ae-6f92a60e7be1 model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-06T18:06:40.25356371Z 2026-09-06 18:06:40 [INFO] backend.main: realtime.session_create_started conversation_id=5319f69a-4ba3-4be2-95ae-6f92a60e7be1 authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-06T18:06:40.2535684Z 2026-09-06 18:06:40 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=5319f69a-4ba3-4be2-95ae-6f92a60e7be1 authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-06T18:06:40.649868327Z 2026-09-06 18:06:40 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=5319f69a-4ba3-4be2-95ae-6f92a60e7be1 status=200 elapsed_ms=396
2026-09-06T18:06:40.649909988Z 2026-09-06 18:06:40 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=5319f69a-4ba3-4be2-95ae-6f92a60e7be1 expires_at_present=True client_secret_present=True
2026-09-06T18:06:40.649954659Z 2026-09-06 18:06:40 [INFO] backend.main: realtime.session_create_completed conversation_id=5319f69a-4ba3-4be2-95ae-6f92a60e7be1 model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=396
2026-09-06T18:06:40.6503623Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-06T18:07:50.372983824Z 2026-09-06 18:07:50 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:07:50.630369408Z 2026-09-06 18:07:50 [INFO] backend.main: realtime.debug.session_config_built conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-06T18:07:50.630391698Z 2026-09-06 18:07:50 [INFO] backend.main: realtime.session_create_started conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-06T18:07:50.630402639Z 2026-09-06 18:07:50 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-06T18:07:50.999083303Z 2026-09-06 18:07:50 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 status=200 elapsed_ms=368
2026-09-06T18:07:50.999115644Z 2026-09-06 18:07:50 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 expires_at_present=True client_secret_present=True
2026-09-06T18:07:50.999167445Z 2026-09-06 18:07:50 [INFO] backend.main: realtime.session_create_completed conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=368
2026-09-06T18:07:50.999579725Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-06T18:07:54.51508957Z 2026-09-06 18:07:54 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:07:54.599559494Z 2026-09-06 18:07:54 [INFO] backend.main: livekit.debug.avatar_session_token_created conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 room_name=areqa-live-0fce397283b6213f-c08b34d6 agent_name=areqa-live-tutor authenticated=True ttl_seconds=900 elapsed_ms=0
2026-09-06T18:07:54.599590165Z 2026-09-06 18:07:54 [INFO] backend.main: livekit.avatar_session_created conversation_id=b05fba67-e786-41ce-a55b-e80097f1ef55 room_name=areqa-live-0fce397283b6213f-c08b34d6 agent_name=areqa-live-tutor authenticated=True elapsed_ms=0
2026-09-06T18:07:54.600002616Z INFO:     74.220.52.32:0 - "POST /api/v1/realtime/livekit-avatar-session HTTP/1.1" 200 OK
2026-09-06T18:08:05.014624802Z ==> Detected service running on port 10000
2026-09-06T18:08:05.436010235Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-09-06T18:42:05.172855086Z 2026-09-06 18:42:05 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-06T18:42:05.173198255Z INFO:     111.80.227.157:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-06T18:42:15.803332069Z 2026-09-06 18:42:15 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-06T18:42:15.803672358Z INFO:     111.80.227.157:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-06T18:42:22.103043794Z 2026-09-06 18:42:22 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:42:22.354800299Z 2026-09-06 18:42:22 [INFO] backend.main: realtime.debug.session_config_built conversation_id=4e4a1210-f4d8-4f35-8937-938f868c2f5b model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-06T18:42:22.35482249Z 2026-09-06 18:42:22 [INFO] backend.main: realtime.session_create_started conversation_id=4e4a1210-f4d8-4f35-8937-938f868c2f5b authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-06T18:42:22.35483771Z 2026-09-06 18:42:22 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=4e4a1210-f4d8-4f35-8937-938f868c2f5b authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-06T18:42:23.513840691Z 2026-09-06 18:42:23 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=4e4a1210-f4d8-4f35-8937-938f868c2f5b status=200 elapsed_ms=1159
2026-09-06T18:42:23.513903772Z 2026-09-06 18:42:23 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=4e4a1210-f4d8-4f35-8937-938f868c2f5b expires_at_present=True client_secret_present=True
2026-09-06T18:42:23.513960874Z 2026-09-06 18:42:23 [INFO] backend.main: realtime.session_create_completed conversation_id=4e4a1210-f4d8-4f35-8937-938f868c2f5b model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=1159
2026-09-06T18:42:23.514373864Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-06T18:42:30.765603579Z 2026-09-06 18:42:30 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:42:30.875670685Z 2026-09-06 18:42:30 [INFO] backend.main: livekit.debug.avatar_session_token_created conversation_id=c4504125-c014-4428-a15b-c25a07ea2d69 room_name=areqa-live-28090f435153837f-5a349571 agent_name=areqa-live-tutor authenticated=True ttl_seconds=900 elapsed_ms=0
2026-09-06T18:42:30.875689915Z 2026-09-06 18:42:30 [INFO] backend.main: livekit.avatar_session_created conversation_id=c4504125-c014-4428-a15b-c25a07ea2d69 room_name=areqa-live-28090f435153837f-5a349571 agent_name=areqa-live-tutor authenticated=True elapsed_ms=0
2026-09-06T18:42:30.876054215Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/livekit-avatar-session HTTP/1.1" 200 OK
2026-09-06T18:43:48.50936767Z 2026-09-06 18:43:48 [INFO] backend.main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
2026-09-06T18:43:48.509741969Z INFO:     111.185.1.55:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-09-06T18:43:50.767326135Z 2026-09-06 18:43:50 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:43:50.856268216Z 2026-09-06 18:43:50 [INFO] backend.main: realtime.debug.session_config_built conversation_id=1ee38429-a5d8-4bcc-90c1-50006b02965b model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-06T18:43:50.856284856Z 2026-09-06 18:43:50 [INFO] backend.main: realtime.session_create_started conversation_id=1ee38429-a5d8-4bcc-90c1-50006b02965b authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-06T18:43:50.856301277Z 2026-09-06 18:43:50 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=1ee38429-a5d8-4bcc-90c1-50006b02965b authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-06T18:43:51.270759909Z 2026-09-06 18:43:51 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=1ee38429-a5d8-4bcc-90c1-50006b02965b status=200 elapsed_ms=414
2026-09-06T18:43:51.270837182Z 2026-09-06 18:43:51 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=1ee38429-a5d8-4bcc-90c1-50006b02965b expires_at_present=True client_secret_present=True
2026-09-06T18:43:51.270889103Z 2026-09-06 18:43:51 [INFO] backend.main: realtime.session_create_completed conversation_id=1ee38429-a5d8-4bcc-90c1-50006b02965b model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=414
2026-09-06T18:43:51.271427616Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK
2026-09-06T18:43:54.331401714Z 2026-09-06 18:43:54 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:43:54.417430233Z 2026-09-06 18:43:54 [INFO] backend.main: livekit.debug.avatar_session_token_created conversation_id=bfba359d-caeb-46a7-a3c7-8794e7221256 room_name=areqa-live-2d4c4251d21fa04e-765a607f agent_name=areqa-live-tutor authenticated=True ttl_seconds=900 elapsed_ms=0
2026-09-06T18:43:54.417490234Z 2026-09-06 18:43:54 [INFO] backend.main: livekit.avatar_session_created conversation_id=bfba359d-caeb-46a7-a3c7-8794e7221256 room_name=areqa-live-2d4c4251d21fa04e-765a607f agent_name=areqa-live-tutor authenticated=True elapsed_ms=0
2026-09-06T18:43:54.417773951Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/livekit-avatar-session HTTP/1.1" 200 OK
2026-09-06T18:44:00.185652817Z 2026-09-06 18:44:00 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-09-06T18:44:00.255607658Z 2026-09-06 18:44:00 [INFO] backend.main: realtime.debug.session_config_built conversation_id=8c8d6946-7437-4c67-b666-d4f44f997fb5 model=gpt-realtime-2.1-mini voice=marin interface_language=en output_modalities=audio input_transcription_model=gpt-4o-mini-transcribe turn_detection_type=server_vad tool_count=1 tool_names=get_areqa_context
2026-09-06T18:44:00.255630418Z 2026-09-06 18:44:00 [INFO] backend.main: realtime.session_create_started conversation_id=8c8d6946-7437-4c67-b666-d4f44f997fb5 authenticated=True model=gpt-realtime-2.1-mini voice=marin interface_language=en
2026-09-06T18:44:00.255642399Z 2026-09-06 18:44:00 [INFO] backend.main: realtime.debug.upstream_request_prepared conversation_id=8c8d6946-7437-4c67-b666-d4f44f997fb5 authenticated=True has_safety_identifier=True timeout_seconds=15.0
2026-09-06T18:44:00.642519833Z 2026-09-06 18:44:00 [INFO] backend.main: realtime.debug.upstream_response_received conversation_id=8c8d6946-7437-4c67-b666-d4f44f997fb5 status=200 elapsed_ms=386
2026-09-06T18:44:00.642657477Z 2026-09-06 18:44:00 [INFO] backend.main: realtime.debug.client_secret_issued conversation_id=8c8d6946-7437-4c67-b666-d4f44f997fb5 expires_at_present=True client_secret_present=True
2026-09-06T18:44:00.642670827Z 2026-09-06 18:44:00 [INFO] backend.main: realtime.session_create_completed conversation_id=8c8d6946-7437-4c67-b666-d4f44f997fb5 model=gpt-realtime-2.1-mini interface_language=en elapsed_ms=387
2026-09-06T18:44:00.643001236Z INFO:     74.220.52.33:0 - "POST /api/v1/realtime/session HTTP/1.1" 200 OK