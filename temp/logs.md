2026-08-26 12:43:55 [INFO] main: features.runtime_served mailbox=False compeer=False compeer_telemetry=False
INFO:     114.42.249.125:0 - "GET /api/v1/features HTTP/1.1" 200 OK
2026-08-26 12:44:11 [INFO] auth: JWT successfully verified for user_id: 39bcc4a1-6be9-4817-80ae-9f5257721717
2026-08-26 12:44:11 [INFO] services.attachment_service: attachment.processing_started count=2
2026-08-26 12:44:11 [WARNING] services.attachment_service: attachment.validation_failed code=ATTACHMENT_UNSUPPORTED_TYPE filename=How Companies Are Building Their Own Intelligence Sonya Huang_ Sequoia Capital _English _auto-generated__ _DownloadYoutu declared_type=text/plain extension=none size_bucket=lt_100kb status_code=422
INFO:     74.220.52.217:0 - "POST /api/v1/stream HTTP/1.1" 422 Unprocessable Entity
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [62]

{"timestamp":"2026-08-26T12:41:21.327Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
{"timestamp":"2026-08-26T12:41:21.875Z","level":"error","message":"FastAPI backend error","context":{"status":422,"clientId":"114.42.249.125"}}
{"timestamp":"2026-08-26T12:44:11.211Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
{"timestamp":"2026-08-26T12:44:11.786Z","level":"error","message":"FastAPI backend error","context":{"status":422,"clientId":"114.42.249.125"}}
==> Detected service running on port 10000
==> Docs on specifying a port: https://render.com/docs/web-services#port-binding