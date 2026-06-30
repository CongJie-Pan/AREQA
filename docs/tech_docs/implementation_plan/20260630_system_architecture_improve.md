# AREQA 系統架構重構實作計畫 (2026-06-30)

> **文件狀態**：已通過可行性審計（Audit 日期：2026-06-30）
>
> **執行方式**：Gate-Driven 漸進式執行。對話中說「**開始 Gate X**」，AI 即刻執行該 Gate 的程式碼與測試並回報結果；你確認後解鎖下一個 Gate。每個 Gate 完成後系統必須保持可運行狀態。
>
> **責任分工**：AI 負責撰寫所有程式碼、執行測試、回報結果；你負責確認測試結果、UI 行為驗證、執行 `git commit`。

---

## 背景：為什麼要重構？

經完整代碼審計，AREQA 目前架構存在以下 **6 個已驗證的技術痛點**，所有問題均已定位至具體程式碼行號：

| # | 問題 | 代碼位置 | 影響 |
|---|---|---|---|
| 1 | `stream_endpoint` 函數高達 627 行，承擔 7 個職責 | `main.py` Line 618–1245 | 極難單元測試與維護 |
| 2 | 前端 `ProactiveManager` 每 30 秒輪詢一次 | `ProactiveManager/index.tsx` Line 95 | 最高 30 秒延遲 + 無效伺服器負載 |
| 3 | `_rag_cache` 為記憶體字典，多 Worker 不共享 | `main.py` Line 24 | 多進程部署快取失效 |
| 4 | `asyncio.Lock()` 僅保護單一進程 | `memory_store.py` Line 7 | 多 Worker 並發寫入競態 |
| 5 | 背景排程依賴 `while True + asyncio.sleep` | `compeer_scheduler.py` Line 166, 152 | 崩潰後無重試機制 |
| 6 | 魔術數字散落各處 | `main.py` Line 487, 658, 712, 799–801 | 更換模型或調參必須改代碼 |

---

## Gate 執行順序總覽

```
Gate 0A ──► Gate 0B ──► Gate 1A ──► Gate 1B
                                        │
                    ┌───────────────────┘
                    ▼
Gate 2A ──► Gate 2B ──► Gate 2C ──► Gate 2D ──► Gate 3A
```

| Gate | 核心改動 | 風險 | UI 驗證 |
|---|---|---|---|
| **0A** | 建立 `config.py` | 🔵 零 | 不需要 |
| **0B** | 提升 `PROJECT_ROOT` 為模組常數 | 🔵 極低 | 不需要 |
| **1A** | 建立 `OrchestrationService`（只新增） | 🟡 低 | ✅ 需要 |
| **1B** | 接線 `stream_endpoint` 使用 Orchestrator | 🟡 中 | ✅ 需要 |
| **2A** | 建立 `ConnectionManager` + WebSocket 端點 | 🟠 低 | 不需要 |
| **2B** | `compeer_scheduler` 整合廣播 | 🟠 低 | 不需要 |
| **2C** | 建立前端 `useProactiveWebSocket` Hook | 🟠 低 | 不需要 |
| **2D** | 切換 `ProactiveManager` 移除 Polling | 🟠 中 | ✅ 需要 |
| **3A** | Redis 取代 `_rag_cache` | 🔴 低（需 Redis） | ✅ 選做 |

---

## Gate 0A：建立集中式設定 `backend/config.py`

> 🔵 **風險：零** — 純粹新增檔案，不動任何現有邏輯
> **解鎖條件**：`pytest tests/backend/test_config.py` 全綠

### 問題現況（審計確認）

以下魔術數字直接寫死於函數體內，更換模型或調整參數必須改程式碼後重新部署：

- `main.py` Line 487, 712：`"qwen/qwen3-30b-a3b-instruct-2507"`（HyDE / Policy 模型）
- `main.py` Line 976, 979：`"qwen/qwen3-235b-a22b-thinking-2507"` / `"qwen/qwen3-235b-a22b-2507"`（主 LLM）
- `main.py` Line 799–801：`MAX_DOCS = 7`、`SCORE_DROP_TOLERANCE = 0.60`、`ABSOLUTE_MIN_SCORE = 0.005`
- `main.py` Line 770：`effective_threshold = 0.35`

