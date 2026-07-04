# AREQA: 身份驗證與 Render 部署遷移計畫 (Implementation Plan)

## 1. 專案目標 (Objectives)
為 AREQA 系統引入多租戶 (Multi-tenant) 會員身分驗證，並徹底解決 Render 平台因「短暫檔案系統 (Ephemeral Storage)」特性所造成的本地資料 (`gum.db`, `hot_memory.json`) 遺失問題，實現雲端無狀態 (Stateless) 擴容架構。

## 2. 核心技術選型 (Tech Stack)
*   **身分驗證 (Authentication)**: Supabase Auth (或 Clerk)
*   **資料庫 (Database)**: Supabase PostgreSQL (或 Render Managed PostgreSQL)
*   **快取與熱記憶 (Cache & Hot Memory)**: Redis (Render 內建或 Upstash Serverless Redis)

---

## 3. 分階段實作藍圖 (Phased Implementation Plan)

### 階段一：基礎設施與資料持久化重構 (Phase 1: Persistence Layer Refactoring)
> **目標**：讓後端完全脫離對本地檔案系統的依賴，所有的讀寫皆轉向 PostgreSQL 與 Redis，並向下傳遞 `user_id` 租戶上下文。

1.  **熱記憶與信箱 (Hot Memory & Mailbox) 遷移至 Redis**
    *   **目標檔案**: `backend/memory_store.py` 與 `backend/mailbox_store.py`
    *   **行動**: 徹底移除 `_atomic_write`、`_read_json` 等檔案 I/O 操作與 threading locks。
    *   **實作**: 導入 `redis.asyncio`。將所有方法改為接收 `user_id: str` (如 `async def get_hot_memory(self, user_id: str)`)，並對應至特定的 Redis Keys (例如：`areqa:hot_memory:{user_id}`, `areqa:mailbox:{user_id}`, `areqa:pending_alerts:{user_id}`)。
2.  **GUM 記憶引擎多租戶化**
    *   **目標檔案**: `backend/gum_integration.py`
    *   **行動**: 移除全域的 `gum_instance` 單例 (Singleton)，改為管理多個實例的字典 `gum_instances: Dict[str, Any]`。
    *   **實作**: 建立工廠模式 `async def get_gum_instance(user_id: str)`。確保 `push_observation`, `query_cold_memory_for_context`, `run_compaction` 等核心函式皆強制接收 `user_id`，並呼叫對應的 GUM 實例。
3.  **排程器與狀態儲存 (Compeer Scheduler) 遷移**
    *   **目標檔案**: `backend/services/compeer_scheduler.py`
    *   **行動**: 將 `user_cooldown_until` 字典從記憶體移至 Redis 快取 (如 `areqa:cooldown:{user_id}`)。
    *   **實作**: 移除寫入 `schedule_{user_id}.json` 的邏輯，改為寫入 Redis List/Hash。並修改 `proactive_scheduler_loop` 與 `daily_scheduler_loop` 使其能迭代查詢 Redis 中「所有活躍的 user_id」，而非只對 `default_user` 執行排程。
4.  **對話節點 (Orchestration) 傳遞 Context**
    *   **目標檔案**: `backend/services/orchestration_service.py`
    *   **實作**: 在 `execute()` 中接收 `user_id`，並向下傳遞至 `get_hot_memory_snapshot`、`async_evaluate_and_update_state` 等子函式中。

### 階段二：後端 API 認證防護與 PostgreSQL Schema (Phase 2: Backend Auth & Multi-tenancy)
> **目標**：確保所有請求合法，並正式將 SQLite `gum.db` 升級為 PostgreSQL，適配 Supabase RLS 與 Vector。

1.  **實作 JWT 驗證依賴 (Auth Dependency)**
    *   **目標檔案**: `backend/main.py`
    *   **實作**: 新增 `get_current_user_id(request: Request)` 依賴，解析 Supabase 的 `Authorization: Bearer <token>` Header 獲取 `sub` claim 作為真實的 `user_id`。
    *   **行動**: 盤點所有路由 (`log_action`, `proactive_check_endpoint`, `ws_notifications`, `stream_endpoint`, `fetch_memory` 等)，拔除 `user_id="default_user"` 的硬編碼，統一注入 JWT 的解析結果。在 `connection_manager.py` 中亦拔除廣播的 `default_user`。
2.  **SQLite 轉 PostgreSQL Schema 重構 (核心重構)**
    *   **目標檔案**: `backend/cold_memory.py` 與 `gum_integration.py`
    *   **連線字串**: 將初始化的 `db_name="gum.db"` 替換為 PostgreSQL 連線字串 (`postgresql+asyncpg://...`)。
    *   **多租戶隔離 (RLS)**: 在 `propositions` 資料表加入 `user_id UUID` 欄位，並於 Supabase 設定 Row Level Security (RLS) 政策：`CREATE POLICY "User isolated" ON propositions FOR ALL USING (auth.uid() = user_id);`。
    *   **FTS5 遷移至 GIN Index**: 廢棄 SQLite 專用的 `propositions_fts` 虛擬表。改在 PostgreSQL 的 `propositions` 表新增 `fts tsvector` 欄位，並以 `to_tsvector` 進行全文檢索與 GIN 索引。
    *   **Byte Vector 遷移至 pgvector**: 廢棄原有的 `vec_memory` 結構與 `struct.pack` 轉換邏輯。啟用 Supabase 的 `pgvector` 擴充功能，在表中新增 `embedding vector(1536)` 欄位，直接以原生陣列讀寫向量。

### 階段三：前端驗證整合 (Phase 3: Frontend Auth Integration)
> **目標**：建立使用者註冊與登入介面，並將 Token 附加於所有對外請求中。

