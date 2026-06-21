# AREQA 混合雙層記憶架構整合計畫 (Hybrid Hermes-GUM Memory Integration)

## 專案目標與架構定位 (Architectural Position & Goals)
本計畫旨在將 `misc/AREQA_HarmesAgent_memory_poc` 的「冷熱雙層記憶 (Bilevel Memory) / 隱式注入」與現有的 **GUMs**、**Generative Agents (對話壓縮與覆寫)** 及 **STITCH (記憶標籤)** 學術理論相結合。

新架構（**AREQA Hybrid Hermes-GUM Memory System**）定位如下：
1. **存取機制 (Retrieval)**：採用 Hermes Agent 的**雙層隱式注入**。熱記憶與冷記憶檢索在系統預處理階段自動組裝，LLM 於第一輪對話（Single Turn）即可直接存取，解決 MemGPT 主動 Tool Call 帶來的高延遲與不穩定性。
2. **寫入與狀態更新 (Write/Update)**：融合 GUMs 與 Generative Agents 的**覆寫邏輯 (`a=b -> a=c`)**。當 LLM 發起前台更新工具時，由 GUMs 引擎在極小的熱記憶中快速進行覆寫與一致性檢查。
3. **冷熱流轉與封存 (Compaction)**：當熱記憶超出容量上限，由 Background Worker 執行**自動壓縮與 STITCH 標籤化**，將過期記憶打上 Tag 歸檔至冷記憶庫。

---

## 記憶儲存與資料庫策略 (Storage & Database Strategy)

為求與 `misc/AREQA_HarmesAgent_memory_poc` 的實證架構保持一致，並發揮 SQL/向量庫的檢索優勢，系統採用以下存儲媒介分工：

| 記憶類型 | 儲存格式 | 檔案/DB 路徑 | 作用說明 |
| :--- | :--- | :--- | :--- |
| **工作記憶 (Hot/Core Memory)** | **JSON / JSONL** | `data/gum_data/hot_memory.json` | 紀錄當前最頻繁、剛被 GUMs 更新的狀態。讀寫速度極快、容易隨對話動態修改。 |
| **使用者畫像 (User Modeling)** | **JSON** | `data/gum_data/user_profile.json` | 紀錄用戶的基本事實、偏好（如姓名、年齡、習慣）。多為單鍵對應，讀寫頻率低。 |
| **長尾記憶 (Cold Memory)** | **SQL + 向量庫** | SQLite `gum.db` + sqlite-vec 延伸模組 | 封存被 Compaction 淘汰的歷史對話、STITCH 標籤化知識。提供大規模語意檢索。 |

---

## 核心設計細節 (Core Design Details)

### 1. sqlite-vec 檢索管道 (sqlite-vec RAG Pipeline)
系統的冷記憶檢索採用兩階段的檢索與重排機制：
```text
使用者問題 (User Query) 
  ↓
OpenRouter Embedding API (qwen/qwen3-embedding-8b)
  ↓
取得 float[] 向量
  ↓
sqlite-vec KNN 搜尋 (基於 L2 距離進行向量檢索，獲取 Top-K 候選)
  ↓
BM25 本地重排 (使用 rank_bm25 套件進行文字匹配度排序)
  ↓
RRF (Reciprocal Rank Fusion) 融合分數計算
  ↓
取得最終最相關的 Top-K 記憶
  ↓
隱式注入至 Prompt 中的 <retrieved_memory> 標籤
```

