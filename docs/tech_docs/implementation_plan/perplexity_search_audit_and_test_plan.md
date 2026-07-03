# Perplexity Search API 整合審查與測試計畫 (Audit & Test Plan)

本文件方針對現有的 AREQA 系統原始碼（包含前後端）進行可行性分析與風險評估，並提供詳細的單元測試、整合測試以及 API 測試計畫。

---

## 🔍 第一部分：可行性審查與潛在風險評估 (Implementation Audit)

藉由審查 `/workspaces/AREQA` 的核心原始碼，我們確認本實作計畫「完全可行」，因為現有的 RAG 串流與狀態設計（透過 SSE 推播與狀態面板）非常模組化。然而，在實際程式碼的層面，我們發現以下 **6 個潛在風險點**，必須在實作時特別注意防範：

### 1. Zustand 狀態與 `createChatStream` 參數不一致
*   **評估現況**：現有前端的 `/frontend/src/services/chat/index.ts` 共在三處呼叫了 `createChatStream`（第 196, 610, 822 行）。這三處呼叫都將 `chatStore.useRag` 與 `chatStore.forceThink` 當作參數傳入。
*   **潛在 Bug**：如果我們只在 Zustand 中增加了 `useWebSearch`，但沒有修改 `createChatStream` 的函式簽名 (signature) 及其這三處呼叫，則發送訊息時，後端將永遠收不到 `use_web_search = true` 的訊號。
*   **防範設計**：
    *   必須修改 `frontend/src/services/chat-stream/client.ts` 中的 `createChatStream` 簽名，新增第 6 個參數 `useWebSearch: boolean = false`。
    *   在 `frontend/src/services/chat/index.ts` 中的三處呼叫點，必須同步補上 `chatStore.useWebSearch`。

### 2. 狀態互斥與 UI 衝突
*   **評估現況**：使用者介面不能同時處於「內部文獻 RAG」與「外部聯網搜尋」兩種相衝突的資料檢索狀態。
*   **防範設計**：
    *   修改 Zustand 狀態變更動作 `toggleWebSearch`：
        ```typescript
        toggleWebSearch: () => set((state) => ({ 
          useWebSearch: !state.useWebSearch,
          useRag: false // 當開啟網路搜尋時，自動關閉 RAG
        })),
        ```
    *   同理，修改 `toggleRag` 動作：
        ```typescript
        toggleRag: () => set((state) => ({ 
          useRag: !state.useRag,
          useWebSearch: false // 當開啟 RAG 時，自動關閉網路搜尋
        })),
        ```

### 3. SSE 新行字元（Newlines）破壞串流協定
*   **評估現況**：Perplexity Search API 回傳的網頁 `snippet` 通常包含多行文字 (`\n` 或 `\r\n`)。
*   **潛在 Bug**：如果直接在 python 端使用格式化字串 `data: {snippet}`，SSE 協定會將裡面的 `\n` 誤解為「下一個 SSE 欄位或事件的開頭」，導致前端 `EventSource` 解析崩潰。
*   **防範設計**：
    *   在後端 `orchestration_service.py` 輸出 `event: sources` 時，必須將整個 `sources_payload` 陣列直接餵給 `json.dumps(..., ensure_ascii=False)`。JSON 序列化會自動將文字內的換行符轉義為 `\n` 字串，從而確保 SSE 傳輸安全。

### 4. API 金鑰缺失與異常降級 (Exception & Fallback Handling)
*   **評估現況**：Perplexity Search API 需要 `PERPLEXITY_API_KEY`。若環境變數未設定、配額用盡或 API 暫時當機，系統如果直接 raise exception，會導致 FastAPI 直接噴 500 錯誤，中斷整個 SSE 連線。
*   **防範設計**：
    *   在後端 `_node_perplexity_search` 的 HTTP 呼叫外層，必須使用 `try...except` 結構包裹：
        ```python
        try:
            # 發送 httpx POST 請求...
        except Exception as e:
            # 1. 向前端 Yield 一個錯誤狀態事件
            yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 聯網搜尋服務暫時無法使用，改用一般對話...'}, ensure_ascii=False)}\n\n"
            # 2. 清空 context prompt，降級為一般無網路 RAG 模式
            self._temp_context_prompt = ""
            return
        ```