### AI 執行內容

**新建** `backend/config.py`：
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LLM Model Names
    model_policy_classifier: str = "qwen/qwen3-30b-a3b-instruct-2507"
    model_hyde_decomposer: str = "qwen/qwen3-30b-a3b-instruct-2507"
    model_main_instruct: str = "qwen/qwen3-235b-a22b-2507"
    model_main_thinking: str = "qwen/qwen3-235b-a22b-thinking-2507"
    model_gum: str = "qwen/qwen3-235b-a22b-2507"

    # RAG Parameters
    rag_max_docs: int = 7
    rag_score_drop_tolerance: float = 0.60
    rag_absolute_min_score: float = 0.005
    rag_reranker_threshold: float = 0.35
    rag_rrf_threshold: float = 0.005
    rag_cache_size: int = 200

    # Infrastructure
    redis_url: str = "redis://localhost:6379"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
```

**新建** `tests/backend/test_config.py`，執行測試，驗證：
- 預設值正確載入
- 環境變數可覆寫（防止未來 Hardcoding 回歸）

### 你的驗收動作

```bash
pytest tests/backend/test_config.py -v
```
確認全綠後執行：
```bash
git commit -m "chore: extract Settings to backend/config.py"
```

---

## Gate 0B：提升 `PROJECT_ROOT` 為模組常數

> 🔵 **風險：極低** — 7 處 scope 變數替換，無邏輯改動
> **解鎖條件**：`pytest tests/backend/` 全部 25 個既有測試 + 新測試全綠

### 問題現況（審計確認）

`project_root` 目前定義在 `try` 區塊的 local scope（`main.py` Line 115），但在以下位置跨 scope 引用：
- `startup_event`（Line 233–234）：`hot_path = project_root / "data" / ...`
- `stream_endpoint`（Line 1204）：`log_path = Path(...).parents[1] / "data" / ...`

若後續拆分模組時直接複製此模式，將在子模組中引發 `NameError`。

### AI 執行內容

1. 在 `main.py` 模組頂層（`from pathlib import Path` 之後）新增：
   ```python
   PROJECT_ROOT = Path(__file__).resolve().parents[1]
   ```
2. 將 `main.py` 中所有 7 處 `project_root` 引用替換為 `PROJECT_ROOT`
3. 新建 `tests/backend/test_startup_config.py`，驗證 `PROJECT_ROOT` 已為模組常數
4. 執行**全部後端測試**確認零回歸

### 你的驗收動作

```bash
pytest tests/backend/ -v --tb=short
```
確認 **全部既有測試 + 新測試全綠**（零回歸）後執行：
```bash
git commit -m "refactor: promote PROJECT_ROOT to module-level constant"
```

---

## Gate 1A：建立 `OrchestrationService`（只新增，不刪舊）

> 🟡 **風險：低** — 新增獨立模組，`stream_endpoint` 原始邏輯完整保留，兩者並存
> **解鎖條件**：新 Node 測試 + 全部既有測試全綠，且你確認手動 UI 正常

### 問題現況（審計確認）

`stream_endpoint`（`main.py` Line 618–1245）承擔 7 個不可分割的職責，全部混在一個 generator 函數體內，且因為 SSE `yield` 語義貫穿全流程，無法簡單抽成普通 async 函數。

**審計發現的關鍵架構決策**：`OrchestrationService` 必須設計為 `AsyncGenerator[str, None]`，每個 Node 也必須是 async generator，才能保留 SSE yield 事件的串流能力。

### AI 執行內容

**新建** `backend/services/orchestration_service.py`，實作 7 個 Node：

```python
from typing import AsyncGenerator
from fastapi import Request