### 2. 教育問答領域 STITCH 記憶標籤設計 (Educational STITCH Tag Schema)
針對教育與知識問答情境（如《紅樓夢》知識場域），將記憶分類為以下 6 種核心 `primary_tags`：
* **`AcademicContext` (學習背景)**：記錄學習者的年級、科目或課程標準（例如：108課綱、高中學測、國文科）。
* **`ConceptMastery` (觀念掌握度)**：記錄學習者已掌握或混淆的核心觀念（例如：已掌握林黛玉判詞、混淆薛寶釵與林黛玉的性格隱喻）。
* **`ErrorWeakness` (常見錯誤與盲點)**：記錄學習者的錯題規律與知識死角（例如：分不清金陵十二釵正冊與副冊的名單分佈）。
* **`LearningGoal` (學習目標)**：記錄學習者當前的考試目標或學習進度（例如：準備古典文學專題、目標為精讀紅樓夢前四十回）。
* **`CognitiveStyle` (認知風格)**：記錄學習者偏好的對答引導方式與互動風格（例如：偏好蘇格拉底式提問引導、偏好表格對比分析）。
* **`GeneralPersonal` (一般個人事實)**：記錄非學科的學習者基本資料或閒聊事實（例如：使用者姓名、今日學習心情）。

### 3. STITCH 標籤化 Prompt 範本 (STITCH Tagging Prompt Template)
在 Hot Memory 超限觸發 Compaction 時，系統使用以下 Prompt 指引 LLM 進行結構化壓縮與標籤化歸檔：
```json
你是一個專業的學習行為分析專家。給定以下待歸檔的熱記憶條目，請執行以下任務：
1. 提煉出精煉的語意內容 (refined_content)
2. 從 [AcademicContext, ConceptMastery, ErrorWeakness, LearningGoal, CognitiveStyle, GeneralPersonal] 中選擇 1-2 個最符合的標籤 (primary_tags)
3. 提取記憶中出現的核心實體 (entities)，如人物、章節、書名
4. 判斷並保留時間脈絡或對話狀態 (temporal_context)

請嚴格以 JSON 格式回傳，範例如下：
{
  "refined_content": "使用者混淆了金陵十二釵正冊的妙玉與副冊的香菱，且對於判詞理解有偏差。",
  "primary_tags": ["ConceptMastery", "ErrorWeakness"],
  "entities": ["妙玉", "香菱", "金陵十二釵"],
  "temporal_context": "2026-06-21 對話第三輪"
}
```

### 4. GUM 衰退降級決策樹 (GUM Decay-based Demotion Strategy)
當 Hot Memory 容量超載時，系統基於 GUM 既有的時間衰退算法決定哪些記憶應被降級（Demotion）至冷記憶庫：
* **啟用衰退計算**：針對熱記憶中的每個條目，呼叫 `db_utils.py` 既有的 Activation Score 計算邏輯：
  $$\text{Activation Score} = \text{Confidence} \times e^{-(11 - \text{Decay}) \times K \times \text{Age}}$$
  * `Confidence` (1–10)：代表該事實的確定度。
  * `Decay` (1–10)：代表記憶的耐久度（1 為短期 transient 資訊，10 為長期 durable 事實）。
  * `Age`：記憶建立至今的相對時間（以天為單位）。
* **降級決策**：
  * **USER_PROFILE (使用者畫像)**：跳過 Decay 計算，**永不降級**，僅在 `user_profile.json` 中進行原處更新。
  * **Hot Memory (熱記憶)**：排序所有條目的 Activation Score。分數最低（即不常用且已過期）的條目將優先觸發 STITCH 標籤化，寫入冷記憶資料庫後從 Hot Memory 清除；高分條目繼續保留在熱記憶中。

---

## 記憶流轉設計 (Memory Flow Design)

### 1. 隱式雙層注入 (Implicit Bilevel Injection)
* 當 User Query 進來時，系統進行**預處理 (Pre-processing)**：
  * **Hot Memory**：直接讀取最新狀態，注入至 System Prompt 的 `<working_memory>`。
  * **Cold Memory**：提取 Query 並結合 STITCH 標籤進行 Hybrid Search，將檢索結果注入至 Prompt 的 `<retrieved_memory>`。
* LLM 直接讀取上述標籤生成回覆，**無需主動呼叫 Tool 進行 Search**。

