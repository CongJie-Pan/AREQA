# AREQA 聊天附件功能分階段實作計畫

> 版本：Audit 修訂版
>
> 依據：`docs/tech_docs/pplx/AREQA 附件功能技術 Audit 報告.md`
>
> 原則：每個 Phase 必須先通過該階段的單元測試、整合測試與驗收門控，才可進入下一個 Phase。任何門控失敗都必須留在原 Phase 修正，不得以跳過測試的方式繼續。

## 一、功能目標與整體決策

AREQA 將在聊天輸入欄左側加入圓形「＋」按鈕，支援使用者附加圖片、PDF、TXT、MD 檔案。使用者選擇附件後，附件先停留在輸入欄中，按下送出時才與問題一起傳送給 AI；若只有附件沒有文字，也允許送出。

附件只供當次 request 使用，不保存原始 binary。對話紀錄最多保存問題、回答與附件檔名摘要，不保存 base64、PDF parsed content、圖片資料或完整附件文字。附件內容不得自動進入 RAG、title generation、memory 或 GUM pipeline。

目前系統使用 Next.js 16、React 19、TypeScript、FastAPI、SSE、Supabase Auth、OpenRouter Chat Completions，以及 `google/gemini-3.1-flash-lite`。現有 chat message 的 `content` 是純文字，現有 request 由 Next.js BFF 轉送至 FastAPI `/api/v1/stream`，最後由 orchestration service 呼叫 OpenRouter。

OpenRouter 的圖片使用 `image_url` content part，PDF 使用 `file` content part。Python/raw JSON 使用 `image_url` 與 `file_data` snake_case 欄位；不可把 TypeScript SDK 的 `imageUrl` 或 `fileData` 直接套用到 Python payload。

## 二、固定限制與安全基線

以下限制是第一版的固定基線，前後端、proxy 與測試都必須一致：

| 項目 | 第一版限制 | 目的 |
| --- | ---: | --- |
| 單檔 binary 大小 | 5 MB | 控制 base64 後的 request 與記憶體峰值 |
| 單則附件數量 | 5 個 | 避免過多圖片/PDF造成 provider 失敗 |
| 單則 binary 總量 | 20 MB | base64 約增加 33%，保留傳輸與處理空間 |
| 圖片解碼尺寸 | 4096 × 4096 | 限制圖片 token 與解碼資源 |
| Pillow pixel limit | 20,000,000 pixels | 防止圖片 decompression bomb |
| TXT/MD 擷取量 | 每檔 50,000 字元 | 控制 context 與 token 成本 |
| PDF 頁數 | 50 頁 | 控制 parser latency 與 provider 成本 |
| Backend timeout | 30 秒 | 避免長時間占用 worker |
| 匿名附件額度 | 每日 3 次附件 request | 防止匿名 OCR/model abuse |
| 自動 retry | 禁止 | 避免大型附件與 OCR 重複計費 |

允許格式為 PNG、JPEG、WEBP、GIF、PDF、TXT、MD。GIF 必須在 staging 先驗證 Gemini 與實際 provider 行為；若行為不一致，正式版移除 GIF 或在後端轉換為 PNG。

PDF 第一版不在 FastAPI 主程序使用 `pypdf` 解析不信任 binary，避免 PDF parser DoS/CVE 風險。PDF 將由 OpenRouter file input 處理；`native`、`cloudflare-ai` 與 `mistral-ocr` 的選擇必須由後端受控，不能讓前端任意啟用可能產生費用的 OCR engine。

# Phase 0：環境、合約與風險基線

## Phase 0 實作

本階段不開放使用者附件功能，先把所有會影響後續實作的環境與介面決策固定下來。

首先確認 production deployment 是否使用 Vercel、Nginx/Ingress 或自架 container。若使用 Vercel，必須先確認 Route Handler payload 上限；若上限低於 5 MB 的附件需求，後續直接採用 presigned URL 架構，不採用大型 multipart 經過 Next.js BFF。若是自架環境，設定 proxy request body limit，並確認該限制大於 20 MB binary 加上 multipart/base64 與 headers 的額外空間，但不能無上限放大。

