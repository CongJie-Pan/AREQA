# AREQA 系統重構計畫：Multi-Agent 架構遷移 (Implementation Plan)

## 1. 背景與動機 (Background & Motivation)

目前 AREQA 系統的核心大腦（位於 `orchestration_service.py`）採用的是**「靜態管線 (Static Pipeline)」**架構。當收到使用者訊息時，系統會強制依序執行固定的步驟：意圖預測 -> HyDE 擴寫 -> RAG 檢索 -> 狀態評估 (EDF) -> Prompt 組裝與產出。

這種架構存在以下痛點：
1. **缺乏彈性**：無論使用者是問深入的知識問題，還是單純的「早安」閒聊，系統都必須跑完繁重的流程，導致延遲時間 (Latency) 不必要地增加。
2. **推理能力受限**：面對複雜的跨主題問題，靜態管線只能進行「單次檢索」。系統無法做到「檢索 A -> 閱讀結果 -> 發現需要更多資訊 -> 檢索 B」的深度推理。
3. **功能擴展困難**：每增加一項新功能（如檢索特定聯網資料、發送信件給老師），都需要修改核心管線的非同步程式碼，耦合度過高。

受到 `misc/agent_mvp` 的啟發，我們計畫將核心管線升級為 **ReAct (Reasoning and Acting) Agent 框架**，並走向**雙智能體 (Multi-Agent)** 協作模式。

---

## 2. 目標架構 (Target Architecture)

重構後，系統將主要由兩個獨立且非同步運作的 Agent 構成：

### 2.1 前台導師智能體 (Tutor Agent)
* **職責**：專注於直接面對使用者，提供具備溫度的教學引導、情緒陪伴與知識解答。
* **運作模式**：透過 `While` 迴圈 (Agent Loop) 自主決策。
* **配備工具 (Tools/Skills)**：
  - `search_rag(query: str)`: 檢索本地教材庫 (FAISS/BM25)。
  - `search_web(query: str)`: 呼叫 Perplexity API 進行即時聯網搜尋。
  - `query_long_term_memory()`: 詢問使用者的過去歷史與偏好。
  - `evaluate_pedagogical_state(context: str)`: 呼叫 EDF 狀態機評估當前最適合的教學策略。

### 2.2 背景記憶總管 (Memory Agent / GUM)
* **職責**：在背景默默監聽對話（透過 Observation Queue），負責萃取長短期記憶、建立知識圖譜，並更新至 SQLite 與 MemoryStore。
* **運作模式**：非同步批次處理 (Batch Processing)，不阻礙前台回應速度。

---

## 3. 實作階段規劃 (Phased Implementation Steps)

為了確保在重構過程中系統依然能穩定運作，我們將採取「逐步替換、平滑過渡」的策略。

### Phase 1: 基礎建設與工具封裝 (Tool/Skill Encapsulation)
**目標**：將現有的邏輯模塊打包成標準的 Python Tools。
1. 將 `_node_rag_retrieval` 邏輯抽取為獨立函式 `def tool_search_rag(query: str) -> str`。
2. 將 `_node_web_search` 抽取為 `def tool_web_search(query: str) -> str`。
3. 將 EDF 評估邏輯抽取為 `def tool_evaluate_learner_state(chat_history: str) -> str`。
4. 建立類似 `agent_mvp/core/tools.py` 的 `ToolRegistry`，確保能自動解析上述函式的 Type Hints 與 Docstrings 轉為 LLM 可讀的 JSON Schema。

### Phase 2: 核心 Agent Loop 實作與串接 (Agent Loop Integration)
**目標**：在 `orchestration_service.py` 引入 ReAct 迴圈。
1. 將 `misc/agent_mvp/core/agent.py` 的核心邏輯引入專案，建立 `TutorAgent` 類別。
2. 攔截現有的 API Router，將使用者的輸入交給 `TutorAgent.run_conversation()`。
3. 實作中介軟體 (Middleware)：在 Agent 呼叫 Tool 時（例如正在搜尋時），將狀態（"正在檢索資料..."）透過 Server-Sent Events (SSE) 即時串流給前端的 `<ThinkingPanel>` 顯示，提升使用者體驗。

### Phase 3: 多智能體協同與記憶分離 (Multi-Agent & Memory Decoupling)
**目標**：完善背景 Memory Agent，讓前台 Agent 變得更輕量。
1. 確保 `gum_integration.py` 獨立於核心對話流之外，僅透過 Event 或是 Queue 接收使用者的 Input 與 Agent 的 Output。
2. 讓 Tutor Agent 具備 `query_memory(topic: str)` 工具，當 Agent 覺得需要回顧使用者歷史時，主動呼叫此工具取得 GUM 提供的摘要。

### Phase 4: 優化與清理 (Optimization & Cleanup)
**目標**：移除舊代碼，提升穩定性。
1. 逐步廢棄原本 `orchestration_service.py` 內冗長的 `_node_xxx` 管線函式。
2. 針對 Agent 的 Prompt 進行調優，確保它不會過度依賴 Tools（例如簡單問候時能直接 `return` 結束迴圈）。
3. 加入 Retry 與 Error Handling 機制，防止 LLM 幻覺產生不存在的工具呼叫。

---

## 4. 預期效益 (Expected Outcomes)

1. **反應速度提升**：對於日常對話，Agent 可以跳過檢索直接回應，大幅降低冷啟動與處理時間。
2. **更高階的教學互動**：Agent 能根據使用者的追問，動態決定要查閱書籍的哪一章，或是上網比對最新資料，不再是一招半式打天下。
3. **擴充成本極低**：未來若要增加「寄信給教授 (Compeer)」功能，只需寫一個 `send_email` 的 Python 函式並掛載到 `ToolRegistry` 即可，核心架構完全無需更動。
