# FastAPI + Supabase 多租戶架構：7 大生產陷阱完整研究報告

> 針對 AREQA 系統（FastAPI + Next.js + Supabase + Redis + pgvector + SSE + WebSocket + Dexie.js）遷移至多租戶雲端架構時，各子系統已知的生產陷阱、靜默失敗（silent failure）與社群回報問題。

***

## 1. Supabase RLS + Service Role Key 繞過

### RLS 何時失效？

`service_role` key 設計上**永遠繞過 RLS**，這是刻意的行為。然而生產環境中最危險的是「明明用了 `service_role` 卻意外讓 RLS 生效」，或相反地「以為有 RLS 保護卻被繞過」，這兩者都屬靜默失敗。[^1][^2]

Supabase 官方文件指出三種常見的 `Authorization` header 被 user session 覆蓋的情境：[^1]

1. **SSR client 以 service_role 初始化**：SSR client 設計為從 cookie 共享 user session，導致 user JWT 覆蓋 `service_role` 的 `Authorization` header。
2. **在 `createClient` options 中直接設定 `Authorization` header 為 user token**：這會直接覆蓋預設行為。
3. **在 service_role client 上呼叫 `signUp` 或其他 auth 函式**：這些函式會回傳 user session 並覆蓋 client 的 key。

**更嚴重的靜默失敗**（CVE-2025-48757）：一項針對 1,645 個 Lovable 平台應用的掃描發現，10.3% 的專案（170 個）因為 **RLS 根本未啟用**，導致未認證的 anon key 請求即可讀取所有資料。這不是 service_role 外洩問題，而是純粹的 RLS 設定缺失。[^3]

另一個常被忽略的靜默失敗：`auth.uid()` 在 anon 請求中回傳 `NULL`。PostgreSQL 對 `NULL = user_id` 的計算結果是 `NULL`（非 `false`），表面上看是「查無資料」而非「存取錯誤」，很容易被誤判為正常行為。[^3]

**效能陷阱（非安全性，但影響極大）**：在 100K 行資料的資料表上，若 RLS policy 寫成 `USING (auth.uid() = user_id)`，因為 `auth.uid()` 被標記為 `VOLATILE`，PostgreSQL 會對每一行呼叫一次，實測執行時間高達 171ms。改為 `USING ((select auth.uid()) = user_id)` 後，PostgreSQL 只呼叫一次（`initPlan`），執行時間降至 0.1ms，效能提升 1,710 倍。[^3]

### FastAPI 後端正確做法：不用 service_role key 的 RLS 實施方式

FastAPI 後端若直接連線 PostgreSQL（而非透過 PostgREST），必須**在每個 transaction 開始時手動設定 PostgreSQL config 變數**來模擬 PostgREST 的行為：[^4]

```sql
BEGIN;
SELECT set_config('request.jwt.claims',
  jsonb_build_object(
    'role', 'authenticated',
    'sub', '<user_uuid>'
  )::text,
  TRUE
);
SET LOCAL ROLE authenticated;
-- 你的查詢
COMMIT;
```

這樣 `auth.uid()` 就能正確回傳對應的 user UUID，RLS policy 便可正常運作。`TRUE` 參數（`is_local = TRUE`）確保設定僅在本次 transaction 有效，不會洩漏到連線池中其他使用者的查詢。[^5][^6]

**關鍵警告**：若使用 `set_config(..., FALSE)`（session 層級），在 PgBouncer 的 transaction pooling 模式下，這個設定**不會在 transaction 結束後自動清除**，可能導致後續連線使用者看到他人的 `auth.uid()`，造成嚴重的資料洩漏。[^6]

***

## 2. pgvector + SQLAlchemy AsyncPG + Supabase PgBouncer Transaction Mode

### 核心問題：Prepared Statement 衝突

這是**最常導致生產環境間歇性崩潰的問題**，且通常在低流量測試時不出現，高流量才爆發。[^7]

`asyncpg` 在執行查詢時會自動建立 prepared statement（如 `__asyncpg_stmt_9__`），並在後續相同查詢時重複使用。然而 Supabase 的 Transaction Pooler（port 6543）採用 PgBouncer transaction mode，**每次 transaction 後可能分配不同的底層連線**，導致下次查詢找不到之前建立的 prepared statement：[^8][^7]