class OrchestrationService:
    def __init__(self, router_service, rag_service, suggestion_service, client):
        self.router = router_service
        self.rag = rag_service
        self.suggestion = suggestion_service
        self.client = client

    async def execute(self, messages, use_rag, force_think,
                      max_tokens, temperature, top_p,
                      repetition_penalty, request: Request) -> AsyncGenerator[str, None]:
        last_user_msg = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        # Node 1: Intent Routing
        denied = False
        async for event in self._node_intent_routing(last_user_msg, messages):
            yield event
            if '"status": "refused"' in event:
                denied = True
        if denied:
            return
        # Node 2 + 3: HyDE & Policy（並行）
        # Node 4: RAG Retrieval
        # Node 5: Prompt Assembly & Memory Injection
        # Node 6: Main LLM Stream + Tool Call
        # Node 7: Post-generation（Suggestions + JSONL Log）
        ...
```

Node 對應關係：

| Node | 對應現有代碼 | 職責 |
|---|---|---|
| `_node_intent_routing` | Line 660–690 | RouterService 呼叫，DENY 則 yield 拒絕並 return |
| `_node_hyde` | Line 729–730 | `parse_and_decompose_query` |
| `_node_policy` | Line 714–717 | `classify_dialogue_policy` asyncio.Task |
| `_node_rag_retrieval` | Line 720–875 | `retrieve_with_events` SSE 串流 |
| `_node_prompt_assembly` | Line 884–948 | System Prompt + Memory 注入 |
| `_node_llm_stream` | Line 973–1166 | 主 LLM 串流 + Tool Call |
| `_node_post_generation` | Line 1169–1213 | Suggestion 生成 + JSONL 日誌 |

**新建** `tests/backend/test_orchestration_service.py`，驗證：
- DENY 時 `_node_intent_routing` yield `refused` SSE 並包含 `[DONE]`
- ALLOW 時不阻斷管線
- Prompt Assembly 正確注入 `<working_memory>`
- 完整管線 SSE 序列與現有 `test_stream_endpoint.py` 期望一致

### 你的驗收動作

```bash
# 1. 測試
pytest tests/backend/ -v --tb=short

# 2. 啟動後端，問一個問題，確認系統仍正常運作（OrchestrationService 此時尚未接線）
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
確認後執行：
```bash
git commit -m "feat: add OrchestrationService with 7 AsyncGenerator pipeline nodes"
```

---

## Gate 1B：接線 `stream_endpoint` 使用 Orchestrator

> 🟡 **風險：中** — 核心路徑切換，SSE 行為必須與重構前完全一致
> **解鎖條件**：全部後端測試全綠，且你在瀏覽器確認 RAG / 思考模式正常

### AI 執行內容

1. **改寫** `main.py` 的 `stream_endpoint`（627 行 → ~15 行）：
   ```python
   @app.post("/api/v1/stream")
   async def stream_endpoint(request: Request, chat_req: ChatRequest):
       from config import settings
       orchestrator = OrchestrationService(
           router_service=router_service,
           rag_service=rag_service,
           suggestion_service=suggestion_service,
           client=_get_openai_client(),
       )
       return StreamingResponse(
           orchestrator.execute(
               messages=chat_req.messages,
               use_rag=chat_req.use_rag,
               force_think=chat_req.force_think,
               max_tokens=chat_req.max_tokens,
               temperature=chat_req.temperature,
               top_p=chat_req.top_p,
               repetition_penalty=chat_req.repetition_penalty,
               request=request,
           ),
           media_type="text/event-stream",
           headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
       )
   ```

2. **更新** `tests/backend/test_stream_endpoint.py` 的 4 個 patch 路徑：

   | 重構前 | 重構後 |
   |---|---|
   | `backend.main.parse_and_decompose_query` | `backend.services.orchestration_service.parse_and_decompose_query` |
   | `backend.main.AsyncOpenAI` | `backend.services.orchestration_service.AsyncOpenAI` |
   | `backend.main.rag_service` | 不變（仍為注入點） |
   | `backend.main.router_service` | 不變（仍為注入點） |

   > `test_gatekeeper_rejection` 和 `test_rag_score_threshold_refusal` 僅 patch 注入點，**不需修改**，可直接作為回歸保護。

3. 執行全部後端測試

### 你的驗收動作

