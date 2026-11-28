# 借鏡 opencode 的 AREQA 改進：審查結果與實作細則

- 日期：2026-11-28
- 對照版本：opencode `eeeeaa0d`（2026-11-27），AREQA `6b13f9d`（master）
- 上游文件：`docs/tech_docs/opencode_project_and_areqa_improvements.md`（初步規劃）
- 狀態：P0–P6 都已實作（見下方進度表）。新功能都在 flag 後面，預設關閉，下一步是 staging 驗證和 eval

### 實作進度（2026-11-28）

| 階段 | 狀態 | Commit | 備註 |
|---|---|---|---|
| P3 文字被清空的 bug | 完成 | `d3e3700` | 先寫 regression test，確認修正前會失敗 |
| P0 量測腳本 | 完成 | `dadcd7a` | `scripts/performance/report_turn_latency.py`。範例 log 中沒附件的對話 `cached_tokens` 是 0% |
| P1-a 摘要保留清單 | 完成 | `84ca68c` | 字數上限維持 450 字，還沒用 live eval 驗證 |
| P1-b 背景預算 | 完成（flag 預設關閉） | `84ca68c` | 設計改成在 `prepare_history` 內排程，並加上 hysteresis。見 Q1 |
| P2 stable prefix | 完成，eval 通過（flag 和 rollout 都是 0） | `6069aa2`、`e36a89d` | Q4 的 eval 已跑（`scripts/evaluate_stable_prefix.py`，gemini-3.8-flash）：遵守指示 B 24/24、A 23/24，沒有任何一項 B 比 A 差。**快取發現**：原本在「最新一輪前一則訊息」加 breakpoint，每輪都會重寫 7.6–8.4K tokens 的快取卻讀不回來，已改成靠 implicit caching，第 2 輪起可讀 ~4.1K tokens、寫入 0。A 版每輪都是 0 |
| P4 AgentProfile | 完成 | `3ec49d0`、`f2e40cd` | **`services/teaching/profiles.py` 的 `ProfileCapabilities` 已經是 AgentProfile**（這份 spec 寫完前就有了）。所以不另外新增模組，改成加 `topic_card` capability。轉場提示依 Q2 存在 Redis（`profile_history.py`，TTL 7 天，讀取上限 300 ms，失敗時只是少了提示） |
| P5 Outcome 重構 | 完成 | `ace7e2f`、`4bfd9c0` | 先錄 golden SSE（6 條路徑），重構後輸出完全相同。`_run_provider_step` + `StepOutcome` + `_AnswerPipeline`；`SSEAdapter.emit` 會自動編號 |
| P6 工具迴圈 | 完成（flag 和 rollout 都是 0） | `2e5600b` | 依 Q3，第 1 步的文字直接串流。搜尋設定和結果格式抽到 `web_search_call.py`，兩條搜尋路徑共用。`memory_query` 還沒開放（照 spec） |

**P6 已知限制**：
- 走模型搜尋的回合，post-turn 拿到的 `use_web_search` 是 False，所以依賴這個值的後續處理不會觸發。
- 第 1 步如果同時呼叫了生圖和搜尋，生圖會被丟掉。
- ~~跟分類器的比較只有 log~~：已補上（`6c0e72f`）。走模型搜尋的回合會在背景跑一次分類器（shadow），`scripts/performance/report_model_search.py` 會算出兩者的一致率和 TTFA 對照。recall 目前只是跟分類器比的代理指標；spec 的淘汰條件要的是有標註的查詢集，這部分還沒建。

---

## 1. 審查結論（摘要）

初步規劃的方向正確：不照搬 opencode 的完整 agent 迴圈，只挑對教學產品延遲友善的部分。不過有幾個事實需要更正，排序也建議調整：

