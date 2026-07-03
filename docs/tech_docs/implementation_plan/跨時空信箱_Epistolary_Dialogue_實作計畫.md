# 跨時空信箱 (Epistolary Dialogue) 實作計畫 (修訂版)

## 1. 緣起與設計動機
使用者提出了一個極具深度的重構構想：**將原本「即時跳出」的 ComPeer 助教彈窗，昇華為「非同步的跨時空筆友對話」**。
透過「寫信」的形式，當系統進入「英靈附體」狀態（例如召喚了柏拉圖、房龍）後，不再以粗暴的即時通知打斷使用者的主對話，而是在使用者對話閒置一段時間後，將這些深刻的歷史反思與靈魂拷問包裝成一封「長篇信件」，默默寄到使用者的「信箱」。

此計畫將徹底廢除目前較少使用的「您可能想知道 (Suggestions)」面板功能，全面改版為 **「跨時空信箱 (Mailbox)」**，創造延遲滿足、具儀式感且沉浸的深度哲學交流體驗。

---

## 2. 系統架構設計與具體修改範圍 (Codebase Mapping)

### 2.1 資料層 (Data Layer)
- **目標檔案**：`backend/mailbox_store.py` (New)
- **實作細節**：
  - 使用本地檔案 `data/gum_data/mailbox.json` 進行儲存。
  - **必須複用 `_atomic_write` + `tempfile` 模式**，避免多個非同步操作（排程器寫信、標記已讀）發生寫入衝突。
  - 每筆信件的 Schema 定義：
    - `mail_id`: string (UUID)
    - `sender`: string (寄件人，例如 "AREQA" 或 "房龍")
    - `recipient`: string (收件人，預設為 "User")
    - `content`: string (信件內容，支援 Markdown)
    - `timestamp`: float (時間戳)
    - `is_read`: boolean
    - `conversation_id`: string (選填)

### 2.2 邏輯層 (Backend Services)
1. **關閉即時彈窗與修正 Race Condition**：
   - **目標檔案**：`backend/services/compeer_scheduler.py`
   - **實作細節**：
     - 將 `avatar_summon_pending` 觸發的寫信任務與 `trigger_proactive` 的即時關懷分流。
     - **繞過 Cooldown 限制**：信件生成管線不應受 `is_in_cooldown` 阻擋（否則剛被觸發過的 ComPeer 會阻礙接下來 1~2 小時的信件發送）。
     - **解決 Race Condition**：LLM 寫信 (`generate_epistolary_letter_via_llm`) 是 `await` 操作，完成後**必須重新 `store.get_hot_memory()`** 取得最新物件，再進行存檔，不可重用 await 前讀取的 `hot_mem` 變數。

2. **`active_avatar` 自動清除機制**：
   - **目標檔案**：`backend/compaction.py` & `backend/gum_integration.py`
   - **實作細節**：
     - 在 `compaction.py` 的 `evaluate_student_state` Prompt 中，明確加入指令：**「若本輪對話中使用者不再提及任何歷史人物，或明確詢問與先前人物無關的問題，則 `active_avatar` 必須回傳 `null`（空值）。」**
     - 後端必須主動清除 `hot_memory` 中的 `active_avatar` 鍵，避免無限期「英靈附身」。在 `gum_integration.py` 中新增：
       ```python
       if state_res.get("active_avatar") is None:
           hot_mem = store.get_hot_memory()
           if "active_avatar" in hot_mem:
               del hot_mem["active_avatar"]
               store._atomic_write(store.hot_memory_path, hot_mem)
       ```

3. **信箱 API Endpoints 與殘留清理**：
   - **目標檔案**：`backend/main.py` & `backend/gum_integration.py`
   - **實作細節**：
     - 新增 `GET /api/v1/mailbox`、`POST /api/v1/mailbox/send`、`POST /api/v1/mailbox/read/{mail_id}`。
     - 在 `POST /api/v1/mailbox/send` 中收到使用者回信後，應立即在後端啟動 `asyncio.create_task(delayed_reply_writer(..., delay_seconds=300))`，作為回信後觸發英靈回覆的延遲計時器。
     - 刪除舊有的 `@app.get("/api/v1/suggestions")` 路由，並**同步清理** `main.py` 中 `get_suggestions` 的 import，以及 `gum_integration.py` 內的函式本體。

4. **WebSocket 新信件廣播**：
   - **目標檔案**：`backend/services/connection_manager.py`
   - **實作細節**：新增 `broadcast_mail_alert`，傳送 `{"has_new_mail": true, "sender": avatar_name}` 結構，僅用於點亮前端紅點。

