### Act 01
- 通過與否 : 通過
- 支持證據 :
  - 對話紀錄 `act01_02/areqa-chat-2026-07-18_act01_act02.md` 顯示，回覆以基礎、循序方式說明牛頓第一運動定律、慣性、靜止／等速度直線運動、摩擦力與空氣阻力。
  - 回覆沒有把使用者說成「基礎較弱／能力不足」，也沒有聲稱使用者已理解、掌握或能應用定律。
  - 回覆中的「為了讓你不再焦慮」是在承接使用者原句「現在好焦慮」，依修正版劇本可接受；它沒有被擴寫成長期人格、能力或診斷標籤。
  - 後端紀錄 `act01_02/backend_log_act01_02.md` 顯示 Redis 啟動狀態為 `system.redis_open_status status=open`。目前 Act 01 資料沒有提供記憶頁出現焦慮、成績、能力或理解程度長期記憶的證據。
- 通過原因 :
  - 依修正版第一幕判準，模型可在使用者明說的範圍內承接情緒；本幕回覆符合教學性要求，且沒有新增未驗證的能力、人格、理解程度或長期狀態判定。

### Act 02
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求第二幕需驗證「一次性 SpaceX 問題顯示可辨識來源」；輸入為「最新的 SpaceX 星艦發射，有運用到這個定律嗎？請提供資料來源。」
  - 對話紀錄 `act01_02/areqa-chat-2026-07-18_act01_act02.md` 顯示，回覆將星艦發射拆成發射台靜止、點火打破平衡、太空慣性飛行三段，能合理連結星艦與牛頓第一運動定律。
  - 同一回覆包含 `#### 文獻來源`，列出 1 到 8 筆來源，且每筆都有可點擊 URL；文中的 `【文獻1, 5, 7】`、`【文獻4, 5, 7】`、`【文獻7】`、`【文獻8】` 可對應到來源清單。
  - 回覆沒有稱使用者已理解慣性，也沒有稱使用者已能應用定律；「你剛才提到『公車煞車時身體會往前傾』」是承接第一幕的教學例子，不是能力或掌握程度判定。
  - 後端紀錄 `act01_02/backend_log_act01_02.md` 顯示搜尋流程成功：`orchestration.web_search_started`、`POST https://api.perplexity.ai/search "HTTP/1.1 200 OK"`、`orchestration.web_search_completed ... result_count=8`。
  - 後端紀錄也顯示本次 SpaceX 問句被判定為工作脈絡而非長期記憶：`memory.ingestion_decided ... state=working_context_only reason=interrogative_not_memory_evidence category=current_focus promoted=False`。
- 通過原因 :
  - 使用者可見回覆符合第二幕的教學與來源顯示要求，且沒有把單次 SpaceX 問句擴寫成航太興趣、學習偏好或能力記憶。
- 觀察事項 :
  - 後端曾出現 `orchestration.response_boundary_blocked ... reason=unsupported_understanding`，表示 guard 有攔截一次不支援的理解程度表述；最終對話紀錄未顯示該違規表述。
  - 來源主要是一般火箭／牛頓定律資料，未明確提供官方「最新 Starship 發射」事件來源。依目前劇本，第二幕重點是可辨識來源與合理物理連結，因此不列為失敗；若之後要嚴格驗證「最新發射」事實，需另行收緊劇本。

### Act 03
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求第三幕驗證「偏好問句不會被當成偏好記憶」；輸入為「我偏好什麼學習方法？」
  - 對話紀錄 `act03/areqa-chat-2026-07-18_act03.md` 顯示，助理回答「目前對你的學習習慣尚無具體數據」，並提供自我探索選項。就使用者可見回覆而言，沒有直接宣稱已知道使用者偏好。
  - 後端紀錄 `act03/backend_log_act03.md` 第 14 行顯示主要 ingestion 判定正確：`candidate_id=none state=working_context_only reason=interrogative_not_memory_evidence category=current_focus promoted=False`。
  - 人工測試補充觀察指出，當時前端記憶頁沒有看到這類偏好或能力記憶，記憶頁仍是空的。
- 通過原因 :
  - 依第三幕人工測試成功標準，重新整理記憶頁後沒有因「我偏好什麼學習方法？」這一句問話新增偏好記憶；可見回覆也沒有把問句本身當成已知偏好。