```
sqlalchemy.exc.ProgrammingError: 
  prepared statement "__asyncpg_stmt_1__" already exists
```

或

```
asyncpg.exceptions.InvalidSQLStatementNameError:
  prepared statement "__asyncpg_stmt_12__" does not exist
```

這兩種錯誤都是**間歇性**的，在正常請求下可能完全不出現，只在並發突增時才爆發。[^9][^7]

### pgvector 的額外複雜性

pgvector 的 SQLAlchemy 整合通常需要呼叫 `register_vector()` 來註冊自訂型別。這個操作在 PgBouncer transaction mode 下會有額外問題：型別資訊是連線層級的，而 PgBouncer 可能將後續請求路由到未執行過 `register_vector()` 的連線，導致向量查詢靜默失敗或型別轉換錯誤。[^10]

### 標準修復方案

**方案 A（推薦）：使用直接連線 port 5432**

對於 Render 免費方案的單一 worker 架構，連線數有限，直接連線是最簡單的解法：[^9]

```python
# 使用直接連線 URL（不含 ?pgbouncer=true），port 5432
DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
```

**方案 B：強制停用 Prepared Statements（若必須用 PgBouncer port 6543）**

```python
engine = create_async_engine(
    DATABASE_URL,
    connect_args={
        "statement_cache_size": 0,           # 停用 asyncpg 快取
        "prepared_statement_cache_size": 0,  # 雙重保險
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
    }
)
```

注意：即使設定 `statement_cache_size=0`，SQLAlchemy 2.x 本身仍可能生成 prepared statement。需**同時**在引擎層加上 `use_prepared_statements=False`：[^11]

```python
engine = create_async_engine(
    DATABASE_URL,
    use_prepared_statements=False,  # SQLAlchemy 2.x 專屬
    connect_args={"statement_cache_size": 0},
)
```

***

## 3. SQLAlchemy Async Session 在多租戶 Factory 模式下的記憶體洩漏與連線池耗盡

### 最危險的反模式：每個 user_id 建立一個 Engine

計畫中的 `get_gum_instance(user_id)` factory 模式若實作為「每次呼叫都用相同 `user_id` 建立全新的 `create_async_engine()`」，會造成嚴重問題。SQLAlchemy 的 `Engine` 是重量級物件，每次建立都會分配連線池資源；如果 GUM instance 沒有被正確回收（`engine.dispose()`），連線將永遠不會關閉。[^12][^13]

100 個並發使用者 × 每個使用者 1 個 Engine × `pool_size=5, max_overflow=10` = 最多 1,500 個資料庫連線，直接吃爆 Supabase 免費版的連線限制（Supabase 免費版最多 60 個連線）。

### Identity Map 記憶體洩漏

SQLAlchemy 的 ORM Session 會在 Identity Map 中保留所有查詢回來的物件的引用，直到 session 被關閉。若 GUM 的 `run_compaction` 等長時間背景任務在同一個 async session 內迴圈查詢大量資料，記憶體會持續增長而無法被垃圾回收：[^12]

```python
# 錯誤：長時間 session 導致 identity map 無限膨脹
async def run_compaction(session: AsyncSession, user_id: str):
    while True:
        rows = await session.execute(select(Memory).where(...))
        # session 持續持有所有 Memory 物件的引用
```

修復方式：定期呼叫 `session.expunge_all()` 或為每次迴圈建立新 session。[^12]

### 網路中斷時的連線洩漏（Chaos Testing 發現）

在混沌測試中發現，當 PostgreSQL 連線突然中斷或延遲時，`asyncpg` 發送 `CancelRequest` 需要時間完成握手。若 session cleanup 程式碼在此之前就關閉連線，連線將進入半損壞狀態，永遠不會歸還連線池：[^14]

```python
# 修復：在 cleanup 中加入短暫等待，讓 asyncpg 完成取消握手
async def _cleanup(self) -> None:
    if self._session:
        await asyncio.sleep(0.1)  # 讓 asyncpg 完成 CancelRequest
        try:
            await asyncio.wait_for(
                asyncio.shield(self._session.close()),
                timeout=3.0
            )
        except TimeoutError:
            pass
        finally:
            self._session = None
```