| # | 原規劃 | 審查意見 |
|---|---|---|
| 1 | 背景預算摘要 | **同意，維持第一優先**。另外補上 opencode 的關鍵細節：預算出來的摘要和現在的對話之間，中間那段要**原樣保留**（verbatim tail），不然下一輪還是得同步摘要。|
| 2 | AgentProfile | 同意，但風險比原文說的低：AREQA 每輪都會重建 system prompt，舊的 tutor 規則不會留在歷史訊息裡。`selected/unselected` 只需要做成「一輪的轉場提示」就夠了。|
| 3 | 有上限的工具迴圈 | 同意要做，但**要排在第 4 點之後**：迴圈需要先有型別化的 step outcome。現有的 shadow 也沒辦法直接拿來比較，要另外設計（見 §6）。|
| 4 | 型別化 Outcome | **提前**，作為第 3 點的前置重構。|
| 5 | 工具錯誤回給模型 | 原文對現況的描述不正確（見 §2）。不過我發現一個**可以馬上修的 bug**：參數不合法時，文字回答會被清掉。|
| 6 | 摘要保留清單 | 同意，而且**一定要跟第 1 點一起上線**。改 `_INSTRUCTION` 會讓所有 checkpoint 失效，分兩次改就會讓使用者冷啟動兩次。|
| 新 | Gemini prefix cache | 原文「沒有確認的部分」**已經確認是問題**：沒有附件的對話，system prompt 每輪都會變，prefix cache 不會命中。建議新增為一個獨立項目。|

建議的上線順序：**P0 量測 → P1（#6 + #1）→ P2（prompt cache）→ P3（#5 的 bug 修正）→ P4（#2）→ P5（#4）→ P6（#3 + #5 的完整版）**。

---

## 2. 事實更正（對照 AREQA 原始碼）

| 原文說法 | 實際情況 | 位置 |
|---|---|---|
| decide_search 的 timeout 是 2 秒 | 函式預設 2.0 秒，但呼叫端傳的是 **1.5 秒** | `services/orchestration/routing.py:30-36` |
| 摘要最長可以等 20 秒 | 有 checkpoint 時是 20 秒；**冷啟動（第一次摘要）是 45 秒** | `config.py:25-26`、`history.py:255` |
| generate_image 參數不合法時會變成 `{}` 繼續跑 | `{}` 只用來決定 `presentation`。`image_generation.py:211` 會重新解析，失敗時送出 `IMAGE_GENERATION_FAILED` 的錯誤區塊，所以不是靜默吞掉。**但是**：`{}` 讓 `presentation` 預設成 `image_only`，於是 `accumulator = ""`，**模型已經寫好的文字回答會被清空** | `stream.py:444-452` |
| web_search 沒有開放 | 它**已經註冊在 ToolRegistry**（`service.py:111`），只是沒有放進主模型的 tool schema。`memory_query` 則**還沒註冊** | `services/orchestration/service.py:110-117` |
| 已經有 shadow routing，可以拿來比較 | 現在的 shadow **只在 auto routing 關閉時才執行**，比的是「分類器 vs 規則」，不是「分類器 vs 模型自己呼叫工具」 | `routing.py:86` |
| 記憶模組搬移還沒 commit | 已經落地（`303bcdc refactor(memory): consolidate flat memory modules`）。這一點不再阻擋 | git log |
| ToolBudget 的 external 上限會讓搜尋和生圖互搶 | 不會。生圖有自己的 `budget_scope="image_generation"` | `image_generation.py:67-75` |

**已確認原文未確認的部分**：`prompt_cache.py` 的 docstring 直接寫著「AREQA's system prompt changes every turn (policy, working memory, learner state)」。`apply_document_cache_layout` 只有在訊息裡有 `DocumentPart` 時才會把每輪的指示搬進 `<turn_instructions>`，**沒有附件的對話完全拿不到 prefix cache**。

---

## 3. opencode 對應機制的重點（實作時要借的細節）