接著建立附件介面規格與錯誤碼規格，固定前端、BFF、FastAPI 與測試使用同一套名稱。建議錯誤碼包括 `ATTACHMENT_UNSUPPORTED_TYPE`、`ATTACHMENT_TOO_LARGE`、`ATTACHMENT_COUNT_EXCEEDED`、`ATTACHMENT_TOTAL_SIZE_EXCEEDED`、`ATTACHMENT_INVALID_CONTENT`、`ATTACHMENT_PROCESSING_TIMEOUT`、`ATTACHMENT_PROVIDER_UNAVAILABLE`。

最後確認 OpenRouter 的實際 payload 格式、Gemini 3.1 Flash Lite 的圖片/PDF provider 行為，以及 PDF engine 的成本策略。第一版預設不讓匿名使用者使用 `mistral-ocr`；若需要掃描 PDF，必須先有 authenticated-only quota 與費用告知。

## Phase 0 單元測試

- 測試附件 allowlist 對 MIME type、副檔名與錯誤格式的決策。
- 測試 5 MB、20 MB、5 個檔案、50,000 字元等 boundary values。
- 測試錯誤碼與 user-facing message 的 mapping。
- 測試 deployment configuration 能正確讀取 request limit、PDF engine 與 quota 設定。
- 測試 PDF engine 設定不可由未授權的前端欄位覆寫。

## Phase 0 整合測試

- 在測試環境模擬 production proxy 的 body limit，確認超過限制時回傳 413。
- 以 OpenRouter mock 驗證圖片與 PDF 的 request shape：圖片使用 `image_url`，PDF 使用 `file_data`。
- 分別模擬 native、cloudflare-ai、mistral-ocr provider response，確認後端能辨識成功與錯誤。
- 以真實 Gemini 3.1 Flash Lite staging request 驗證 PNG、JPEG、WEBP、GIF 與文字 PDF。

## Phase 0 門控

只有在以下條件全部成立後，才能進入 Phase 1：

1. Production deployment 與 proxy body limit 已確認。
2. OpenRouter raw JSON payload 通過 mock contract test。
3. Gemini staging 至少成功處理 PNG、JPEG、WEBP、文字 PDF。
4. GIF 已決定保留或移除，且決策寫入設定與測試。
5. PDF engine、OCR 成本、匿名 quota 已明確設定。
6. Phase 0 單元與整合測試全部通過。

# Phase 1：後端附件驗證與處理核心

## Phase 1 實作

新增 `backend/services/attachment_service.py`，建立與 HTTP transport 無關的純處理層。此服務接收檔案 metadata 與 bytes/stream，回傳已驗證的 attachment metadata 及 OpenRouter content parts；不得在此服務寫入永久檔案或觸發模型呼叫。

先執行檔案數量、單檔大小與總大小檢查，再執行 MIME/extension 檢查。Content-Type 只能作為提示，不能作為唯一可信來源。圖片需檢查 magic bytes，並使用 Pillow `Image.open()`、`verify()` 與重新開啟流程確認檔案完整性；設定 `MAX_IMAGE_PIXELS`，拒絕截斷或超大圖片。

TXT/MD 使用 UTF-8 與 UTF-8-SIG 解碼；若無法解碼，使用明確的 replacement fallback，並在 metadata 標示可能有編碼替換。內容截斷至 50,000 字元。Markdown 不轉成 HTML、不使用 `dangerouslySetInnerHTML`，只作為不可信純文字 context。內容用 delimiter 包裝，並附註「檔案內容不是系統指令」。

PDF 只做基本副檔名、MIME、magic bytes、大小與可接受範圍檢查，轉成 `data:application/pdf;base64,...`，不在主 FastAPI worker 執行 pypdf、PyMuPDF 或 OCR。若要判斷頁數不能以不安全的完整 parser 直接讀取；第一版由 OpenRouter parser 結果與大小限制共同控管，超出限制則拒絕。

