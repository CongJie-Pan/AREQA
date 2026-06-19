# AREQA Memory System 實作計畫 (基於四大頂會論文)

建立日期：2026-06-14
目標：解決目前 AREQA 系統（底層使用 GUM）中「記憶存太多」與「檢索不精準」的問題，並提出具體的單元與整合測試計畫。

---

## 1. 問題描述 (Problem Description)

在長期的教育陪伴場景中，如果我們僅依賴最基本的對話紀錄與 RAG 檢索，系統將面臨三個致命問題：

1. **記憶存太多 (Information Overload & Redundancy)：** 
   若逐字記錄學生的每一次對話與閒聊，資料庫將無限膨脹。這不僅會大幅增加 API 的 Token 成本，還會導致記憶庫充滿過期或衝突的資訊（例如：昨天不會寫 For 迴圈，今天學會了，但兩個記憶同時存在）。
2. **檢索不精準 (Contextual Interference)：** 
   傳統的語義搜尋（如 FAISS/BM25）只看字面相似度。當學生在不同天問了關於「參數」的問題，系統會把所有包含「參數」的歷史紀錄全部撈出來，導致上下文污染 (Context Pollution)。
3. **缺乏自主性 (Passive Retrieval)：** 
   目前的系統架構傾向於「只要使用者說話，就把前三筆記憶硬塞進 Prompt 裡」。這剝奪了大語言模型自主判斷「我需不需要翻找記憶」的能力，浪費了寶貴的 Context Window。

---

## 2. 解決方案 (Solutions)

我們將融合四篇頂尖學術論文的機制來解決上述問題：

### [OK] 解方 A：記憶反思與動態演化 (Reflection & Evolution)
* **針對問題：** 記憶存太多、充滿過期衝突資訊。
* **實作機制：** 
  1. **反思壓縮：** 設定背景排程（如每 20 輪對話），讓 LLM 將近期的短期對話萃取成高階的「核心事實 (Insights)」，並封存原始對話。
  2. **動態更新與修剪：** 當新記憶（學會迴圈）寫入時，系統會先找出最相關的舊記憶（不會寫迴圈），並讓 LLM 決定是否要 **更新 (Update)** 或 **覆蓋/修剪 (Prune)** 該舊記憶，確保知識圖譜持續進化。
* **參考論文與開源碼：**
  * *Generative Agents: Interactive Simulacra of Human Behavior* (Stanford, 2023)
    * GitHub: [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents)
    * docs/paper/memory_work/Generative Agents_Interactive Simulacra of Human Behavior.pdf
    * misc/generative_agents/generative_agents
  * *A-MEM: Agentic Memory for LLM Agents* (Rutgers, 2025)
    * GitHub: [WujiangXu/A-mem-sys](https://github.com/WujiangXu/A-mem-sys)
    * docs/paper/memory_work/A-MEM_Agentic Memory for LLM Agents.pdf
    * misc/A-MEM/A-mem-sys

### [OK] 解方 B：情境意圖過濾 (Contextual Intent Filtering)
* **針對問題：** 檢索不精準、字面相似導致撈錯記憶。
* **實作機制：** 
  1. 在記憶寫入時，強制 LLM 以 JSON 格式標註三個 Metadata：`Thematic Scope (主題範圍)`、`Event Type (事件類型)`、`Key Entity (關鍵實體)`。
  2. 檢索時，先預測使用者問題的「意圖標籤」，然後進行 **Label Density Ranking (標籤重疊度排序)**。只有標籤完全符合的記憶，才進入下一步的語義算分（搭配 GUM 原有的 Decay 與 Confidence 演算法）。
* **參考論文與開源碼：**
  * *Grounding Agent Memory in Contextual Intent (STITCH)* (UIUC/Stanford, 2026)
    * 專案網站: [contextual-intent.github.io](https://contextual-intent.github.io/)
    * misc/STITCH/contextual-intent

### 解方 C：代理式工具調用 (Agentic Tool-use Retrieval)
* **針對問題：** 如何靈活的存取記憶、缺乏自主性、Token 浪費。
* **實作機制：** 
  不再強制硬塞記憶。我們將檢索功能包裝成 Function Calling（例如 `search_long_term_memory(query)`）。LLM 就像作業系統在調度虛擬記憶體 (Virtual Memory) 一樣，只有在覺得自己缺乏使用者背景知識時，才會主動發起檢索。
* **參考論文與開源碼：**
  * *MemGPT: Towards LLMs as Operating Systems* (UC Berkeley, 2024)
    * GitHub: [cpacker/MemGPT](https://github.com/cpacker/MemGPT) 或 [research.memgpt.ai](https://research.memgpt.ai)
    * misc/letta_MemGPT/MemGPT

解方c補充 :



---

## 3. 單元測試與整合測試計畫 (Testing Plan)

遵循 Test-Driven Development (TDD) 與本專案的測試規範，實作前應先建立以下測試案例：

### 3.1 單元測試 (Unit Tests)

1. **`test_memory_evolution_prune` (A-MEM 演化測試)**
   * **情境：** 資料庫中已存在 `{"text": "學生對 Python 閉包不熟", "confidence": 9}`。現在寫入新筆記 `{"text": "學生已完全掌握 Python 閉包的用法", "confidence": 10}`。
   * **斷言 (Assert)：** 舊記憶應被標記為 `archived` 或被合併，不再出現於 active 查詢結果中。
2. **`test_contextual_intent_labeling` (STITCH 意圖萃取測試)**
   * **情境：** 輸入一段模糊的對話：「那我昨天的作業該怎麼改？」
   * **斷言 (Assert)：** 萃取函數應回傳正確的 JSON 標籤，例如 `Thematic Scope` 必須成功指向前幾輪對話建立的 `Homework_Python_List` 主題。
3. **`test_gum_decay_calculation` (GUM 算分回歸測試)**
   * **情境：** 載入 `db_utils.py`。建立一個 30 天前的記憶，且 `decay = 1.0`。
   * **斷言 (Assert)：** 確認 `math.exp(gamma)` 的分數相較於剛建立的記憶有顯著的指數型下降，確保衰減公式運作正常。

### 3.2 整合測試 (Integration Tests)

1. **`test_long_horizon_multi_hop_retrieval` (長文本多步推論測試)**
   * **情境：** 模擬 5 個 Sessions 的對話。Session 1 提到學生喜歡天文學；Session 2~4 穿插完全無關的數學解題；Session 5 學生問：「所以用我最喜歡的那個學科來舉例，這題該怎麼解？」
   * **斷言 (Assert)：** 系統（結合 MemGPT 的工具調用與 STITCH 的意圖過濾）必須精準調出 Session 1 的天文學記憶，並結合 Session 5 的數學知識，給出以星球軌道為例的正確回答。
2. **`test_proactive_scaffolding_trigger` (主動陪伴 UI 觸發測試)**
   * **情境：** 模擬使用者連續 3 次送出包含錯誤語法的 Python 程式碼，且系統的認知診斷判定熟練度持續下降。
   * **斷言 (Assert)：** 系統應主動拋出 Server-Sent Event (SSE)，觸發前端的 `proactive_hint`（Summary-Preview UI），確保鷹架輔助能夠在不打擾使用者的情況下適時介入。
