# 2026-07-13 實驗分析

## 總結

本次測試不是完整成功。對話、EDF 學習狀態判斷、Web Search 與「只從 user message 抽取候選」已運作；但 ComPeer 只確認到排程，沒有確認實際投遞，且記憶頁目前混合了長期記憶、候選與模型內部 learning state。

本次分析的產品原則是：

> 記憶頁只顯示真正存在於 Cold Memory、可跨對話使用、且有使用者證據支持的長期記憶。

## 1. ComPeer 排程成功，但投遞未完成

**命題**：ComPeer 已成功觸發與建立延遲任務，但正式環境的背景寄信 worker 沒有穩定完成投遞，或投遞結果沒有被記錄與呈現。

**證據**：

- 實驗 log 出現 `trigger_proactive: True` 與 `[ComPeer] Proactive trigger needed`。
- `MailboxStore` 建立了 `compeer-...` delayed task，延遲時間為 `300s`。
- 預定時間約為 05:55:10，但提供的 log 沒有 worker claim、delivery、mailbox insert 或前端 mailbox 讀取新信件紀錄。
- `delayed_mail_worker()` 是在 FastAPI startup 中以 `asyncio.create_task()` 啟動，依附於 Render web process：[backend/main.py:297-309](/workspaces/AREQA/backend/main.py:297)。

**解方**：

- 將 ComPeer 延遲改為設定值 `120` 秒，而不是散落的 magic number `300`。
- 為 delayed task 增加 `scheduled`、`claimed`、`delivered`、`failed` 的明確 log 與查詢能力。
- 排程成功與實際寄出分開記錄；只有 delivery 成功後才更新 `last_compeer_message`。
- 短期保留資料庫恢復機制；長期將 delayed mail worker 移出 API process，改成獨立 worker 或外部排程服務。

**預期結果**：ComPeer 觸發後約兩分鐘內出現在 mailbox；即使 API process 重啟，也能辨識任務是否已投遞，並可定位失敗層級。

## 2. 記憶候選仍可能把模型改寫當成使用者事實

**命題**：系統驗證了使用者 evidence 的存在，但沒有驗證 LLM 改寫後的候選文字是否仍忠實於使用者原意，之後便把改寫文字保存至 profile。

**證據**：

- `extract_user_memory_candidates()` 確實只處理 `role == "user"` 的訊息，並驗證 `evidence_quote` 存在：[backend/memory_gate.py:246-309](/workspaces/AREQA/backend/memory_gate.py:246)。
- 但 `promote_cold_candidate()` 寫入的是 `candidate["text"]`，不是原始 evidence：[backend/memory_store.py:235-256](/workspaces/AREQA/backend/memory_store.py:235)。
- 實驗中「國中理化不及格」被轉成「在理化科目上有學習困難」；這是語意推論，不是原始使用者表述。
- GUM Reflection 也產生「基礎較弱」與「對考試感到焦慮」等高層推論：[backend_log.md:63-68](/workspaces/AREQA/docs/worklog/202607/2026_07_13_experiment/backend_log.md:63)。

**解方**：

- 分開儲存 `source_text`、`evidence_quote`、`normalized_text` 與 Stitch tags。
- Cold Memory 的事實內容以使用者原文或可驗證的中性化內容為主，LLM 摘要不可直接取代原文。
- Stitch 只負責分類與檢索標籤，不負責改寫使用者事實。
- 單次問題、能力判斷、人格特質與模型推論不得直接成為長期 profile。

**預期結果**：長期記憶可追溯到使用者原話，不會把 AI 回答或模型推論冒充成使用者事實。

## 3. 自動升級政策過度信任 LLM

**命題**：目前 `requires_confirmation` 完全由 LLM 決定，伺服器只依照該欄位與跨對話次數自動升級，因此敏感、負面或時效性資料可能被保存。

**證據**：

- 候選的 `requires_confirmation` 由抽取模型輸出：[backend/memory_gate.py:260-293](/workspaces/AREQA/backend/memory_gate.py:260)。
- 自動升級只檢查 `requires_confirmation` 與不同 `conversation_ids` 的數量：[backend/gum_integration.py:873-893](/workspaces/AREQA/backend/gum_integration.py:873)。
- 實驗中「使用者在理化科目上有學習困難」被自動升級；「高一學生」則是可能過期的時間性資訊。

**解方**：

- 增加伺服器端 deterministic policy，不讓 LLM 單獨決定是否可長期保存。
- 一般偏好與穩定使用習慣可跨對話自動升級。
- 負面能力標籤、心理狀態、健康、身份、家庭與財務資訊預設不進入長期記憶。
- 考試、年級、當前目標與短期情緒加入 TTL 或 expiration。
- 高風險資訊預設不保存，不要求使用者逐筆審核；只有使用者明確要求記住時才保存。