| 機制 | opencode 位置 | 要借的細節 |
|---|---|---|
| 背景摘要 | `packages/core/src/session/compaction.ts` 的 `precompute` / `usePrecomputed` | (a) 距離門檻還有 `PRECOMPUTE_LEAD` 時就開始；(b) 摘要範圍只到「最新一則 assistant 之前」，所以讀得到 cache；(c) **摘要先保留起來，等真的需要 compaction 時才換上**，免得每一步都改到 prefix；(d) 換上時，摘要之後的部分原樣保留，但有 `tailLimit` 上限（預算的 40%）；(e) 歷史被改過（`heldIndex < 0`）就丟掉；(f) 失敗 2 次就停（`PRECOMPUTE_MAX_FAILURES`）；(g) 下一輪如果摘要還在算，就等它算完 |
| 摘要 prompt | 同上的 `SUMMARY_TEMPLATE`、`SUMMARY_RULES` | 固定的段落標題；回覆沒有照模板時，提醒一次（`NUDGE`）再算失敗；「未回答的使用者問題要逐字保留」|
| Step outcome | `session/runner/step.ts:30` | `Completed{needsContinuation}`、`Retry`、`Compacted`、`OutputLimit`；由外層統一決定下一步 |
| 步數上限 | `session/runner/max-steps.ts` | 到達上限時，加一段「工具已停用，只能用文字回答」的 prompt，而不是直接截斷 |
| Agent 指示的進出 | `instructions/agent.ts` | `active`、`inactive`、`changed` 三種文字；離開時要說明「使用者要求的事仍然有效」，不然模型會連使用者加的限制一起丟掉 |
| 工具錯誤 | `step.ts:155-160` | `Tool.Error` 會變成 `failTool` 的 tool result，回給模型 |

和 opencode 不同的地方：opencode 的 instructions 會以 delta 的形式**存在歷史訊息裡**（為了保住 cache），所以一定要明確送 `unselected`。AREQA 每輪都重組 system prompt，所以只需要轉場的那一輪提示一次。

---

## 4. P0：先量測（約 0.5 天）

所有項目都需要基準值。現有的 log 大部分已經夠用：

- `history.prepared`：`cache_hit`、`cache_source`、`covered`、`total`、`degraded`
- `history.compaction_started` 到 `history.summary_completed` 的 `elapsed_ms`
- `orchestration.provider_finish`：`prompt_tokens`、`cached_tokens`、`cache_write_tokens`
- trace marks：`search_routing_started` / `finished`、`main_model_finished`

**要做的事**：寫一個 `scripts/report_turn_latency.py`，從 log 算出以下數字：
1. 出現「正在整理較早對話」狀態的回合比例，以及這些回合的 p50/p95 等待時間
2. 有附件和沒附件的對話各自的 `cached_tokens / prompt_tokens`
3. search routing 的 p50/p95 延遲，以及 should_search 為 true 的比例

這三個數字分別是 P1、P2、P6 的成功指標。

---

## 5. 各項實作細則

### P1-a：摘要 prompt 加入學習專用的保留清單（#6）

**檔案**：`backend/services/conversation/history.py`（`_INSTRUCTION`）

**改動**：在現有的段落清單（Current goal; Active decisions and constraints; …）之後，加上一個 `Learning state` 段落，要求原樣保留以下內容：
- 學習目標，以及學生自己說的程度或期限
- 學生的迷思概念：**用學生原本的說法**記錄，並註明是否已經更正
- 學生還沒得到回答的問題：**逐字保留**（借用 opencode 的規則）
- 練習進度：題目或任務、嘗試了幾次、最後一次回饋的重點
- 已經做出的教學承諾，例如「不會直接幫你寫完段落」、「先讓你自己試一次」
- 判斷 ZPD 或 EDF 時所根據的對話證據（**只記證據，不寫結論**；learner state 由 EDF 管線負責，摘要不要重複）

**注意事項**：
- 改 `_INSTRUCTION` 之後，`scope` 的 hash（`history.py:226`）會跟著變，所以**所有現存的 checkpoint 都會失效**，每個長對話都會冷啟動一次（最長 45 秒）。所以這項要和 P1-b 一起上線，讓背景預算負責吸收這次冷啟動。
- 450 字的上限可能不夠，建議改成 550 字（`summary_tokens=1536` 還裝得下）。這要用 eval 確認，不要直接改。

