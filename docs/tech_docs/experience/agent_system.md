綜合業界在建構 Agent 化系統時的實戰經驗與架構演進，目前將系統「Agent 化」的底層邏輯與最常遇到的坑位/盲點，可以歸納為以下幾個核心維度：

### 1. 邊界與控制權的盲點（最致命的坑位）
**底層邏輯：** Agent 的本質是「機率引擎」，它擅長模糊推論與動態規劃，但不擅長遵循嚴格的業務流程。
**坑位/盲點：**
- **過度代理化 (Over-Agentification)**：開發者常誤以為「Agent 很聰明，甚麼都可以交給它判斷」。這會導致原本簡單且必須 100% 發生的系統剛需（如 UI 渲染、寫入 Log、合規檢查）交由機率模型決策，進而引發系統行為不可預期、前端崩潰 。
- **解法：確定性外殼 (Deterministic Wrapper)**：Agent 只負責「動態思考與提案」，而系統的「執行與驗證」必須由傳統的程式碼層（Pipeline/Wrapper）強制攔截與控制。凡是關乎業務邏輯底線的環節，絕不能依賴 Agent 自主決定。

### 2. 多智能體 (Multi-Agent) 的協作與狀態盲點
**底層邏輯：** 當系統從單一 Agent 走向 Multi-Agent，核心挑戰不再是「模型多聰明」，而是「狀態與上下文如何交接」。
**坑位/盲點：**
- **無窮迴圈與狀態遺失**：若未設計好中斷機制，兩個 Agent 可能會互相呼叫形成死迴圈。同時，如果對話輪數過多，Context 溢出會導致 Agent「失憶」，忘記最初的任務目標 。
- **缺乏強制結構化約束**：如果 Agent 使用工具（如聯網搜尋、資料庫檢索）後，取得的資料是未經結構化處理的「純文字裸奔」，LLM 極易產生幻覺或忽略資料來源 。
- **解法：主控層架構與護欄**：採用「主控 Agent + 執行 Agent」的三層架構，並強制在程式碼層將工具獲取的資料包裝成特定的標籤（如 `<context>`），以強硬約束 LLM 的注意力與輸出格式 。

### 3. 可觀測性 (Observability) 與除錯盲點
**底層邏輯：** 傳統程式碼出錯會拋出明確的 Exception，但 Agent 出錯時通常是「一本正經地胡說八道」或「默默跳過步驟」。
**坑位/盲點：**
- **缺乏追蹤的黑箱化**：如果開發者只看 Agent 最終的文字輸出，一旦發生邏輯錯誤，根本無從得知是「Prompt 寫不好」、「呼叫工具失敗」還是「模型推理錯亂」 。
- **解法：全鏈路日誌與分步驗證**：必須建立包含「決策路徑 (Reasoning)」、「工具調用 (Tool Calls)」、「最終輸出」的三層監控日誌。複雜任務必須拆解為獨立可驗證的 Phase，不能讓 Agent 一次性處理到底，且必須提供中間檢查點讓人類可以介入 。

### 4. 工具負載與注意力分散 (Tool Overload)
* **底層邏輯**：大語言模型（LLM）的注意力機制有其極限。給予越多工具，模型要在「選擇哪一個工具」與「如何組合工具」上消耗的推理資源就越多，出錯機率呈指數上升。
* **坑位盲點**：工程師常患上「火力不足恐懼症」，初期就給 Agent 塞入十幾種工具（例如同時給予靜態分析、LSP、Test Runner 等） 。這會導致 Agent 頻繁選錯工具，或是在工具選擇中產生幻覺。
* **解決方案**：限制單一 Agent 的工具數量（經驗法則是不要超過 3 個）。如果任務確實需要多種工具，應該將其拆分為「專職的 Micro-Agents（微型智能體）」，例如將原本的「萬能助手」拆分成「規劃 Agent」、「安全檢查 Agent」與「排版 Agent」 。

