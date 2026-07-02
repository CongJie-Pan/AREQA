# ComPeer × EDF × 記憶系統 問題分析與改善計畫

> **日期**：2026-07-02
> **分析者**：基於用戶實際使用對話紀錄（`temp/areqa-chat-2026-07-02.md`、`temp/compeer_converstaion.txt`）與原始碼審查
> **涉及檔案**：
> - `backend/services/compeer_scheduler.py`
> - `backend/gum_integration.py`
> - `backend/compaction.py`
> - `backend/memory_store.py`
> - `backend/services/orchestration_service.py`

---

## 背景：本次問題的成因脈絡

用戶在對話中說「我想要入門紅樓夢」，明確表示自己是**初學者**。但系統在整個對話過程中出現了以下異常行為：

1. 主 AI (AREQA) 第一回應就使用「草蛇灰線」、「詩讖系統」、「哲學框架」等進階紅學術語，違背初學者認知負荷原則。
2. EDF 將用戶誤判為 TINKERING（思辨階段），因為用戶順著 AI 提問問了「女媧補天有何意涵？」。
3. ComPeer 在用戶說「我還沒讀阿」之後，依然彈出詢問「你剛看到石頭開頭的部分嗎？」這種前後矛盾的問題。
4. ComPeer 的某些提示直接是陳述而非詢問，缺乏引導性。

本文件整理所有發現的根本問題，並標記優先順序與建議改法。

---

## 高優先度問題（直接影響用戶體驗）

---

### 問題 1：EDF 的 trigger_proactive 觸發條件設計過於粗糙

**位置**：`backend/compaction.py` Line 98

**現象**：

用戶才剛回應「我還沒讀阿」（表達的是「我根本還沒讀，所以不懂你在問什麼」），EDF 系統就立刻將其判定為「學習挫折」，觸發 `trigger_proactive: true`，召喚 ComPeer 出來「安慰」。

**根本原因**：

`evaluate_student_state` 在 `compaction.py` 中的 prompt 將 `trigger_proactive` 定義為：「如果學生展現出氣餒、沮喪、或是需要鼓勵，設為 true」。這個定義讓 LLM 僅憑文字情緒判斷是否觸發，完全沒有考慮「用戶是否真的已經在學習」這個前提條件。「我還沒讀」的語義對 LLM 而言可能看起來像「我不知道」，進而誤觸發。

**影響**：ComPeer 在用戶尚未開始學習的情況下，卻詢問關於已讀內容的細節問題，造成脈絡斷裂與體驗混亂。

**建議改法**：

新增一個狀態 `NOT_STARTED`，在此狀態下，`trigger_proactive` 預設為 `false`：

```python
# compaction.py - 新增 NOT_STARTED 狀態定義
"""
- NOT_STARTED: 用戶尚未開始實際閱讀或互動，只是詢問入門方向，
  此階段不應主動干預，trigger_proactive 必須設為 false。
"""
```

---

### 問題 2：ComPeer 的兩條觸發路徑邏輯混用，存在重複觸發風險

**位置**：`backend/services/compeer_scheduler.py`，`proactive_scheduler_loop()`，Line 177–274

**現象**：ComPeer 偶爾會連續彈出兩條訊息，或在極短時間內重複出現。

**根本原因**：

ComPeer 在同一個 10 秒 tick 內存在兩條完全獨立的觸發路徑：

| 路徑 | 觸發條件 | 位置 |
|------|---------|------|
| 路徑 A | 偵測到 trigger_proactive 旗標（來自 EDF 非同步寫入） | Line 186–214 |
| 路徑 B | 大於等於 6 次 scroll 事件 + 1 分鐘無互動 → LLM 判斷 | Line 226–269 |

兩條路徑分別在同一次迴圈中執行，但 `set_cooldown` 只在路徑執行完成後才設定，可能導致兩條路徑都通過 `is_in_cooldown` 的檢查。

**建議改法**：

使用 `asyncio.Lock()` 確保在同一個 tick 中只有一條路徑可以發送訊息：

```python
_send_lock = asyncio.Lock()

async def proactive_scheduler_loop():
    while True:
        async with _send_lock:
            # 路徑 A 和路徑 B 都在 lock 內執行
            # 一旦路徑 A 發送並設置 cooldown，路徑 B 會因為 is_in_cooldown 而跳過
            ...
        await asyncio.sleep(10)
```