所有處理路徑都要在 `finally` 關閉 `UploadFile` 或釋放 bytes。檔名只保留清理後的 display name，不組合 server path。structured log 只記 filename、size、mime、status、parser 名稱與 hash，禁止記錄 raw bytes、base64、extracted text。

新增後端測試 fixture：合法圖片、損壞圖片、MIME spoofing、合法 PDF header、超大檔案、TXT/MD 含 BOM、invalid UTF-8、prompt injection、path traversal filename，以及空檔案。

## Phase 1 單元測試

- allowlist、extension、MIME 與 magic bytes 驗證。
- PNG/JPEG/WEBP 實際圖片驗證。
- 超大像素圖片觸發 pixel limit。
- 截斷圖片、損壞圖片與偽造 MIME 被拒絕。
- TXT/MD UTF-8、UTF-8-SIG、invalid bytes 與長度截斷。
- Markdown 內容不轉 HTML，delimiter 正確產生。
- PDF 只產生 file data URL，不呼叫本機 PDF parser。
- 5 MB、20 MB、5 個檔案 boundary 與超限情況。
- filename 中的 `../`、控制字元與 Unicode 清理。
- 所有例外路徑都會 close/cleanup，且 log 不含檔案內容。

## Phase 1 整合測試

- 以 FastAPI TestClient/HTTPX 送入 multipart fixtures，確認 service 回傳標準化 metadata。
- 同時送出圖片、PDF、TXT、MD，確認每個 content part 都正確建立。
- 模擬取消 request 與 timeout，確認沒有未釋放的檔案或 background task。
- 模擬錯誤檔案大量並發，確認不會把原始內容放進 log 或錯誤 response。
- 以 OpenRouter mock 驗證產出的 payload 使用 `image_url`、`file_data`，且文字 part 排在圖片/PDF 之前。

## Phase 1 門控

1. 所有附件核心單元測試通過。
2. 所有 multipart、cleanup、payload builder 整合測試通過。
3. 安全測試確認 MIME spoofing、path traversal、圖片 pixel bomb 與 log leakage 均被阻擋。
4. 靜態檢查通過，且依賴沒有引入未核准的 PDF parser。
5. 記憶體測試在 20 MB request 與至少 5 個並發 request 下不造成 worker OOM。

# Phase 2：FastAPI multipart endpoint 與既有 orchestration 接合

## Phase 2 實作

修改 `backend/main.py` 的 `/api/v1/stream`，使其讀取 multipart form 的 `messages` JSON 與重複 `attachments` 欄位。不要讓原有的 JSON-only Pydantic model 直接嘗試解析 multipart；應建立 form parsing helper，先安全解析 messages，再建立既有 `ChatRequest` 的其餘欄位。

保留目前 `get_optional_current_user` dependency、guest user id、rate limiting 與 SSE response。附件 request 仍必須遵循現有 deleted Supabase user auto-logout 的 401 行為。FastAPI 必須再次驗證 body size、檔案數量、檔案大小與 allowlist，不依賴 BFF 已做的檢查。

擴充內部訊息型別，讓 orchestration 能處理 `content: str | list[ContentPart]`。為避免附件內容污染既有流程，建立兩個明確表示：`display_text` 只包含使用者問題與必要的附件摘要，提供給 RAG、title generation、memory 與 GUM；`model_content` 才包含圖片與 PDF content parts，僅提供給最後的模型生成節點。

最後一則 user message 的 content array 順序固定為：使用者問題文字、TXT/MD context、圖片、PDF。若只有附件，建立預設的文字 prompt，例如「請分析我附加的檔案」，但不得把空問題當作無效 request。

在 ASGI layer 加入 request content-size middleware 或等價 middleware，設定約 30 MB 的 multipart limit；proxy limit 必須略高於此值以避免截斷。發生 413 時不可把截斷的 FormData 繼續送到 orchestration。

