# Topic Finder（選題）開發計畫與任務清單

- 狀態：三個階段皆已實作，關卡全部通過（2026-11-18）。待作者依實機測試劇本驗收：`docs/tech_docs/dev_docs/research_coach_manual_test_script.md`
- 建立日期：2026-11-18
- 來源：
  - Heptabase 白板 `docs/paper/paper_review/Adaptive AI Learning with Human - Extracted`
  - 回顧論文 `docs/paper/paper_review/Adaptive AI Learning with Human - Manuscript`
  - 2026-11-18 的設計討論

## 1. 目標

把作者本人在 2026-08-09 ～ 08-22 找研究題目的歷程，做成 AREQA 的一個獨立空間「Topic Finder／選題」，帶領使用者從自己的痛點出發，收斂出適合自己、可以被驗證、現在做得到的研究題目。

AREQA 的角色**不是替使用者想題目**，而是在對的時機逼使用者自己反駁、自己砍題目。白板上真正推動收斂的，都是作者自己寫的反問卡片，例如「奧卡姆剃刀」「一直被問會煩」「20260819 反問」。AI 給出的肯定判斷，例如 8/17 檢查表上幾乎全部打 ✅，反而偏寬鬆。

## 2. 方法論（skill 的內容來源）

### 2.1 主循環

發散 → 篩選 → 反問推翻 → 定一版，重複進行。這對應白板上的 Edition01（8/14）、Edition02（8/19）、Edition 3（8/22）。

### 2.2 五個階段（2026-11-18 改版，可以跳著走）

原本是「起點＋五道篩子」，必須依序過關。作者的實際歷程是來回跳躍的，所以改成五個**階段**：使用者在題目卡上自由切換，AI 只專注在目前階段的目標。原本第 1 道篩子「技術進步會不會自動解決」不再單獨成為一個階段，改成第 2 階段順便問的一句話。

| 階段 | 主要目標（題目卡主標題） | AI 專注做的事 | 題目卡多出來的東西 | 白板上的對應 |
|---|---|---|---|---|
| 1 | 觀察痛點，先發散 | 從生活痛點或研究缺口出發，陪使用者發想幾個想解決的問題 | AI 建議：搜尋關鍵字、可能的研究缺口、相關議題 | 痛點卡片、Edition01 的發散 |
| 2 | 有沒有很簡單的解法？ | 陪使用者想最偷懶的解法（現成工具、現有論文、研究成果），夠了就淘汰；順便問「會不會過幾年就被新技術或局勢自己解決？」；引導使用者**自己到外面找**（關鍵字、提示詞、Google Scholar 等，或請他自己打開網路搜尋） | AI 建議：搜尋關鍵字 | 奧卡姆剃刀卡片；記憶、心智建模被刪掉 |
| 3 | 你真正想知道的是什麼？ | 拿掉工具和案例，陪使用者自己寫出母問題 | 「你真正想知道的（母問題）」欄位 | 「AI 的答覆如何影響人類的認知」 |
| 4 | 怎麼證明？ | 每個關鍵詞用什麼證據看；結果能不能證明自己錯了 | 「怎麼證明」欄位，沒想好證據的標 ⚠️ | 8/17 的操作化表；「量效果，不量內容」 |
| 5 | 做得到嗎？ | 用反問一項一項陪使用者評估時間、資料與場域、指導教授與方法、有沒有人做過、研究倫理 | 可行性檢查表（✅ 可以／⚠️ 還不確定／❌ 有困難／⚠️ 還沒討論，狀態照使用者的回答填） | LearnLM 缺口、邱老師的 IPA 計畫 |

- 題目卡上方的 1～5 可以直接點，切換到任一階段；另有「下一階段 →」。
- 「採用這份整理」只把 AI 草稿存成新版本，不會換階段。換階段一律由使用者決定，AI 不能代勞。
- 欄位在該階段打開；已經有內容的欄位，跳回前面的階段時仍然顯示。
- AI 建議是參考用，直接更新、不需要採用、不算版本；也不得列出具體論文或作者。
- 候選題目若是 AI 提議、使用者只是同意列入，題目卡上會標「AI 提議」；使用者用自己的話改寫後標記消失（借自 Academic Research Skills 區分「AI 起點」和「使用者洞見」的做法）。
- 選題空間不會自動上網搜尋：搜尋模式為「自動」時一律不搜，只有使用者自己打開網路搜尋才會搜。

### 2.3 三條貫穿規則

1. **反問要能推翻 AI 的判斷。** AI 不能宣告「過關」，只能說「我看不出反例，你自己能想到嗎？」過關一定由使用者確認。
2. **砍掉的題目要留紀錄，不要直接刪。** 淘汰清單要記下「在第幾階段砍掉、理由、能不能降級保留」。被砍的題目後來常以「要有可檢驗的機制才值得加入」的形式回來。
3. **每一版都要標版本號**，寫明這版改了什麼、為什麼改。

### 2.4 對話行為規則

- 專注在使用者選的階段，只問該階段的問題；使用者在對話裡自己跳到別的階段時，AI 跟著走，提醒一句可以在題目卡上切換，不把他拉回來。
- 對使用者一律說「第 n 階段」，不說「關」「篩子」或內部名稱。
- 使用者要資訊時直接給，例如「ICAP 是什麼」「這個領域有哪些經典研究」；使用者在判斷或選擇時才反問。這是為了平衡講解和提問：作者 8/18 自己發現「一直被問會煩」，Manuscript 的結論也不支持固定「只答」或「只問」的規則。
- 使用者做選擇時不先稱讚，先用平和、一起想的語氣提出一個最值得檢查的疑慮（以問句呈現，不說「最強烈的反對意見」「硬傷」「評審一定會質疑」），也不在同一則就給修正方案，先請使用者回應。
- 使用者提到的近期事實（誰執政、新法案、選舉）不要用 AI 自己可能過時的知識反駁；不確定時請使用者確認或去查。
- 使用者說「這量不了」時，提示他換量化對象：「它會造成什麼可以觀察到的行為改變？」
- 使用者只回「好」、沒有提出自己的反問時，AI 不替他補完反問，改問他的理由。

## 3. 已定案的設計決策

