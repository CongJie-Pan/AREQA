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
> **目標**：讓後端完全脫離對本地檔案系統的依賴，所有的讀寫皆轉向 PostgreSQL 與 Redis。

1.  **環境變數準備**
    *   在 `.env` 中加入 `DATABASE_URL` 與 `REDIS_URL`。
2.  **熱記憶 (Hot Memory) 遷移**
    *   **目標檔案**: `backend/memory_store.py`
    *   **行動**: 捨棄讀寫 `hot_memory.json` 的邏輯。
    *   **實作**: 改用 `redis.asyncio`，將原本的暫存列表改以 Redis 的 `HASH` 或 `LIST` 儲存，並強制所有存取需帶入 `user_id` 作為 Redis Key 的前綴 (例如：`hot_memory:{user_id}`)。
3.  **冷記憶與長期記憶 (Cold Memory) 遷移**
    *   **目標檔案**: `backend/gum_integration.py` 等相關資料庫腳本。
    *   **行動**: 捨棄本地 `gum.db` (SQLite)。
    *   **實作**: 引入 `SQLAlchemy` 或 `SQLModel`，建立 PostgreSQL 連線。修改現有 Schema，確保所有 Table (如 GUM 記憶節點) 皆具備 `user_id` 欄位以支援多租戶。
4.  **排程器狀態儲存遷移**
    *   **目標檔案**: `backend/services/compeer_scheduler.py`
    *   **行動**: 將 `schedule_{user_id}.json` 改存至 PostgreSQL 或 Redis。

### 階段二：後端 API 認證防護 (Phase 2: Backend Auth & Multi-tenancy)
> **目標**：確保所有進入後端的請求都是合法的，並根據 Token 辨識 `user_id`。

1.  **實作 JWT 驗證依賴 (Dependency)**
    *   新增 `backend/dependencies.py`，實作 `def verify_token(token: str = Depends(...))`。
    *   解析 Supabase/Clerk 傳來的 JWT，驗證合法性並回傳 `user_id`。
2.  **替換全域 `default_user`**
    *   檢視 `main.py` 與 `compeer_scheduler.py`，將所有硬編碼的 `"default"` 或 `"default_user"` 替換為從 JWT 獲取的真實 `user_id`。
3.  **WebSocket 認證實作**
    *   **目標檔案**: `backend/services/connection_manager.py` 與 `main.py`
    *   **行動**: 修改 WS 端點，要求連線時在 URL Query Parameter 帶入 Token (`?token=...`)，並在握手 (Handshake) 階段進行 JWT 驗證。

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