### 2. 前台更新工具 (Foreground Update Tool)
* 當 LLM 識別到需要記憶的新事實（例如使用者提到「我換工作了」）：
  * LLM 呼叫前台工具 `update_memory(key, value)`。
  * 系統攔截工具呼叫，由 **GUMs / Generative Agents** 執行 `a=b -> a=c` 的實體覆寫邏輯，直接更新 Hot Memory JSON 中的狀態。

### 3. 背景防抖與自動壓縮 (Background Compaction)
* **背景佇列**：使用 `asyncio.Queue` 進行 3 秒防抖（Debounce），合批（Batch）處理對話觀察值。
* **容量門檻**：設定硬性上限（如 1000 字元）。
* **自動壓縮**：當 Hot Memory 超限時，Background Worker 啟動：
  * 提取不常用或過期的熱記憶。
  * 使用 **STITCH 理論** 為這些記憶打上標籤（例如 `#ConceptMastery #ErrorWeakness`，以《紅樓夢》為例，打上 `#ConceptMastery` 標籤並註明 `Entity: 林黛玉`）。
  * 寫入冷記憶庫 SQLite (`gum.db`) 與 sqlite-vec 向量資料庫，並清理 Hot Memory。

---

## 擬定變更 (Proposed Changes)

### 1. 記憶儲存層 (Memory Storage)
#### [NEW] `backend/memory_store.py`
實作基於 JSON 的熱記憶/使用者畫像讀寫，以及對 Cold SQLite DB 的儲存介面。包含：
* 原子化寫入操作 (Atomic operations) 確保 JSON 檔案寫入不毀損。
* `_check_budget` 邏輯，驗證容量上限。

### 2. GUM 整合與背景程序 (GUM Integration & Background Worker)
#### [MODIFY] `backend/gum_integration.py`
* **實作熱記憶注入**：新增 `get_hot_memory_snapshot()` 供主 API 抓取工作記憶。
* **改寫觀察值推送 (Push Observation)**：實作 `asyncio.Queue` 作為防抖佇列，由 Background Worker 以 3 秒防抖視窗進行 Batch 處理。
* **實作 GUMs 狀態覆寫與 STITCH 標籤壓縮**：當 Hot Memory 超限時，執行 Compaction。**沿用 `misc/gum/gum/db_utils.py` 既有的衰減算法** 計算 Activation Score，將低分條目打上 STITCH 教育標籤，儲存至冷記憶庫中（SQLite `gum.db` + sqlite-vec 向量庫），並將高分與 `USER_PROFILE` 保留在熱記憶中。

### 3. FastAPI 路由與 System Prompt (FastAPI Routing)
#### [MODIFY] `backend/main.py`
* **System Prompt 修改**：強制掛載 `<working_memory>` 與 `<retrieved_memory>` 於 System Prompt 中。
* **整合 Function Calling**：註冊前台更新工具 `update_memory`，並實作攔截與執行邏輯。

---

## 驗證計畫 (Verification Plan)

本計畫設計了分層測試體系，以《紅樓夢》知識場域為核心測試案例，確保記憶儲存、背景防抖、STITCH 標籤分類與 GUM 衰退機制的正確性。

### 1. 單元測試 (Unit Tests)

新增及更新的單元測試將置於 `tests/` 下，詳細設計如下：