| 項目 | 決策 |
|---|---|
| 產品名稱 | 英文 `Topic Finder`，中文「選題」 |
| 圖示 | lucide `Telescope`。不用 `Search` 放大鏡，因為側欄的搜尋對話已經用了（`frontend/src/components/ConversationList/index.tsx:12`） |
| 和一般對話的關係 | 獨立空間（workspace）。「選題」是**對話的類型**，不是單則訊息的模式，所以不沿用 `requestModes` 或 `tutorProfile` 這類「每則訊息可以開關」的機制 |
| 側欄切換 | 側欄上方加圖示切換 `[💬][🔭]`，一直顯示。切換空間時，對話列表跟著篩選 |
| 上方分段切換 | `( Chat \| Topic Finder )`，**只在空白的新對話首頁顯示**。對話開始後（送出第一則訊息後）就不再顯示 |
| 狀態來源 | 兩個切換鈕讀寫同一個 `workspace` 狀態，永遠一致 |
| 進入對話後的上方 | 選題對話的上方顯示標籤「🔭 選題」。第二階段之後再加上階段，例如「🔭 選題 · 篩子 3/5」 |
| 選題對話裡的加號選單 | 保留上傳檔案（使用者會丟論文進來）；隱藏 Create Image 和 English Tutor |
| 過關 | 只能由使用者按「我確認這一關過了」，AI 只能提出建議 |

## 4. 介面規格

### 4.1 側欄

```
┌──────────────────┐
│ AREQA   [💬][🔭] │  ← 空間切換，aria-pressed 標示目前空間
│ + 新對話          │  ← 開的是目前空間類型的對話
│ 🔍 搜尋           │  ← 只搜尋目前空間的對話
│ ── 選題對話 ──     │
│ 🔭 AI 回饋與認知   │
└──────────────────┘
```

- 切換空間時，跳到該空間的空白新對話首頁。
- 舊對話（沒有 `kind` 欄位）一律視為 `chat`。

### 4.2 新對話首頁

```
        ( 對話 | 🔭 選題 )          ← 只在空白首頁顯示

   你最近卡在什麼問題上？            ← 選題空間的標語
 [ +  說說你的痛點……        🎤 ➤ ]
```

- 選題空間的標語和輸入框提示文字要另外寫，引導使用者進入篩子之前的第一步「找痛點」。
- 送出第一則訊息時，用目前空間的 `kind` 建立對話。之後不能再改。

### 4.3 選題對話（第二階段加上題目卡）

```
┌──────────────────────────────┬─────────────────────────┐
│ 🔭 選題 · 篩子 3/5：核心        │  題目卡  v2        [收合] │
│                                │  痛點 / 母問題            │
│  （對話）                       │  篩子進度 ✅✅⏳○○        │
│                                │  操作化表（未填的標 ❗）  │
│                                │  淘汰清單 / 我的反問      │
│ [ 輸入框 ]                      │  [ 我確認這一關過了 ]     │
└──────────────────────────────┴─────────────────────────┘
```

- 在手機寬度，題目卡改成從右側滑出的抽屜。
- 從選題對話分支出去的新對話，會繼承 `kind = research_coach`。第三階段用分支來做「發散」。

## 5. 資料與後端設計

### 5.1 對話類型

- Supabase：新增 migration `alter table public.conversations add column if not exists kind text not null default 'chat'`，並加上 check 限制只能是 `('chat','research_coach')`。寫法比照 `20261114000000_conversation_branches.sql`。
- 前端 `Conversation`（`frontend/src/database/schema.ts`）新增 `kind?: ConversationKind`，缺少時視為 `'chat'`。
- MVP 在記憶體中篩選列表，不建 Dexie 索引，所以不需要升級 Dexie 版本。之後如果要建索引，再新增 version 11。
- `syncService.ts` 的推送和拉取都要帶上 `kind`。如果雲端缺少這個欄位，比照 `request_modes` 的作法：只丟掉缺少的選填欄位，其他照常同步。

### 5.2 串流請求

- `backend/app/routes/stream.py` 的請求 model 新增 `conversation_kind: str = "chat"`，比照 `tutor_profile`：用白名單正規化，不認得的值一律當成 `chat`。
- 前端 `services/chat/index.ts` 依目前對話的 `kind` 帶上這個欄位。
- 當 `conversation_kind == "research_coach"` 時，忽略 `tutor_profile=english` 和生成圖片的請求，避免模式混在一起。

### 5.3 Prompt skill

- 新增 `backend/prompts/skills/research_topic_coach_skill.md`：
  - 說明文字寫在 runtime 區塊外面。
  - runtime 規則放在 `<!-- AREQA_RUNTIME_PROMPT_BEGIN/END -->` 之間的 JSON payload。
- 在 `backend/services/prompt_skills.py` 的 `_SCHEMAS` 登記 `"research-topic-coach"` 和它的欄位 schema，並把 `lru_cache(maxsize=3)` 調大。
- 組裝方式：一般教學 skill → 選題 skill → 題目卡摘要（第二階段才有）。
- 規則來自第 2 節。
- 載入失敗時不中斷：退回一般教學 skill，並記錄安全日誌。

### 5.4 題目卡（第二階段）

新增資料表 `research_topic_cards`，只允許後端存取，比照 `conversation_summary_checkpoints` 的 RLS 寫法：

```
user_id uuid, conversation_id uuid (on delete cascade),
version int, stage smallint (0=痛點, 1..5=篩子),
card jsonb      -- 痛點、母問題、候選題目、操作化表、淘汰清單、反問紀錄
history jsonb   -- [{version, changed, reason, confirmed_at}]
updated_at bigint
primary key (user_id, conversation_id)
```

- **AI 只能提出建議**：每輪回答結束後，在背景跑一次結構化輸出，從這輪對話抽出 `card_patch`，存成「待確認建議」。主回答本身不做解析。
- **使用者確認才算數**：只有使用者確認時，才推進 `stage`、把 `version` 加一，並寫入 `history`。
- API：FastAPI `GET /api/v1/research-coach/{conversation_id}/card` 和 `POST .../confirm`。前端透過 Next.js proxy `frontend/src/app/api/research-coach/...` 呼叫；瀏覽器不直接存取這張表。
- 每輪 prompt 只注入題目卡摘要，有長度上限，不注入完整歷史。