`asyncio.shield()` 確保 cleanup 本身不會被取消。[^14]

### 正確的多租戶 Engine Factory 模式

```python
# 正確做法：全域共享一個 engine，透過 set_config 切換 user context
_global_engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=10)

async def get_gum_instance(user_id: str):
    # 不建立新 engine，而是在同一個 engine 的 transaction 裡設定 user context
    async with AsyncSession(_global_engine) as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('request.jwt.claim.sub', :uid, TRUE)"),
                {"uid": user_id}
            )
            # 執行使用者隔離的 GUM 查詢
```

***

## 4. Render 免費方案的 FastAPI SSE 已知問題

### 問題一：15 分鐘閒置休眠斬斷 SSE 長連線

Render 免費方案在**15 分鐘無新請求**後自動休眠（spin down）。**關鍵點**：已建立的 SSE 長連線**不被計為「新請求」**，因此即使有使用者正在監聽 SSE stream，服務仍然會在 15 分鐘後休眠，強制切斷連線。[^15][^16]

首次喚醒（cold start）耗時約 30~60 秒，期間 SSE 端點完全不可用。[^17]

### 問題二：Cloudflare 反向代理緩衝 SSE

Render 使用 Cloudflare 作為反向代理。早期版本的 Cloudflare 會緩衝 SSE 回應，導致前端收不到即時 chunk，直到整個回應結束才一次性收到所有內容。[^18]

**已知修復**：在 FastAPI 的 SSE response header 中加入 `X-Accel-Buffering: no`：[^19]

```python
# FastAPI SSE endpoint
return StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # 關鍵：停用 Nginx/Cloudflare 緩衝
        "Connection": "keep-alive",
    }
)
```

### 問題三：uvicorn 單 worker 的 SSE 並發限制

計畫中的 Start Command 是 `uvicorn main:app --host 0.0.0.0 --port 10000`，這是**單 worker**。每個 SSE 連線會佔用一個 asyncio coroutine，但 uvicorn 單 worker 在同時處理多個長時間 SSE stream 時，若某個 stream 的 generator 有阻塞操作（例如同步 DB 查詢），會導致其他 SSE client 延遲收到事件。[^20]

### 建議緩解措施

- 在 SSE generator 中每 30 秒發送一次 heartbeat comment（`:ping\n\n`），防止 Cloudflare/Render 代理因閒置超時關閉連線。[^21]
- 前端的 `EventSource` 應設定自動重連（`retry: 3000`）。
- 若 LLM streaming 超過 30 秒仍可能觸發 Render 的代理超時（非 Render 自身，而是 uvicorn/gunicorn 工作者的 timeout），確保 uvicorn 的 `--timeout-keep-alive` 設定足夠長。[^22][^23]

***

## 5. Supabase Auth JWT 在 FastAPI 驗證的已知問題（python-jose / PyJWT）

### 問題一：`aud` claim 必須明確傳入，否則驗證被靜默跳過

Supabase 發出的 JWT 中，`aud` claim 預設為字串 `"authenticated"`。若在 `jwt.decode()` 時**不傳入** `audience` 參數，PyJWT 和 python-jose 預設**跳過 audience 驗證**，不報錯但驗證不完整——這是一個靜默失敗：[^24][^25]

```python
# 錯誤：跳過 audience 驗證
jwt.decode(token, secret, algorithms=["HS256"])

# 正確：明確指定 audience
jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
```

### 問題二：`aud` claim 突然變成 array（已回報 Bug）

Supabase GitHub 有已回報的 issue：在某些 OAuth 流程（如 Google OAuth）後，JWT 的 `aud` claim 可能從字串 `"authenticated"` 變為陣列 `["authenticated"]`。[^26]

`python-jose` **不接受 list 作為 `audience` 參數**，傳入 list 時直接拋出 `TypeError: audience must be a string or None`。這不是 JWT 驗證失敗，而是程式碼執行錯誤，會導致 FastAPI dependency 拋出 500 而非 401。[^27]