- 觀察事項 :
  - 同一後端紀錄第 96 行顯示 GUM Evolution 產生過一段未明說的學習偏好／能力推論：`should_evolve=True`、`actions=['update']`、`target_ids=[480, 482]`，且 `revised_proposition` 寫成「使用者在學習上具備強烈的來源查證意識與科學邏輯分析能力，偏好透過理性論證與實證資料來建立知識基礎，而非單純的記憶。」
  - 由於人工測試時前端記憶頁仍為空，這項後端紀錄不列為 Act 03 失敗；但它仍是後續工程審查可追蹤的潛在風險，需確認 GUM Evolution 的更新是否只作用於不可見／非長期記憶，或是否可能在其他條件下外顯到記憶頁。

### Act 04
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求第四幕驗證「第一次明確偏好不會立即成為已記住的偏好」；輸入為「我偏好用具體例子理解抽象概念。」
  - 對話紀錄 `act04/areqa-chat-2026-07-18_act04.md` 顯示，助理可依使用者明確表達的偏好，以「概念骨架 + 具體場景」方式回應；回覆沒有明說「我已永久記住」或「已儲存到記憶」。
  - 前端紀錄 `act04/frontend-memory_shown_none.txt` 是空檔，檔名與內容都表示當時記憶頁沒有顯示新增記憶。
  - 後端紀錄 `act04/backend_log_act04.md` 第 52 行顯示系統建立候選記憶：`memory.candidate_created ... category=passive_preference ... evidence_count=1 distinct_conversation_count=1`。
  - 後端紀錄第 53 行顯示晉升被阻擋：`memory.promotion_blocked ... reason=insufficient_independent_evidence`。
  - 後端紀錄第 54 行顯示 ingestion 結果為候選、未晉升：`state=candidate ... category=passive_preference promoted=False`。
- 通過原因 :
  - 在晉升門檻為 2 的條件下，第一次明確偏好只形成候選記憶，沒有被立即 promoted 成長期記憶；前端記憶頁也沒有顯示這筆偏好，因此符合第四幕成功標準。
- 觀察事項 :
  - 可見回覆中的「我們未來的對話將會遵循...」語氣接近已套用長期個人化承諾；雖然沒有宣稱已永久記住，也沒有外顯成記憶頁項目，但未來可考慮把語氣改成「這次我可以先用...」以更貼近候選記憶尚未確認的狀態。

### Act 05
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求第五幕驗證「不同對話的重複偏好只顯示一筆記憶」；對話 D 第一則輸入為「學抽象概念時，我希望先看具體案例或實際情境，再理解原理。」，第二則同對話輸入為「我真的比較喜歡用實際例子來學抽象概念。」
  - 前端記憶頁紀錄 `act05/memory.md` 只顯示一筆已記住的語意等同偏好：「學抽象概念時，我希望先看具體案例或實際情境，再理解原理。」
  - 後端紀錄 `act05/backend_log_act05.md` 第 28 行顯示第一則輸入命中第四幕建立的同一候選：`memory.canonical_match_accepted ... candidate_id=f7b8f1524533d02359894ab3 ... reason=canonical_key_match`。
  - 後端紀錄第 29 行顯示候選累積到兩個不同對話證據：`evidence_count=2 distinct_conversation_count=2`。
  - 後端紀錄第 32 至 33 行顯示該候選被晉升為 profile 記憶：`memory.profile_promoted ... evidence_count=2 distinct_conversation_count=2`，且 ingestion 結果為 `state=promotion_eligible ... promoted=True`。
  - 後端紀錄第 107 行顯示第二則同對話重複輸入仍指向同一 candidate，且 `promoted=False`，沒有證據顯示前端新增第二筆相同記憶。
- 通過原因 :
  - 跨對話重複偏好成功讓候選達到門檻並成為一筆已記住偏好；同一對話內的再次重複沒有在前端產生第二筆語意重複記憶，因此符合「至多一筆」成功標準。
- 觀察事項 :
  - 後端第 94 行的 GUM Evolution 執行 `actions=['prune']`，並產生較強語氣的 `revised_proposition`，例如「極度仰賴並偏好...」。目前前端只顯示原始、較保守的偏好文字，因此不列為 Act 05 失敗；但後續仍應避免不可見演化層把偏好擴寫成過度推論。
  - Act 05 對話回覆多次使用「既然你已經明確了這個路徑」、「以後無論我們探討什麼...」等長期承諾語氣。因本幕記憶已達晉升門檻，這不違反本幕成功標準，但語氣仍可考慮更精準地對齊使用者實際明說的偏好。