### 5.5 日誌與失敗處理

- 只記錄：`conversation_kind`、skill 載入結果、階段、版本、確認事件、抽取耗時與成功或失敗。
- 不記錄：使用者文字、題目卡內容、模型輸出。
- 題目卡抽取或讀取失敗時，對話照常進行，題目卡維持上一版。

## 6. 測試策略與階段關卡

### 6.1 四種測試的定義

| 類型 | 範圍 | 工具與位置 |
|---|---|---|
| 單元測試 | 單一函式、元件、store 或 service 的行為 | 前端：Vitest，放在 `tests/frontend/{components,store,services,utils,database}`。後端：pytest，放在 `tests/backend` |
| 整合測試 | 跨元件、store、service、路由的連動，外部服務一律 mock | 前端：`tests/frontend/integration/topicFinder*.test.tsx`。後端：用 FastAPI 測試 client 打 `stream`／`research-coach` 路由 |
| 回歸測試 | 確認既有功能沒有被改壞 | 重跑既有的相關測試檔（清單見各階段），最後跑完整套件 |
| 冒煙測試 | 在真實瀏覽器走一遍主要流程，確認可用 | Playwright，新增 `tests/e2e/topic-finder/`，測試標上 `@smoke`。**只在第三階段的最後執行** |

### 6.2 關卡規則（每一階段都適用）

**一個階段的所有測試都通過，才能進入下一階段。** 每個階段結束時都要完成以下步驟：

1. 這個階段新增或更新的單元測試全部通過。
2. 這個階段的整合測試全部通過。
3. 回歸測試全部通過：
   - 前端：`npm run test:frontend`
   - 後端：`npm run test:backend`
   - 前端品質：`npm run check:report:strict`
4. 只要有失敗，就留在本階段修正，**不能把問題標成「已知問題」帶到下一階段**。
   - 例外：如果失敗的測試確定和本功能無關，而且在改動前就已經失敗，要附上測試名稱和證據，例如在 master 上同樣失敗，記錄在第 6.7 節，並請作者確認後才能放行。
5. 在第 6.7 節填寫本階段的關卡紀錄：日期、commit、執行的指令、通過數量。
6. commit 到 master，commit 訊息註明階段，例如 `feat(topic-finder): phase 1 …`。

### 6.3 第一階段：MVP（空間 + skill）

**實作任務**

前端：
- [ ] `schema.ts` 新增 `ConversationKind` 和 `Conversation.kind`；在 repository 和 store 裡，缺少 `kind` 時預設為 `chat`。
- [ ] `syncService.ts` 推送和拉取都帶上 `kind`，雲端缺欄位時退回不帶。
- [ ] 在 chat store 新增 `workspace` 狀態（`'chat' | 'research_coach'`），存在本機偏好設定裡；讀不到時退回 `chat`。
- [ ] 側欄 `ConversationList`：
  - 加上 `[💬][🔭]` 圖示切換（`MessageSquare` / `Telescope`），並加上 aria 標籤。
  - 列表依 `workspace` 篩選，搜尋也限定在目前空間。
  - 「新對話」開的是目前空間類型的對話。
- [ ] 新對話首頁：分段切換 `( Chat | Topic Finder )` 只在沒有訊息時顯示；選題空間要有自己的標語和輸入框提示。
- [ ] 選題對話上方顯示「🔭 選題」標籤。
- [ ] `ChatInput`：在選題對話裡隱藏 Create Image 和 English Tutor，保留上傳檔案。
- [ ] 送出請求時帶上 `conversation_kind`。
- [ ] 分支繼承 `kind`。
- [ ] 在 `UserPreferencesContext.tsx` 新增中英文介面文字：`Topic Finder`／`選題`、標語、tooltip。

後端：
- [ ] migration：`conversations.kind` 欄位。
- [ ] `stream.py`：新增並正規化 `conversation_kind`；在選題對話裡停用 english tutor 和生成圖片。
- [ ] 新增 `research_topic_coach_skill.md`，並在 `prompt_skills.py` 登記。
- [ ] prompt 組裝：選題對話要注入選題 skill，載入失敗時退回一般 skill。
- [ ] 安全日誌：`conversation_kind` 和 skill 載入結果。

**單元測試**

後端：
- [ ] `conversation_kind` 正規化：`chat` 和 `research_coach` 原樣保留；空值、未知值、大小寫錯誤、非字串一律變成 `chat`。
- [ ] `load_prompt_skill("research-topic-coach")`：
  - 合法 payload 能載入。
  - 缺欄位、型別錯誤、重複 key、超過大小上限時，回傳 `None`，而且日誌不含檔案內容。
- [ ] prompt 組裝：
  - 選題對話包含選題 skill。
  - 一般對話不包含選題 skill。
  - skill 載入失敗時退回一般 skill。

前端：
- [ ] `schema` 和 repository：沒有 `kind` 的對話讀出來是 `chat`。
- [ ] chat store 的 `workspace`：
  - 預設值是 `chat`。
  - 切換後會寫入偏好設定。
  - 偏好設定讀取時拋錯，會退回 `chat`。
- [ ] `syncService`：
  - 推送 payload 帶有 `kind`，拉取時能還原 `kind`。
  - 雲端回報缺少 `kind` 欄位時，只丟掉 `kind`，其他照常同步。
- [ ] `ConversationList`：
  - 切換圖示有正確的 aria 狀態。
  - 列表和搜尋只顯示目前空間的對話。
- [ ] 新對話首頁：
  - 沒有訊息時顯示分段切換，有訊息時不顯示。
  - 選題空間的標語和輸入框提示正確。
- [ ] `ChatInput`：選題對話的加號選單沒有 Create Image 和 English Tutor，但有上傳檔案。
- [ ] 分支：從選題對話分支出去的新對話，`kind` 是 `research_coach`。

**整合測試**

- [ ] 後端 `stream` 路由：
  - 帶 `conversation_kind=research_coach` 時，最後的 prompt 包含選題 skill。
  - 同時帶 `tutor_profile=english` 時，english overlay 不會生效。
  - 日誌只有 kind 和 skill 狀態，沒有使用者文字。