### 問題三：python-jose 不支援多 audience 驗證

當架構中有多個服務（如未來 AREQA 擴展）需要接受同一個 JWT 但 audience 不同時，python-jose 無法處理 audience 為 list 的情況。RFC 7519 允許 `aud` 為字串陣列，但 python-jose 的實作不支援此規格。[^27]

**修復方案**：停用 python-jose 的內建 audience 驗證，改為手動驗證：

```python
from jose import jwt, JWTError

def verify_supabase_jwt(token: str, secret: str) -> dict:
    # 停用 audience 自動驗證，手動處理 aud claim 的 string/list 兩種形式
    payload = jwt.decode(
        token, secret,
        algorithms=["HS256"],
        options={"verify_aud": False}
    )
    
    token_aud = payload.get("aud")
    allowed = {"authenticated"}
    aud_set = set(token_aud) if isinstance(token_aud, list) else {token_aud} if token_aud else set()
    
    if not (aud_set & allowed):
        raise JWTError(f"Invalid audience: {token_aud!r}")
    
    return payload
```

### 問題四：GoTrue ES256 vs PostgREST HS256 演算法不符（靜默失敗）

有未解決的 GitHub issue（#43066）回報：GoTrue 在某些配置下以 ES256 簽發 JWT，但 PostgREST 期望 HS256。當演算法不符時，PostgREST **靜默降級為 anon 角色**而非回傳 401。若出現「認證請求卻像 anon 請求一樣」的行為，需確認 `SUPABASE_JWT_SECRET` 確實是 HS256 用的對稱金鑰，而非 ES256 的私鑰。[^3]

***

## 6. One-Time Ticket + Redis 的 WebSocket 認證安全問題

### 為何選擇 ticket 模式是正確的

WebSocket 的 JavaScript API 不支援在 handshake 時傳送自訂 HTTP header。直接把 JWT 放在 URL query string（`?token=<jwt>`）有被記錄到 server log 的風險。Ticket 模式的優點是 ticket 本身是短效的亂數 token，即使洩漏到 log 中，30 秒後也已失效。[^28][^29]

### 競爭條件（Race Condition）風險

計畫中的 ticket 流程（GET ticket → WS connect with `?ticket=xxx` → 後端驗證後立即刪除）存在一個潛在 race condition：

1. 前端 fetch ticket（ticket 存入 Redis，TTL=30s）
2. 若前端在 TTL 到期前發起**兩次** WS 連線（網路重試、重複點擊等），兩次連線都攜帶相同 ticket
3. 第一次連線驗證後刪除 ticket；第二次連線嘗試讀取同一 ticket，因已刪除而被拒

解決方案是使用 Redis 的原子操作（`SET ... EX ... NX` 或 Lua 腳本）確保「讀取 + 刪除」是原子的。在 Python 中：[^30]

```python
# 原子操作：讀取並刪除（確保只能使用一次）
async def consume_ws_ticket(ticket_id: str, redis) -> str | None:
    # GETDEL 是 Redis 6.2+ 的原子命令
    user_id = await redis.getdel(f"ws_ticket:{ticket_id}")
    return user_id  # None 表示 ticket 不存在或已被消費
```

### TTL 建議與安全考量

**建議 TTL：10~30 秒**，計畫中的 30 秒在合理範圍內。注意事項：[^31]

- TTL 不宜太長（> 60 秒），否則 ticket 洩漏後的攻擊視窗過大
- 在 WS 連線建立成功後，**必須立即刪除 ticket**（計畫已有此設計）
- 需驗證 `Origin` header，防止 Cross-Site WebSocket Hijacking（CSWSH）。WebSocket 不受 Same-Origin Policy 保護，任何網站都可以嘗試連線你的 WS endpoint：[^32]

```python
# FastAPI WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, ticket: str):
    allowed_origins = {"https://your-frontend.onrender.com"}
    if ws.headers.get("origin") not in allowed_origins:
        await ws.close(code=4001)
        return
    # ... 繼續 ticket 驗證
```

### Render 免費方案 WebSocket 特別警告