---

### 問題 3：Hot Memory 中的 scroll 事件噪音污染 ComPeer 的 Snapshot

**位置**：`backend/gum_integration.py`，`get_hot_memory_snapshot()`，Line 507–526

**現象**：ComPeer 生成的鷹架訊息有時與用戶的實際學習狀況明顯不符。

**根本原因**：

系統記錄每次滾動行為，並以 obs_ 前綴存入 Hot Memory：

```json
{
  "obs_1782973802.74666_6ffe6a48": {
    "text": "User Action: scroll, scrollY: 577.5",
    "confidence": 8.0
  }
}
```

`get_hot_memory_snapshot()` 在組成快照時，直接提取所有 Hot Memory 的 text 欄位，沒有過濾 scroll 事件，導致 LLM 從大量「User Action: scroll, scrollY: XXX」噪音中推測用戶狀態，判斷品質大幅下降。

**建議改法**：

```python
# 在 get_hot_memory_snapshot() 中過濾噪音
meaningful_hot = {
    k: v for k, v in hot_mem.items()
    if not (isinstance(v, dict)
            and "User Action: scroll" in v.get("text", ""))
    and k not in ("user_cooldown_until", "trigger_proactive")
}
```

---

## 中優先度問題（設計層面的邏輯缺陷）

---

### 問題 4：EDF 評估函式接收完整對話記錄，缺少「最近 N 輪」的截取

**位置**：`backend/services/orchestration_service.py` Line 142

**現象**：EDF 狀態在長對話後難以反映「當下」學習狀態，且 API 成本隨對話長度線性增長。

**根本原因**：

`asyncio.create_task(async_evaluate_and_update_state(self.client, model, messages))` 中的 `messages` 是從第一條到最後一條的完整對話歷史，LLM 受到早期對話的影響，無法準確反映「用戶此刻的學習狀態」。

**建議改法**：

```python
# orchestration_service.py
RECENT_WINDOW = 10  # 只傳入最近 10 條訊息給 EDF 評估
recent_messages = messages[-RECENT_WINDOW:]
asyncio.create_task(async_evaluate_and_update_state(self.client, model, recent_messages))
```

---

### 問題 5：Cooldown 時長硬寫死為 30 分鐘，缺乏動態調整能力

**位置**：`backend/services/compeer_scheduler.py`，`set_cooldown()` 預設值，Line 17

**現象**：所有情境下的 ComPeer 靜默期都是固定 30 分鐘，無法依據學習狀態彈性調整。

**根本原因**：

所有觸發路徑都使用 `hours: float = 0.5` 預設值，不論是 GIVING_UP 還是 MASTERY 狀態，靜默時間都一樣。此外，scroll 觸發但被判定為「正常瀏覽」時，系統沒有設置任何 cooldown，可能立刻再次觸發 LLM 偵測，浪費 API 成本。

**建議改法**：

```python
COOLDOWN_BY_STATE = {
    "NOT_STARTED": 2.0,  # 尚未開始，長時間不干預
    "GIVING_UP":   0.25, # 15 分鐘後再關心
    "STARTING":    1.0,  # 1 小時
    "TINKERING":   0.5,  # 30 分鐘
    "MASTERY":     2.0,  # 2 小時，高手不需要太多打擾
    "default":     0.5
}
```

---

### 問題 6：`trigger_proactive` 旗標的消費機制存在 Race Condition

**位置**：`backend/services/compeer_scheduler.py` Line 191–192

**現象**：在極少數情況下，ComPeer 可能對同一個學習事件發送兩次訊息。

**根本原因**：

```python
del hot_mem["trigger_proactive"]
store._atomic_write(store.hot_memory_path, hot_mem)  # 同步 I/O 在 asyncio 中執行
```

若兩個 asyncio 任務幾乎同時讀取到 `hot_mem`（在 atomic write 完成前），兩者都會看到旗標存在並觸發 ComPeer。

**建議改法**：

使用模組級的 `asyncio.Lock()` 保護旗標的讀-消費-寫三段操作：