- [ ] 前端 `tests/frontend/integration/topicFinderWorkspace.test.tsx`，以下步驟串在一起測：
  1. 從側欄切換到選題空間。
  2. 首頁出現分段切換和選題標語。
  3. 送出第一則訊息後，建立的對話 `kind = research_coach`，請求帶上 `conversation_kind`，分段切換消失。
  4. 切回 Chat 空間，列表裡看不到這個選題對話。
  5. 重新整理（重建 store）後，`kind` 和 `workspace` 都正確還原。

**回歸測試（必跑）**

- [ ] 既有測試檔：
  - `tests/backend/test_answer_style_service.py`
  - English Tutor 相關的後端測試
  - `tests/frontend/integration/generatedImageFlow.test.tsx`
  - 對話分支相關的前端測試
  - sync 相關的前端測試
  - `ConversationList` 和 `ChatInput` 既有的元件測試
- [ ] 完整套件：`npm run test:frontend`、`npm run test:backend`、`npm run check:report:strict`。
- [ ] 重點確認：
  - 一般對話：English Tutor、Create Image、分支、附件、停止生成的行為都沒有改變。
  - 沒有 `kind` 的舊對話照常顯示在 Chat 空間。

**對話品質評估（第一階段才有，人工判讀）**

- [ ] 以國關朋友那份對話紀錄的開頭當腳本，分別在一般模式和選題模式跑一次，看三個指標：
  1. 題目有沒有越收越窄。
  2. 使用者做選擇時，AI 有沒有先提出反對理由。
  3. AI 有沒有替使用者宣告過關（應該沒有）。
- [ ] 結果寫在 6.7 節。如果第 2 或第 3 項不符合，要先修改 skill 再重跑，才能進入第二階段。

**關卡：** 單元、整合、回歸測試全部通過，品質評估三項都符合，才能進入第二階段。

### 6.4 第二階段：題目卡

**實作任務**

- [ ] migration：`research_topic_cards` 資料表和 RLS。
- [ ] 後端 service：讀寫題目卡、在背景抽取 `card_patch`（結構化輸出，有長度上限）、確認後推進版本。
- [ ] FastAPI 路由和 Next.js proxy：`GET card`、`POST confirm`。
- [ ] prompt 注入題目卡摘要；階段規則由後端決定，每個階段只放該階段的篩子問題。
- [ ] 前端右側題目卡面板（手機版用抽屜）、確認過關按鈕、上方標籤顯示階段。

**單元測試**

後端：
- [ ] `card_patch` schema 驗證：合法建議會被接受；未知欄位、超過長度、型別錯誤的建議會被拒絕。
- [ ] 確認邏輯：
  - 只有確認時 `stage` 才推進、`version` 才加一，並寫入 `history`。
  - 抽到建議時不會改變 `stage` 和 `version`。
  - 重複確認同一關不會重複推進（冪等）。
  - 超過最後一關時不會越界。
- [ ] 摘要產生：輸出有長度上限，只包含目前階段需要的欄位。
- [ ] 階段規則：每個 `stage` 只放對應篩子的問題。
- [ ] 抽取失敗、逾時、回傳格式錯誤時，題目卡維持上一版，日誌不含內容。

前端：
- [ ] 題目卡面板：
  - 正確渲染各區塊。
  - 未填的測量方式標 ❗。
  - 收合狀態正確。
  - 手機寬度改成抽屜。
- [ ] 確認按鈕：
  - 請求進行中時停用。
  - 失敗時顯示錯誤並保留原狀態。
- [ ] 上方標籤：顯示 `篩子 n/5：名稱`。

**整合測試**

- [ ] 後端：
  - 用 `GET card` 讀到空卡，發一輪 `stream`，抽取建議。
  - 再 `GET card`：建議存在，但 `stage` 沒有改變。
  - `POST confirm` 之後 `stage` 和 `version` 推進，下一輪 prompt 的摘要反映新階段。
- [ ] 後端權限：
  - 使用者 A 不能讀取或確認使用者 B 的題目卡。
  - 未登入呼叫回傳 401。
- [ ] 前端 `tests/frontend/integration/topicFinderCard.test.tsx`：
  1. 打開選題對話，面板載入題目卡。
  2. 送出一則訊息後出現待確認建議。
  3. 按下確認，版本和階段更新。
  4. API 失敗時，對話仍然可以繼續。
- [ ] Next.js proxy：正確轉發驗證資訊，不把後端錯誤細節洩漏給瀏覽器。

**回歸測試（必跑）**

- [ ] 第一階段的全部 Topic Finder 測試。
- [ ] 既有的串流、摘要 checkpoint、RLS 隔離測試：
  - `tests/unit/test_rls_isolation.py`
  - 摘要 checkpoint 相關的後端測試
  - 串流相關的前端整合測試
- [ ] 完整套件：`npm run test:frontend`、`npm run test:backend`、`npm run check:report:strict`。
- [ ] 重點確認：一般對話不會呼叫題目卡 API，回應延遲也沒有增加，因為抽取在背景進行。

**關卡：** 單元、整合、回歸測試全部通過，才能進入第三階段。

### 6.5 第三階段：發散、匯出與冒煙測試

**實作任務**

- [ ] 在「發散」步驟，為每個候選題目開一條分支；主線題目卡只保留通過篩選的題目。
- [ ] 題目卡和版本歷史可以匯出成 Markdown。

**單元測試**

- [ ] 從候選題目開分支：新分支繼承 `kind`，並帶入該候選題目。
- [ ] 分支和主線題目卡的關係：分支不會改到主線題目卡。
- [ ] Markdown 匯出：
  - 各區塊和版本歷史格式正確。
  - 特殊字元有跳脫。
  - 空的題目卡也能匯出。

**整合測試**

- [ ] 前端 `tests/frontend/integration/topicFinderDivergence.test.tsx`：
  1. 在發散步驟為兩個候選題目各開一條分支。
  2. 兩條分支都只出現在選題空間。
  3. 回到主線確認過關後，匯出的 Markdown 包含淘汰清單和版本歷史。