Render 免費方案的服務休眠機制對 WebSocket 影響與 SSE 相同：**已建立的 WebSocket 連線不計為活動**，服務仍會在 15 分鐘後休眠並強制切斷所有 WS 連線（close code 1006）。計畫中的指數退避重連機制可以緩解此問題，但用戶體驗上仍會有明顯中斷。[^15]

***

## 7. Dexie.js IndexedDB 多使用者隔離：Schema 版本遷移風險

### 加入 `userId` 欄位到既有 Schema 的正確做法

Dexie.js 的版本遷移機制是安全的：IndexedDB 在 schema 升級時**預設保留所有既有資料**，不會刪除任何記錄。但有幾個需要特別注意的陷阱：[^33][^34]

**陷阱一：忘記加 `.upgrade()` 導致舊資料缺少 `userId` 欄位**

若只宣告新 schema 版本而不寫 `.upgrade()` 函式，現有資料的 `conversations` 和 `messages` 物件**不會自動加上 `userId` 欄位**——欄位只會在「新寫入」的資料上存在。查詢時若用 `userId` 做 index 過濾，舊資料永遠查不到，出現資料「蒸發」的靜默失敗：[^35][^34]

```typescript
// 錯誤：只宣告新 schema，不遷移舊資料
db.version(2).stores({
  conversations: '++id, userId, title',  // 加了 userId index
  messages: '++id, conversationId, userId'
});
// 結果：舊資料的 userId 是 undefined，被 index 查詢時完全不可見

// 正確：同時加 upgrade 函式，將舊資料補上 userId
db.version(1).stores({
  conversations: '++id, title',
  messages: '++id, conversationId'
});
db.version(2).stores({
  conversations: '++id, userId, title',
  messages: '++id, conversationId, userId'
}).upgrade(async tx => {
  const currentUserId = getCurrentUserId(); // 從 auth state 取得
  await tx.table('conversations').toCollection().modify(conv => {
    conv.userId = conv.userId ?? currentUserId;
  });
  await tx.table('messages').toCollection().modify(msg => {
    msg.userId = msg.userId ?? currentUserId;
  });
});
```

**陷阱二：多個分頁同時開啟時版本升級被阻塞**

當使用者在多個瀏覽器分頁開啟應用程式時，其中一個分頁部署新版本並嘗試升級 IndexedDB schema，其他舊版本分頁的 DB 連線會阻擋升級。Dexie 預設會發出 `versionchange` 事件並關閉舊連線，但若舊分頁的 JS 沒有回應（例如 tab 掛了），`blocked` 事件就會觸發，升級一直掛著。[^36]

需要在應用初始化時明確處理：

```typescript
db.on('versionchange', () => {
  // 強制重新載入舊分頁以使用新 schema
  window.location.reload();
});

db.on('blocked', () => {
  alert('資料庫升級被其他分頁阻擋，請關閉其他分頁後重新整理。');
});
```

**陷阱三：Dexie 版本號內部乘以 10**

Dexie 內部將所有版本號**乘以 10** 後儲存到 IndexedDB。例如 `db.version(1)` 在瀏覽器 DevTools 中顯示為版本 10，`db.version(2)` 顯示為 20。這不影響功能，但在 DevTools 偵錯時容易混淆，需要知道換算方式。[^37]

**陷阱四：登出時清空資料的競爭條件**

計畫中登出時要清空 Dexie 資料庫。需注意若同時有背景 async 操作（例如正在寫入新對話）和登出操作，清空可能與寫入競爭：

```typescript
// 登出時的安全清空方式
async function clearUserData(userId: string) {
  // 用 userId 作為條件刪除，而非直接 db.delete()
  // 避免誤刪正在遷移中的其他使用者資料
  await db.conversations.where('userId').equals(userId).delete();
  await db.messages.where('userId').equals(userId).delete();
}
```

***

## 綜合風險矩陣

