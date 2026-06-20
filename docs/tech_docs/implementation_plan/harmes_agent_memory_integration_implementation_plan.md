# AREQA 雙層記憶架構整合計畫 (Hermes Memory PoC 導入)

## 專案目標與背景 (Goal Description)
本計畫旨在將 `misc/AREQA_HarmesAgent_memory_poc` 實證之「冷熱雙層記憶 (Bilevel Memory)」、「容量門檻與自動壓縮 (Budget Gate & Auto-Compaction)」、「前台顯式工具與背景防抖 (Debounced Background)」等先進機制，整合至 AREQA 系統的後端 (`backend` 與 `misc/gum` 模組)。
此升級將解決當前依賴純向量檢索（Cold Memory）可能導致的上下文近因效應（Context Recency Bias）與指代消解失敗問題，並防止 LLM Context 膨脹，大幅提升智慧體記憶的精準度與反應效率。

> [!NOTE]
> 熱記憶（Hot Memory）包含 `USER_PROFILE` 與 `CORE_MEMORY`，將作為常駐知識無條件注入 System Prompt；冷記憶（Cold Memory）則沿用現行 `gum.db` 處理長尾知識與龐大對話歷史。

## 需使用者審查項目 (User Review Required)
> [!IMPORTANT]
> 1. **資料庫與檔案存放策略**：目前的 PoC 採用 `.jsonl` 檔案存放熱記憶。在正式環境中，是否同意在 `data/gum_data/` 下獨立出 `hot_memory.jsonl` 與 `user_profile.jsonl`？或是希望直接整併進入 SQLite (`gum.db`) 建立專屬 Table？
> 2. **Function Calling 支援**：由於前台工具 (`add_memory`, `replace_memory` 等) 需要依賴 LLM 的 Function Calling 功能。目前專案使用 OpenRouter 呼叫 `qwen/qwen-2.5-7b-instruct` 或 `qwen3` 等模型，是否確認這些模型版本對 Function Calling 的支援度足以勝任？

## 開放性問題 (Open Questions)
> [!WARNING]
> 1. **字元/Token 容量門檻設定**：針對熱記憶，初步建議設定 800 字元的硬性上限（超過即觸發自動壓縮）。此數字是否符合目前前端介面與實際業務場景的需求？
> 2. **背景防抖佇列的時間視窗**：初步設定為 3 秒防抖 (Debounce Window)。這意味著使用者若在 3 秒內連續輸入兩句話，系統會將其合併為單一批次進行記憶萃取。此時間長度是否需要調整？

---

## 擬定變更 (Proposed Changes)

### 1. 記憶儲存層 (Memory Storage)
#### [NEW] `backend/memory_store.py`
實作基於 JSONL (或 SQLite) 的熱記憶讀寫層。包含：
* 原子化寫入操作 (Atomic operations) 確保資料不毀損。
* `_check_budget` 邏輯，負責在寫入前驗證 `memory_char_limit` 與 `user_char_limit`。

### 2. GUM 整合與背景程序 (GUM Integration & Background Worker)
#### [MODIFY] `backend/gum_integration.py`
* **新增熱記憶快照讀取**：實作 `get_hot_memory_snapshot()` 函式，供主 API 抓取並注入。
* **改寫觀察值推送 (Push Observation)**：實作 `asyncio.Queue` 作為防抖佇列。將原先同步/立即觸發的 `push_observation`，改為推入佇列，並由常駐的 Background Worker 以 3 秒防抖視窗進行 Batch 處理與冷記憶語意萃取。
* **實作自動壓縮機制**：當 `MemoryStore` 拋出容量滿載錯誤時，呼叫 `compact_memory()` 強制 LLM 重新整理熱記憶。

### 3. FastAPI 路由與 System Prompt (FastAPI Routing)
#### [MODIFY] `backend/main.py`
* **System Prompt 修改**：在組裝給 LLM 的 System Prompt (`BASE_PERSONA` / `SYSTEM_PROMPT_WITH_RAG`) 時，強制掛載透過 `get_hot_memory_snapshot()` 取得的熱記憶字串。
* **整合 Function Calling**：修改 `/api/v1/stream` 中的 LLM 請求邏輯，註冊前台記憶操作工具 (`add_memory`, `remove_memory`, `replace_memory`)，並實作攔截與執行邏輯。

---

## 驗證計畫 (Verification Plan)

### 自動化測試 (Automated Tests)
1. **單元測試**：在 `tests/backend/` 下新增 `test_memory_store.py`，模擬並驗證字元超過上限時，是否正確拋出滿載例外並觸發壓縮流程。
2. **單元測試**：新增 `test_background_debounce.py` 驗證 `asyncio.Queue` 在 3 秒內連續推入三筆訊息時，最終只會觸發一次背景 Batch 萃取。
3. **整合測試**：更新現有 `test_gum_integration.py`，驗證 `get_hot_memory_snapshot()` 是否被正確呼叫且回傳非空字串。

### 手動驗證 (Manual Verification)
1. **冷熱記憶交叉驗證**：
   * 在對話中發送：「我國小的導師是張美麗」。
   * 發送幾句閒聊將上下文洗掉。
   * 發送：「我的老師叫什麼名字？」
   * **預期結果**：系統能夠直接命中熱記憶回答「張美麗」，而不受近因效應或冷檢索失敗影響。
2. **容量超限測試**：
   * 故意手動將大量字串要求系統記住，直到超過 800 字元門檻。
   * **預期結果**：系統應在背景觸發 `compact_memory`，並在下一輪對話中，能觀察到熱記憶字串已被精煉與縮減。