### Act 06
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求第六幕驗證「完成暫時目標後停止提醒」；第一則輸入要求本月協助安排牛頓運動定律複習，第二則輸入明確表示已完成本月複習目標並要求不要再提醒。
  - 對話紀錄 `act06/areqa-chat-2026-07-18_act06.md` 第 8 至 48 行顯示，第一次回覆提供四週複習路徑，符合「可協助安排當月練習」。
  - 同一對話紀錄第 57 至 60 行顯示，第二次回覆確認「就此打住，不再談論這個複習計畫」，符合「確認停止相關提醒」。
  - 前端記憶頁紀錄 `act06/memory.md` 只顯示 Act 05 已確認的學習偏好：「學抽象概念時，我希望先看具體案例或實際情境，再理解原理。」沒有把「這個月完成牛頓運動定律複習」顯示為長期偏好或人物特質。
  - 後端紀錄 `act06/backend_log_act06md` 第 35 行顯示暫時目標完成：`memory.temporary_goal_completed ... status=completed reason=explicit_user_completion`。
  - 後端紀錄第 37 行顯示目標焦點已清除：`memory.goal_focus_cleared ... cleared_keys=current_focus,current_focus_conversation_id`。
  - 後端紀錄第 38 行顯示 ingestion 結果為工作脈絡、未晉升：`state=working_context_only reason=temporary_goal_completed category=temporary_goal_completed promoted=False`。
- 通過原因 :
  - 助理有確認停止提醒；後端將目標標記為完成並清除 goal focus；前端記憶頁沒有把本月複習目標外顯為長期偏好或人物特質，因此符合第六幕成功標準。
- 觀察事項 :
  - 第二次可見回覆第 60 行說「既然牛頓定律已經內化」，這是未經測試證明的學習成果推論。它不是記憶頁外顯失敗，因此不改變 Act 06 判定；但回覆品質上應改成「既然你說這個月的複習目標已完成」這類只承接使用者明說內容的表述。
  - 後端第 29 行的 GUM Evolution 曾產生「使用者目前正面臨高一物理考試壓力...要求 AI 協助安排本月的複習計畫」的不可見更新紀錄。由於後續第 35 至 38 行明確完成並清除暫時目標，且前端記憶頁沒有顯示該目標，因此不列為失敗；但仍建議追蹤 GUM Evolution 是否可能把短期目標或壓力狀態寫成持久使用者描述。

### Act 07
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求第七幕驗證「明確『請記住』只記錄指定偏好」；輸入為「請記住：我偏好你先給我一個具體例子，再解釋抽象概念。」
  - 對話紀錄 `act07_08/areqa-chat-2026-07-18_act07_08.md` 顯示，助理確認「我已經將這個偏好納入我的回應邏輯中」，符合「可確認已處理該偏好」。
  - 前端記憶頁紀錄 `act07_08/memory.md` 顯示一筆明確記憶後續被編輯為「我偏好先看生活化案例，再理解抽象概念。」；使用者補充確認 `（已編輯、已刪除）` 是人工流程註記，表示該筆 Act 07 明確記憶先被編輯、後被刪除。
  - 前端記憶內容只保留學習方式偏好，沒有額外推論能力、人格或未明說特徵。
- 通過原因 :
  - 明確「請記住」有產生指定偏好記憶，內容仍落在使用者指定的「先給具體例子／生活化案例，再解釋抽象概念」範圍內，沒有外顯成能力或人格推論。
- 觀察事項 :
  - 對話回覆「無論我們探討多麼深奧的理論...」語氣偏長期承諾，但本幕本來就是明確請記住，因此不構成失敗。

### Act 08A
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求將第五或第七幕產生的一筆記憶編輯為「我偏好先看生活化案例，再理解抽象概念。」並於儲存後重新整理仍顯示更新文字。
  - 前端記憶頁紀錄 `act07_08/memory.md` 顯示更新後文字：「我偏好先看生活化案例，再理解抽象概念。」；使用者補充確認 `（已編輯、已刪除）` 是人工流程註記，表示此筆曾完成編輯流程。
  - 後端紀錄 `act07_08/backend_log_act07_act08.md` 第 30 行顯示 `memory.correction_applied ... operation=edit result=persisted`。
  - 後端紀錄第 32 行顯示編輯 API 回傳 `PUT /api/v1/memory/profile%3Aexplicit%3Af0d2157e6791f42581011cad HTTP/1.1" 200 OK`，未出現 4xx 或 5xx。
