# Agentic PELICAN 人工測試劇本：前端輸入輸出驗收

本劇本用來驗收依照 `docs/implemenation_plan/Agentic_PELICAN_Methods_Blueprint_Implementation_plan.md` 完成實作後，前端使用者看到的學習流程是否符合預期。人工驗證只檢查畫面上的輸入與輸出是否 match；後端狀態、事件順序、proposal validation、schema migration、privacy 邊界與 smoke/integration checks，應由 implementation plan 內各 phase 的 gate 與自動測試負責。

## 測試前置條件

- 使用已完成 revised implementation plan 的版本。
- 使用乾淨 learner session，建議 learner id 使用 `manual_agentic_pelican_20260723`。
- 啟動 rule mode，避免 LLM nondeterminism 影響人工驗收。
- 啟動服務：

```bash
cd /workspaces/AREQA/misc/PELICAN_mvp
python -m pelican_mvp --port 8000
```

- 開啟瀏覽器頁面：

```text
http://127.0.0.1:8000
```

- 若頁面已有舊紀錄，先按 `Reset`。
- 後端預期結果不在本人工劇本內手動查核；請以 implementation plan 的 phase gate、integration test、smoke test 驗證。

## 第一幕：初始頁面與乾淨狀態

### 輸入

測試者開啟頁面，選擇 rule mode，按下 `Reset`，等待 1 秒。

### 預期輸出

- 畫面顯示聊天介面。
- phase 顯示為 `onboarding`。
- 老的聊天內容、舊的 methodology stage 狀態、舊 agent proposal、舊 learner progress 不應殘留成已完成狀態。
- 若有 methodology panel，六個核心 stage 應存在但尚未全部顯示 completed。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 1 gate 檢查 session reset、turn/cycle ID、schema migration 與 resume 不重複事件。

### 成功標準

Reset 後，前端呈現乾淨 onboarding 狀態，且沒有上一輪學習流程殘留成目前進度。

## 第二幕：輸入學習主題後進入目標校準

### 輸入

在聊天輸入框輸入：

```text
深度學習
```

按送出。

### 預期輸出

- 系統不應直接跳到很細的 MLP、參數、程式實作題。
- 系統應詢問學習目標或學習方向，例如概念理解、實作、小專案、考試面試等。
- phase 應仍然顯示 `onboarding`。
- 若 methodology panel 已實作，Goal Framing 應顯示目前已有進展。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 2、Phase 4 gate 檢查 Goal Framing event、turn/cycle correlation 與 safe metadata。

### 成功標準

使用者輸入 broad topic 後，前端先進行校準，不直接丟出進階診斷題。

## 第三幕：輸入學習目標後繼續程度校準

### 輸入

在聊天輸入框輸入：

```text
想理解原理
```

按送出。

### 預期輸出

- 系統應繼續詢問目前基礎或熟悉程度。
- phase 應仍然顯示 `onboarding`。
- 畫面不應出現診斷結果或 mastery 更新，因為尚未開始診斷。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 2 gate 檢查 learner profile calibration 與 progress 尚未誤判 mastery。

### 成功標準

前端顯示的是程度校準問題，而不是直接進入診斷或教學回覆。

## 第四幕：輸入初學程度後產生基礎診斷

### 輸入

在聊天輸入框輸入：

```text
完全沒有基礎
```

按送出。

### 預期輸出

- phase 應變成 `diagnosis`。
- 畫面應顯示深度學習相關的 foundation-first 診斷題。
- 診斷題應偏向「模型、預測、目標、誤差」這類基礎概念。
- 不應第一題就問 MLP 實作、activation function 細節、參數量計算或程式碼。
- knowledge tree 或 progress panel 應顯示深度學習的基礎學習路徑。
- 若 methodology panel 已實作，Skill Construction 與 Cognitive Diagnosis 應顯示目前進展。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 2、Phase 4、Phase 5 gate 檢查 generated plan、foundation-first route、methodology events 與 progress snapshot。

### 成功標準

完成 onboarding 後，前端顯示的是基礎診斷題，而且學習路徑看起來符合初學者的深度學習入門順序。

## 第五幕：正確回答第一題後看到掌握與下一步

### 輸入

若畫面問題為「如果一個模型做出預測後，我們想知道它離目標有多遠，為什麼需要一個錯誤衡量？」或語意相同的 foundation 題，輸入：

```text
用來衡量預測與目標之間的差距
```

若畫面問題文字不同，但仍是 foundation 題，請輸入與題目相符的簡短正確答案。

### 預期輸出

- 系統應判定回答正確或以正向方式確認理解。
- knowledge tree 或 learner progress 應顯示目前 foundation node 已掌握、部分掌握，或有明確正向進展。
- 系統應前往下一個合理的深度學習基礎概念，或進入 tutor response 說明下一步。
- 若 methodology panel 已實作，Knowledge State Update、EDF Strategy Selection、Tutor Response 應在目前 cycle 顯示進展。
- 畫面不應顯示 raw backend JSON、raw prompt、raw model output。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 2、Phase 3、Phase 4 gate 檢查 state update、EDF ordering、agent proposal before mutation 與 current-cycle event ledger。

### 成功標準

正確回答 foundation 題後，前端立即反映學習進展，並給出合理下一步。

## 第六幕：回答不知道後看到鷹架式回覆

### 輸入

在下一個診斷題或 tutor prompt 出現後，輸入：

```text
我不知道
```

按送出。

### 預期輸出

