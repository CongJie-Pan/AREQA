# Agentic PELICAN Agent Executor 人工測試劇本：理想前端互動驗收

本劇本用來驗收 `Agentic_PELICAN_Agent_Executor_Implementation_plan.md` 完成後，使用者從前端看到的系統互動是否符合 agent-executor methodology。重點不是人工檢查後端資料結構，而是確認前端能清楚呈現：每個 methodology stage 由對應 agent 產生 bounded proposal，Learning System Pipeline 採用後，才推進 skill、diagnosis、state、strategy 與 tutor response。本劇本刻意使用「中國春秋時期歷史」作為主測案例，避免只驗證既有深度學習 catalog demo 或固定 hardcode 輸出。

## 測試前置條件

- 使用完成 agent-executor implementation plan 全部 phases 的版本。
- 使用乾淨 learner session，建議 learner id：

```text
manual_agentic_pelican_20260723_agent_executor
```

- 使用 LLM-based / Agentic mode。若模型服務不可用，前端必須清楚顯示 fallback 狀態；fallback run 不可宣稱通過完整 agentic executor 驗收。
- 啟動服務：

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pelican_mvp --port 8000 --pelican-log debug --pelican-log-channels api,intake,skill,diagnosis,edf,memory,tutor,methodology
```

- 開啟瀏覽器：

```text
http://127.0.0.1:8000/?learner_id=manual_agentic_pelican_20260723_agent_executor
```

- 若頁面已有紀錄，先按 `Reset`。
- 建議測試視窗至少執行一次桌面寬度與一次 mobile viewport `390×844`。

## 第一幕：初始頁面顯示 agent-executor trace 容器

### 輸入

測試者開啟頁面，切換到 LLM-based mode，按 `Reset`，等待系統回到 onboarding。

### 預期輸出

- phase 顯示為 `onboarding`。
- Chat 區顯示系統詢問學習主題，例如「你想學什麼？」。
- Methodology panel 顯示六個核心 stage：
  - Goal Framing
  - Skill Construction
  - Cognitive Diagnosis
  - Knowledge State Update
  - EDF Strategy Selection
  - Tutor Response
- 前端可見 agent executor trace 區塊，初始可為空狀態，例如 `No agent executor proposals yet`。
- 不應顯示舊 session 的 completed stage、舊 agent proposal 或舊 learner progress。

### 後端查核

- 不做人工後端查核。
- session reset、legacy state migration、proposal reset 與 event ordering 由 implementation plan 的 Phase 1 / Phase 5 gate 與 integration tests 驗證。

### 成功標準

Reset 後前端是乾淨 onboarding 狀態，且可見後續用來驗收 agent executor proposal 的 UI 區塊。

## 第二幕：Intake Agent 解讀學習主題

### 輸入

在 chat input 輸入：

```text
中國春秋時期歷史
```

按 `送出`。

### 預期輸出

- 系統不直接進入診斷題，而是詢問學習目標、學習角度或偏好。
- Agent Executor Trace 顯示 `Intake Agent`。
- `Intake Agent` trace 應顯示安全摘要，例如：
  - artifact type: `topic_interpretation`
  - validation status: `accepted`
  - output/ref: scoped topic 或 goal framing reference
- Goal Framing stage 顯示目前 cycle 有進展。
- 前端不應顯示 raw prompt、raw model output、API key、provider response body 或完整內部 JSON。

### 後端查核

- 不做人工後端查核。
- Intake Agent proposal contract、safe metadata、turn/cycle correlation 由 Phase 3 / Phase 5 gate 與 integration tests 驗證。

### 成功標準

使用者輸入 broad topic 後，前端能看出是 `Intake Agent` 完成 topic interpretation，而不是 engine 直接硬切下一步。

## 第三幕：Intake Agent 解讀學習目標

### 輸入

```text
想理解春秋時期的政治秩序和諸侯爭霸脈絡
```

### 預期輸出

- 系統繼續詢問目前程度、背景或先備知識。
- Agent Executor Trace 新增或更新 `Intake Agent` 的 `goal_interpretation` proposal。
- proposal 顯示 validation status 為 `accepted`。
- phase 仍顯示 `onboarding`。
- Knowledge tree / progress 不應顯示 mastery 更新，因為尚未進入 diagnosis。

### 後端查核

- 不做人工後端查核。
- goal interpretation、semantic classifier fallback 與 profile mutation ordering 由 Phase 3 gate 與 integration tests 驗證。

### 成功標準

前端明確呈現目標校準由 Intake Agent proposal 驅動，且尚未誤觸發診斷或掌握狀態。

## 第四幕：Intake Agent 解讀程度後觸發 Skill Agent

### 輸入

```text
只有大概聽過春秋五霸，沒有系統學過
```

### 預期輸出

- phase 從 `onboarding` 進入 `diagnosis`。
- Agent Executor Trace 顯示：
  - `Intake Agent`: `level_interpretation`
  - `Skill Agent`: `skill_generation`
- `Skill Agent` trace 顯示 proposal source，例如 `catalog`、`runtime_cache`、`runtime_generated` 或 `generic:<domain>`。
- 若 source 是 `catalog` 或 `runtime_generated`，validation status 應為 `accepted`。
- 若 source 是 fallback，前端必須顯示 `fallback_used`，不可把 fallback 包裝成正式 runtime generation。
- Skill Artifact Summary 顯示：
  - skill id
  - domain category
  - concept path
  - current diagnostic target
  - teaching moves
- 系統顯示歷史脈絡優先的診斷題，內容應接近「周王室權威下降、分封秩序、諸侯互動、霸主角色、禮制與政治秩序」等基礎概念。
- 不應第一題就問過細的年代背誦、冷僻人物、單一戰役細節、史料版本差異，或直接套用深度學習/程式/數學相關內容。

### 後端查核

- 不做人工後端查核。
- Skill Agent executor、catalog/cache/runtime/fallback ordering、validator 與 compiler 由 Phase 2 gate 與 integration tests 驗證。

### 成功標準

前端可判斷 skill construction 是由 `Skill Agent` 產生 bounded skill proposal，且 proposal 被採用後才出現知識地圖與診斷題。

## 第五幕：Diagnosis Agent 選擇診斷任務

### 輸入

完成第四幕後，不輸入新文字，觀察診斷題與 trace。

### 預期輸出

- Chat 顯示單一歷史基礎診斷題。
- Agent Executor Trace 顯示 `Diagnosis Agent`。
- `Diagnosis Agent` trace 顯示：
  - artifact type: `diagnostic_selection` 或 `diagnostic_task`
  - validation status: `accepted`
  - current node id / diagnostic target safe reference
- Cognitive Diagnosis stage 顯示完成或 active。
- 前端不應顯示 expected answer。

### 後端查核

- 不做人工後端查核。
- diagnostic selection、skill-locked diagnostic、LLM diagnostic fallback 與 answer-leak protection 由 Phase 3 gate 與 integration tests 驗證。

### 成功標準

前端能看出診斷題是由 `Diagnosis Agent` proposal 選出，而不是任意硬寫題目。

## 第六幕：正確回答後顯示 State Agent 與 Policy Agent

### 輸入

若題目語意為「春秋時期為什麼會出現諸侯爭霸」或「周王室權威下降和諸侯秩序的關係」，輸入：

```text
因為周王室控制力下降，諸侯需要在名義上的周禮秩序下競爭主導權
```

若題目不同，輸入與該春秋歷史基礎題相符的簡短正確答案。

### 預期輸出

- Knowledge tree 或 Progress Snapshot 顯示目前歷史基礎節點有正向進展，例如 mastered、partially mastered 或 confidence 提升。
- Agent Executor Trace 依序顯示：
  - `State Agent`: state update proposal
  - `Policy Agent`: strategy recommendation proposal
- State Agent trace 顯示 safe state feedback，例如 current focus、updated mastery map summary 或 node status，不顯示完整 learner answer。
- Policy Agent trace 顯示 selected strategy，例如 confirmation、next diagnostic、focused mini-lesson 或 guided example。
- 系統前往下一個合理歷史概念，例如諸侯爭霸、霸主秩序、尊王攘夷、禮崩樂壞、春秋到戰國的轉變，或顯示下一步 tutor response。

### 後端查核

- 不做人工後端查核。
- state delta proposal、GUM direct evidence、EDF ordering 與 state mutation ownership 由 Phase 3 gate 與 integration tests 驗證。

### 成功標準

正確回答後，前端能看到 evidence → state update → policy recommendation 的 agent proposal chain。

## 第七幕：不知道時觸發 Tutor Agent 鷹架回覆

### 輸入

```text
我不知道
```

### 預期輸出

- 系統不應只說「錯了」，也不應直接跳過。
- Tutor response 應提供較簡單提示、拆解、補前置概念或引導式問題。
- Agent Executor Trace 顯示 `Fast Tutor Agent` 或 `Slow Simulator Agent`。
- Tutor Agent trace 顯示：
  - artifact type: `tutor_proposal`
  - validation status: `accepted` 或明確 `fallback_used`
  - pedagogical move: `scaffold`、`decomposition`、`simplification` 或等價安全摘要
  - final message preview
- Learner progress 不應把「我不知道」顯示為 mastered。

### 後端查核

- 不做人工後端查核。
- unknown signal、remediation-first routing、tutor proposal validation 與 fallback semantics 由 Phase 4 gate 與 integration tests 驗證。

### 成功標準

前端能看出 `unknown` 不是普通錯誤，而是由 Tutor Agent 產生鷹架式 proposal 後形成 final response。

## 第八幕：題目太細時觸發層級重新校準

### 輸入

```text
這太細了，我完全沒有基礎
```

### 預期輸出

- 系統承認目前題目或說明太細，改以更高層直覺、生活比喻或更簡單問題重新引導。
- Agent Executor Trace 顯示 Tutor Agent proposal。
- proposal 的 pedagogical move 應接近：
  - `scope_recalibration`
  - `simplification`
  - `level_recalibration`
- 回覆不應與第七幕 `我不知道` 的鷹架回覆相同。
- 系統不應繼續追問更細的年代背誦、冷僻人物、單一戰役細節、公式、程式碼、參數或實作細節。

### 後端查核

- 不做人工後端查核。
- too_detailed signal、scope mismatch handling、State/Policy/Tutor proposal ordering 由 Phase 3 / Phase 4 gate 與 integration tests 驗證。

### 成功標準

前端能看出 `too_detailed` 會改變策略與 final response，而不是套同一個固定模板。

## 第九幕：Slow Simulator Agent 在重複困難時出現

### 輸入

在同一個概念或 tutor prompt 下，連續輸入兩次困難訊號，例如：

```text
我還是不懂
```

接著輸入：

```text
還是不會，能不能更慢一點？
```

### 預期輸出

- 系統應切換到更慢、更拆解的教學回覆。
- Agent Executor Trace 應顯示 `Slow Simulator Agent`，或明確顯示 slow route 被選中。
- Slow Simulator Agent trace 應包含：
  - reason code，例如 repeated difficulty、fragile state、slow route 或 equivalent
  - validation status
  - bounded final message preview
- 回覆應比 Fast Tutor 更詳細或更分步，但仍只處理目前 focus node。

### 後端查核

- 不做人工後端查核。
- slow route selection、repeated failure detection、Fast/Slow Tutor split 由 Phase 4 gate 與 integration tests 驗證。

### 成功標準

重複困難時，前端能辨識系統不是重複 fast template，而是切到 Slow Simulator Agent route。

## 第十幕：Agent Executor Trace 對齊六階段 methodology

### 輸入

完成第二幕到第九幕後，觀察 methodology panel 與 agent executor trace。

### 預期輸出

- 六個核心 stage 仍只包含：
  - Goal Framing
  - Skill Construction
  - Cognitive Diagnosis
  - Knowledge State Update
  - EDF Strategy Selection
  - Tutor Response
- Agent Executor Trace 至少能看到：
  - Intake Agent
  - Skill Agent
  - Diagnosis Agent
  - State Agent
  - Policy Agent
  - Fast Tutor Agent 或 Slow Simulator Agent
- GUM 可以顯示為 subsystem/supporting event，但不應變成第七個核心 methodology stage。
- 每個 agent row 應顯示 role、artifact type、validation status、safe reason/source/summary。
- 不應只有 agent 名稱，卻沒有 proposal/adoption/fallback 資訊。

### 後端查核

- 不做人工後端查核。
- methodology event ordering、agent proposal adoption、six-stage invariant 由 Phase 3 / Phase 5 gate 與 integration tests 驗證。

### 成功標準

前端能把六階段 pipeline 和 agent proposal layer 對齊展示，而不是只顯示一串聊天訊息。

## 第十一幕：Markdown 匯出可重建 agent executor loop

### 輸入

按下 `匯出對話 MD`。

### 預期輸出

匯出的 Markdown 應包含以下 section 或等價內容：

- Conversation transcript
- Skill Artifact Summary
- Agent Executor Trace
- Methodology Events
- Recent Evidence-to-Response Trace
- Tutor Proposal Trace
- Learner Progress Snapshot

匯出內容應能從前端觀察角度重建：

```text
learner input
→ agent proposal
→ validation/adoption/fallback status
→ methodology stage
→ visible tutor response or progress update
```

匯出內容不應包含 raw prompt、raw model output、API key、provider response body 或 hidden reasoning。

### 後端查核

- 不做人工後端查核。
- Markdown export safe serialization、raw payload exclusion 與 trace completeness 由 Phase 5 gate 與 integration tests 驗證。

### 成功標準

匯出檔能支援人工實驗報告判斷「每個前端輸出是由哪個 agent proposal 被採用後產生」。

## 第十二幕：未知或弱支援領域不偽裝成完整專家 skill

### 輸入

按 `Reset`，重新開始後輸入一個刻意模糊或弱支援的主題，例如：

```text
我想學一個很冷門、你可能不確定分類的交叉領域
```

### 預期輸出

- 系統應要求澄清，或清楚顯示 fallback / generic route。
- Skill Agent trace 不應把 fallback 顯示成 `accepted runtime_generated`。
- 若產生 generic skill，Skill Artifact Summary 必須讓使用者看出這是 broad/generic fallback，不是假裝有完整專家知識地圖。
- 系統不應直接輸出過度自信的完整 domain-specific 知識地圖。

### 後端查核

- 不做人工後端查核。
- unknown domain fail-closed、generic fallback labeling、router behavior 由 Phase 2 gate 與 integration tests 驗證。

### 成功標準

弱支援主題時，前端誠實呈現 clarification 或 fallback，不誤導使用者以為系統已建立高品質專家 skill。

## 第十三幕：Mobile 版仍可完成核心互動

### 輸入

將瀏覽器 viewport 設為 `390×844`，使用新的 learner id 重新執行第二幕到第四幕。

### 預期輸出

- Chat input、送出按鈕、Reset 按鈕都可見且可點擊。
- Methodology stages 可見。
- Skill Artifact Summary 與 Agent Executor Trace 可讀或可捲動查看。
- 不應因 trace panel 增加而遮住聊天輸入框。

### 後端查核

- 不做人工後端查核。
- mobile layout 與 e2e clickability 由 Phase 5 gate 與 Playwright/integration tests 驗證。

### 成功標準

手機尺寸下仍能完成 onboarding 到 diagnosis，且能看到至少 Skill Agent / Diagnosis Agent trace。

## 最終判定

所有幕次都通過時，才可標記為「Agentic PELICAN Agent Executor 前端人工驗收通過」。

若任一幕失敗，請記錄：

- 失敗幕次
- learner id
- exact input/action
- 測試時間
- 畫面截圖
- 當時 phase
- 可見的 methodology stage 狀態
- 可見的 agent executor trace row
- 可見的 tutor response 或 error message
- 是否為 LLM unavailable / fallback run

失敗判定原則：

- 若前端只顯示 agent 名稱，沒有 proposal/adoption/fallback 資訊，視為失敗。
- 若 fallback 被顯示成 accepted runtime generation，視為失敗。
- 若 `unknown`、`too_detailed`、重複困難產生幾乎相同模板回覆，視為失敗。
- 若任一 UI/export 顯示 raw prompt、raw model output、API key、provider response body 或 hidden reasoning，視為失敗。
- 若六個 methodology stages 被 GUM/chat/agent trace 擴充成七個或更多核心 stage，視為失敗。