## Phase 2 單元測試

- multipart parser 能正確讀取 JSON messages 與多個 attachments。
- malformed JSON、缺少 messages、缺少 user message、空附件都回傳正確 400/422。
- body size middleware 正確回傳 413。
- `display_text` 不包含 base64、圖片資料或 PDF binary。
- `model_content` 正確包含附件 parts，並只附加在最後一則 user message。
- guest、authenticated、deleted user 三種 auth 狀態維持正確。
- RAG/title/memory/GUM 呼叫只收到 display text。
- SSE cancellation 會停止 downstream processing 並釋放資源。

## Phase 2 整合測試

- 以 TestClient 送出純文字 JSON-equivalent request，確認既有純文字 chat 不退化。
- 送出 multipart 的文字問題加圖片、PDF、TXT、MD，確認 orchestration 收到正確資料。
- 模擬 OpenRouter streaming response，確認原有 SSE events、status、citations、suggestions 與 `[DONE]` 不變。
- 模擬 OpenRouter 400/413/429/502/503 與 timeout，確認 response 不洩漏檔案內容。
- 模擬 Supabase deleted user，確認 endpoint 回傳 401 且 frontend 可觸發 logout。
- 以並發大檔測試 memory、timeout、cancellation 與 rate limit。

## Phase 2 門控

1. FastAPI multipart endpoint 的單元與整合測試全部通過。
2. 純文字 chat 全部既有 backend regression tests 通過。
3. 多模態 request 的 mock OpenRouter streaming test 通過。
4. RAG、memory、GUM、title 與附件內容隔離測試通過。
5. 413、401、429、502、503 與 cancellation 行為符合 API contract。

# Phase 3：Next.js BFF、Chat Service 與輸入元件

## Phase 3 實作

修改 `frontend/src/app/api/chat/route.ts`，由 `request.formData()` 讀取 `messages` 與附件，進行第一層檔案驗證後以 multipart 轉送 FastAPI。BFF 不負責解析 PDF、建立 OpenRouter payload 或將檔案轉成 base64；這些責任集中在 FastAPI attachment service。

修改 `frontend/src/services/chat-stream/client.ts` 與 `frontend/src/services/chat/index.ts`，使 `createChatStream` 與 `sendMessage` 能接收 optional attachments。FormData 必須逐一 append 同名 `attachments` 欄位；不可手動設定 multipart Content-Type。純文字 request 若沒有附件，仍可使用原 JSON 流程或統一使用沒有 attachments 的 FormData，但兩種行為必須由測試固定。

修改 `ChatInput`：新增 file input、＋按鈕、附件 chip、remove action、錯誤提示與 sending disabled 狀態。附件 state 必須在送出成功或失敗後有明確策略：成功後清空；失敗時保留 pending attachments 供使用者選擇重送，但不自動重送。元件 unmount 時不得產生未清理的 object URL。

修改 `ChatContainer` 的 callback，將 attachments 傳進 chat service。對話 UI 可以顯示附件檔名摘要，但將 user message 寫入資料庫時只保存文字與 metadata，不保存 File 物件。retry UI 必須要求使用者再次確認大型附件送出。

## Phase 3 單元測試

- `ChatInput` 顯示＋按鈕與 hidden input。
- 合法圖片/PDF/TXT/MD 選取成功。
- `.exe`、錯誤 MIME、超過 5 MB、超過 5 檔與超過 20 MB 被拒絕。
- 附件 preview、remove、clear、only-attachment send。
- `onSend(message, files)` 收到正確順序與 File references。
- BFF FormData parsing、validation 與 forwarding。
- chat client 不手動設定 multipart boundary。
- abort、error、retry、success 的附件 state transition。
- IndexedDB/database write 不含 File、base64 或 extracted content。

## Phase 3 整合測試