**預期結果**：系統保留智能自動適應能力，但不會默默建立使用者不想要的負面或過期標籤。

## 4. 前端記憶頁目前不是純 Cold Memory

**命題**：前端記憶頁目前是混合視圖，而不是單純的使用者長期記憶視圖，因此造成內容雜亂與逐筆核准的壓力。

**證據**：

- `build_memory_view()` 合併 GUM propositions、Redis user profile 與 Redis cold candidates：[backend/main.py:345-397](/workspaces/AREQA/backend/main.py:345)。
- `/api/v1/memory` 將除了 profile/candidate 之外的 GUM propositions 歸為 `learning_state`：[backend/main.py:408-416](/workspaces/AREQA/backend/main.py:408)。
- `GumPanel` 將 profile、candidate 與 learning state 放在同一條時間線，並顯示「待確認」及確認／拒絕按鈕：[frontend/src/components/GumPanel/index.tsx:272-320](/workspaces/AREQA/frontend/src/components/GumPanel/index.tsx:272)。
- Hot Memory 本身雖被排除於直接時間線之外，但 memory summary 仍使用整個混合後的 `build_memory_view()` 結果：[backend/main.py:418-461](/workspaces/AREQA/backend/main.py:418)。

**解方**：

- 前端記憶頁只顯示真正已通過政策的 Cold Memory／User Profile records。
- Hot Memory、Working Memory、GUM learning state 與未驗證候選留在系統內部，不放進長期記憶時間線。
- 將「不要記住這件事」與「撤銷最近記憶」作為主要控制，而不是要求使用者逐筆批准模型推論。
- Memory summary 只使用篩選後的長期記憶資料。

**預期結果**：記憶頁只呈現使用者回答內容與穩定傾向，介面簡潔且不會讓使用者感覺自己在審核監控紀錄。

## 5. Hot Memory compaction 與 Stitch 的現況

**結論**：目前確實存在 `Hot Memory -> Compaction -> Stitch -> GUM propositions` 的程式路徑，但它不是目前可靠的長期記憶主流程。

**實際流程**：

1. `schedule_compaction()` 在觀察處理後被呼叫：[backend/gum_integration.py:395-418](/workspaces/AREQA/backend/gum_integration.py:395)。
2. `run_compaction()` 只有在 Hot Memory JSON 超過 `store.budget_limit` 時才真正處理；目前 startup 設定為 `1,000,000` bytes：[backend/main.py:279-282](/workspaces/AREQA/backend/main.py:279)。
3. compaction 會呼叫 `generate_stitch_tags()`，產生 refined content 與分類欄位：[backend/gum_integration.py:501-507](/workspaces/AREQA/backend/gum_integration.py:501)。
4. refined content 被寫入 `propositions`，再從 Hot Memory 移除：[backend/gum_integration.py:511-543](/workspaces/AREQA/backend/gum_integration.py:511)。

**目前風險**：

- 一般測試資料量很難達到一百萬 bytes，因此三天測試沒有看到 compaction 並不意外。
- `INSERT INTO propositions` 沒有明確寫入 `user_id`：[backend/gum_integration.py:515-527](/workspaces/AREQA/backend/gum_integration.py:515)。若資料表以 `default_user` 作為預設值，正式使用者的 compaction 結果可能無法被該使用者查詢到。
- Stitch 的 `refined_content` 會改寫 Hot Memory 內容，因此可能再次引入「學習弱點」或「人格推論」等污染。
- compaction 目前會處理多種 Hot Memory key，不等於只處理使用者明確回答。

**建議處理方式**：

- 不再用容量超過一百萬 bytes 作為唯一 compaction 觸發條件。
- 以 session boundary 或明確的長期記憶候選流程處理，而不是將所有 Hot Memory 整批歸檔。
- 寫入 Cold Memory 時明確帶入 `user_id`。
- 保留使用者原始 evidence；Stitch 僅寫入 tags、scope、event type 與檢索 metadata。
- 前端只讀取通過政策的 Cold Memory records，不直接讀取 compaction 中間狀態。

## 最終驗收標準

- `/api/v1/memory` 的前端資料只包含已通過政策的 Cold Memory／User Profile。
- 每筆長期記憶都能追溯至使用者訊息 evidence。
- AI 回答、GUM learning state、Hot Memory 與單次查詢不會成為長期使用者事實。
- Hot Memory compaction 寫入正確的 `user_id`，且可由該使用者查詢。
- Stitch 只增加標籤，不改寫或取代使用者事實。
- ComPeer 在兩分鐘內完成投遞，且 log 能區分排程成功與投遞成功。
