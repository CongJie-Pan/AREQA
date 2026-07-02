# 跨時空信箱 (Epistolary Dialogue) 實作計畫

## 1. 緣起與設計動機
在導入「英靈附體 (Active Avatar)」功能後，我們發現若系統以即時彈窗 (ComPeer Pop-up) 的方式，在主對話進行時突然跳出歷史人物的短對話，會嚴重打斷使用者的沉浸感與心流。

使用者提出了一個極具教育心理學價值的重新想像：**將「即時助教彈窗」昇華為「非同步的跨時空筆友」**。
透過寫信 (Letter-writing) 的形式，歷史人物（如柏拉圖、房龍）會在對話結束或閒置一段時間後，針對使用者的表現寄來一封長篇的深度反思信。使用者可以在專屬的「信箱」頁面中閱讀、沉澱，並非同步地回信。這種延遲滿足與長篇幅的交流，能引發更深度的哲學探討與自我反思。

因此，本計畫旨在廢除原本的「您可能想知道 (Suggestions)」頁面，全面改版為 **「跨時空信箱 (Mailbox)」** 系統。

---

## 2. 系統架構設計

### 2.1 資料層 (Data Layer)
為了儲存信件對話，將在 `data/gum_data/` 目錄下新增信件儲存機制（可為獨立的 `letters.db` 或是 JSON 架構 `mailbox.json`）。
每封信件的 Schema 應包含：
- `mail_id`: 唯一識別碼
- `sender`: 寄件人（例如："AREQA", "柏拉圖", "房龍" 或 "User"）
- `recipient`: 收件人
- `content`: 信件內容（支援 Markdown）
- `timestamp`: 寄出時間
- `is_read`: 是否已讀

### 2.2 邏輯層 (Backend Services)
1. **關閉即時彈窗**：修改 `compeer_scheduler.py`，當偵測到 `avatar_summon_pending` 或非急迫性的主動關懷時，不再直接透過 `ws_manager.broadcast_alert` 彈出對話，而是將訊息轉入「信箱生成管線」。
2. **延遲寫信機制**：在排程器中加入計時器邏輯（例如閒置滿 5 分鐘），當觸發發信條件時，呼叫 LLM。
3. **長文案 Prompt**：為信件模式撰寫專屬 Prompt。不再限制 60 字，而是鼓勵 LLM 寫出幾百字的深度詰問、比喻與歷史情境描繪，並帶有濃厚的寫信儀式感（如稱呼、結語）。
4. **API Endpoints**：
   - `GET /api/v1/mailbox`：獲取使用者的信件列表與未讀數量。
   - `POST /api/v1/mailbox/send`：使用者發送信件給特定歷史人物。
   - `POST /api/v1/mailbox/read`：標記信件為已讀。
5. **WebSocket 通知**：信件生成完畢寫入資料庫後，透過 WS 廣播 `{"has_new_mail": true, "sender": "..."}`，通知前端顯示紅點。

### 2.3 呈現層 (Frontend UI)
1. **移除舊功能**：移除原有的 `Suggestions` 推薦問題相關頁面。
2. **信箱介面 (Mailbox UI)**：
   - **收件匣 (Inbox)**：左側顯示歷史人物的信件列表（按時間排序，未讀標記粗體或紅點）。
   - **閱讀與回信區 (Mail Viewer & Editor)**：右側顯示古典風格的信紙介面，呈現信件內容，並提供「回信 (Reply)」編輯器。
3. **導覽列更新**：導覽列加入信箱圖示 (Mail Icon) 與未讀計數 Badge。
4. **Toast 通知**：收到 WebSocket 的 `has_new_mail` 事件時，於畫面角落低調滑出「您有一封來自 [人物名稱] 的新信件」通知，不再霸佔畫面中央。

---

## 3. 分段實作步驟 (Phased Execution Plan)

### Phase 1: 基礎清理與資料庫建置 (Backend)
- [ ] 移除 `compeer_scheduler.py` 中 `avatar_summon_pending` 觸發即時彈窗的邏輯。
- [ ] 建立 `mailbox_store.py`，封裝信件的 CRUD 邏輯（初始化 DB 或 JSON 檔案）。
- [ ] 設計信件生成的 LLM Prompt（`generate_epistolary_letter_via_llm`）。

### Phase 2: API 串接與非同步排程 (Backend)
- [ ] 實作 `/api/v1/mailbox` 相關路由（GET, POST）。
- [ ] 修改 `compeer_scheduler.py` 中的 `tick_proactive_schedule`，讓背景引擎在發現使用者離開對話或閒置後，自動觸發「英靈寫信」邏輯，寫入 DB，並推播 WebSocket `has_new_mail` 通知。
- [ ] 實作「使用者回信後，觸發英靈思考並延遲回信」的背景任務 (Background Task)。

### Phase 3: 前端介面大改版 (Frontend)
- [ ] 移除前端路由與組件中與 Suggestions 相關的程式碼。
- [ ] 開發 `/mailbox` 頁面與組件（可參考 Ant Design 的 Layout 與 List 進行左右分欄設計）。
- [ ] 實作信件閱讀器與 Markdown 編輯器，營造沉浸式寫信體驗。

### Phase 4: 通知與細節打磨 (Integration)
- [ ] 將 WebSocket 事件綁定到導覽列的未讀紅點 (Badge)。
- [ ] 將 Toast 通知設定為不干擾主畫面的低調樣式。
- [ ] 進行 End-to-End 測試，確保主對話的「附體」與信箱的「非同步回信」不會在 Prompt 狀態上產生衝突。