```bash
# 1. 測試
pytest tests/backend/ -v --tb=short

# 2. 瀏覽器 UI 驗證（三項必須全部確認）
#    ① RAG 模式：問一個問題，確認 SSE 進度列正常顯示：
#       📖 翻閱古籍索引... → ⚖️ 比較段落關聯性... → ✍️ 援引文獻，生成解說...
#    ② 思考模式（force_think）：開啟思考開關後問問題，確認 <think> 展開面板正常
#    ③ 域外拒絕：問數學問題，確認出現拒絕訊息
```
確認後執行：
```bash
git commit -m "refactor: wire stream_endpoint through OrchestrationService (627 lines → 15 lines)"
```

---

## Gate 2A：建立 `ConnectionManager` + WebSocket 端點

> 🟠 **風險：低** — 純粹新增；Polling 端點 `/api/v1/proactive-check` 維持不動，兩者並存
> **解鎖條件**：全部後端測試全綠

### 問題現況（審計確認）

`ProactiveManager/index.tsx` Line 95：`}, 30000)` — 每 30 秒輪詢，最高延遲 30 秒。
FastAPI 的 `CORSMiddleware` 不覆蓋 WebSocket 路由，必須手動驗證 `Origin` header。

### AI 執行內容

**新建** `backend/services/connection_manager.py`：
```python
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, ws: WebSocket):
        await ws.accept()
        self.active[user_id] = ws

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)

    async def broadcast_alert(self, user_id: str, content: str):
        ws = self.active.get(user_id)
        if ws:
            await ws.send_json({"has_alert": True, "content": content})

ws_manager = ConnectionManager()
```

**在** `main.py` 新增 WebSocket 端點：
```python
from backend.services.connection_manager import ws_manager

@app.websocket("/api/v1/ws/notifications")
async def ws_notifications(websocket: WebSocket, user_id: str = "default_user"):
    # 手動驗證 Origin（CORSMiddleware 不覆蓋 WebSocket）
    origin = websocket.headers.get("origin", "")
    allowed = ["http://localhost:3000", "http://127.0.0.1:3000"]
    if origin not in allowed:
        await websocket.close(code=1008)  # Policy Violation
        return
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # 維持連線存活
    except Exception:
        ws_manager.disconnect(user_id)
```

**新建** `tests/backend/test_connection_manager.py`，驗證：
- `connect()` 將 WebSocket 加入 `active`
- `broadcast_alert()` 對活躍使用者發送 JSON
- `broadcast_alert()` 對未連線使用者不拋出例外
- `disconnect()` 從 `active` 移除
- 惡意 Origin 被 close code 1008 拒絕

### 你的驗收動作

```bash
pytest tests/backend/ -v --tb=short
```
確認全綠後執行：
```bash
git commit -m "feat: add WebSocket /api/v1/ws/notifications with ConnectionManager and Origin validation"
```

---

## Gate 2B：`compeer_scheduler` 整合 WebSocket 廣播

> 🟠 **風險：低** — 在既有 `set_pending_alert` 之後**額外**呼叫廣播，不替換原有邏輯
> **解鎖條件**：全部後端測試全綠（特別是 `test_edf_unit.py` 的 compeer 相關測試不受影響）

### AI 執行內容

修改 `backend/services/compeer_scheduler.py` Line 191 區段，在 scroll alert 寫入後追加廣播：
```python
# 原有：寫入 hot_memory（保留）
hot_mem[f"pending_alert_default_user"] = "AREQA發現你好像來回看了幾遍..."
store._atomic_write(store.hot_memory_path, hot_mem)

# 新增：同時透過 WebSocket 即時推播
from backend.services.connection_manager import ws_manager
import asyncio
asyncio.create_task(
    ws_manager.broadcast_alert("default_user", hot_mem["pending_alert_default_user"])
)
```

> ⚠️ **循環引用避免**：`compeer_scheduler` 不直接 import `main`，而是透過 `connection_manager` 模組存取 `ws_manager`，確保無循環引用。

執行全部後端測試。

### 你的驗收動作

```bash
pytest tests/backend/ -v --tb=short
```
確認全綠後執行：
```bash
git commit -m "feat: compeer_scheduler broadcasts scroll alert via WebSocket"
```

---