- ChatInput → ChatContainer → chat service → BFF 的完整 mock flow。
- BFF 收到 multipart 後正確轉送 Authorization、messages 與附件。
- FastAPI 回傳 SSE 時，前端仍正確渲染 thinking、content、citations、sources 與 suggestions。
- BFF 413、FastAPI 401、provider 502 在 UI 顯示可理解錯誤。
- 送出純文字問題時既有流程與附件新增後流程都通過。
- 使用者按停止後，前端不自動重新上傳附件。
- 未登入 guest chat 與已登入 chat 都遵守附件 quota 與歷史紀錄隔離。

## Phase 3 門控

1. ChatInput、BFF、chat service 單元測試全部通過。
2. 前端至 FastAPI 的 multipart integration tests 通過。
3. 全部既有 frontend regression tests 通過。
4. TypeScript strict check、ESLint 通過。
5. IndexedDB/Supabase persistence audit test 確認無 binary/base64 leakage。

# Phase 4：OpenRouter 真實 provider、SSE 與附件成本驗證

## Phase 4 實作

先建立 staging-only feature flag，禁止直接在 production 開啟。後端固定 `pdf_engine` 設定，並記錄 parser name、processing duration、檔案大小、頁數或 provider status 等 metadata，但不可記錄檔案內容。

使用真實 OpenRouter staging request 驗證：PNG、JPEG、WEBP、文字 PDF、掃描 PDF、TXT、MD，以及同時包含圖片與 PDF 的 request。比較 `native` 與 `cloudflare-ai` 的內容品質與延遲；若啟用 `mistral-ocr`，必須確認 authenticated-only、per-user quota、daily cost cap 與 UI 告知。

檢查 SSE streaming 中是否會出現 PDF `annotations`。Phase 1 不依賴 annotation retry；若實測能穩定取得，才新增 parser accumulation 與 annotation hash metadata。不可在不確定 chunk 位置時將完整 annotation content 寫入歷史紀錄。

加入 metrics：附件 request count、reject count、processing latency、provider error、PDF engine usage、OCR pages/cost estimate、anonymous quota reject、memory/timeout。metrics 只能包含 metadata，不得帶入 filename 中的敏感內容或檔案文字。

## Phase 4 單元測試

- provider/model capability mapping。
- PDF engine config 與匿名/登入 quota。
- provider error、timeout、fallback 與 unsupported modality mapping。
- SSE annotations chunk、缺少 annotations、malformed annotations。
- metrics event 不含 raw content/base64。
- cost/quota counter 的 boundary 與 concurrency behavior。

## Phase 4 整合與 staging 測試

- 真實 PNG/JPEG/WEBP 圖片分析。
- 真實文字 PDF 分析。
- 真實掃描 PDF：確認 native/cloudflare/OCR 的實際差異。
- TXT/MD 含 Markdown、HTML、zero-width characters 與 prompt injection 的安全測試。
- 混合圖片+PDF+TXT request。
- SSE stop generation、client disconnect、provider timeout。
- 5 個並發 20 MB request 的 memory 與 latency test。
- 匿名使用者超過每日 3 次附件 request 時回傳 429。
- deleted Supabase user 使用附件時仍自動登出。

## Phase 4 門控

1. staging 真實圖片與文字 PDF 至少各成功一次。
2. 掃描 PDF 的行為、費用與是否開放已形成書面決策。
3. provider fallback 不會把 unsupported multimodal request 靜默降級成錯誤文字回答。
4. quota、cost、latency、memory metrics 正常產生且無內容洩漏。
5. staging security、load、abort、provider failure tests 全部通過。

# Phase 5：Production hardening、回歸與上線

## Phase 5 實作

完成 production deployment settings：reverse proxy body limit、FastAPI content limit、timeout、worker concurrency、rate limit、anonymous quota、provider policy 與 feature flag。確認 proxy limit 不會截斷 multipart，也不會設定成無限制。