**測試**：`tests/backend/test_history_summary_retention.py`
- 準備 3 到 5 份固定的教學對話（含迷思、未回答的問題、練習進度），用 stub client 驗證送出去的 prompt 有包含新段落（純單元測試）
- 另外加一個需要時才跑的 live eval（依照 Teaching Layer eval 的慣例），檢查迷思概念和未回答問題是否保留下來

### P1-b：較早對話的摘要改成背景預先計算（#1）

**目標**：讓長對話不再出現「正在整理較早對話」的等待；摘要失敗時，行為和現在完全一樣。

**新增設定**（`config.py`，預設關閉）：
```
enable_conversation_summary_precompute: bool = False
conversation_summary_precompute_ratio: float = 0.75   # chat_bytes / budget 到這個比例就開始預算
conversation_summary_precompute_wait_seconds: float = 3.0  # 下一輪最多等背景任務多久
conversation_summary_keep_turns: int = 2               # 背景摘要不涵蓋最後 N 個 user turn
```

**步驟 1：重構 `history.py`（行為不變）**
- 把 `compact()` closure 抽成模組層級的函式 `extend_summary(scope, old, prefixes, summary, covered, *, client, model, summary_tokens, summary_context_tokens) -> tuple[str, int]`
- 把切分邏輯（`instructions` / `old` / `recent`，以及 `budget` 的計算）抽成 `split_history(...)`
- 把 checkpoint 查詢（先查記憶體 `_CACHE`，再查 DB）抽成 `lookup_checkpoint(scope, old, prefixes)`
- 現有的測試全部要通過，這一步單獨 commit

**步驟 2：新模組 `backend/services/conversation/summary_precompute.py`**
```python
class SummaryPrecomputer:
    _inflight: dict[Scope, asyncio.Task]   # 每個 scope 同時只跑一個
    _failures: dict[Scope, int]            # 失敗 2 次後，這個 scope 就不再預算（和 opencode 一樣）

    def maybe_schedule(self, *, transcript, tools, user_id, conversation_id, ...) -> None
    async def wait_inflight(self, scope, timeout) -> None
```
- `maybe_schedule` 要用和 `prepare_history` 相同的 `split_history` 算出 budget。`chat_bytes < ratio * budget` 時就跳過。
- 涵蓋範圍是 `transcript` 中最後 `keep_turns` 個 user turn **之前**的訊息。這樣下一輪的 `old` 一定比它長（`covered <= len(old)`），checkpoint 才用得上。
- 不要用 `PostTurnService.queue_post_turn_work`，因為它固定 2 秒 timeout。要自己保留 task 的 strong reference，timeout 用 `conversation_summary_cold_timeout_seconds`。
- 寫入的位置還是現有的 `_CACHE` 和 `summary_store.save`，**不新增儲存層**。

**步驟 3：在 completion.py 觸發**
- 放在 `completion.py` 的 `queue_post_turn_work` 旁邊。傳入的 transcript 是 `messages + [{"role": "assistant", "content": answer_content_accumulator}]`。
- **這一步是整個功能成敗的關鍵**：hash 是對整個 message dict 做 `json.dumps(sort_keys=True)`，背景用的 transcript 必須和下一輪瀏覽器送回來的 messages **逐 byte 相同**。要先確認以下幾點（見 §7-Q1）：
  - 瀏覽器回傳的 assistant content 是 `accumulator` 原文，還是經過 `PublicAnswerFilter` 或 image block 處理後的版本？
  - 附件訊息（`DocumentPart`）序列化之後是否一致？
  - 如果做不到逐 byte 相同，退路是改成在**下一輪的 `prepare_history` 一開始**就排背景任務（範圍是當輪的 `old`），然後在該輪結束後才用到。這樣會晚一輪生效，但 hash 一定一致。