### 2.3 呈現層 (Frontend UI)
1. **集中化 Union Type 定義**：
   - **目標檔案**：新增 `frontend/src/types/panel.ts`
   - **實作細節**：定義 `type SidePanelType = 'memory' | 'mailbox' | null`，並統一替換散落在 `GumPanel/index.tsx`、`ChatContainer/index.tsx`、`ConversationList/index.tsx` 與 `gum/store` 的 5 處字串寫法，避免 TypeScript 編譯盲區導致面板無法開啟。

2. **WebSocket Hook 擴充與修復**：
   - **目標檔案**：`frontend/src/hooks/useProactiveWebSocket.ts`
   - **實作細節**：
     - 在 `onmessage` 中新增對 `has_new_mail` 訊號的解析分支，並透過 callback 更新 mailbox store 的未讀計數 (`unreadCount`)。
     - **避免連線震盪**：使用 `useRef` 包裝 callbacks，使 `useEffect` 的依賴陣列不再直接依賴 callback 函式，防止 React 重渲染時引發 WebSocket 重連。

3. **信箱介面 (Mailbox UI) 與狀態管理**：
   - **目標檔案**：`frontend/src/components/MailboxPanel/index.tsx` & `frontend/src/store/mailbox/index.ts`
   - **實作細節**：
     - **收件匣 (Inbox)**：歷史人物信件列表。
     - **閱讀與回信區 (Mail Viewer & Editor)**：古典風格信紙呈現 `content` (Markdown)，底部提供 TextBox 讓使用者發送回信。
     - **狀態管理**：在 `mailbox/index.ts` 加入 `sendingReply: boolean` 鎖定按鈕。回信成功後，本地信件列表應立即追加一筆 `sender: 'User'` 的記錄（Optimistic Update），不等待後端確認。標記已讀時也同樣進行本地 Optimistic Update。

4. **觸發按鈕與導覽列**：
   - **目標檔案**：`frontend/src/components/ConversationList/index.tsx`
   - **實作細節**：將「您可能想知道」按鈕改名為「跨時空信箱 (Mailbox)」，並加上動態紅點 Badge（讀取 `unreadCount`）。

---

## 3. 分段實作步驟 (Phased Execution Plan)

### Phase 1: 防錯機制與基礎模型清理 (Backend)
- [x] 修改 `compaction.py` 讓其能回傳明確的空值以清除 `active_avatar` 狀態，並於 `gum_integration.py` 實作刪除邏輯。
- [x] 移除 `main.py` 與 `gum_integration.py` 內所有關於 `suggestions` 的路由、import 及函式本體。
- [x] 同步更新 `tests/backend/test_compeer_scheduler.py` 的斷言（改為 `sender_name=mock.ANY`），並新增 `avatar_summon_pending` 觸發信件管線且**不**被 cooldown 阻擋的測試。
- [x] 刪除前端廢棄 API 對應的 `test_suggestion_regression.py` 和 `test_suggestion_service.py` 測試。
- [x] 定義並替換前端集中的 Union Type (`SidePanelType`)，確保 TypeScript 型別一致。

### Phase 2: 信件儲存層與 API (Backend)
- [x] 建立 `mailbox_store.py` (包含 `_atomic_write` 保護機制)。
- [x] 在 `main.py` 註冊新的 `MailboxStore` 實例，實作 `/api/v1/mailbox` 完整 GET/POST 路由。

### Phase 3: 非同步發信管線 (Backend & Integration)
- [x] 於 `gum_integration.py` 開發 `generate_epistolary_letter_via_llm`，定義 300~500 字長信的 LLM Prompt。
- [x] 於 `compeer_scheduler.py` 修改 `avatar_summon_pending` 路徑，使其**繞過 cooldown** 限制。
- [x] 修正 `compeer_scheduler.py` 的 Race Condition：LLM 寫信後重新 fetch `hot_memory` 再寫入。
- [x] 開發使用者回信後的延遲計時器任務 `delayed_reply_writer`。
- [x] 擴充 `connection_manager.py` 與前端的 `useProactiveWebSocket.ts`，打通 `has_new_mail` 的 WebSocket 訊號傳遞與防震盪處理。

### Phase 4: 前端介面大改版 (Frontend)
- [x] 開發 `frontend/src/store/mailbox/index.ts` 串接後端 API（包含 Optimistic Update 邏輯）。
- [x] 刻建 `MailboxPanel/index.tsx` 組件，取代原本的 Suggestions 區塊。
- [x] 進行端對端 (End-to-End) 測試：確保信件來回互動順暢，主對話的「附體狀態」不會無限期卡住，且 WebSocket 紅點能正確顯示。

---

## 4. 測試計畫 (Test Plan)

### 4.1 後端單元測試 (`tests/backend/`)