| 問題 | 嚴重度 | 是否靜默失敗 | 最危險的情境 | 修復複雜度 |
|------|--------|------------|------------|----------|
| RLS `auth.uid()` NULL bypass | 🔴 嚴重 | ✅ 靜默 | anon role 有表格存取權 | 低（改 SQL policy）|
| RLS policy 效能（171ms/row）| 🟠 高 | ✅ 靜默 | 資料量大時查詢極慢 | 低（加 `select` 包裝）|
| asyncpg + PgBouncer prepared statement | 🟠 高 | ❌ 有錯誤 | 並發突增時 | 中（設定 `statement_cache_size=0`）|
| Engine-per-user Factory 連線耗盡 | 🔴 嚴重 | ✅ 靜默 | 使用者數增加時 | 高（重構 Factory 模式）|
| Render SSE Cloudflare 緩衝 | 🟡 中 | ✅ 靜默 | 首次部署 | 低（加 header）|
| Render 15 分鐘休眠斬斷連線 | 🟡 中 | ❌ 有錯誤 | 低流量時段 | 無法修（升級方案）|
| JWT `aud` 未驗證 | 🔴 嚴重 | ✅ 靜默 | 所有環境 | 低（加 `audience` 參數）|
| `aud` claim array vs string | 🟠 高 | ❌ 拋 500 | OAuth 登入流程 | 低（手動驗證）|
| WS Ticket CSWSH 未驗證 Origin | 🟠 高 | ✅ 靜默 | 跨站攻擊 | 低（加 Origin 驗證）|
| Dexie 舊資料缺少 userId | 🟠 高 | ✅ 靜默 | 現有使用者升級後 | 中（加 upgrade 函式）|
| Dexie versionchange 多 Tab 阻塞 | 🟡 中 | ❌ 掛起 | 多分頁使用者 | 低（加事件處理）|

***

## 優先修復建議

1. **立即修復（上線前必做）**：
   - RLS policy 改為 `(select auth.uid())`，避免效能問題與 NULL 漏洞
   - JWT 驗證必須傳入 `audience="authenticated"`，且改為手動驗證 `aud` claim 以支援 string/array 兩種形式
   - WS endpoint 加上 `Origin` header 驗證
   - FastAPI 後端直連 PostgreSQL 時，每個 transaction 必須設定 `request.jwt.claim.sub` 和 `set local role authenticated`

2. **架構調整（避免資料庫危機）**：
   - GUM Factory 模式改為全域共享一個 Engine，禁止 per-user Engine 實例化
   - SQLAlchemy engine 加上 `statement_cache_size=0`（無論用哪個 port）
   - 若使用 PgBouncer port 6543，必須加 `use_prepared_statements=False`

3. **部署前確認（Render 相關）**：
   - SSE Response 加入 `X-Accel-Buffering: no` header
   - Dexie schema 遷移必須包含 `.upgrade()` 函式補填 `userId`
   - 加入 Dexie `versionchange` 和 `blocked` 事件處理

---

## References

