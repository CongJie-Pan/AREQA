# Agentic PELICAN 人工測試劇本：paper-aligned 前端輸入輸出驗收

本劇本用來驗收 PELICAN MVP 是否符合 `docs/paper_draft/paper.md` 描述的 agentic tutoring loop。人工測試不接受只靠固定 template 或 rule fallback 產生的「看起來有回覆」；必須能在前端與匯出紀錄中看到：

```text
Goal framing
→ Skill construction
→ Cognitive diagnosis
→ Knowledge-state update
→ EDF/GUM strategy selection
→ Bounded tutor proposal
→ Final tutor response
```

## 測試前置條件

- 使用乾淨 learner session，建議 learner id：`manual_agentic_pelican_20260723`。
- 啟動 agentic/LLM mode；若 LLM 不可用，測試應明確標示為 fallback run，不可宣稱通過 paper-aligned agentic 驗收。
- 啟動 safe debug logger：

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pelican_mvp --port 8000 --pelican-log debug --pelican-log-channels api,skill,diagnosis,edf,memory,tutor,methodology
```

- 開啟：

```text
http://127.0.0.1:8000/?learner_id=manual_agentic_pelican_20260723
```

- 若頁面已有紀錄，先按 `Reset`。

## 不可接受的通過條件

以下任一情況都視為未通過：

- tutor response 多輪重複固定句型，例如每次都導向「我們先停在某概念」。
- 前端只顯示 agent role/status，沒有 skill artifact 或 tutor proposal trace。
- `unknown` 與 `too_detailed` 產生幾乎相同的教學回覆。
- 匯出檔無法追蹤 evidence → state → EDF/GUM → proposal → final response。
- log、proposal 或 UI 顯示 raw prompt、raw model output、API key、provider response body，或完整 learner answer payload。

## Act 1：初始頁面與乾淨狀態

### 輸入

開啟頁面，切換到 LLM-based mode，按 `Reset`。

### 預期輸出

- phase 顯示 `onboarding`。
- 六個核心 methodology stages 存在，但不應殘留前一輪 completed 狀態。
- Skill Artifact Summary、Tutor Proposal Trace 可以是空狀態，但容器應可見或有明確空訊息。

### 成功標準

頁面乾淨，且後續驗收會以 agentic trace 為通過標準。

## Act 2：輸入 broad topic 後進入 goal framing

### 輸入

```text
深度學習
```

### 預期輸出

- 系統詢問學習目標或學習角度，不直接跳進 MLP、activation、參數量等細節。
- Goal Framing stage 有目前 cycle 的進展。
- 不應出現 raw backend JSON、raw prompt、raw model output。

### 成功標準

系統先校準目標，而不是以固定深度學習模板直接開題。

## Act 3：輸入學習目標後繼續程度校準

### 輸入

```text
想理解原理
```

### 預期輸出

- 系統詢問目前基礎或熟悉程度。
- 尚未顯示 mastery 更新。
- Goal Framing 仍屬於目前 cycle。

### 成功標準

前端仍在 onboarding calibration，不誤觸發診斷或掌握狀態。

## Act 4：輸入初學程度後產生 skill artifact 與 foundation-first 診斷

### 輸入

```text
完全沒有基礎
```

### 預期輸出

- phase 進入 `diagnosis`。
- 顯示深度學習 foundation-first 診斷題，主軸應接近「模型、預測、目標、誤差、資料表示」。
- Skill Artifact Summary 顯示安全摘要，例如 skill id、domain、concept path、current diagnostic target、teaching moves。
- Skill Construction 與 Cognitive Diagnosis stage 顯示目前 cycle 進展。

### 成功標準

可以從畫面判斷系統真的產生/編譯 skill，而不是硬寫一題診斷題。

## Act 5：正確回答第一題後看到狀態更新與 proposal trace

### 輸入

若題目語意為「預測與目標的差距/錯誤衡量」，輸入：

```text
用來衡量預測與目標之間的差距
```

若題目不同，輸入與該 foundation 題相符的簡短正確答案。

### 預期輸出

- Knowledge tree 或 progress panel 顯示目前 foundation node 有正向進展。
- 系統前往下一個合理 foundation node，例如資料表示、函數轉換或相近概念。
- Agent Proposals / Tutor Proposal Trace 顯示 safe proposal metadata，包括 role、validation status、strategy/reason code、node id。
- Final tutor response 與 proposal trace 有可理解的連結。

### 成功標準

正確回答會觸發 state update、EDF/GUM 更新與 tutor proposal，而不是只把下一題固定印出。

## Act 6：回答不知道後看到鷹架式 agentic tutor response

### 輸入

```text
我不知道
```

### 預期輸出

- 回覆應給出更簡單提示、拆解、補前置概念或引導式問題。
- Tutor Proposal Trace 應顯示 strategy 接近 scaffold/decompose/simplify。
- learner progress 不應把這次回答顯示為 mastered。
- 回覆不應與 Act 7 的 too-detailed 回覆相同。

### 成功標準

`unknown` 被視為學習證據與教學策略輸入，產生鷹架式 proposal 與 final response。

## Act 7：題目太細時重新校準難度

### 輸入

```text
這太細了，我完全沒有基礎
```

### 預期輸出

- 系統承認題目層級太細，降低抽象層級或接回更高層直覺。
- Tutor Proposal Trace 應顯示 strategy/reason 接近 simplification、scope recalibration 或 level recalibration。
- 不應繼續追問更細的公式、程式或實作細節。
- 這輪 final response 不應重複 Act 6 的鷹架模板。

### 成功標準

`too_detailed` 會改變教學策略與 final response，而不是被視為一般錯誤答案。

## Act 8：methodology graph 維持六個核心 stage

### 輸入

完成 Act 2 到 Act 7 後，觀察 methodology panel。

### 預期輸出

- 核心 stage 僅包含：
  - Goal Framing
  - Skill Construction
  - Cognitive Diagnosis
  - Knowledge State Update
  - EDF Strategy Selection
  - Tutor Response
- GUM 顯示為 subsystem/supporting event，不可成為第七個核心 stage。
- stage 狀態屬於目前 cycle，不混入 reset 前資料。

### 成功標準

前端 presentation 與 paper 的六階段 pipeline 一致。

## Act 9：匯出 Markdown 驗證 paper-aligned trace

### 輸入

按 `匯出對話 MD`。

### 預期輸出

Markdown 應包含：

- Session metadata。
- Conversation transcript。
- Skill Artifact Summary。
- Agent Executor Trace。
- Recent Evidence-to-Response Trace。
- Methodology Events。
- Agent/Tutor Proposals。
- Learner Progress Snapshot。

### 成功標準

匯出檔能支援實驗報告判斷「為何最後 tutor response 會這樣產生」。

## Act 10：safe logger 驗證

### 輸入

觀察啟動服務的 terminal log。

### 預期輸出

- 應看到 safe event，例如：
  - `pelican_agent_proposal_recorded`
  - `pelican_tutor_proposal_generated`
  - `pelican_tutor_proposal_validated`
  - `pelican_methodology_event_recorded`
- 不應看到 raw prompt、raw model output、API key、provider body 或完整 learner answer。

### 成功標準

debug logger 足以支援後續 debug，但不破壞 privacy boundary。

## 最終驗收結論

只有在以下條件全部成立時，才可標記為通過：

- 前端對話體驗不是固定 template baseline。
- skill artifact 與 tutor proposal trace 都能被使用者觀察。
- Agent Executor Trace 可看出每個 stage 的 input ref、proposal artifact、validation status 與 adopted output/effect。
- `correct`、`unknown`、`too_detailed` 導致不同的 state/strategy/final response。
- Markdown export 可以重建 evidence → state → EDF/GUM → proposal → response。
- logs 與 UI 都維持 safe metadata boundary。
