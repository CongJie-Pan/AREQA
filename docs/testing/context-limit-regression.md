# 上下文容量整合、回歸與 Smoke 測試

## 執行

在 repository root 執行，先安裝專案 Python／frontend 依賴及 Playwright Chromium。測試會啟動本機 FastAPI（18100）與 Vite（18101）；兩個連接埠必須可用。請勿同時執行共用此環境的 image-tools 與 context 測試。

```bash
npm run test:smoke --prefix frontend
npm run test:e2e:context --prefix frontend
npm run test:e2e:image-tools --prefix frontend
npm test --prefix frontend -- ../tests/frontend/api/chat/route.attachments.test.ts ../tests/frontend/services/chat-stream/client.latency-events.test.ts
npm run check:report:strict --prefix frontend
```

Smoke 是完整 context 套件中標記 `@smoke` 的 5 個案例，包含四種附件與超額後恢復。`test:e2e:image-tools` 同時執行既有圖片流程與新的 context 案例，保護共用測試環境。

## 新增驗收情境

| 情境 | 驗證 |
| --- | --- |
| 第一輪提問，第二輪上傳 PDF | 400 KB 實際 PDF 的傳輸大小不會被當成對話文字容量；模型收到原生附件；回答可保存、重整後讀回、繼續提問 |
| 第二輪 TXT／Markdown | 52,000 字元後的尾端標記確實到達模型，防止 50,000 字元靜默截斷；回答可保存與繼續 |
| 第二輪 PNG | 原生圖片附件送達模型，完成回答及下一輪 |
| 模型首次拒絕上下文 | 僅重試一次；移除舊訊息而保留目前附件；介面正常結束載入 |
| 重試仍超額 | 最多兩次呼叫、顯示可採取行動的錯誤，下一輪可用 |
| 回答途中超額 | 保留部分回答，不重播整段；顯示錯誤，下一輪可用 |
| 模型 HTTP 429 | 不誤判為容量錯誤，不觸發容量重試；介面可繼續 |
| 附件閱讀成本超額 | 140,000 字元附件在模型呼叫前拒絕；錯誤後可再送訊息 |
| 101 則歷史＋Markdown multipart | 真實 HTTP 路由接受請求，附件尾端完整，SSE 回傳答案與恰好一個 `[DONE]` |

## 測試邊界

瀏覽器使用實際 ChatInput、MessageItem、聊天服務、store、IndexedDB 與 FastAPI 串流／附件／容量／重試流程。模型、認證、雲端記憶及同步使用測試替身；context 案例停用可選的圖片預檢及 PDF 圖表補強，但保留實際附件解析及獨立程序容量檢查。

Vite 測試代理直接接 FastAPI，不啟動正式 Next.js BFF；BFF 的 multipart 轉送由 `route.attachments.test.ts` 分別驗證。這些測試驗證工程流程，不評估真實模型摘要品質、線上供應商容量、網路延遲或部署設定，也不代表不存在其他 bug。

101 則案例保護歷史傳輸上限，不宣稱觸發摘要。摘要失敗、檢索裁切、附件檢查逾時與程序清理另由下列後端回歸套件涵蓋：

```bash
OPENROUTER_API_KEY=mock-token backend/.venv/bin/python -m pytest \
  tests/backend/test_context_audit_regressions.py \
  tests/backend/test_attachment_context_budget.py \
  tests/backend/test_attachment_service.py \
  tests/backend/test_conversation_history.py \
  tests/backend/test_conversation_history_stream.py \
  tests/backend/test_retrieval_budget.py \
  tests/backend/test_orchestration_service.py \
  tests/backend/test_conversation_context_service.py \
  tests/backend/test_history_transport.py \
  tests/backend/test_summary_store.py -q
```

失敗時 Playwright 將 trace 與畫面狀態放在 `/tmp/areqa-image-tools-playwright`。測試 fixture 僅回傳呼叫次數、訊息數、附件存在及尾端保留的布林值，不輸出附件原文。

## 回歸測試敏感度

2026-11-09 驗證時，曾暫時在測試程序注入舊的 50,000 字元截斷行為。新增 TXT 瀏覽器案例在 `tail_preserved` 斷言確實失敗；移除注入後通過。這證明案例不只驗證固定的模型替身回答，也驗證附件尾端真正送達模型邊界。此故障注入沒有保留在 fixture 或正式程式中。

## 本次執行紀錄（2026-11-09）

- 上下文整合／回歸：10 passed。
- 後端相關回歸：186 passed、2 skipped；兩項為既有 `Router feature bypassed by user request` 標記，另有 FastAPI lifespan 棄用警告。
- 前端附件 BFF 與串流事件：20 passed。
- `check:report:strict`：ESLint、TypeScript 全部通過。
- 擴大到既有圖片瀏覽器流程：13 passed、4 failed。失敗均在 `tests/e2e/image-tools/flow.spec.ts`，目前不可宣稱整個圖片流程回歸全綠：
  - `mixed analysis and image survive loading, completion and IndexedDB history`
  - `switching conversations during generation cancels work and keeps the new chat empty`
  - `stopping generation rejects late output and cancels backend work`
  - `provider failure preserves completed analysis and ends loading`

以上四項的失敗點是預期圖片生成載入狀態沒有被測試觀察到，需另行調查圖片工具串流／載入時序；沒有放寬或刪除原有斷言。

以 `git show HEAD:tests/e2e/image-tools/e2e_app.py` 還原原始模型 fixture，單獨重跑上述四項，也得到相同四項失敗。測試介面固定繁體中文以符合既有 selector；此次新增 context provider 分支不是這四項失敗的必要條件。這是對照證據，尚未完成圖片問題的根因分析。

2026-11-10 接續驗證：`npm run test:smoke --prefix frontend` 單獨執行，5 passed（PDF、TXT、Markdown、PNG，以及附件超額後再提問）。