- 系統不應只說錯誤或直接跳過。
- 系統應給出較簡單的提示、拆解、補前置概念，或用更高層直覺重新說明。
- EDF 或教學策略區塊若有顯示，應偏向 scaffold、decompose、simplify 或類似策略。
- learner progress 不應把這次回答誤顯示成掌握。
- 若 GUM subsystem 區塊已實作，可以顯示有學習記憶或 evidence 更新，但不應把 GUM 當成第七個核心 pipeline stage。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 2、Phase 4 gate 檢查 GUM evidence、EDF policy、strategy context 與 GUM subsystem event type。

### 成功標準

使用者表示不知道時，前端顯示的是補救式教學回覆，而不是無關跳題或錯誤懲罰。

## 第七幕：題目太細時重新校準難度

### 輸入

在診斷題或 tutor prompt 出現後，輸入：

```text
這太細了，我完全沒有基礎
```

按送出。

### 預期輸出

- 系統應承認目前題目太細或需要降低抽象層級。
- 系統應回到更基礎的說明、重新校準程度，或提供更簡單的問題。
- 畫面不應繼續追問更細的實作或公式細節。
- learner progress 應維持合理，不應因這句話被顯示成已掌握該概念。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 2、Phase 4 gate 檢查 response classification、EDF/GUM current-turn ordering 與 strategy selection。

### 成功標準

前端能從「太細」訊號調整教學難度，回到初學者可理解的路徑。

## 第八幕：目前 cycle 的 methodology graph 顯示正確

### 輸入

完成第二幕到第七幕後，不再輸入文字，觀察 methodology panel。

### 預期輸出

- 前端只應把以下六項顯示為核心 methodology stages：
  - Goal Framing
  - Skill Construction
  - Cognitive Diagnosis
  - Knowledge State Update
  - EDF Strategy Selection
  - Tutor Response
- GUM 可以顯示為 subsystem 或 supporting event，但不應顯示成第七個核心 stage。
- Chat / learner interaction 可以顯示為 interaction 或 loop，但不應顯示成第七或第八個核心 stage。
- stage 狀態應看起來屬於目前學習 cycle，不應混入 reset 前或上一輪 session 的完成狀態。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 4、Phase 5 gate 檢查 six-stage event ledger、current_cycle_id filtering 與 stale UI prevention。

### 成功標準

methodology graph 在前端呈現六個核心階段，且 GUM/chat 不被誤當成核心 pipeline stage。

## 第九幕：Agent proposals 顯示為安全摘要

### 輸入

完成至少一次 onboarding、一次 diagnostic answer、一次 tutor response 後，觀察 agent proposals 或 agent panel。

### 預期輸出

- 畫面應能看到近期 agent role，例如 Intake Agent、Skill Agent、Diagnosis Agent、State Agent、Policy Agent、Fast Tutor Agent 或 Slow Simulator Agent。
- 每筆 proposal 應顯示角色、狀態、reason code 或安全 reference。
- 不應顯示 raw LLM response、完整 prompt、API key、provider response body。
- 不應把使用者完整原句當作 proposal payload 顯示。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 3、Phase 5 gate 檢查 typed proposal、validation status、rejected/fallback metadata 與 privacy tests。

### 成功標準

前端能看出 agentic proposal layer 的存在，但只顯示安全、簡短、可理解的 metadata。

## 第十幕：匯出 Markdown 與畫面內容一致

### 輸入

按下 Export 或開啟匯出功能。

### 預期輸出

- Markdown 匯出內容應包含本次學習主題、知識樹或 learner progress、methodology events、agent proposals 或相應安全摘要。
- 匯出內容應與前端目前看到的學習狀態一致。
- 匯出內容不應包含 API key、raw prompt、raw model output、provider response body。
- 若使用者曾輸入 `這太細了，我完全沒有基礎`，匯出可以包含一般聊天記錄或可見 transcript，但 methodology/proposal 區塊不應把它當成 raw hidden payload。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 5 gate 檢查 Markdown export safety、API serialization 與 privacy boundaries。

### 成功標準

匯出的 Markdown 與前端學習進度一致，且不洩漏隱藏 prompt、模型原文或敏感資料。

## 第十一幕：手機寬度畫面不重疊

### 輸入

將瀏覽器調整到手機寬度，約 390px 到 430px，重新整理頁面，觀察聊天區、methodology panel、agent proposals、learner progress。

### 預期輸出

- 聊天輸入框可見且可輸入。
- methodology panel 不應壓住聊天輸入框。
- agent proposals 與 learner progress 文字不應互相重疊。
- 按鈕文字不應超出按鈕邊界。
- 使用者仍可送出一則訊息，例如：

```text
請用更簡單的方式說明
```

且畫面能正常出現回覆。

### 後端查核

- 不做人工後端查核。
- 對應後端驗證應由 plan 的 Phase 5 Playwright / E2E gate 檢查 mobile viewport smoke test。

### 成功標準

手機寬度下仍可完成閱讀、輸入、送出與查看進度，不出現明顯重疊或不可操作區塊。

## 最終判定

所有幕次都必須通過，才算前端人工輸入/輸出驗收通過。若任一幕失敗，請記錄：

- 失敗幕次
- 測試時間
- learner id
- 瀏覽器與視窗尺寸
- rule/llm mode
- 送出的精確輸入
- 畫面可見輸出
- 截圖
- 是否剛執行過 Reset
- 若有匯出 Markdown，保留該檔案內容

後端相關失敗不在本人工劇本中手動判定；請回到 implementation plan 對應 phase 的 gate、integration test 或 smoke test 補上可重現證據。