- 通過原因 :
  - 編輯請求成功持久化，前端紀錄顯示更新後文字，且沒有 4xx/5xx 錯誤，因此符合第八幕 A 成功標準。

### Act 08B
- 通過與否 : 通過
- 支持證據 :
  - 劇本要求僅在第八幕 A 通過後，刪除同一筆已編輯記憶，重新整理後不得復活舊值。
  - 使用者補充確認 `act07_08/memory.md` 中的 `（已編輯、已刪除）` 是人工流程註記，明確表示該筆記憶完成編輯後又被刪除，不是刪除後仍外顯的 UI 內容。
  - 後端紀錄 `act07_08/backend_log_act07_act08.md` 第 190 行顯示刪除前 CORS 預檢成功：`OPTIONS /api/v1/memory/batch-delete HTTP/1.1" 200 OK`。
  - 後端紀錄第 195 行顯示刪除後 working memory 更新：`Updated working memory ... ['explicit_memories']`。
  - 後端紀錄第 196 行顯示刪除 API 成功：`POST /api/v1/memory/batch-delete HTTP/1.1" 200 OK`，未出現 4xx 或 5xx。
- 通過原因 :
  - Act 08A 已通過；同一筆已編輯記憶的刪除 API 成功，且人工註記確認流程已刪除，因此符合第八幕 B 成功標準。
- 觀察事項 :
  - `memory.md` 是人工整理後的流程紀錄，不是單純的刪除後最終頁面 snapshot；因此此幕判定依賴使用者補充的人工觀察來解讀 `（已編輯、已刪除）`。

### Act 09
- 通過與否 : 不通過
- 支持證據 :
  - 劇本要求第九幕驗證「正常使用後 ComPeer 以信箱送達」；成功標準是在 `T0 + 150` 秒前恰好出現一封符合內容限制的新信，沒有新信即判定失敗。
  - 前端紀錄 `act09/no_mail.txt` 是空檔，檔名表示本幕檢查結果為未收到信。
  - 後端紀錄 `act09/backend_log_act09.md` 第 156 至 157 行顯示測試使用者 `41f635cc-ca99-40dc-a0c8-4e065954739c` 在 `inactive_seconds=121.698` 時被評估，但 `trigger_present=False`，並被 `reason=absent_trigger` 阻擋。
  - 後端紀錄第 201 至 202 行顯示同一測試使用者在 `inactive_seconds=149.216` 時再次被評估，仍為 `trigger_present=False`，並被 `reason=absent_trigger` 阻擋。
  - 後端紀錄第 215 行雖有 `GET /api/v1/mailbox HTTP/1.1" 200 OK`，但沒有看到新信建立、排程成功、送達成功或 `task_id` 非 `none` 的證據。
- 不通過原因 :
  - 在第九幕要求的 `T0 + 150` 秒窗口內，沒有一封新信送達信箱；後端也顯示 ComPeer preflight 因沒有 trigger 而未排程，因此違反「恰好出現一封新信」的成功標準。
- 觀察事項 :
  - 因為沒有新信，無法驗證信件內容是否避開焦慮、能力推論、單次 SpaceX 問題或候選記憶等限制；本幕主要失敗點是未送達。
  - 後續重測時需明確定義 Act 09 的時間窗：若使用行為訊號 fallback path，`T0` 應至少拆成「最後一次使用者互動時間」、「scheduler 判定 eligible / 建立 task 的時間」與「信箱 delivery delay 到期時間」。目前 production `compeer_delivery_delay_seconds=120`，因此若 scheduler 約在 inactive `T0 + 120` 秒才建立 task，人工檢查信箱應等待到「task 建立時間 + 120 秒」附近，而不是只用「最後互動時間 + 150 秒」判定。
  - 人工 pass condition 維持使用者可見標準：信箱中恰好出現一封新的 ComPeer/AREQA 信件、聊天視窗不直接插入打擾訊息、未讀狀態同步，且信件內容不得把焦慮、能力推論、單次 SpaceX 問題或候選記憶寫成已確認長期事實。