**步驟 4：`prepare_history` 前景的改動**
1. 開始時，如果這個 scope 有正在跑的任務，呼叫 `wait_inflight(scope, precompute_wait_seconds)`
2. **verbatim gap 規則（借用 opencode 的 tail）**：查到 checkpoint 涵蓋前 `k` 則，而且 `k < len(old)` 時，如果 `instructions + summary + history[k:]` 放得進 budget，就把 `start` 移到 `k`，**不呼叫摘要模型**。放不下，才同步摘要 `old[k:]` 這一小段。
3. 只有在完全沒有 checkpoint 時，才走現在的完整同步路徑

**安全性**：
- 對話被編輯、分支或重試時，prefix hash 會對不上，查詢自然就 miss，這部分沿用現有設計
- 背景任務的 log 只能有 count、時間和原因代碼，不能有文字內容
- 多個 worker 的情況：`wait_inflight` 只在同一個 process 有效；跨 worker 靠 DB checkpoint。這樣可以接受，最差的情況就是退回同步路徑

**Log**：
- `history.precompute_scheduled conversation_id covered target ratio`
- `history.precompute_skipped reason=below_ratio|inflight|failure_limit|anonymous`
- `history.precompute_completed elapsed_ms covered`
- `history.precompute_failed reason error_type`
- 在 `history.prepared` 加上 `precompute_wait_ms`、`gap_messages`、`sync_summary=True|False`

**測試**：`tests/backend/test_history_precompute.py`
- post-turn 的 transcript 和下一輪輸入的 prefix hash 一致（用真實的 message 形狀）
- verbatim gap 放得下時，stub client 被呼叫的次數是 0
- 有任務在跑時，前景會等它，而且等不到也不會出錯
- 編輯過較早的訊息時，checkpoint 會 miss，退回同步摘要
- 背景任務失敗 2 次後就不再排程
- flag 關閉時，行為和現在完全一樣

**成功指標**：P0 第 1 項（等待狀態出現的比例）下降 80% 以上，而且 `degraded` 的比例沒有上升。

### P2：沒有附件的對話也套用 prefix cache 的 layout（新增項目）

**檔案**：`backend/services/conversation/prompt_cache.py`

**改動**：加一個 `apply_turn_instruction_layout(messages)`。沒有 `DocumentPart` 時也一樣：system 改用 `STABLE_SYSTEM_PROMPT`，每輪的指示放到最新一則 user 訊息開頭的 `<turn_instructions>`。歷史摘要（P1 產生、以 user role 插入的那則）放在 stable prefix 之後。

**風險**：把指示搬進 user 訊息，可能讓模型比較不遵守指示。有附件的對話已經這樣跑了一段時間，可以先比較兩組的品質 eval。用 flag 控制（`enable_stable_system_prefix`），並且用 `CapabilityPolicy.rollout_enabled` 做百分比上線。

**指標**：P0 第 2 項，也就是沒附件對話的 `cached_tokens / prompt_tokens`。

### P3：修正「參數不合法時文字回答被清空」（#5 的最小版本，可以馬上做）

**檔案**：`backend/services/conversation/stream.py:446-452`

**改動**：`json.loads` 失敗時，不要讓 `presentation` 走預設的 `image_only`。要保留 `accumulator`，並記一筆 `orchestration.tool_arguments_invalid tool=generate_image`。其餘維持現在的錯誤區塊流程。

**測試**：在現有的 stream 測試加一個案例：模型先輸出文字，再送出不合法的 tool arguments。驗證最後的 `answer_blocks` 仍然有那段文字，而且有 error image block。

### P4：AgentProfile（#2）

**新模組**：`backend/services/conversation/agent_profile.py`
```python
@dataclass(frozen=True, slots=True)
class AgentProfile:
    profile_id: str                 # "general" | "english" | "research_coach"
    label: str
    prompt_block: Callable[[], str] # 包裝現有的 render_*_prompt，不搬動 skill 檔案
    allowed_tools: frozenset[str]   # 例如 {"generate_image"}；research_coach 是空集合
    max_image_slots: int | None     # None 代表沿用每輪的計算結果
    topic_finder: bool
    max_tool_steps: int = 1         # P6 之前都是 1
    leave_note: str = ""            # 離開這個 profile 時，轉場那一輪要說的話

def resolve_agent_profile(*, tutor_profile: object, prompt_profile: object) -> AgentProfile
```
- 現在其實有**兩個維度**：`tutor_profile`（general/english）和 `prompt_profile`（Research Coach）。`resolve_agent_profile` 是唯一合併兩者的地方。**API 欄位不變**，維持向下相容。
- 搜尋政策和記憶範圍**這一版先不放進來**：`CapabilityPolicy` 和 `MemoryPolicy` 維持現狀，只接收 profile 當參數。等真的有第二個需要不同搜尋或記憶政策的 tutor 時再加，避免過早抽象。