1.  **引入 Auth Provider**
    *   在 Next.js 的外層 (例如 `app/layout.tsx`) 包覆 `<SupabaseProvider>` 或 `<ClerkProvider>`。
2.  **實作 Auth UI 與側邊欄整合 (Sidebar Integration)**
    *   **未登入狀態 (Logged Out)**：在側邊欄 (Sidebar) 左下角顯示系統選單 (如 Settings, Help 等)，並在最底部放置一個引導卡片 (例如 "和 AREQA 一起探討知識的世界 ") 與顯眼的 **「登入」按鈕**。
    *   **登入對話方塊 (Login Modal/Page)**：點擊 Log in 後顯示登入介面，需支援多種登入方式 (OAuth)：包含 **Continue with Google**、**Continue with Apple**、**Continue with phone**，以及傳統的 **Email address** 輸入與註冊。
    *   **已登入狀態 (Logged In)**：登入完成後，側邊欄左下角切換為顯示**用戶頭像 (Avatar)** 與 **用戶名稱** (下方可帶有帳號方案標籤與 Upgrade 按鈕)。使用者點擊此區域即可進入「帳號設定頁面 (Account Settings)」來修改用戶名稱、頭像等個人資料。
3.  **API 請求攔截器 (Request Interceptor)**
    *   將發送訊息的 API (如 `/api/v1/stream`) 統一加上 `Authorization: Bearer <token>` Header。
    *   確保 `useProactiveWebSocket.ts` 建立連線時附加 token。
4.  **本地歷史紀錄管理 (Dexie.js)**
    *   修改 Zustand store 與 Dexie 邏輯。當檢測到使用者「登出」時，主動呼叫 Dexie 的 `clear()` 函數清除本地歷史，避免下一個登入者看到前一個使用者的聊天內容。

### 階段四：Render 雲端部署與 Supabase 整合細節 (Phase 4: Render & Supabase Deployment Details)
> **目標**：在 Render 上配置正確的服務拓樸，並與 Supabase (Auth + DB) 無縫串接，實現正式上線。

1.  **Supabase 專案建立與資料庫配置**
    *   **開設專案**：在 Supabase Dashboard 建立新專案，系統會自動分配一組 PostgreSQL 資料庫與 Auth 模組。
    *   **獲取連線字串**：取得 `DATABASE_URL` (連線字串需包含連線池參數，如 `?pgbouncer=true` 以適應 Serverless 架構)。
    *   **獲取金鑰**：取得 `NEXT_PUBLIC_SUPABASE_URL`、`NEXT_PUBLIC_SUPABASE_ANON_KEY` (供前端使用) 以及 `SUPABASE_JWT_SECRET` (供後端解析 Token)。
    *   **執行 Migration**：透過 Supabase SQL Editor 或 CLI 將原先 SQLite 的 `gum.db` Schema 建立至 Supabase 專案中。
2.  **Redis 快取服務配置**
    *   **方案選擇**：建議註冊 **Upstash** (Serverless Redis)，因為它提供極佳的免費額度，且與 Render 相容性極高；或者也可以使用 Render 內建的付費 Redis 實例。
    *   **獲取連線字串**：取得 `REDIS_URL` (如 `rediss://...`) 備用。
3.  **配置 FastAPI Backend (Render Web Service)**
    *   在 Render Dashboard 點選 **New > Web Service**，連結 GitHub 儲存庫。
    *   **Root Directory**: 填入 `backend`。
    *   **Environment**: 選擇 `Python 3`。
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 10000` (Render 預設監聽 Port 為 10000)。
    *   **Environment Variables (環境變數設定)**：
        *   `DATABASE_URL`: 填入 Supabase 提供的連線字串。
        *   `REDIS_URL`: 填入 Upstash / Render Redis 網址。
        *   `JWT_SECRET`: 填入 `SUPABASE_JWT_SECRET` (用於 `verify_token` 依賴驗證)。
        *   `OPENROUTER_API_KEY` 與 `PERPLEXITY_API_KEY`: 填入您的 LLM 與檢索 API Key。
4.  **配置 Next.js Frontend (Render Web Service)**
    *   在 Render Dashboard 再次點選 **New > Web Service**，連結相同的 GitHub 儲存庫。
    *   **Root Directory**: 填入 `frontend`。
    *   **Environment**: 選擇 `Node`。
    *   **Build Command**: `npm install && npm run build`
    *   **Start Command**: `npm start`
    *   **Environment Variables (環境變數設定)**：
        *   `NEXT_PUBLIC_API_URL`: 填入上方 Backend 部署完成後獲得的 Render 網址 (如 `https://areqa-backend.onrender.com`)。
        *   `NEXT_PUBLIC_SUPABASE_URL`: 填入 Supabase API URL。
        *   `NEXT_PUBLIC_SUPABASE_ANON_KEY`: 填入 Supabase 前端匿名金鑰。

---

## 4. 預期風險與注意事項 (Risks & Mitigations)
*   **資料庫遷移風險**: 目前的 `gum.db` Schema 需要轉換為 PostgreSQL 相容的語法。部分 SQLite 專有函數 (若有) 需改寫。
*   **SSE (Server-Sent Events) 與連線中斷**: 若 Render 針對長連線有超時限制 (Timeout)，前端的 WebSocket `useProactiveWebSocket.ts` 已內建指數退避重連機制，應能有效應對。
*   **冷卻機制同步**: 確保 `compeer_scheduler.py` 內的 `user_cooldown_until` 從記憶體 dict 移至 Redis，否則當 FastAPI 擴展為多個 Instance (Worker) 時會發生冷卻狀態不一致。