#### 4.1.1 `test_mailbox_store.py` (New)
與現有 `test_memory_store.py` 結構相同，使用 `pytest` + `tmp_path`。

| 測試名稱 | 測試目的 | 方法 |
|---|---|---|
| `test_add_mail` | 新增信件後可正確讀取 | 呼叫 `add_mail()`，`assert mail_id in store.get_all_mails()` |
| `test_mark_as_read` | 標記已讀後 `is_read` 為 True | 呼叫 `mark_as_read(mail_id)`，讀取確認 |
| `test_get_unread_count` | 未讀計數準確 | 新增 3 封信，讀 1 封，`assert unread_count == 2` |
| `test_atomic_write_integrity` | 原子寫入失敗不破壞舊資料 | Monkeypatch `os.replace` 拋出例外，確認 JSON 未損毀 |
| `test_conversation_thread` | 同一 `conversation_id` 的信件可被正確篩選 | 新增 2 封相同 `conversation_id` 的信，確認回傳只有該串 |

#### 4.1.2 `test_compeer_scheduler.py` (Update)
更新現有測試並新增以下測試：

| 測試名稱 | 測試目的 | 方法 |
|---|---|---|
| `test_avatar_summon_triggers_mail_despite_cooldown` | `avatar_summon_pending` 繞過 cooldown | 設定 cooldown 中，設 `avatar_summon_pending=True`，確認信件生成被呼叫 |
| `test_avatar_summon_flag_consumed_after_letter` | 信件生成後 flag 被清除 | 確認 LLM 呼叫完成後 `avatar_summon_pending` 不在 hot_mem |
| `test_race_condition_fix_hot_mem_refetch` | LLM await 後使用最新 hot_mem | Mock LLM await 期間更新 hot_mem，確認寫入信件時讀取的是最新版本 |
| `test_broadcast_alert_now_includes_sender_name` | 廣播包含 `sender_name` | `mock_broadcast.assert_called_with(..., sender_name="柏拉圖")` |

#### 4.1.3 `test_active_avatar_clear.py` (New)
| 測試名稱 | 測試目的 | 方法 |
|---|---|---|
| `test_avatar_cleared_when_llm_returns_null` | LLM 回傳 `null` 時清除 hot_memory | Mock `evaluate_student_state` 回傳 `active_avatar: None`，確認 hot_memory 中 `active_avatar` 鍵已刪除 |
| `test_avatar_not_cleared_when_same_person` | 同一人物不重複觸發 summon | Mock 回傳相同人物名稱，確認 `avatar_summon_pending` 未被設定 |
| `test_avatar_changes_trigger_new_summon` | 換人物時觸發新的 summon | 先設 `active_avatar=柏拉圖`，再回傳 `active_avatar=蘇格拉底`，確認 `avatar_summon_pending=True` |

#### 4.1.4 `test_mailbox_api.py` (Update)
使用 FastAPI 的 `TestClient` 進行路由層測試。目前已有基本的 4 個測試，還需要補齊：

| 測試名稱 | 測試目的 |
|---|---|
| `test_get_mailbox_empty` | 初始狀態回傳空陣列與 `unread_count: 0` (已實作) |
| `test_post_send_reply_creates_user_mail` | `POST /api/v1/mailbox/send` 後，信件列表出現 `sender: User` (已實作) |
| `test_post_read_marks_correct_mail` | `POST /api/v1/mailbox/read/{mail_id}` 正確標記 (已實作) |
| `test_post_read_not_found` | `POST /api/v1/mailbox/read/{mail_id}` 404 錯誤路徑 (已實作) |
| `test_get_suggestions_returns_404` | 舊 API 已刪除，確認回傳 404 (已實作) |
| `test_get_mailbox_with_mails` | 驗證 `GET /api/v1/mailbox` 在有信件時回傳正確資料結構，且 `unread_count` 計算無誤 (New) |
| `test_post_send_reply_triggers_background_task` | 驗證 `POST /api/v1/mailbox/send` 時，有正確透過 `asyncio.create_task` 呼叫 `delayed_reply_writer` (New) |
| `test_post_send_reply_validation` | 驗證 `SendMailRequest` 的 payload 欄位驗證 (New) |

### 4.5 潛在 Bug 與邊界條件修復 (Phase 6: Edge Cases & Bugs)