**要改的呼叫點**：
- `execution.py:223`、`execution.py:469`：`is_research_coach(...)` 改成 `profile.topic_finder`
- `stream.py:128`：`tools_for_image_slots` 改成依 `profile.allowed_tools` 和 `max_image_slots` 過濾
- 組 prompt 的地方（`prompting.py`）：改成呼叫 `profile.prompt_block()`

**轉場提示**：
- 需要知道上一輪用的是哪個 profile（見 §7-Q2）。拿到之後，如果上一輪的 profile 不等於這一輪，就在這輪的 `<turn_instructions>` 加上上一個 profile 的 `leave_note`，**只加這一輪**。
- English Tutor 的 `leave_note` 參考 opencode 的寫法：「你已經不是 English Tutor。不需要再遵守 English Tutor 的規則（例如反代寫規則）。使用者自己提出的要求仍然有效。」
- log：`orchestration.agent_profile_transition from=english to=general`

**測試**：`resolve_agent_profile` 的組合表測試；Research Coach 不會拿到 `generate_image`；轉場的那一輪才會出現 leave_note，下一輪就沒有。

### P5：型別化的 step Outcome（#4，P6 的前置）

**原則**：行為完全不變的重構，用 golden SSE 測試把關。

**改動**：
1. `stream.py` 的單次串流拆成 `run_step(...) -> StepResult`
   ```python
   class StepOutcome(Enum):
       COMPLETED = "completed"
       OUTPUT_LIMIT = "output_limit"          # 現在的 finish_reason == "length"
       CONTEXT_OVERFLOW = "context_overflow"  # 現在的 context_recovery.py
       TOOL_CALLS = "tool_calls"              # 有 pending 的 tool call
   @dataclass
   class StepResult:
       outcome: StepOutcome
       text: str
       tool_calls: list[PendingToolCall]
       usage: Any
   ```
2. 由外層的 driver 依 outcome 決定下一步：OUTPUT_LIMIT 時補上「回覆繼續」的提示；CONTEXT_OVERFLOW 時呼叫 `context_recovery` 重試一次；TOOL_CALLS 時執行生圖（現在的邏輯）
3. SSE 序號：`sse_adapter` 改成自己維護遞增的 counter，拿掉 `execution.py:195` 那種手動對齊的序號和註解

**測試**：先為現有的 4 種路徑錄 golden SSE 序列（一般回答、length 截斷、context overflow 重試、生圖），重構前後都要完全一致。這一步先做，再開始重構。

### P6：有上限的工具迴圈（#3 + #5 的完整版）

**範圍**：只在 `SearchMode.AUTO`、沒有附件、而且 flag `enable_model_tool_routing` 開啟時生效。其他模式維持現在的路徑。

**改動**：
1. 把 web_search 的 schema 放進主模型的 tools（只有 `query: string` 一個參數）。這一輪**跳過** `decide_search`
2. driver 迴圈最多跑 `profile.max_tool_steps = 2` 步：
   - 第 1 步：如果 outcome 是 TOOL_CALLS(web_search)，送出 status SSE「正在搜尋資料」，透過 `tool_registry.execute` 執行，結果走現有的 retrieval/citation 格式
   - 第 2 步：tools 關掉，再加一段類似 opencode `MAX_STEPS_PROMPT` 的精簡版提示：「不能再呼叫工具，請根據搜尋結果回答並標註來源」
   - 第 1 步如果在呼叫工具前已經輸出了文字，要決定要不要保留（見 §7-Q3）