| 測試檔案 | 測試對象與函式 | 測試情境與輸入 | 測試類型 | 預期結果 |
| :--- | :--- | :--- | :--- | :--- |
| `test_memory_store.py` | `_check_budget` | 熱記憶未達 1000 字元上限 | 正常情況 | 允許寫入，不觸發 Compaction 流程。 |
| `test_memory_store.py` | `_check_budget` | 熱記憶寫入後超過 1000 字元 | 邊界情況 | 拋出 `MemoryBudgetExceeded` 例外，正確觸發背景 Compaction。 |
| `test_memory_store.py` | `USER_PROFILE` 隔離 | 熱記憶滿載觸發 Compaction | 邊界情況 | 確保 `user_profile.json` 中的事實不被降級或刪除。 |
| `test_memory_store.py` | `a=b -> a=c` 覆寫 | 寫入：「林黛玉的丫鬟是雪雁」<br>後續寫入：「林黛玉的丫鬟是紫鵑」 | 正常情況 | 熱記憶中「林黛玉的丫鬟」的值成功更新為「紫鵑」，舊記憶被覆寫。 |
| `test_memory_store.py` | 原子化寫入 | 模擬在寫入 JSON 期間發生中斷或異常 | 失敗與異常 | 檔案系統能夠藉由臨時暫存檔機制恢復，JSON 檔案不毀損。 |
| `test_background_debounce.py` | `asyncio.Queue` 防抖 | 3 秒內連續推送 3 筆對話觀察值 | 正常情況 | 防抖機制運作，最終只觸發 1 次背景 Batch 處理。 |
| `test_background_debounce.py` | `asyncio.Queue` 間隔觸發 | 推送第 1 筆後間隔 4 秒，再推送第 2 筆 | 邊界情況 | 正確識別時間間隔，觸發 2 次獨立的背景處理。 |
| `test_stitch_tagger.py` | LLM STITCH 標籤分類 | 輸入：「我常常分不清賈寶玉和甄寶玉的性格差異」 | 正常情況 | LLM 返回的 JSON 包含 `primary_tags: ["ConceptMastery", "ErrorWeakness"]`。 |
| `test_stitch_tagger.py` | LLM 返回格式校驗 | STITCH Tagging Prompt 執行結果 | 正常情況 | 返回格式為合法的 JSON 且包含所有必要欄位（refined_content 等）。 |
| `test_stitch_tagger.py` | Tagging 異常降級 | LLM 返回格式毀損或非 JSON 格式 | 失敗與異常 | 系統能夠優雅降級（Fallback），以純文字與默認標籤寫入冷記憶庫而不崩潰。 |
| `test_gum_decay.py` | GUM 衰退分數 | 輸入高耐久性記憶（Decay=9）在短時間（Age=0.1天）內 | 正常情況 | 計算出高 Activation Score，記憶正確保留在 Hot Memory 中。 |
| `test_gum_decay.py` | GUM 衰退降級 | 輸入暫時性記憶（Decay=2）在長時間（Age=5天）後 | 正常情況 | 計算出極低 Activation Score，在 Compaction 時被正確降級至 Cold Memory。 |
| `test_gum_decay.py` | USER_PROFILE 衰退跳過 | 計算 `user_profile.json` 內容的分數 | 邊界情況 | 該類型記憶不進行衰退與分數計算，確保其始終留存。 |

### 2. 整合測試 (Integration Tests)

| 測試檔案 | 測試對象與情境 | 測試方法與流程 | 預期結果 |
| :--- | :--- | :--- | :--- |
| `test_gum_integration.py` | 記憶快照注入 | 呼叫 `get_hot_memory_snapshot()` | 成功取得當前熱記憶字串，且格式符合主對話 System Prompt 注入標準。 |
| `test_gum_integration.py` | 狀態動態更新與反映 | 更新熱記憶中的紅樓夢人物關係，隨即呼叫快照 | 取得的快照內容能立即反映最新的覆寫結果（如：林黛玉的老師更新為賈雨村）。 |
| `test_rag_pipeline.py` | sqlite-vec 檢索管道整合 | 寫入冷記憶：「王熙鳳的判詞是凡鳥偏從末世來」<br>提問：「王熙鳳的判詞是什麼？」 | 經過 OpenRouter Embedding -> sqlite-vec KNN -> BM25 -> RRF 重排，Top-1 檢索結果與預期一致。 |
| `test_rag_pipeline.py` | 雲端 API 失敗降級 | 模擬 OpenRouter Embedding API 連線超時或失敗 | 系統自動降級至本地純文字 BM25 檢索，返回相關候選記憶，確保服務不中斷。 |
| `test_compaction_flow.py` | 端到端 Compaction 流程 | 連續寫入 20 條不同的紅樓夢知識事實，迫使總字元數突破 1000 | 背景 Worker 自動觸發，將低分記憶壓縮並寫入 SQLite 冷資料庫，熱記憶成功縮減至預算範圍內。 |