**回歸測試（必跑）**

- [ ] 第一、二階段的全部 Topic Finder 測試。
- [ ] 既有的分支和分享測試：
  - `tests/e2e/conversation-branches` 測試組
  - 分支和分享相關的前端測試
- [ ] 完整套件：`npm run test:frontend`、`npm run test:backend`、`npm run check:report:strict`。

**冒煙測試（全部實作完成後才執行）**

新增 `tests/e2e/topic-finder/flow.spec.ts`，結構比照 `tests/e2e/conversation-branches`，每個測試都標上 `@smoke`：

- [ ] `@smoke` 從側欄切換到選題空間，首頁出現分段切換和選題標語。
- [ ] `@smoke` 送出第一則訊息後，回答會串流完成，分段切換消失，上方出現選題標籤。
- [ ] `@smoke` 題目卡面板會載入，確認一關之後階段和版本更新；重新整理後狀態仍在。
- [ ] `@smoke` 切回 Chat 空間，看不到選題對話；一般對話可以正常收發一輪。
- [ ] `@smoke` 從候選題目開分支後，分支出現在選題空間；匯出的 Markdown 可以下載。
- [ ] `@smoke` 手機寬度（390px）時題目卡變成抽屜，畫面沒有水平捲動。
- [ ] 執行：新增 `test:e2e:topic-finder` 這個 npm script，並跑 `npm run test:smoke`，同時確認既有的 `@smoke` 測試也都通過。

**關卡：** 單元、整合、回歸、冒煙測試全部通過，才能交付實機測試劇本，進行人工驗收。

### 6.6 交付：實機測試劇本

全部實作完成、第三階段關卡通過後，新增 `docs/tech_docs/dev_docs/research_coach_manual_test_script.md`，讓作者在實際環境中手動驗收。內容至少包括：

1. **事前準備**：
   - 啟動前端和後端的指令。
   - 確認 Supabase migration 已經套用。
   - 準備一個測試帳號，以及一個有舊對話（沒有 `kind`）的帳號。
2. **劇本 A｜空間切換**：
   - 側欄切換。
   - 首頁的分段切換只在空白首頁出現。
   - 列表和搜尋只顯示目前空間的對話。
   - 舊對話出現在 Chat 空間。
3. **劇本 B｜完整選題流程**：用作者自己 8 月的痛點「AREQA 做出來跟 Gemini 差不多」當輸入，從痛點走到第五道篩子。每一步列出：
   - 輸入範例。
   - 預期 AI 的行為，例如提出反對理由、不宣告過關、資訊型問題直接回答。
   - 預期題目卡的變化。
4. **劇本 C｜反問推翻**：
   - 使用者只回「好」時，AI 不推進階段。
   - 使用者提出反例時，題目卡記錄這條反問。
5. **劇本 D｜模式隔離**：
   - 選題對話的加號選單沒有 Create Image 和 English Tutor。
   - 一般對話的這兩個功能照常可用。
6. **劇本 E｜發散與匯出**：從候選題目開分支，然後匯出 Markdown。
7. **劇本 F｜失敗與降級**：
   - 中斷後端，或模擬題目卡 API 失敗：對話仍可繼續，題目卡維持原樣。
   - 重新整理後狀態可以還原。
8. **劇本 G｜裝置與存取**：
   - 手機寬度。
   - 深色和淺色主題。
   - 中英文介面。
   - 鍵盤操作切換鈕。
9. **紀錄表**：每一步都有「通過／失敗／備註」欄位，最後由作者簽核。

### 6.7 關卡紀錄

| 階段 | 日期 | commit | 單元 | 整合 | 回歸 | 冒煙 | 品質評估或備註 |
|---|---|---|---|---|---|---|---|
| 第一階段 | 2026-11-18 | 見 git log `feat(topic-finder): phase 1` | 通過 | 通過 | 通過（無新增失敗；既有失敗見下方） | — | 三項通過（見 6.8） |
| 第二階段 | 2026-11-18 | 見 git log `feat(topic-finder): phase 2` | 通過 | 通過 | 通過（無新增失敗；既有失敗經作者同意先不處理） | — | 見 6.9 |
| 第三階段 | 2026-11-18 | 見 git log `feat(topic-finder): phase 3` | 通過 | 通過 | 通過（無新增失敗） | 通過（Topic Finder 6/6） | 見 6.10 |

### 6.8 第一階段關卡細節（2026-11-18）

**本功能測試（全部通過）**

- 後端：`tests/backend/test_research_coach.py`（31）、`test_prompt_skills.py`；相關回歸 `test_stream_endpoint.py`、`test_conversation_context_service.py`、`test_tutor_profile_service.py`、`test_answer_style_service.py`。
- 前端：`utils/conversationKind.test.ts`、`store/conversation/workspace.test.ts`、`database/conversationRepo.kind.test.ts`、`services/syncService.test.ts`（新增 5 項）、`components/ConversationList.test.tsx`（新增 4 項）、`components/ChatInput/index.test.tsx`（新增 3 項）、`integration/topicFinderWorkspace.test.tsx`（2 項）。
- `npm run check:report:strict`：通過。

**既有失敗（與 master 逐項比對完全相同，本功能未新增任何失敗）**

- 後端完整套件：master 與本分支同為 13 failed、4 collection errors。
  - collection errors 是環境缺套件（`respx`、`livekit`）：`test_livekit_agent.py`、`test_perplexity_node.py`、`test_realtime_websocket_integration.py`、`test_stream_api_perplexity.py`。
  - failed：`test_edf_integration.py::test_compeer_daily_schedule_e2e`、`test_generate_title.py::test_generate_title_uses_english_for_english_first_query`、`test_gum_evolution.py`（2 項）、`test_gum_integration.py`（4 項）、`test_memory_injection_regression.py::...test_vector_failure_does_not_abort_bm25_search`、`test_multi_user_isolation.py::test_batch_process_observations_multi_user_isolation`、`test_realtime_routes.py::test_create_livekit_avatar_session_mints_dispatch_token_without_logging_secrets`、`test_suggestion_service.py`（2 項）。