完成資料保存 audit：IndexedDB、Supabase message writes、錯誤回報、structured logs、browser cache、server temp files 與 OpenRouter provider policy。確保任何錯誤 response 都只回傳錯誤碼與安全摘要，不回傳 extracted text、base64 或 PDF annotation content。

為 production feature flag 設定 gradual rollout。先只對內部測試帳號開啟，再對 authenticated users 開啟，最後才評估 anonymous users。每次 rollout 都要觀察 error rate、413/429、provider failure、平均 latency、memory、OCR cost 與取消率。

## Phase 5 單元與回歸測試

- Frontend full Vitest。
- Backend `tests/backend` 中與 auth、stream、附件、memory、GUM、RAG 相關測試。
- ESLint、TypeScript strict check。
- Production build。
- Security regression：MIME spoofing、malformed PDF/image、prompt injection、path traversal、log leakage、quota bypass。
- Data regression：純文字對話、歷史紀錄、LaTeX、RAG、guest/authenticated separation、deleted-user auto logout。

## Phase 5 整合測試與驗收

- Production-like environment 完整走一次 browser → BFF → FastAPI → OpenRouter → SSE。
- 連續送出純文字、單附件、多附件、錯誤附件、取消 request 與重新送出。
- 重新整理頁面後確認附件 binary 不存在於歷史紀錄、IndexedDB 或 API response。
- 登出、Supabase account deletion、token expiry 後確認 attachment endpoint 仍受保護。
- 觀察至少一個 staging soak window，確認沒有 memory leak、background task leak 或成本異常。

## Phase 5 門控與上線條件

只有全部條件成立才可 production rollout：

1. 全部 Phase 0–4 gate 已通過且有測試紀錄。
2. Full frontend/backend regression tests 通過。
3. Build、lint、typecheck 通過。
4. Security review 沒有未接受的 Critical/High blocker。
5. Production body limits、quota、provider policy、logging redaction 已驗證。
6. PDF OCR/native engine、成本上限與匿名政策已由產品負責人確認。
7. Rollback 方式明確：關閉 feature flag 不得影響純文字聊天。

## 三、主要檔案與介面預計變更

| 子系統 | 預計變更 |
| --- | --- |
| ChatInput | ＋按鈕、hidden input、附件 chips、validation、send callback |
| ChatContainer/chat service | 傳遞附件、錯誤/取消/重送狀態、文字 persistence isolation |
| Chat stream client | FormData、附件 request、SSE 維持相容 |
| Next.js BFF | multipart parsing、第一層 validation、FastAPI forwarding |
| FastAPI stream | multipart parsing、request limit、auth、SSE cancellation |
| attachment service | magic bytes、圖片驗證、TXT/MD decode、PDF data URL、metadata |
| orchestration | `str | ContentPart[]`、display_text/model_content 分離 |
| tests | frontend unit、backend unit、BFF integration、provider mock、staging smoke/security |

## 四、正式實作前的必要決策

1. Production 是否部署於 Vercel；若是，Phase 1 前改採 presigned URL。
2. Gemini provider routing 是否鎖定 Google provider，或允許 OpenRouter fallback。
3. 掃描 PDF OCR 是否開放；若開放，僅 authenticated 使用者或是否允許匿名 quota。
4. GIF 是否通過 staging 實測並保留。
5. 歷史對話是否只顯示附件檔名，或未來需要重新下載附件。
6. 是否保存 annotation hash 供同一 conversation 的 PDF follow-up 使用；Phase 1 預設不保存 annotation content。

## 五、參考資料

- `docs/tech_docs/pplx/AREQA 附件功能技術 Audit 報告.md`
- `docs/tech_docs/API_model_docs/Gemini_3.1_Flash_Lite_-_API_Pricing_&_Providers_OpenRouter.md`
- https://openrouter.ai/google/gemini-3.1-flash-lite
- https://openrouter.ai/docs/guides/overview/multimodal/image-understanding
- https://openrouter.ai/docs/guides/overview/multimodal/pdfs
- https://owasp.org/www-project-top-10-for-large-language-model-applications/
