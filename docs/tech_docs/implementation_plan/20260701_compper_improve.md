# ComPeer 主動關懷系統改進實作計畫書 (2026-07-01)

## 背景與目標
目前 AREQA 的 ComPeer 模組（主動關懷路徑）存在兩個主要痛點：
1. **干擾感過重**：彈跳視窗時常在用戶不需要時跳出（僅依賴單純的 Scroll 數量或閒置時間）。
2. **內容流於空泛**：彈跳視窗的內容為預設的罐頭訊息或空泛綜整，缺乏針對性。

本計畫基於《ComPeer: A Generative Conversational Agent for Proactive Peer Support》論文的設計原則，結合 AREQA 現有的 GUM（長期記憶）與 EDF（教學策略）架構，提出具體的程式碼級別改進方案。

---

## 核心改進一：精準的時機控制 (適應性排程與靜默)

### 1. 實作 Event Detector (事件偵測器) 代替單純計數
**現狀**：`compeer_scheduler.py` 中的 `proactive_scheduler_loop` 僅判斷 `scroll_count >= 6` 就觸發警告。
**改進**：
* 滿足高頻 Scroll 或長時間 Dwell (閒置) 時，**不直接發送罐頭訊息**。
* 呼叫一個輕量級的 LLM Prompt（Event Detector），傳入最近的 `hot_memory` 快照。
* **Prompt 邏輯**：判斷用戶是否正在面臨「具體挑戰」或「負面情緒」。如果是，才提取事件；如果只是正常的閱讀瀏覽，則回傳 `no event`，系統保持靜默。

### 2. 導入動態 Importance Value 與退避策略 (Back-off)
**現狀**：排程觸發後，`user_flag` 只是設為 `False`，缺乏明確的長期冷卻與重要性權衡。
**改進**：
* 在 `evaluate_importance_gate` 中落實重要性評分：只有當 LLM 評定的 `importance_score` 大於隨機生成的閾值時才發送。
* **Back-off 機制**：如果前端回報用戶關閉了視窗（或忽略超過一定時間），後端將 `user_flag["default_user"]` 的冷卻時間強制設定為 3~6 小時，避免反覆打擾。

---

## 核心改進二：深度的客製化內容 (結合 GUM 與 EDF)

### 1. 深度每日反思 (Reflection Module 升級)
**現狀**：`compeer_scheduler.py` 中的 `run_reflection_and_initialization` 僅傳遞 `[f"User had {len(chat_logs)} interactions yesterday."]` 給 `initialize_daily_schedule`，內容極度匱乏。
**改進**：
* 修改 `run_reflection_and_initialization`，讓它去呼叫 `gum_integration.py` 中強大的 `run_reflection()` 函數。
* 透過 GUM 將昨日對話進行高階語義濃縮（Insights），找出「用戶的知識盲區」或「潛在的學習計畫」。
* 將這些深度的 Insights 作為 context 傳入 `initialize_daily_schedule`，讓 LLM 生成帶有具體知識點的每日關懷排程。

### 2. 觸發時結合 EDF 教學策略與長期記憶
**現狀**：主動觸發時寫死 `content = "AREQA發現你好像來回看了幾遍，有哪邊覺得不太清楚，需要我幫忙梳理嗎？"`。
**改進**：
* 觸發前，先呼叫 `gum_integration.py` 中的 `async_evaluate_and_update_state` 或 `query_cold_memory_for_context`。
* **組合 Prompt**：
  * **Input**: 當前的 `hot_memory` (用戶剛讀的東西) + `GUM` (用戶過去的弱點) + `learner_state` (學習狀態)。
  * **Output**: 基於 EDF 策略（如 PROBE_UNDERSTANDING 或 SUGGEST_ACTION）生成一句切中要害的引導。
* **範例**：不再是罐頭訊息，而是「我注意到你在看『深度學習的注意力機制』。結合你昨天對『矩陣內積』的疑惑，我們需要用圖解來拆解這兩個概念的關聯嗎？」

---

## 預計實作步驟與修改檔案

### Step 1: 修改 `backend/services/compeer_scheduler.py`
* 重構 `proactive_scheduler_loop`：移除 hardcode 的 `scroll_count >= 6` 直接跳罐頭訊息的邏輯。加入呼叫 LLM 進行 `Event Detection` 的流程。
* 重構 `run_reflection_and_initialization`：接入 `gum_integration.py` 的真實反思洞察。

### Step 2: 在 `backend/gum_integration.py` 新增輔助方法
* 新增 `detect_proactive_event_via_llm` 方法：負責分析 hot memory 是否值得打擾用戶，並計算 `importance`。
* 新增 `generate_scaffolding_message_via_llm` 方法：負責結合 GUM 與 EDF 生成最終要推播給用戶的客製化訊息。

### Step 3: 前端協同調整 (若需要)
* 確保 `log_action` API 能夠正確記錄用戶「拒絕/忽略」主動關懷的行為，以此觸發後端的 Back-off (冷卻) 邏輯。

---
**評估標準**：改進完成後，ComPeer 彈出的頻率應顯著下降，且每次彈出的內容必須包含用戶正在學習的特定知識點或情感狀態。