- 前端完整套件：master 與本分支同為 42 failed，分布在 `chatContainer.avatarSplit`、`MessageList`（regression／ImageGenerationLoading／streamingCascade）、`RAGStatusPanel`、`SuggestedQuestions`、`TextSelectionToolbar`、`integration/`（TextSelection、explicitWebSearchFlow、guestChatAuthPrompt、liveTutorAvatar×2、mailboxFlow）、`messageItem.visual`。
- 依 6.2 第 4 點，這些既有失敗需作者確認後才能進入第二階段。

**對話品質評估**

- 國關朋友的原始對話紀錄不在 repo 內，改用同情境的固定腳本：國關所碩一想寫 AI 相關論文，共 6 輪，包含只回「好」、選定大題目、詢問研究方法、要求宣告過關。
- 兩種模式都用實際組出的系統提示與正式主模型（`google/gemini-3.8-flash`）、max_tokens 2048 執行。

| 指標 | 選題模式 | 一般模式 |
|---|---|---|
| 題目越收越窄 | ✅ 每輪短答並只問一個選擇；只回「好」時不推進，追問方向與理由 | 只回「好」也照樣往下講解 |
| 選擇點先提反對理由 | ✅ 開頭即「範圍過於龐大且難以測量」，沒有先稱讚 | 先說「主題很吸引人」，再替使用者寫好論文題目 |
| 不替使用者宣告過關 | ✅「我也不能替你宣布過關」，接著提出最強質疑 | 直接給出「真正過關的題目」 |

### 6.9 第二階段關卡細節（2026-11-18）

- 作者已確認：6.8 列出的既有失敗先不處理，可進入下一階段。
- 後端：`tests/backend/test_topic_card.py`（37 項），涵蓋：
  - patch 驗證；只有確認才推進階段與版本；重複確認不會重複推進；完成後不越界。
  - 摘要長度上限；每個階段只放該階段的焦點。
  - 抽取失敗、逾時、格式錯誤都會退回；資料表缺少時退回，且日誌不含內容。
  - SQLite 實際執行 SQL，驗證使用者之間互相隔離。
  - API：讀取、版本檢查、404、422、401、503。
  - 只有選題對話會排程抽取。
  - 另外跑了相關回歸：`test_summary_store.py`、`tests/unit/test_rls_isolation.py`。
- 前端：
  - `api/researchCoach/routes.test.ts`（4）、`services/topicCard.test.ts`（4）、`hooks/useTopicCard.test.tsx`（5）、`components/TopicCard/TopicCardPanel.test.tsx`（6）。
  - `integration/topicFinderCard.test.tsx`（2）：回答後出現建議、確認後才推進；題目卡 API 失敗時對話仍可繼續。
- 完整套件：後端 13 failed + 4 errors、前端 42 failed，與 master 逐項相同，沒有新增失敗；`npm run check:report:strict` 通過。

### 6.10 第三階段關卡細節（2026-11-18）

**本功能測試**

- 前端：
  - `utils/topicCardMarkdown.test.ts`（3）：各區塊、跳脫、空卡。
  - `components/TopicCard/TopicCardPanel.test.tsx`（新增 2）：分支探索按鈕、Markdown 下載。
  - `integration/topicFinderDivergence.test.tsx`（2）：兩個候選各開一條分支，分支繼承 `research_coach` 並只出現在選題空間；主線對話與題目卡不受影響；匯出內容包含淘汰清單與版本紀錄。
- 冒煙測試：`tests/e2e/topic-finder/flow.spec.ts`，執行指令 `npm run test:e2e:topic-finder --prefix frontend`，6/6 通過，涵蓋：
  - 切換與頂部切換鈕的位置。
  - 第一則訊息、標籤與加號選單。
  - 題目卡確認後重新整理仍在。
  - Chat 空間隔離。
  - 分支與匯出。
  - 390px 手機抽屜，無水平捲動。

**冒煙測試抓到並已修正的問題**

- 空白首頁的切換鈕原本掛在垂直置中的回應區上，實際位置在 y≈180px。改掛在主欄後，距頂部 16px。
- 選題對話在桌機上，第一則訊息被右上角的標籤列遮住。已讓訊息區從標籤列下方開始。

**回歸測試**

- 完整套件：後端 13 failed + 4 errors、前端 42 failed，與 master 逐項相同，沒有新增失敗；`npm run check:report:strict` 通過。
- 既有的 `@smoke`（例如 `tests/e2e/conversation-branches`）在 master 上就已失敗，原因是首次登入的引導導覽擋住畫面，屬於既有失敗。Topic Finder 的冒煙測試會主動略過引導導覽。

**交付**

- 實機測試劇本：`docs/tech_docs/dev_docs/research_coach_manual_test_script.md`。

### 6.11 改版：五個可跳躍的階段（2026-11-18）

依作者回饋改版，內容見 2.2 節。另外在首頁切換鈕的「選題」右邊加上「測試版」（英文 Beta）小標。

**後端**
- `topic_card.py`：階段改為 1～5（6 = 完成），舊資料的 0 讀成 1，不需要 migration。`confirm` 改為 `adopt`（只採用草稿、版本 +1、不換階段）；新增 `set_stage`。新增 `feasibility` 欄位和 AI 建議（`keywords`、`gaps`、`related`）；建議存在 `card` JSON 的 `_suggestions` 鍵，不需要新欄位。各欄位依階段開放。
- 新 API：`POST /api/v1/research-coach/{id}/stage`（`{stage: 1..6}`）；`/confirm` 回傳 `adopted`。
- 選題教練 skill 升到 `RESEARCH_TOPIC_COACH_SKILL_V2`：可跳躍的階段、第 2 階段引導使用者自己到外面找、第 5 階段反問可行性、對使用者只說「階段」。
- `execution.py`：選題對話在 `search_mode=auto` 時不搜尋（`orchestration.topic_finder_auto_search_skipped`）。

**前端**
- 題目卡：可點的 1～5 步驟列、階段主標題＋副標題（取代「這一關要回答」和「為什麼要問這個」）、AI 建議區（關鍵字可點擊複製）、「採用這份整理」／「我再想想」／「下一階段 →」、可行性檢查表、⚠️ 標示。
- 新 proxy：`/api/research-coach/[conversationId]/stage`。導覽、Markdown 匯出、標籤都改成「階段」。