### 5. 網路連線逾時 (Timeout Management)
*   **風險**：Perplexity 爬取外部網頁的時間不穩定，若連線卡住會導致使用者等待超時。
*   **防範設計**：
    *   在 python 使用 `httpx.AsyncClient(timeout=6.0)`，強制作業限制在 6 秒內，逾時即觸發上述的降級邏輯。

---

## 🧪 第二部分：詳細測試計畫 (Detailed Testing Plan)

為確保此項更新不影響原有的 RAG 功能且新功能運作正常，我們規劃了三層測試：

### 一、 單元測試 (Unit Tests)

#### 1. 前端 Zustand Store 互斥與狀態測試
*   **檔案路徑**：`frontend/src/store/chat/__tests__/store.test.ts` (若無此檔則新增)
*   **測試框架**：`Vitest`
*   **測試情境**：
    *   [ ] **RAG 轉 網路搜尋**：
        1. 呼叫 `chatStore.toggleRag()` (此時 `useRag` 應為 `true`)。
        2. 接著呼叫 `chatStore.toggleWebSearch()`。
        3. 斷言 (Assert) `useWebSearch` 為 `true` 且 `useRag` 已自動變為 `false`。
    *   [ ] **網路搜尋 轉 RAG**：
        1. 呼叫 `chatStore.toggleWebSearch()` (此時 `useWebSearch` 應為 `true`)。
        2. 接著呼叫 `chatStore.toggleRag()`。
        3. 斷言 `useRag` 為 `true` 且 `useWebSearch` 已自動變為 `false`。

#### 2. 後端 Perplexity 檢索節點單元測試
*   **檔案路徑**：`backend/tests/test_perplexity_node.py`
*   **測試框架**：`pytest` + `pytest-asyncio` + `respx` (Mock HTTP client)
*   **測試情境**：
    *   [ ] **測試搜尋成功**：
        *   使用 `respx` 攔截 `https://api.perplexity.ai/search` 並回傳模擬的 JSON 結果（2 筆資料）。
        *   呼叫 `_node_perplexity_search("測試問題")` 並遍歷其 Yield 的事件。
        *   驗證事件序列依序為：`event: status (routing)` ➡️ `event: status (reranking)` ➡️ `event: sources` ➡️ `event: status (generating)` ➡️ `event: results_obj`。
        *   驗證 `event: sources` 的內容中，`chunk_id` 正確填入了 `url`。
    *   [ ] **測試連線失敗/超時降級**：
        *   Mock `https://api.perplexity.ai/search` 回傳 `500 Internal Server Error`。
        *   呼叫 `_node_perplexity_search("測試問題")`。
        *   驗證它不會噴拋 Exception，而是正常發送 `status: error` 狀態，且最終正常產出空的 `results_obj` 事件。

---

### 二、 整合與 API 測試 (Integration & API Tests)

#### 1. 端到端 FastAPI /api/v1/stream 整合測試
*   **檔案路徑**：`backend/tests/test_stream_api.py`
*   **測試框架**：FastAPI `TestClient`
*   **測試情境**：
    *   [ ] **情境 A (使用網路搜尋)**：
        *   發送 POST 請求至 `/api/v1/stream`，攜帶參數 `use_web_search=True`。
        *   讀取 SSE 串流，驗證串流首部是否有發出 `🌐 網路檢索中...` 狀態事件。
        *   驗證是否有發送 `event: sources` 且結構包含 `title`、`snippet`、`chunk_id` 等必要欄位。
    *   [ ] **情境 B (維持原本的 RAG 流程)**：
        *   發送 POST 請求，攜帶參數 `use_web_search=False, use_rag=True`。
        *   驗證系統走的是原本的本地檢索邏輯（BM25 & FAISS），並且沒有呼叫 Perplexity API 的任何痕跡。

---

### 三、 使用者手動與 UI 冒煙測試 (UI Smoke Tests)

1.  **按鈕點擊反應**：在前端網頁點擊「🌐 網路搜尋」按鈕，確認能順利開啟/關閉，且原有的 RAG 按鈕會隨之關閉。
2.  **狀態動態顯示**：點擊發送訊息後，確認對話框上方會先顯示 `🌐 網路檢索中...`，接著短暫閃爍 `⚡ 篩選與統整網路資訊...`，最後進入 `✍️ 援引網路文獻，生成解說...`。
3.  **引用連結跳轉**：生成完畢後，在右側 Citation 元件中會列出搜尋來源網站（例如 Wikipedia 等）。點擊來源卡片，驗證是否能順利在新分頁中打開該網頁原始連結。