3. **工具錯誤回給模型（#5）**：參數不合法或執行失敗時，送 `{"error": "invalid_arguments" | "tool_failed"}` 當作 tool result，第 2 步由模型用文字說明。不要重試工具，因為步數上限只有 2
4. `memory_query`：**這一版不開放**。它還沒註冊，而且必須先確認 `MemoryPolicy` 的 scope 和使用者隔離會在 handler 裡強制執行。等 web_search 穩定之後再另外排

**比較方式（取代原文的 shadow 構想）**：
- 這個迴圈沒辦法 shadow 執行，因為它就是主模型的呼叫本身，跑兩次成本會加倍。
- 改用 `CapabilityPolicy.rollout_enabled` 做 5% 到 10% 的灰度，比較 P0 第 3 項的指標：TTFT 的 p50/p95（分成要搜尋和不搜尋兩組）、搜尋率、每輪成本
- 離線部分：參考 `scripts/benchmark_paper_intent.py` 的格式，建一份有標註的查詢集（需不需要搜尋），比較分類器和「主模型第 1 步有沒有呼叫工具」的準確率
- **淘汰條件**：要搜尋的回合 p95 TTFT 變差超過 2 秒，或是搜尋召回率比分類器低超過 5 個百分點

---

## 6. 不建議做的項目（同意原文）

Effect 或 event-sourcing 重寫、plugin hook、Code Mode、萬用字元版的 MemoryPolicy、背景 subagent：都維持不做。另外補一項：**opencode 的 native compaction 和 subagent 的 checkpoint**（`compaction-subagents.ts`、`compaction-background.ts`）也不用借，AREQA 沒有對應的情境。

---

## 7. 待決問題（開工前需要確認）

- **Q1（已解決，2026-11-28）**：不再從 `completion.py` 用瀏覽器回送的訊息排程，改在 `prepare_history` 裡用 provider 形式的訊息排程，只依賴現有 checkpoint 已經依賴的「歷史訊息 hash 跨輪穩定」。另外加了 hysteresis：背景摘要涵蓋到 tail ≤ 剩餘空間的 `TAIL_SHARE`，前景優先用「checkpoint + 原樣 tail」，避免過門檻後每輪都要同步摘要一小段。實作見 `summary_precompute.py`、`history.py`。原問題：
  （原 P1-b 步驟 3）瀏覽器在下一輪送回來的 assistant 訊息，和後端的 `answer_content_accumulator` 是否逐 byte 相同？有 image block 或引用過濾時又是如何？如果不同，P1-b 就要改用「晚一輪生效」的退路。
- **Q2（阻擋 P4 的轉場提示）**：上一輪的 tutor profile 要從哪裡拿？選項有三個：(a) 前端多送一個 `previous_tutor_profile`；(b) 存在 conversation 這筆資料上；(c) 存在訊息的 metadata 裡。建議 (b)，因為伺服器端可信，又不用改前端的 contract。
- **Q3（P6）**：第 1 步在呼叫工具之前就輸出的文字，要直接串流給使用者，還是先暫存、等第 2 步一起決定？前者 TTFT 比較好，但可能出現「我來查一下……」這種贅句。
- **Q4（P2）**：把每輪的指示搬進 user 訊息，對 Gemini 遵守指示的程度有沒有可測量的影響？有附件的對話是否已經有相關的 eval 數據？

---

## 8. 工作量估計

| 階段 | 估計 | 依賴 |
|---|---|---|
| P0 量測 | 0.5 天 | 無 |
| P1-a 摘要 prompt + eval | 1 天 | P0 |
| P1-b 背景預算 | 3 到 4 天 | Q1、P1-a |
| P2 stable prefix | 1.5 天 + eval | Q4 |
| P3 bug 修正 | 0.5 天 | 無，可以馬上做 |
| P4 AgentProfile | 2 天 | Q2 |
| P5 Outcome 重構 | 2 到 3 天 | 先錄 golden SSE |
| P6 工具迴圈 | 4 到 5 天 + 灰度期 | P4、P5 |