1. **`mailbox_store.py` 並發寫入問題**：目前的 `_atomic_write` 僅保證單次寫入不會寫壞檔案，但 `get_all_mails()` 到 `_atomic_write()` 中間的 read-modify-write 週期沒有跨協程/執行緒的鎖定 (Lock)，並發呼叫 `add_mail` 或 `mark_as_read` 可能覆蓋彼此。需要加入 `asyncio.Lock` 或 `threading.Lock`。(已修正)
2. **`gum_integration.py` 的 `delayed_reply_writer` 寫死參數**：該函式內的 `hot_memory_snapshot` 和 `cold_memory_context` 都是寫死的字串，無法反映使用者的真實脈絡，且未處理例外狀況。(已修正)
3. **`main.py` 的 `/api/v1/mailbox/send` 遺漏 `conversation_id`**：沒有將 `conversation_id` 傳遞給 `store.add_mail`，導致無法支援信件對話串 (Thread)。(已修正)
4. **`compeer_scheduler.py` 無限制發信**：`avatar_summon` 分支會完全繞過 Cooldown，雖然設定了這項機制，但若發生反覆觸發，將造成大量發信。(已評估，僅有頭像切換時會觸發一次，風險低，目前不修改)
5. **WebSocket 廣播的靜默失敗**：`connection_manager.py` 和 `compeer_scheduler.py` 中，WebSocket 廣播失敗時只會記錄，不會有額外處理。(已評估，信箱模組前端在連線恢復或刷新時會自動 pull 最新狀態，WS 僅做通知用，靜默處理無礙)

### 4.2 前端單元測試 (`tests/frontend/`)

使用現有的 Vitest + jsdom + `@testing-library/react` 環境。

#### 4.2.1 `store/mailboxStore.test.ts` (New)
| 測試名稱 | 測試目的 | 方法 |
|---|---|---|
| `fetches mails and updates store` | `fetchMails` 正確更新 state | Mock `fetch`，呼叫 `fetchMails()`，確認 `mails` 與 `unreadCount` 更新 |
| `sendReply sets sendingReply to true then false` | 回信期間 loading 狀態正確 | Mock `fetch`，確認 `sendingReply` 在 await 前後的狀態變化 |
| `markAsRead updates local state` | 標記已讀後本地 `is_read` 即時更新（Optimistic Update） | 確認不等待後端就更新 UI 狀態 |

#### 4.2.2 `hooks/useProactiveWebSocket.test.ts` (Update)
| 測試名稱 | 測試目的 | 方法 |
|---|---|---|
| `calls onNewMail when has_new_mail received` | `has_new_mail` 訊號觸發正確 callback | Mock WebSocket，`dispatchEvent` 模擬訊息，確認 `onNewMail` 被呼叫 |
| `does not reconnect when only callback ref changes` | `useRef` 修正後不觸發重連 | 重渲染元件，確認 WebSocket 連線未被關閉重建 |

#### 4.2.3 `components/MailboxPanel.test.tsx` (New)
| 測試名稱 | 測試目的 |
|---|---|
| `renders inbox list when mails exist` | 信件列表正確渲染寄件人與時間 |
| `clicking mail shows content in viewer` | 點擊信件後右側顯示 Markdown 內容 |
| `reply button disabled when sendingReply is true` | 回信期間按鈕被鎖定 |
| `unread count badge updates after mark as read` | 點擊信件後 Badge 數字減少 |

### 4.3 整合測試 (`tests/frontend/integration/` & `tests/backend/`)

#### 4.3.1 後端整合測試 `test_mailbox_flow.py` (New)
模擬完整的「英靈召喚 → 閒置 → 寫信 → 廣播」流程：
```
1. Mock evaluate_student_state 回傳 active_avatar=「柏拉圖」
2. 確認 hot_memory 中 active_avatar 被更新
3. 確認 avatar_summon_pending=True 被設定
4. 手動觸發 proactive_scheduler_loop 一輪
5. 確認 generate_epistolary_letter_via_llm 被呼叫
6. 確認信件被寫入 mailbox.json
7. 確認 broadcast_mail_alert 被呼叫且 sender="柏拉圖"
```

#### 4.3.2 前端整合測試 `integration/mailboxFlow.test.tsx` (New)
使用 Mock Service Worker (MSW) 模擬後端 API，驗證完整的前端信箱流程：
```
1. 渲染 App，確認信箱按鈕無紅點
2. 模擬 WebSocket 接收 has_new_mail 訊號
3. 確認信箱按鈕紅點出現
4. 點擊信箱按鈕，確認 MailboxPanel 開啟
5. 確認信件列表正確顯示，未讀信件粗體標示
6. 點擊信件，確認內容顯示且紅點計數減少
7. 輸入回信並送出，確認 POST /api/v1/mailbox/send 被呼叫
```

### 4.4 回歸測試 (Regression)

由於移除了 Suggestions 功能，以下兩個測試檔案需要同步刪除或重構，避免誤報：
- `tests/backend/test_suggestion_regression.py` → 刪除
- `tests/backend/test_suggestion_service.py` → 刪除