```python
_flag_lock = asyncio.Lock()

async def _try_consume_proactive_flag(store) -> bool:
    async with _flag_lock:
        hot_mem = store.get_hot_memory()
        if not hot_mem.get("trigger_proactive"):
            return False
        del hot_mem["trigger_proactive"]
        store._atomic_write(store.hot_memory_path, hot_mem)
        return True
```

---

## 低優先度問題（體驗微調）

---

### 問題 7：ComPeer 生成訊息缺乏「上一次問過什麼」的記憶

**現象**：ComPeer 可能在短時間內問出兩個主題相近的問題，讓用戶感覺被重複追問。

**根本原因**：每次 `generate_scaffolding_message_via_llm` 都是全新生成，沒有將「上一條 ComPeer 訊息」注入 prompt 作為「不得重複」的參考。

**建議改法**：

```python
# 讀取上一條 ComPeer 訊息並注入 prompt
last_msg = store.get_hot_memory().get("last_compeer_message", "")
last_msg_hint = f"\n【禁止重複】上一次已問過：「{last_msg}」，本次不得與此主題重複。" if last_msg else ""

# 發送後記錄，以供下次參考
await store.update_hot_memory_async("last_compeer_message", message)
```

---

### 問題 8：每日反思時間硬綁在 23:59，且反思 prompt 為英文

**位置**：`backend/services/compeer_scheduler.py` Line 168；`backend/gum_integration.py`，`run_reflection()` Line 99

**問題 A - 時間硬編碼**：`now.hour == 23 and now.minute == 59` 若服務在深夜重啟，反思任務將跳過直到隔天，導致長期記憶更新中斷。

**問題 B - prompt 語言不一致**：`run_reflection()` 的 prompt 是英文（`"Summarize the following recent interactions into high-level insights..."`），但所有對話記錄都是繁體中文，可能導致 Cold Memory 的反思結果與主體語義脫節。

**建議改法 A**：在服務啟動時，檢查今天是否已執行過反思（寫入 `last_reflection_date` 欄位），若未執行則補跑。

**建議改法 B**：將 `run_reflection()` 的 prompt 改為繁體中文，與整體系統語言保持一致。

---

## 問題優先度摘要表

| # | 問題描述 | 優先度 | 影響面 | 實作難度 |
|---|----------|--------|--------|---------|
| 1 | trigger_proactive 觸發條件過於粗糙，缺乏「是否已開始學習」的前提判斷 | 高 | ComPeer 觸發品質 | 中 |
| 2 | 兩條觸發路徑並行執行，存在重複發送風險 | 高 | ComPeer 重複觸發 | 中 |
| 3 | Scroll 事件噪音污染 Hot Memory Snapshot | 高 | ComPeer 生成品質 | 低 |
| 4 | EDF 評估使用完整對話歷史，無法反映當下狀態且成本高 | 中 | EDF 準確度 + API 成本 | 低 |
| 5 | Cooldown 硬寫死 30 分鐘，缺乏動態調整 | 中 | 用戶騷擾頻率 | 低 |
| 6 | trigger_proactive 消費機制存在 Race Condition | 中 | 系統穩定性 | 中 |
| 7 | ComPeer 缺乏「上一次提問」的記憶，可能重複追問 | 低 | 用戶體驗感受 | 低 |
| 8 | 每日反思時間硬編碼 + 反思 prompt 為英文 | 低 | 長期記憶品質 | 低 |

---

## 建議修復順序

1. **問題 3**（Scroll 噪音過濾）→ 修改 `get_hot_memory_snapshot()`，一行過濾，效果立竿見影
2. **問題 4**（EDF 只看最近 N 輪）→ 截取 `messages[-10:]`，成本低、效果大
3. **問題 1**（trigger_proactive 前提條件）→ 新增 `NOT_STARTED` 狀態至 `compaction.py`
4. **問題 2 + 6**（競態條件）→ 使用 `asyncio.Lock()` 一起修，放在 `compeer_scheduler.py`
5. **問題 5**（動態 Cooldown）→ 依狀態設定不同靜默時長，`COOLDOWN_BY_STATE` 字典
6. **問題 7**（ComPeer 去重記憶）→ 注入 `last_compeer_message` 至 prompt
7. **問題 8**（反思語言 + 時間）→ 長期優化項目，下一個 sprint 處理
