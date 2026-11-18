# Topic Finder（選題）開發計畫與任務清單

- 狀態：規劃完成，尚未實作
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

### 2.2 五道篩子

| # | 篩子 | 問使用者的話 | 白板上的對應 |
|---|---|---|---|
| 1 | 時間：技術進步會不會自動解決它？ | 「兩年後模型更強了，這題還成立嗎？」 | 記憶、心智建模、沉默期訊號被這道刪掉 |
| 2 | 最簡方案：一個簡單做法就能解決嗎？ | 「最偷懶的解法是什麼？它為什麼不夠？」 | 奧卡姆剃刀卡片 |
| 3 | 核心：拿掉工具和案例，問題還在嗎？ | 「如果不准用你的系統，你還想知道什麼？」 | 「AI 的答覆如何影響人類的認知」 |
| 4 | 可測：每個名詞都能寫成「我用＿＿測量」嗎？能被推翻嗎？ | 「哪個詞你還填不出測量方式？」 | 8/17 的操作化表；「量效果，不量內容」 |
| 5 | 現實：有人做完了嗎？我做得到嗎？場域和指導教授容得下嗎？ | 「以你現在的資源，能做的最小版本是什麼？」 | LearnLM 缺口、邱老師的 IPA 計畫、最後先寫回顧論文 |

### 2.3 三條貫穿規則

1. **反問要能推翻 AI 的判斷。** AI 不能宣告「過關」，只能說「我看不出反例，你自己能想到嗎？」過關一定由使用者確認。
2. **砍掉的題目要留紀錄，不要直接刪。** 淘汰清單要記下「被哪道篩子砍掉、理由、能不能降級保留」。被砍的題目後來常以「要有可檢驗的機制才值得加入」的形式回來。
3. **每一版都要標版本號**，寫明這版改了什麼、為什麼改。

### 2.4 對話行為規則

- 一次只推進一個階段，只問該階段的篩子問題。
- 使用者要資訊時直接給，例如「ICAP 是什麼」「這個領域有哪些經典研究」；使用者在判斷或選擇時才反問。這是為了平衡講解和提問：作者 8/18 自己發現「一直被問會煩」，Manuscript 的結論也不支持固定「只答」或「只問」的規則。
- 使用者做選擇時不先稱讚，先提出最強的反對理由，再請使用者回應。
- 使用者說「這量不了」時，提示他換量化對象：「它會造成什麼可以觀察到的行為改變？」
- 使用者只回「好」、沒有提出自己的反問時，AI 不替他補完反問，也不推進階段。

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

## 6. 任務清單

### 第一階段：MVP（空間 + skill）

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

測試：
- [ ] 後端：`conversation_kind` 正規化；skill payload 的 schema 驗證；選題對話會注入 skill；skill 載入失敗會退回；選題對話裡會忽略 english 和生成圖片。
- [ ] 前端：
  - 沒有 `kind` 的舊對話視為 `chat`。
  - 側欄切換會篩選列表。
  - 分段切換只在空白首頁出現，送出第一則訊息後消失。
  - 選題對話的加號選單隱藏指定項目。
  - 分支繼承 `kind`。
  - sync 會帶上 `kind`。
- [ ] 對話品質評估：以國關朋友那份對話紀錄的開頭當腳本，比較一般模式和選題模式。指標包括：題目有沒有越收越窄、有沒有在選擇點提出反對理由、有沒有替使用者宣告過關。

### 第二階段：題目卡

- [ ] migration：`research_topic_cards` 資料表和 RLS。
- [ ] 後端 service：讀寫題目卡、在背景抽取 `card_patch`（結構化輸出，有長度上限）、確認後推進版本。
- [ ] FastAPI 路由和 Next.js proxy：`GET card`、`POST confirm`。
- [ ] prompt 注入題目卡摘要；階段規則由後端決定，每個階段只放該階段的篩子問題。
- [ ] 前端右側題目卡面板（手機版用抽屜）、確認過關按鈕、上方標籤顯示階段。
- [ ] 測試：
  - 沒有確認就不能推進階段。
  - 抽取失敗時對話不受影響。
  - 摘要長度上限。
  - 日誌不包含內容。
  - 面板和抽屜的響應式顯示。

### 第三階段：發散與匯出

- [ ] 在「發散」步驟，為每個候選題目開一條分支；主線題目卡只保留通過篩選的題目。
- [ ] 題目卡和版本歷史可以匯出成 Markdown。

## 7. 驗收與品質關卡

- 前端先跑相關的 Vitest 檔案，再跑 `npm run check:report:strict`。
- 後端相關的 pytest 都要通過。
- 確認一般對話的行為完全不變：沒有 `kind` 的舊對話、English Tutor、Create Image、分支都要回歸測試。
- 第一階段完成後，先做對話品質評估，再決定是否進入第二階段。

## 8. 不在這次範圍內

- 自動搜尋文獻或判斷研究缺口：第五道篩子只引導使用者自己去查。之後可以再評估接上現有的搜尋工具。
- 在選題對話裡使用語音或 avatar（Live Tutor）。
- 分享快照時顯示題目卡。
- 讓 AI 自動判定階段：階段推進一律由使用者確認。

## 9. 待確認事項

- `Topic Finder` 的英文標語和輸入框提示的確切文字。
- 第二階段的題目卡抽取要用哪個模型，以及成本上限。
- 舊使用者第一次看到側欄切換時，是否需要 onboarding 提示（可以比照 `services/onboardingFeatures.ts`）。