**測試**
- 後端：`test_topic_card.py`（階段 0→1、adopt、set_stage、建議、可行性、各階段開放欄位、API）、`test_research_coach.py`（V2 規則）、`test_orchestration_service.py`（選題不自動搜尋）全部通過。完整套件 13 failed + 4 errors，與 master 相同。
- 前端：TopicCardPanel、useTopicCard、topicCard service、Markdown、proxy routes、三個整合測試全部通過；完整套件 42 failed，與 master 相同，沒有選題相關的檔案；`npm run check:report:strict` 通過。
- 冒煙：Topic Finder e2e 9/9 通過（含跳階段、手機寬度、英文 Beta 標籤一行顯示）。
- 真實模型抽查（gemini-3.8-flash）：第 2 階段回覆會問「會不會過幾年被局勢自己解決」，並給 Google Scholar、Connected Papers、智庫和可複製的關鍵字，沒有宣稱自己查過；第 1 階段抽取出 5 個關鍵字、2 個問句形式的缺口、3 個相關議題，沒有捏造論文。

### 6.12 借用 Academic Research Skills 的兩個做法（2026-11-18）

參考 `.agents/skills/academic-research-suite`（v3.22.0）的蘇格拉底模式。只借和本功能方向一致的兩點：其他規則（絕不直接回答、不產生候選、每層至少兩輪、devil's advocate、AI 給 FINER 分數設門檻）和作者已定的方向衝突，不採用。

- **研究倫理**：FINER 的「合乎倫理」是五個階段唯一沒涵蓋的，加為第 5 階段可行性檢查表的第五項（`ethics`），一樣照使用者的回答填，不打分數。
- **AI 提議標記**：`TopicCard.ai_candidates` 記錄由 AI 提出、使用者尚未改寫的候選；候選清單變動時自動過濾。題目卡、AI prompt 和 Markdown 匯出都會標示。
- 測試：後端、前端元件、Markdown 和整合測試都已更新並通過；`check:report:strict` 通過；e2e 9/9 通過。真實模型抽查：使用者自己想的題目沒有被標記，AI 提議、使用者只說「列進去」的兩題被標成 AI 提議。

### 6.13 推理與修改的循環：回頭檢查與題目卡缺口焦點（2026-11-24）

參考 Favero et al.〈Thinking Is Not Writing〉（MAIKE，2026）。這篇研究的證據是探索性的：65 人，文章分數沒有明顯差異。但「討論之後真的去修改」的次數和進步正相關。所以只借兩個機制，不借多組產生器、裁判挑題、每輪三個候選回覆這套多次呼叫 LLM 的流程，也不借只會發問的模式（理由同 6.12）。

- **回頭檢查**（對應論文的 Module E）：採用時，`revision_review` 比對採用前後的卡片。只有「修改」才會觸發（第一次填入不算），而且修改要碰到其他已經做過的階段才會觸發：
  - 已經做過的階段：該階段有採用過的版本，或該階段的欄位已經有內容。
  - 每個欄位會影響的階段：痛點 → 2–5；候選 → 2、5；母問題 → 2、4、5；操作化 → 5。
  - 下一輪 prompt 會出現 `【回頭檢查】`，教練只問一題，由學習者判斷；學習者說沒影響就接受，不追問。
  - 那一輪回答完之後，`refresh_pending_card` 會用該輪的開始時間清掉回頭檢查。如果是在回答串流途中才採用的，會留到下一輪。
- **題目卡缺口焦點**（對應論文的 Module A–C 精簡版）：`diagnose_gaps` 用規則找出目前階段的缺口，不呼叫模型。例如：痛點未填、候選全是 AI 提議、母問題未填、關鍵詞沒有量測方式、可行性未談或還不確定。
  - 第一個沒被放下的缺口會成為 `【本輪缺口】`；如果有待處理的回頭檢查，就讓回頭檢查先問。
  - 題目卡顯示「這輪先看：…」，旁邊有「換一個」按鈕，呼叫 `POST /api/v1/research-coach/{id}/focus/skip`。
  - 被放下的缺口在這段對話裡不會再成為焦點，但題目卡上的 ⚠️ 仍然保留。
  - 缺口 id 會把學習者的詞雜湊，日誌只記缺口種類。
- **儲存**：`review` 和 `skipped_focus` 和建議一樣存在 card JSON 的保留鍵（`_review`、`_skipped_focus`），不需要 migration。API 回應多一個推導出來的 `focus` 欄位。
- **過程指標**（只記事件，不記內容）：`topic_card.draft_adopted review_stages=`、`topic_card.review_asked`、`topic_card.focus_skipped focus_kind=`、`topic_card.prompt_steer steer=review|focus|stage`。
- 選題教練 skill 升到 `RESEARCH_TOPIC_COACH_SKILL_V3`，新增「回頭檢查」和「題目卡缺口焦點」兩條規則。

### 6.14 實測後的修正：教練守規矩與題目卡狀態 log（2026-11-24）

依 `temp/conversation_test_script.md` 實測：12 輪中 0 輪完全符合。教練回成長篇報告、開頭先稱讚、編造案例和數據、替使用者下結論，還把【回頭檢查】標籤直接寫進回覆；題目卡也記到 AI 的話。

**根本原因**：選題教練規則雖然放在 system prompt 中段，但後面還有每輪的「本回合回答策略」，選題話題常被判成 `DEEP_DIVE`，覆蓋了教練規則。

**A：教練守規矩**
- `context.py`：Topic Finder 不套用每輪的回答策略；教練規則和題目卡資料改放在 system prompt 最後，並註明「最後且優先的回答規則」。
- `answer_preparation.py`：選題回答的 token 上限為 `TOPIC_FINDER_MAX_TOKENS`（1200）；使用者強制思考時不套用。
- Skill 升到 `RESEARCH_TOPIC_COACH_SKILL_V4`，新增：
  - 回答 3–6 句、不用標題、結尾只問一題、不給 A/B 選單。
  - 開頭不稱讚；不編造案例和數據（開網路搜尋時也一樣）。
  - 重複送出時指回上一輪的內容。
  - 以使用者的用語為準；不替使用者下結論（含倫理）。
  - 內部標籤不寫進回覆；不宣稱已替使用者切換階段。