## Gate 2C：前端建立 `useProactiveWebSocket` Hook（雙軌並行）

> 🟠 **風險：低** — 只新增 hook，`ProactiveManager` 尚未改動，Polling 仍在運行
> **解鎖條件**：全部前端測試全綠

### AI 執行內容

**新建** `frontend/src/hooks/useProactiveWebSocket.ts`：
```typescript
import { useCallback, useEffect, useRef } from 'react';

export function useProactiveWebSocket(onAlert: (content: string) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const retryDelayRef = useRef(1000); // 初始退避 1 秒

  const connect = useCallback(() => {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    const wsUrl = backendUrl.replace(/^http/, 'ws');
    wsRef.current = new WebSocket(`${wsUrl}/api/v1/ws/notifications?user_id=default_user`);

    wsRef.current.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.has_alert && data.content) onAlert(data.content);
    };
    // 連線成功：重置退避
    wsRef.current.onopen = () => { retryDelayRef.current = 1000; };
    // 斷線：指數退避重連（最多 30 秒）
    wsRef.current.onclose = () => {
      setTimeout(connect, retryDelayRef.current);
      retryDelayRef.current = Math.min(retryDelayRef.current * 2, 30000);
    };
  }, [onAlert]);

  useEffect(() => {
    connect();
    return () => wsRef.current?.close();
  }, [connect]);
}
```

**新建** `tests/frontend/hooks/useProactiveWebSocket.test.ts`，驗證：
- 收到 `has_alert: true` 時呼叫 `onAlert`
- 收到 `has_alert: false` 時不呼叫 `onAlert`
- 斷線後以指數退避重連（1s → 2s → 4s...）
- 重連成功後退避重置為 1s

### 你的驗收動作

```bash
cd frontend && npm run test
```
確認全綠後執行：
```bash
git commit -m "feat: add useProactiveWebSocket hook with exponential backoff reconnection"
```

---

## Gate 2D：切換 `ProactiveManager` 移除 Polling

> 🟠 **風險：中** — 使用者可見行為改變，需人工瀏覽器驗證
> **解鎖條件**：全部前端測試全綠，且你完成 DevTools + UI 行為驗證

### AI 執行內容

**修改** `frontend/src/components/ProactiveManager/index.tsx`：
- **移除**（Line 51–98）：`setInterval` 的 30 秒輪詢 `useEffect`
- **新增**：使用 `useProactiveWebSocket(handleAlert)` hook

```typescript
// 修改後的 ProactiveManager
export function ProactiveManager() {
  const { notification } = App.useApp();

  const handleAlert = useCallback((content: string) => {
    const key = `proactive-${Date.now()}`;
    notification.info({
      key,
      message: 'AREQA',
      description: content,
      icon: <BulbOutlined style={{ color: '#d8a25c' }} />,
      placement: 'top',
      duration: 0,
      // ... 按鈕邏輯保持不變
    });
  }, [notification]);

  // 以 hook 取代 setInterval
  useProactiveWebSocket(handleAlert);

  // scroll telemetry 保持不變
  useEffect(() => { /* ... handleScroll 邏輯完全保留 ... */ }, []);

  return null;
}
```

**更新** `tests/frontend/ProactiveManager.test.tsx`：
- 移除：`vi.advanceTimersByTime(30000)` 輪詢驗證 + `global.fetch` mock（proactive-check 相關）
- 新增：mock `useProactiveWebSocket`，驗證 hook callback 觸發時顯示通知
- **保留不變**：`should log scroll action with throttling`（scroll telemetry 行為不受影響）

執行全部前端測試。

### 你的驗收動作

```bash
# 1. 測試
cd frontend && npm run test

# 2. DevTools 驗證
#    ① 開啟 DevTools → Network → 篩選 XHR
#    ② 觀察 30 秒，確認不再出現 proactive-check 請求

# 3. UI 行為驗證
#    ① 在聊天頁面連續向上/向下滾動超過 6 次
#    ② 確認關懷提示燈泡立即出現（不再等 30 秒）
```
確認後執行：
```bash
git commit -m "feat: replace 30s polling with WebSocket push in ProactiveManager"
```

