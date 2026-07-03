# Perplexity Search API 系統遷入實作計畫 (Implementation Plan)

## 🎯 目標 (Objective)
將 Perplexity 官方推出的純搜尋服務（Search API）無縫遷入現有的 AREQA 系統中。本計畫採取「雙軌制 (Dual-track)」架構，在保留現有內部知識庫 RAG 的前提下，於前端新增獨立的「網路搜尋」按鈕。
本文件已基於對專案 `/frontend` 與 `/backend` 原始碼的深度審查 (Audit) 進行了全面更新，確保實作具備高可靠性、防呆互斥、以及完整的錯誤降級機制，並附有詳細的測試計畫。

---

## 🏗️ 系統架構設計 (Architecture Design)

本計畫主打「高內聚、低耦合」，核心概念為**在資料獲取層 (Node 4) 建立分流，但在組裝層 (Node 5) 統一規格**。

*   **開啟 RAG 模式** 👉 走原本本地 FAISS / BM25 混合檢索。
*   **開啟 Web Search 模式** 👉 走 Perplexity Search API。
*   **皆不開啟** 👉 純 LLM 聊天。

---

## 🛠️ 具體實作步驟 (Implementation Steps)

### 階段一：前端狀態管理與互斥防禦 (Frontend Store)
1. **Zustand 狀態擴充 (`frontend/src/store/chat/types.ts`)**
   - 在 `ChatState` 介面新增 `useWebSearch: boolean;`。
   - 在 `ChatActions` 介面新增 `toggleWebSearch: () => void;`。
2. **實作狀態互斥邏輯 (`frontend/src/store/chat/store.ts`)**
   - 在 `createChatStore` 初始化新增 `useWebSearch: false`。
   - 修改 `toggleRag`，確保開啟 RAG 時關閉 WebSearch：
     ```typescript
     toggleRag: () => set((state) => ({ 
       useRag: !state.useRag,
       useWebSearch: false // 互斥設計
     })),
     ```
   - 實作 `toggleWebSearch`，確保開啟 WebSearch 時關閉 RAG：
     ```typescript
     toggleWebSearch: () => set((state) => ({ 
       useWebSearch: !state.useWebSearch,
       useRag: false // 互斥設計
     })),
     ```

### 階段二：前端串流連線與 UI (Frontend Stream Client)
1. **擴充 `createChatStream` 簽名 (`frontend/src/services/chat-stream/client.ts`)**
   - 找到 `export async function createChatStream(...)`，在結尾新增第 6 個參數：`useWebSearch: boolean = false`。
   - 在內部的 `fetchOptions.body` 中，新增傳遞 `"use_web_search": useWebSearch`。
2. **同步修改發送邏輯 (`frontend/src/services/chat/index.ts`)**
   - 檔案中有 3 處呼叫了 `createChatStream` (大約位於第 196, 610, 822 行)。
   - 在這三處呼叫的尾端，補上 `chatStore.useWebSearch` 作為傳入參數，否則後端將永遠收不到指令。
3. **UI 元件更新 (`frontend/src/components/ChatInput/index.tsx`)**
   - 在 `line 188` 被隱藏的 RAG `<button>` 旁，加入一個新的 Toggle 按鈕（綁定 `useWebSearch` 與 `toggleWebSearch`），顯示文案為「🌐 網路搜尋」。

### 階段三：API 路由串接 (Next.js API Layer)
1. **API Payload 串接 (`frontend/src/app/api/chat/route.ts`)**
   - 找到 `POST` 請求解析 `body` 的地方，在介面中加入 `use_web_search?: boolean;`。
   - 轉送至 FastAPI 後端的 `payload` 中新增 `use_web_search: body.use_web_search || false`。

### 階段四：後端資料模型與核心檢索 (Backend - Orchestration)
1. **擴充資料模型 (`backend/main.py`)**
   - 找到 `class ChatRequest(BaseModel):` (大約 409 行)，新增屬性 `use_web_search: bool = False`。
   - 找到呼叫 `orchestration_service.execute(...)` (大約 727 行)，補上參數 `use_web_search=chat_req.use_web_search`。
2. **擴充 OrchestrationService 參數 (`backend/services/orchestration_service.py`)**
   - 在 `execute` 方法的定義中新增 `use_web_search: bool` 參數。
   - 在 `execute` 內部 (Node 4 區塊)，新增分流邏輯：
     ```python
     if use_web_search and last_user_msg:
         async for event in self._node_perplexity_search(last_user_msg):
             if event.startswith("event: results_obj"):
                 continue
             if event == "event: REFUSED\n\n":
                 yield "data: [DONE]\n\n"
                 return
             yield event
     elif use_rag and self.rag and last_user_msg:
         # 原本的 FAISS RAG 邏輯
     ```