### 5. 狀態共享與隱性依賴 (Implicit State Sharing)
* **底層邏輯**：隨著 Agent 流程圖（Graph）變得龐大，不同節點（Nodes）之間的狀態傳遞與覆蓋會變得極度複雜。
* **坑位盲點**：在開發 Multi-Agent 系統時，開發者常依賴框架預設的「全域狀態共享」，導致節點的責任邊界模糊。系統能跑起來，但沒有人知道「為什麼 Agent 選擇了這條路徑」或「哪個節點不小心覆蓋了關鍵變數」。當多個工程師共同維護，或系統需要長時間運行時，這將引發災難性的「靜默失敗（Silent Failures）」 。
* **解決方案**：採用「契約驅動（Contract-driven）」設計  。強制要求每個 Agent 節點明確宣告其輸入與輸出（I/O），並在 Supervisor 層級建立嚴格的路由約束與狀態驗證。

### 6. 缺乏強制推論的黑箱輸出 (Missing Explicit Reasoning)
* **底層邏輯**：LLM 如果沒有先「思考（Chain of Thought）」，直接給出最終答案，其產生幻覺與誤判的機率極高。
* **坑位盲點**：開發 Agent 時，只要求它回傳最終的結果字串，導致開發者無法審核其判斷邏輯，也無法建立有效的回饋迴圈（Feedback Loop） 。
* **解決方案**：強制要求 Agent 在輸出最終結果前，必須先回傳「結構化推理過程（如 JSON 格式）」。例如要求它列出 `confidence_score`、`reasoning_steps`，這樣開發者就能藉此快速識別並封鎖產生錯誤判斷的思維模式。

### 7. 記憶機制的過早複雜化 (Premature Memory Complexity)
* **底層邏輯**：無限制的長期記憶（Long-term Memory）不僅會消耗大量 Token，還會帶來「上下文腐敗（Context Rot）」的問題，讓模型被過時或無關的資訊干擾。
* **坑位盲點**：許多專案一開始就試圖打造複雜的長期記憶系統與向量資料庫，卻忽略了基礎的「精確檢索」。
* **解決方案**：在初期，專注於「精確的上下文檢索（RAG）」而非「讓 Agent 記住所有事」。為避免 Context Rot，與其將所有記憶塞給一個巨大的 Agent，不如透過小型的微型智能體來處理各自所需的最小上下文 。

### 8. 終止條件的缺失 (Missing Stop Conditions)
* **底層邏輯**：Agentic 系統具備自我迭代的特性，若未設定邊界，它會無止盡地嘗試解決問題。
* **坑位盲點**：未設立明確的退出機制（Exit Criteria），導致 Agent 在遇到無法解決的任務或工具失效時，陷入死迴圈（Endless Loops），最終耗盡 API 額度或運算資源。
* **解決方案**：在系統外殼（Wrapper）或 Supervisor 層級建立防護網（Guardrails），例如限制最大迭代次數（Max Iterations），或在連續失敗兩次後強制降級（Fallback）回傳統的回覆模式。

## Turn Interpretation Ownership

問題不是 multi-agent 本身，而是「同一輪 user turn 有多個元件都在重新解讀意圖」，造成 ownership diffusion。

目前系統若同時讓下列元件各自判斷 learner intent，就會形成架構壞味道：

- Learning Manager / Orchestrator
- Deterministic pipeline validator
- Legacy rule-based DialogueActAgent

現代 agentic system 應遵守 single-owner turn interpretation 原則：

- 只能有一個 owner 負責解讀 user turn。
- 其他元件只能根據這個 owner 的解讀結果執行、驗證或補局部欄位。
- Pipeline validator 的責任是驗證安全性、狀態轉移與 policy，不應重新決定 learner intent。
- DialogueActAgent 只能作為 bounded executor 或 fallback classifier，不應在 Learning Manager 已有有效解讀時重新搶奪回合解讀權。

對 PELICAN 來說，Learning Manager / Orchestrator 應是 user turn interpretation 的 owner；pipeline 與 legacy agents 應退為 validator、executor 或 compatibility fallback。