1. [Why is my service role key client getting RLS errors or not returning ...](https://supabase.com/docs/guides/troubleshooting/why-is-my-service-role-key-client-getting-rls-errors-or-not-returning-data-7_1K9z) - A Supabase client with the Authorization header set to the service role API key will ALWAYS bypass R...

2. [Supabase Row Level Security in Production: Patterns That Actually ...](https://dev.to/whoffagents/supabase-row-level-security-in-production-patterns-that-actually-work-2l78) - Supabase Row Level Security (RLS) is PostgreSQL's built-in access control system. When it's set up.....

3. [Supabase RLS pitfalls — what we learned in production](https://toolchew.com/en/deepdive-supabase-rls-pitfalls/) - 7 Supabase RLS pitfalls: NULL auth.uid(), service_role leaks, 171ms policies, infinite recursion, pr...

4. [How to enforce row level security on the server side? #7000 - GitHub](https://github.com/orgs/supabase/discussions/7000) - I'm doing all the DB queries for my supabase project in the server side. However, since I use a conn...

5. [Run queries as authenticated user with direct connection](https://github.com/orgs/supabase/discussions/30124) - https://supabase.com/docs/guides/functions/connect-to-postgres#using-a-postgres-client Hi, this guid...

6. [Use Supabase RLS with Drizzle](https://gist.github.com/rphlmr/88d6b759ddce83c4af3a769a55af0768) - Use Supabase RLS with Drizzle. GitHub Gist: instantly share code, notes, and snippets.

7. [Python asyncpg fails with burst requests on both Supabase ...](https://github.com/supabase/supabase/issues/39227) - The error occurs because prepared statements like "asyncpg_stmt_9" are being created and pgbouncer i...

8. [Frequently Asked Questions — asyncpg Documentation](https://magicstack.github.io/asyncpg/current/faq.html) - pgbouncer, when in the "transaction" or "statement" pooling mode, does not support prepared statemen...

9. [Supabase Pooling and asyncpg Don't Mix](https://medium.com/@patrickduch93/supabase-pooling-and-asyncpg-dont-mix-here-s-the-real-fix-44f700b05249) - When I began building my backend, the setup seemed simple enough: a Python service using SQLAlchemy ...

10. [pgvector + Postgres for SQL-Friendly RAG (HNSW + Async) | OSS AI Hub Code Starters](https://ossaihub.com/code/pgvector-postgres-setup/) - Self-hosted Postgres 16 + pgvector 0.7 with HNSW index, JSONB metadata filters, partial indexes per ...

11. [使用SQLAlchemy+asyncpg+pgbouncer时遇 ...](https://www.volcengine.com/article/993109) - 若能修改Supabase的pgbouncer配置，将 pool_mode 从 transaction 改为 session 模式。session模式支持预准备语句，但需注意连接复用逻辑的变化——若Su...

12. [Deep Dive: Resolving Asyncio Deadlocks and Memory Leaks in Python SQLAlchemy](https://dev.to/_80a1fa98d19e605032996/deep-dive-resolving-asyncio-deadlocks-and-memory-leaks-in-python-sqlalchemy-c49) - The Hidden Traps of Asyncio + ORM in High-Concurrency Python Moving from synchronous Python to...

13. [Connection Pooling - SQLAlchemy](https://sqlalchemy-sqlalchemy.mintlify.app/core/pooling) - Connection pool strategies, QueuePool, NullPool, and pool configuration

14. [How We Discovered and Fixed a Connection Leak in ...](https://medium.com/@har.avetisyan2002/how-we-discovered-and-fixed-a-connection-leak-in-async-sqlalchemy-during-chaos-testing-bf45acf65559) - When we first ran chaos tests against our backend, we didn’t expect to uncover a deep, timing-sensit...

15. [Render Free node.js websocket disconnects for no reason](https://community.render.com/t/render-free-node-js-websocket-disconnects-for-no-reason/21750) - I have seen posts about this from a few years ago, that the free version of Render will just randoml...

16. [Render service goes to sleep after a few minutes of inactivity](https://github.com/orgs/community/discussions/197645) - This behavior is expected on Render's free tier. Free web services automatically spin down after a p...

17. [Deploy FastAPI on Render Fast Without the Usual ...](https://kuberns.com/blogs/deploy-fastapi-on-render/) - Render's free tier sleeps your FastAPI app after 15 minutes of inactivity. Cold starts take 30 to 60...

18. [Server Sent Events and Cloudflare](https://community.render.com/t/server-sent-events-and-cloudflare/3238) - I’m developing an API for a service that’s gonna launch soon. Clients will connect and listen for da...

19. [Server-Sent Events (SSE) - FastAPI](https://fastapi.tiangolo.com/tutorial/server-sent-events/) - Set a special header X-Accel-Buffering: no to prevent buffering in some proxies like Nginx. You don'...

20. [The Streaming Infrastructure Behind Real-Time Agent UIs](https://tianpan.co/blog/2026-04-10-streaming-real-time-agent-uis-sse-backpressure-reconnection) - Four ways agent streaming fails in production — and the server-side architecture decisions for SSE t...

21. [Remix: Using Server-Sent Events](https://community.render.com/t/remix-using-server-sent-events/26840) - Hello, all! I’m trying out Render and it’s not bad so far. Main reason I’m using it is because I’m t...

22. [30 second connection limit? - Render Community](https://community.render.com/t/30-second-connection-limit/12016) - Is there a connection timeout limit of some sort? I am running a flask app, which makes a streaming ...

23. [Increase Flask Service Timeout Limit - Render](https://community.render.com/t/increase-flask-service-timeout-limit/1664) - I have a Flask web service that constantly fails because it times out after 30 seconds. This service...

24. [Validating a Supabase JWT locally with Python and FastAPI](https://dev.to/zwx00/validating-a-supabase-jwt-locally-with-python-and-fastapi-59jf) - Supabase is nice, but the functionality it provides for verifying tokens (auth.get_user) for some...

25. [Verifying Supabase JWT Myself - Bad Practice? #20763 - GitHub](https://github.com/orgs/supabase/discussions/20763) - I am creating a backend server with micronaut and would like to use the existing supabase auth for m...

26. [JWT aud claim suddenly an array instead of string · Issue #1656 · supabase/auth](https://github.com/supabase/auth/issues/1656) - Bug report I confirm this is a bug with Supabase, not with my own application. I confirm I have sear...

27. ["One JWT, five services, and the python-jose audience list trap"](https://dev.to/zoetaka38/one-jwt-five-services-and-the-python-jose-audience-list-trap-5e3i) - audience must be a string or None. That was the exception python-jose threw the moment our unified.....

28. [Is it secure to send JWT tokens in url query parameters if we use nonce to make it a one time token?](https://security.stackexchange.com/questions/276235/is-it-secure-to-send-jwt-tokens-in-url-query-parameters-if-we-use-nonce-to-make) - Websockets don't support sending auth tokens during websocket handshake as part of HTTP headers, rat...

29. [ID Token in url is not a security best practice · Issue #15 · aws-samples/websocket-api-cognito-auth-sample](https://github.com/aws-samples/websocket-api-cognito-auth-sample/issues/15) - websocket-api-cognito-auth-sample/frontend/src/views/Echo.vue Line 63 in d0ca229 this.client = new w...

30. [Redis get and set race condition question](https://stackoverflow.com/questions/63958463/redis-get-and-set-race-condition-question) - I have been reviewing every topic I can on this and cant seem to get the answer I'm looking for so h...

31. [Solving a race condition in a real-time system with Redis](https://www.linkedin.com/posts/himanshu-marasini_backendengineering-distributedsystems-activity-7327344402815688704-A0AH) - 🚨 𝗥𝗮𝗰𝗲 𝗖𝗼𝗻𝗱𝗶𝘁𝗶𝗼𝗻𝘀 𝗶𝗻 𝗥𝗲𝗮𝗹-𝗧𝗶𝗺𝗲 𝗦𝘆𝘀𝘁𝗲𝗺𝘀: 𝗟𝗲𝘀𝘀𝗼𝗻𝘀 𝗳𝗿𝗼𝗺 𝘁𝗵𝗲 𝗕𝗮𝗰𝗸𝗲𝗻𝗱 𝗧𝗿𝗲𝗻𝗰𝗵𝗲𝘀 Recently, I encountered a ...

32. [What is the right way to handle authentication over web ...](https://news.ycombinator.com/item?id=29893638)

33. [How do you handle schema migrations in IndexedDB (e.g., adding a ...](https://www.mindstick.com/interview/34320/how-do-you-handle-schema-migrations-in-indexeddb-e-g-adding-a-new-field-or-object-store) - How do you handle schema migrations in IndexedDB (e.g., adding a new field or object store)?

34. [Understanding the basics - Offline-First Database | Dexie.js - Dexie.js](https://dexie.org/docs/Tutorial/Understanding-the-basics) - Understanding the basics documentation for Dexie.js. Learn offline-first development with IndexedDB ...

35. [Data versioning approaches - Mastering Dexie.js: A Complete Guide to IndexedDB Development](https://app.studyraid.com/en/read/11356/355150/data-versioning-approaches) - Data versioning is a critical aspect of managing data synchronization in IndexedDB applications usin...

36. [Dexie.on.versionchange - Offline-First Database for JavaScript](https://dexie.org/docs/Dexie/Dexie.on.versionchange) - Dexie.on.versionchange documentation for Dexie.js. Learn offline-first development with IndexedDB wr...

37. [Version numbers increased by 10 · dexie Dexie.js · Discussion #1841](https://github.com/dexie/Dexie.js/discussions/1841) - So imagine me seeing the database number for the first time, being 10. Huh? Test db, so I deleted it...