---

## Gate 3A：Redis 取代 `_rag_cache`（需要 Redis 環境）

> 🔴 **前置條件**：你需先執行 `redis-cli ping` 確認回傳 `PONG`
> **風險：低（基礎設施依賴）**
> **解鎖條件**：全部後端測試全綠（Redis 測試使用 Mock，不需真實 Redis）

### 問題現況（審計確認）

`main.py` Line 24：`_rag_cache: dict = {}` — 記憶體字典，多 Worker 無法共享。
`main.py` Line 755–758：手動 LRU 淘汰邏輯，`asyncio.Lock` 亦僅保護單進程。

### AI 執行內容

**新建** `backend/services/cache_service.py`：
```python
import redis.asyncio as aioredis
import pickle

class RagCacheService:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = aioredis.from_url(redis_url)
        self.TTL = 3600  # 1 小時 TTL，取代手動 LRU

    async def get(self, fingerprint: str):
        data = await self.redis.get(f"rag:{fingerprint}")
        return pickle.loads(data) if data else None

    async def set(self, fingerprint: str, result):
        await self.redis.setex(f"rag:{fingerprint}", self.TTL, pickle.dumps(result))
```

**修改** `main.py`：
- 移除 `_rag_cache: dict = {}` 和 `RAG_CACHE_SIZE = 200`（Line 24–25）
- 在 `startup_event` 初始化 `RagCacheService`
- 以 `await rag_cache.get/set()` 替換 Line 724–758 的字典操作

**新建** `tests/backend/test_cache_service.py`，驗證：
- `set()` 使用 pickle 序列化並帶 TTL 3600 秒
- `get()` 在未命中時回傳 `None`（不拋例外）
- `get()` 在命中時正確 unpickle 回傳原始物件

### 你的驗收動作

```bash
# 1. 確認 Redis 可用
redis-cli ping   # 應回傳 PONG

# 2. 測試（Redis 相關測試使用 Mock，無需真實 Redis）
pytest tests/backend/ -v --tb=short

# 3. 壓力測試（選做）
#    連問同一個問題 3 次，確認第 2、3 次回應速度明顯加快（快取命中）
```
確認後執行：
```bash
git commit -m "feat: replace in-memory _rag_cache dict with Redis RagCacheService"
```

---

## Gate 狀態追蹤（執行時更新）

| Gate | 說明 | AI 測試 | UI 驗證 | Commit | 狀態 |
|---|---|---|---|---|---|
| 0A | 建立 `config.py` | ⬜ | — | ⬜ | ⏳ 待開始 |
| 0B | 提升 `PROJECT_ROOT` | ⬜ | — | ⬜ | 🔒 |
| 1A | OrchestrationService 骨架 | ⬜ | ⬜ | ⬜ | 🔒 |
| 1B | 接線 `stream_endpoint` | ⬜ | ⬜ | ⬜ | 🔒 |
| 2A | ConnectionManager + WS | ⬜ | — | ⬜ | 🔒 |
| 2B | Scheduler 整合廣播 | ⬜ | — | ⬜ | 🔒 |
| 2C | `useProactiveWebSocket` | ⬜ | — | ⬜ | 🔒 |
| 2D | 切換 ProactiveManager | ⬜ | ⬜ | ⬜ | 🔒 |
| 3A | Redis Cache Service | ⬜ | ⬜（選做）| ⬜ | 🔒 |

> **圖例**：✅ 完成 ｜ ❌ 失敗 ｜ ⬜ 待執行 ｜ 🔒 前置 Gate 未完成 ｜ — 不需要

---

## Gate 失敗時的處理

```
Gate 失敗？
    │
    ├─ AI 測試紅燈 ──► 你不需做任何事，AI 自行修復並重跑
    │
    └─ 你的 UI 驗證失敗 ──► 描述具體問題給 AI
                              AI 定位根因並修復
                              AI 重跑測試
                              你再次驗證
```

> ⚠️ Gate 驗證失敗時，**不可強行推進到下一個 Gate**。每個 Gate 是後續 Gate 的前提，跳過會導致問題層疊難以追蹤。