3. **實作新的網路搜尋節點 `_node_perplexity_search` (含安全防護)**
   - 必須包裝在 `try...except` 與 Timeout 機制中，防止連線阻塞與破壞 SSE 結構：
     ```python
     async def _node_perplexity_search(self, last_user_msg: str):
         # 推播狀態：啟動搜尋
         yield f"event: status\ndata: {json.dumps({'status': 'routing', 'message': '🌐 網路檢索中...'}, ensure_ascii=False)}\n\n"
         
         try:
             # 使用 httpx.AsyncClient(timeout=6.0) 對 https://api.perplexity.ai/search 發起 POST 請求
             # 提取 response JSON 中的 results 陣列
             pass 
         except Exception as e:
             # 異常降級機制：向前端報錯，並退出該節點交由後續純 LLM 處理
             yield f"event: status\ndata: {json.dumps({'status': 'error', 'message': '⚠️ 聯網搜尋服務暫時無法使用，改用一般對話...'}, ensure_ascii=False)}\n\n"
             self._temp_context_prompt = ""
             return
         
         # 收到結果推播狀態
         yield f"event: status\ndata: {json.dumps({'status': 'reranking', 'message': '⚡ 篩選與統整網路資訊...'}, ensure_ascii=False)}\\n\\n"
         
         # 資料格式統整與偽裝 (確保 json.dumps 防護 \n)
         sources_payload = []
         context_texts = []
         for idx, res in enumerate(results, 1):
             title, url, snippet = res["title"], res["url"], res["snippet"]
             context_texts.append(f"[文獻{idx}] {title}\n{snippet}")
             sources_payload.append({"title": title, "snippet": snippet, "score": 1.0, "chunk_id": url})
             
         # 透過 json.dumps 保護帶有換行符的 snippet，避免破壞 SSE 串流
         yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
         
         # 發送準備生成的狀態
         yield f"event: status\ndata: {json.dumps({'status': 'generating', 'message': '✍️ 援引網路文獻，生成解說...' }, ensure_ascii=False)}\n\n"
         
         self._temp_context_prompt = "<context>\n" + "\n\n".join(context_texts) + "\n</context>\n\n"
         yield "event: results_obj\n\n"
     ```

### 階段五：LLM 提示詞無縫接軌 (Prompt Assembly)
- 在 Node 5 的 `_node_prompt_assembly` 中，若有存取到 `self._temp_context_prompt`，會自動將其與 System Prompt 組合。
- 前端的 `Citations` 元件與 `RAGStatusPanel` 會依然完美運作，並支援點擊 `chunk_id` (已被替換為真實網址) 進行外連。

---

## 🧪 測試計畫 (Testing Plan)

### 一、 單元測試 (Unit Tests)
1. **前端狀態互斥測試 (`frontend/src/store/chat/__tests__/store.test.ts`)**
   - 斷言 (Assert) 啟動 `toggleWebSearch()` 時，`useRag` 是否自動轉為 `false`。
   - 斷言 (Assert) 啟動 `toggleRag()` 時，`useWebSearch` 是否自動轉為 `false`。
2. **後端網路搜尋節點測試 (`backend/tests/test_perplexity_node.py`)**
   - **工具**: 使用 `pytest` + `respx` (Mock HTTP Client)。
   - **情境 A (成功檢索)**: Mock Perplexity API 回傳正常 JSON。斷言是否能正確 Yield 出 `status: routing` -> `status: reranking` -> `sources` (包含 JSON 解析) -> `status: generating` 等 5 個正確的 SSE 事件。
   - **情境 B (錯誤降級)**: Mock 拋出網路 Timeout 或是 401 Unauthorized。斷言系統能平穩 Catch Exception，Yield 出 `status: error` 且後續沒有拋出錯誤崩潰。

### 二、 整合與 API 測試 (Integration / API Tests)
1. **端到端 FastAPI SSE 串流驗證 (`backend/tests/test_stream_api.py`)**
   - **工具**: FastAPI `TestClient`。
   - 發送帶有 `use_web_search=true` 的 `POST /api/v1/stream` 請求。
   - 驗證串流輸出的事件是否如預期，且 JSON 格式沒有被 `snippet` 裡面的換行符截斷。
   - 再次發送 `use_web_search=false, use_rag=true`，確認完全不呼叫 Perplexity API，保留原始本地檢索。

### 三、 使用者手動與 UI 冒煙測試 (UI Smoke Tests)
1. **按鈕點擊反應**：在前端網頁點擊「🌐 網路搜尋」按鈕，確認能順利開啟/關閉，並觀察原本被隱藏的 RAG 按鈕狀態（如果有被顯示）。
2. **狀態動態顯示**：發送訊息後，確認對話框上方依序顯示 `🌐 網路檢索中...` 👉 `⚡ 篩選與統整網路資訊...` 👉 `✍️ 援引網路文獻，生成解說...`。
3. **引用連結可點擊性**：生成完成後，點選右側 Citations 面板出現的網頁來源，確認是否能順利在新分頁中打開原始連結。