- `STAGE_FOCUS` 第 3、4 階段以使用者的母問題為準，第 5 階段倫理問題請他向學校的研究倫理審查單位確認。內部提示改標為「給你的內部指示，不要寫進回覆」。
- 抽取規則加上反例：使用者發問不等於同意；可行性預設「還不確定」；AI 的疑慮不算反問。
- 淘汰的題目忽略空白和標點後去重。
- 版本說明只留最近兩則不重複的說明，最多 80 字。

**B：題目卡狀態 log**
- Migration `20261125000000_research_topic_card_events.sql`，只能往後加，每筆存完整快照。
  - 事件：`proposed`、`adopted`、`rejected`、`stage_set`、`focus_skipped`、`review_set`、`review_cleared`、`extraction_failed`。
  - 來源：`api`（使用者按按鈕）、`background`（回答後的背景程序）、`chat`（在對話裡要求）。
- 和題目卡在同一個交易裡寫入，並用 savepoint 包住：log 寫入失敗只會少一筆，不會影響題目卡。
- 每段對話保留最新 500 筆；刪除對話或使用者時一起刪除；終端機日誌不記快照。
- 讀取：`GET /api/v1/research-coach/{id}/card/log?limit=200`（只限本人；`ENABLE_TOPIC_CARD_EVENT_LOG_API` 可關閉），前端 proxy 為 `/api/research-coach/{id}/log`。

### 6.15 在對話裡帶領每個階段（2026-11-24）

研究新手不知道什麼時候、怎麼切換階段。階段按鈕保留，但引導改在對話裡做：
- **進入新階段的開場**：每次切換階段（不論來自題目卡或對話）都會記下 `stage_entered`。下一輪教練先用一到兩句說明這個階段要做什麼、題目卡上看哪一欄，再問第一個問題。
  - 說明內容來自固定的 `STAGE_GUIDE`，不讓模型臨場發揮。
  - 該輪結束後由 `finish_turn` 清除；如果是在回答串流途中才切換的，會留到下一輪。
- **可以前進**：`ready_for_next` 只看已採用的內容判斷，規則如下：

  | 階段 | 可以前進的條件 |
  |---|---|
  | 1 | 有痛點，而且至少一個候選題目是使用者自己的 |
  | 2 | 有候選題目，而且在第 2 階段淘汰過題目或採用過版本 |
  | 3 | 有母問題 |
  | 4 | 每個關鍵詞都有證據 |
  | 5 | 可行性五項都談過 |

  - 符合條件時，教練在回覆最後問一次要不要前進，用 `offered_next` 記住，每個階段只問一次。
  - API 回傳 `next_stage`，輸入框上方出現「前往第 N 階段：…」（第 5 階段之後是「整理最終題目」）。
- **在對話裡切換**：按下那顆按鈕，會以使用者的身分送出「好，我們進到第 N 階段：…」。使用者自己打「我們到第五階段好了」「進下一階段」也一樣有效。
  - `requested_stage` 只在「移動動詞＋階段」時才切換；單純詢問（「第 4 階段要做什麼？」）不會切換。
  - 切換在組 prompt 前完成，所以同一輪就會開場；log 裡的來源記為 `chat`。

### 6.16 題目卡精簡：對話負責想，題目卡只負責記（2026-11-24）

依「沒有介面就是好介面」，題目卡只放使用者已經決定、之後需要回頭看的東西。實測 v7 的第 5 階段原本要滑三個畫面，精簡後一個畫面就看得完。

- **保留**：
  - 階段按鈕，和「第 N 階段 · 標題」合成一行（副標題只放在滑鼠提示）。
  - 題目大標：有母問題就顯示母問題，沒有就顯示痛點；痛點用灰色、最多兩行。
  - 第 1、2 階段可複製的搜尋關鍵字。
  - **只展開目前階段那一欄**：第 1–3 階段顯示候選題目，第 4 階段顯示看得見的證據，第 5 階段顯示可行性檢查。
  - 草稿問句和「需要／不需要」。
- **草稿只列出變動的部分**：新增或修改的項目前面加「＋」，被移除的候選題目用刪除線，新淘汰的題目附上原因。已經在題目卡上的內容不再重列。
- **收合**：其他欄位、淘汰的題目、反問、版本紀錄，全部收進「其他紀錄 · 淘汰 3 · 反問 3 · 版本 7」。
- **移到對話**：
  - 「這輪先看」和回頭檢查提示（教練在對話裡問）。
  - 「換一個」：改成在對話裡說「先放著」，由抽取欄位 `focus_set_aside` 處理，原本的 `/focus/skip` API 移除。
  - 「下一階段 →」（改由對話裡的按鈕處理，見 6.15）。
- **拿掉**：固定提示句、可能的研究缺口和相關議題（不再顯示，也不再要求模型產生）。
- 欄位名稱「怎麼證明（…）」改成「看得見的證據」；草稿問句改成「要更新到題目卡嗎？」。

## 7. 其他品質要求

- 前端改動要先跑相關的 Vitest 檔案，再跑全部套件。
- 日誌不能包含使用者文字、題目卡內容或模型輸出。每個階段的整合測試都至少要有一個案例檢查這件事。
- 新的介面元件要支援深色和淺色主題、手機寬度，以及鍵盤操作。

## 8. 不在這次範圍內

- 自動搜尋文獻或判斷研究缺口：AI 只引導使用者自己去查（第 2、5 階段），題目卡上的研究缺口只是待查證的問句。
- 在選題對話裡使用語音或 avatar（Live Tutor）。
- 分享快照時顯示題目卡。
- 讓 AI 自動判定或切換階段：階段一律由使用者選。

## 9. 待確認事項

- `Topic Finder` 的英文標語和輸入框提示的確切文字。
- 第二階段的題目卡抽取要用哪個模型，以及成本上限。
- 舊使用者第一次看到側欄切換時，是否需要 onboarding 提示（可以比照 `services/onboardingFeatures.ts`）。
