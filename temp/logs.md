2026-08-25T11:41:38.949271591Z ==> Detected service running on port 10000
2026-08-25T11:41:39.308405077Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-08-25T11:49:47.707504818Z {"timestamp":"2026-08-25T11:49:47.707Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T11:51:56.458584516Z {"timestamp":"2026-08-25T11:51:56.458Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T11:53:22.412006307Z {"timestamp":"2026-08-25T11:53:22.411Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T11:54:59.484332498Z {"timestamp":"2026-08-25T11:54:59.484Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T12:06:01.671448735Z {"timestamp":"2026-08-25T12:06:01.671Z","level":"info","message":"share.create.request_received","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289"}}
2026-08-25T12:06:01.6716179Z {"timestamp":"2026-08-25T12:06:01.671Z","level":"info","message":"share.create.auth_header_present","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289"}}
2026-08-25T12:06:01.956118577Z {"timestamp":"2026-08-25T12:06:01.955Z","level":"info","message":"share.create.authenticated","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289"}}
2026-08-25T12:06:01.956541679Z {"timestamp":"2026-08-25T12:06:01.956Z","level":"info","message":"share.create.payload_received","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289","hasConversationPayload":true,"messageCount":2}}
2026-08-25T12:06:01.956702714Z {"timestamp":"2026-08-25T12:06:01.956Z","level":"info","message":"share.create.conversation_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289","titleLength":15}}
2026-08-25T12:06:02.049518666Z {"timestamp":"2026-08-25T12:06:02.049Z","level":"info","message":"share.create.conversation_upsert_succeeded","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289"}}
2026-08-25T12:06:02.049726762Z {"timestamp":"2026-08-25T12:06:02.049Z","level":"info","message":"share.create.messages_validated","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289","messageCount":2,"validMessageCount":2}}
2026-08-25T12:06:02.049803114Z {"timestamp":"2026-08-25T12:06:02.049Z","level":"info","message":"share.create.messages_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289","validMessageCount":2}}
2026-08-25T12:06:02.14559704Z {"timestamp":"2026-08-25T12:06:02.145Z","level":"error","message":"share.create_messages_upsert_failed","context":{"shareDebugId":"8d32b456dda0","conversationId":"96826ede-6281-41d5-b31e-d6199a857289","messageCount":2,"supabaseError":{"code":"23502","message":"null value in column \"attachments\" of relation \"messages\" violates not-null constraint","details":null,"hint":null}}}
2026-08-25T12:13:44.088740578Z {"timestamp":"2026-08-25T12:13:44.088Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T12:13:58.190150297Z {"timestamp":"2026-08-25T12:13:58.189Z","level":"info","message":"Forwarding title request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/generate-title"}
2026-08-25T12:14:06.595381819Z {"timestamp":"2026-08-25T12:14:06.595Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T12:14:16.246725945Z ==> Deploying...
2026-08-25T12:14:16.458445218Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-08-25T12:14:20.928976564Z {"timestamp":"2026-08-25T12:14:20.928Z","level":"info","message":"Forwarding title request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/generate-title"}
2026-08-25T12:14:28.243736413Z {"timestamp":"2026-08-25T12:14:28.243Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T12:14:40.800490619Z {"timestamp":"2026-08-25T12:14:40.800Z","level":"info","message":"Forwarding title request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/generate-title"}
2026-08-25T12:14:46.681228891Z ==> Running 'npm run start'
2026-08-25T12:14:47.364421688Z 
2026-08-25T12:14:47.364439398Z > areqa@0.1.0 start
2026-08-25T12:14:47.364443258Z > next start -H 0.0.0.0
2026-08-25T12:14:47.364464609Z 
2026-08-25T12:14:47.969851756Z    ▲ Next.js 16.0.7
2026-08-25T12:14:47.969965849Z    - Local:         http://localhost:10000
2026-08-25T12:14:47.969976749Z    - Network:       http://0.0.0.0:10000
2026-08-25T12:14:47.970081332Z 
2026-08-25T12:14:47.970114063Z  ✓ Starting...
2026-08-25T12:14:48.562400282Z [baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
2026-08-25T12:14:48.77226806Z  ⚠ Warning: Next.js inferred your workspace root, but it may not be correct.
2026-08-25T12:14:48.77228929Z  We detected multiple lockfiles and selected the directory of /opt/render/project/src/package-lock.json as the root directory.
2026-08-25T12:14:48.77229341Z  To silence this warning, set `outputFileTracingRoot` in your Next.js config, or consider removing one of the lockfiles if it's not needed.
2026-08-25T12:14:48.77229649Z    See https://nextjs.org/docs/app/api-reference/config/next-config-js/output#caveats for more information.
2026-08-25T12:14:48.772299531Z  Detected additional lockfiles: 
2026-08-25T12:14:48.772302711Z    * /opt/render/project/src/frontend/package-lock.json
2026-08-25T12:14:48.772304961Z 
2026-08-25T12:14:48.981461561Z  ✓ Ready in 1327ms
2026-08-25T12:14:57.169429066Z ==> Your service is live 🎉
2026-08-25T12:14:57.468042481Z ==> 
2026-08-25T12:14:57.469966777Z ==> ///////////////////////////////////////////////////////////
2026-08-25T12:14:57.472490559Z ==> 
2026-08-25T12:14:57.474510918Z ==> Available at your primary URL https://areqa-frontend-nzmx.onrender.com
2026-08-25T12:14:57.476294798Z ==> 
2026-08-25T12:14:57.478221698Z ==> ///////////////////////////////////////////////////////////
2026-08-25T12:19:10.709662213Z {"timestamp":"2026-08-25T12:19:10.709Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T12:19:28.31949227Z {"timestamp":"2026-08-25T12:19:28.319Z","level":"info","message":"Forwarding title request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/generate-title"}
2026-08-25T12:19:56.094550605Z ==> Detected service running on port 10000
2026-08-25T12:19:56.474701979Z ==> Docs on specifying a port: https://render.com/docs/web-services#port-binding
2026-08-25T12:20:26.714341059Z {"timestamp":"2026-08-25T12:20:26.714Z","level":"info","message":"share.create.request_received","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:20:26.714515514Z {"timestamp":"2026-08-25T12:20:26.714Z","level":"info","message":"share.create.auth_header_present","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:20:27.041763384Z {"timestamp":"2026-08-25T12:20:27.041Z","level":"info","message":"share.create.authenticated","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:20:27.042208105Z {"timestamp":"2026-08-25T12:20:27.042Z","level":"info","message":"share.create.payload_received","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","hasConversationPayload":true,"messageCount":2}}
2026-08-25T12:20:27.04243532Z {"timestamp":"2026-08-25T12:20:27.042Z","level":"info","message":"share.create.conversation_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","titleLength":10}}
2026-08-25T12:20:27.245792466Z {"timestamp":"2026-08-25T12:20:27.245Z","level":"info","message":"share.create.conversation_upsert_succeeded","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:20:27.246039602Z {"timestamp":"2026-08-25T12:20:27.245Z","level":"info","message":"share.create.messages_validated","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","messageCount":2,"validMessageCount":2}}
2026-08-25T12:20:27.246126044Z {"timestamp":"2026-08-25T12:20:27.246Z","level":"info","message":"share.create.messages_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","validMessageCount":2}}
2026-08-25T12:20:27.348196142Z {"timestamp":"2026-08-25T12:20:27.347Z","level":"error","message":"share.create_messages_upsert_failed","context":{"shareDebugId":"9a5388c22896","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","messageCount":2,"supabaseError":{"code":"23502","message":"null value in column \"attachments\" of relation \"messages\" violates not-null constraint","details":null,"hint":null}}}
2026-08-25T12:22:38.678387925Z {"timestamp":"2026-08-25T12:22:38.678Z","level":"info","message":"Forwarding chat request to internal backend: https://areqa-backend-v9ln.onrender.com/api/v1/stream"}
2026-08-25T12:24:58.590115424Z {"timestamp":"2026-08-25T12:24:58.589Z","level":"info","message":"share.create.request_received","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:24:58.590156295Z {"timestamp":"2026-08-25T12:24:58.590Z","level":"info","message":"share.create.auth_header_present","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:24:58.830375195Z {"timestamp":"2026-08-25T12:24:58.830Z","level":"info","message":"share.create.authenticated","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:24:58.830714153Z {"timestamp":"2026-08-25T12:24:58.830Z","level":"info","message":"share.create.payload_received","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","hasConversationPayload":true,"messageCount":4}}
2026-08-25T12:24:58.830775195Z {"timestamp":"2026-08-25T12:24:58.830Z","level":"info","message":"share.create.conversation_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","titleLength":10}}
2026-08-25T12:24:58.889755363Z {"timestamp":"2026-08-25T12:24:58.889Z","level":"info","message":"share.create.conversation_upsert_succeeded","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:24:58.889809684Z {"timestamp":"2026-08-25T12:24:58.889Z","level":"info","message":"share.create.messages_validated","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","messageCount":4,"validMessageCount":4}}
2026-08-25T12:24:58.889901946Z {"timestamp":"2026-08-25T12:24:58.889Z","level":"info","message":"share.create.messages_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","validMessageCount":4}}
2026-08-25T12:24:59.096572205Z {"timestamp":"2026-08-25T12:24:59.096Z","level":"error","message":"share.create_messages_upsert_failed","context":{"shareDebugId":"31f9e2a30209","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","messageCount":4,"supabaseError":{"code":"23502","message":"null value in column \"attachments\" of relation \"messages\" violates not-null constraint","details":null,"hint":null}}}
2026-08-25T12:35:52.533113544Z ==> Deploying...
2026-08-25T12:35:52.782834195Z ==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-08-25T12:36:28.063378957Z  ✓ Starting...
2026-08-25T12:36:28.679694146Z [baseline-browser-mapping] The data in this module is over two months old.  To ensure accurate Baseline data, please update: `npm i baseline-browser-mapping@latest -D`
2026-08-25T12:36:28.983109267Z  ⚠ Warning: Next.js inferred your workspace root, but it may not be correct.
2026-08-25T12:36:28.983133958Z  We detected multiple lockfiles and selected the directory of /opt/render/project/src/package-lock.json as the root directory.
2026-08-25T12:36:28.983137389Z  To silence this warning, set `outputFileTracingRoot` in your Next.js config, or consider removing one of the lockfiles if it's not needed.
2026-08-25T12:36:28.983140269Z    See https://nextjs.org/docs/app/api-reference/config/next-config-js/output#caveats for more information.
2026-08-25T12:36:28.983143059Z  Detected additional lockfiles: 
2026-08-25T12:36:28.983145629Z    * /opt/render/project/src/frontend/package-lock.json
2026-08-25T12:36:28.983147499Z 
2026-08-25T12:36:29.279145156Z  ✓ Ready in 1610ms
2026-08-25T12:36:33.74305996Z ==> Your service is live 🎉
2026-08-25T12:36:33.99168595Z ==> 
2026-08-25T12:36:33.993983532Z ==> ///////////////////////////////////////////////////////////
2026-08-25T12:36:33.995931132Z ==> 
2026-08-25T12:36:33.997369075Z ==> Available at your primary URL https://areqa-frontend-nzmx.onrender.com
2026-08-25T12:36:33.999112488Z ==> 
2026-08-25T12:36:34.001339656Z ==> ///////////////////////////////////////////////////////////
2026-08-25T12:39:08.772825725Z {"timestamp":"2026-08-25T12:39:08.772Z","level":"info","message":"share.create.request_received","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:39:08.772936562Z {"timestamp":"2026-08-25T12:39:08.772Z","level":"info","message":"share.create.auth_header_present","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:39:09.117851205Z {"timestamp":"2026-08-25T12:39:09.117Z","level":"info","message":"share.create.authenticated","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:39:09.11861251Z {"timestamp":"2026-08-25T12:39:09.118Z","level":"info","message":"share.create.payload_received","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","hasConversationPayload":true,"messageCount":4}}
2026-08-25T12:39:09.118755638Z {"timestamp":"2026-08-25T12:39:09.118Z","level":"info","message":"share.create.conversation_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","titleLength":10}}
2026-08-25T12:39:09.185793765Z {"timestamp":"2026-08-25T12:39:09.185Z","level":"info","message":"share.create.conversation_upsert_succeeded","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:39:09.186000747Z {"timestamp":"2026-08-25T12:39:09.185Z","level":"info","message":"share.create.messages_validated","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","messageCount":4,"validMessageCount":4}}
2026-08-25T12:39:09.188137202Z {"timestamp":"2026-08-25T12:39:09.185Z","level":"info","message":"share.create.messages_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","validMessageCount":4}}
2026-08-25T12:39:09.335534306Z {"timestamp":"2026-08-25T12:39:09.335Z","level":"warn","message":"share.create_messages_upsert_full_failed","context":{"shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","messageCount":4,"supabaseError":{"code":"23502","message":"null value in column \"attachments\" of relation \"messages\" violates not-null constraint","details":null,"hint":null}}}
2026-08-25T12:39:09.335629002Z {"timestamp":"2026-08-25T12:39:09.335Z","level":"info","message":"share.create.messages_minimal_upsert_started","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","validMessageCount":4}}
2026-08-25T12:39:09.388716501Z {"timestamp":"2026-08-25T12:39:09.388Z","level":"info","message":"share.create.messages_upsert_succeeded","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","validMessageCount":4}}
2026-08-25T12:39:09.388750273Z {"timestamp":"2026-08-25T12:39:09.388Z","level":"info","message":"share.create.conversation_lookup_started","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:39:09.417971815Z {"timestamp":"2026-08-25T12:39:09.416Z","level":"info","message":"share.create.conversation_lookup_succeeded","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:39:09.417987696Z {"timestamp":"2026-08-25T12:39:09.416Z","level":"info","message":"share.create.existing_lookup_started","context":{"component":"share-conversation-route","shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527"}}
2026-08-25T12:39:09.511521515Z {"timestamp":"2026-08-25T12:39:09.511Z","level":"error","message":"share.create_existing_lookup_failed","context":{"shareDebugId":"b5d7b4ad8363","conversationId":"b5fef0b1-cc64-41a5-b721-a7faadea1527","supabaseError":{"code":"PGRST205","message":"Could not find the table 'public.conversation_shares' in the schema cache","details":null,"hint":"Perhaps you meant the table 'public.conversations'"}}}