### 3. 手動驗證情境 (Manual Verification Scenarios)

以下手動測試以《紅樓夢》為範例場域，於前端/後端介面中逐一驗證：

1. **冷熱記憶交叉驗證**：
   * **操作步驟**：
     1. 在對話中發送：「林黛玉的開蒙老師是賈雨村」。
     2. 發送 5-10 句閒聊（例如談論今日天氣、古典小說格式等）將上下文 Context 洗掉。
     3. 發送提問：「林黛玉的老師是誰？」
   * **預期結果**：系統能夠直接從 `<working_memory>` 命中熱記憶並回答「林黛玉的老師是賈雨村」，證明熱記憶隱式注入有效，不受近因效應或上下文長度影響。

2. **記憶狀態覆寫驗證**：
   * **操作步驟**：
     1. 發送：「我原以為寶玉住大觀園的瀟湘館」。
     2. 發送：「但後來發現不對，寶玉住的其實是怡紅院，瀟湘館是黛玉住的」。
     3. 發送提問：「寶玉住在哪個院落？」
   * **預期結果**：系統成功執行 `a=b -> a=c` 覆寫，將熱記憶中寶玉的住處改為「怡紅院」，並在回答中正確回答寶玉住怡紅院、黛玉住瀟湘館。

3. **容量超限壓縮測試**：
   * **操作步驟**：
     1. 發送大量關於《紅樓夢》的知識設定，包括金陵十二釵判詞、大觀園格局、賈府人物關係等，直到熱記憶長度超過 1000 字元門檻。
   * **預期結果**：系統自動在背景觸發 Compaction，低 Activation Score 的暫時性閒聊或歷史對話被 STITCH 標籤化歸檔至冷記憶庫中，熱記憶長度被成功精簡（可經由後端日誌或 snapshot 查看）。

4. **教育 STITCH 標籤分類驗證**：
   * **操作步驟**：
     1. 發送：「我常常搞不清楚金陵十二釵正冊和副冊的人物，像香菱和晴雯到底是哪一冊的？」
     2. 觸發 Compaction 後，至冷記憶 SQLite DB (`gum.db`) 查詢該條歸檔記憶。
   * **預期結果**：該條記憶被正確打上 `["ErrorWeakness", "ConceptMastery"]` 標籤，核心實體 `["香菱", "晴雯", "金陵十二釵"]` 被成功提取。

5. **GUM Decay 降級優先序驗證**：
   * **操作步驟**：
     1. 發送 A 訊息（暫時性興趣，LLM 判定 Decay=2，如：「我這兩天想特別看一下賈府的螃蟹宴在第幾回」）。
     2. 發送 B 訊息（長期背景知識，LLM 判定 Decay=9，如：「我正準備撰寫一篇關於《紅樓夢》女性悲劇命運的學術論文」）。
     3. 連續發送訊息強制觸發 Compaction。
   * **預期結果**：A 訊息因 Activation Score 衰退極快被優先降級（Demote）至冷記憶庫，而 B 訊息因為高 Decay 分數（耐久度高）仍留在熱記憶 `<working_memory>` 中。

6. **USER_PROFILE 不降級驗證**：
   * **操作步驟**：
     1. 發送：「我是國立臺灣大學中文系三年級的學生，專門研究古典小說」。
     2. 強制觸發多次 Compaction 流程。
   * **預期結果**：該事實被儲存在 `user_profile.json` 中，即使經過多次 Compaction 壓縮，使用者的學校與年級等核心畫像資訊依然完整保留，絕不被降級或遺失。
