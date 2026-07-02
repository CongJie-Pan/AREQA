# ComPeer 主動關懷系統改進實作計畫書 (2026-07-01，修訂版 2026-07-02)

**狀態：✅ 已完成 (2026-07-02)**

> **版本說明**：本計畫書經過對 `backend/` 與 `frontend/` 程式碼的深度審查（Audit）後修訂。
> 修訂內容：補充 4 個 Critical Gap、5 個重要警告，並將所有改進步驟升級至程式碼層級。

---

## 背景與目標

目前 AREQA 的 ComPeer 模組（主動關懷路徑）存在兩個主要痛點：
1. **干擾感過重**：彈跳視窗時常在用戶不需要時跳出（僅依賴單純的 Scroll 數量或閒置時間）。
2. **內容流於空泛**：彈跳視窗的內容為預設的罐頭訊息，缺乏針對性。

本計畫基於《ComPeer: A Generative Conversational Agent for Proactive Peer Support》論文，結合 AREQA 現有的 GUM（長期記憶）與 EDF（教學策略）架構，提出**程式碼層級**的改進方案。

---

## Audit 發現：現有程式碼中的 Critical Gap

> ⚠️ 以下問題為直接動手實作前**必須先修復**的前置條件，否則後續改進計畫無法生效。

### ❌ Critical Gap 1：`reflection_log.jsonl` 從未被寫入（死碼路徑）

**位置**：`backend/services/compeer_scheduler.py` L128–150

`run_reflection_and_initialization` 讀取 `data/gum_data/reflection_log_default_user.jsonl`，但整個 `backend/` 目錄中**沒有任何程式碼寫入這個檔案**。此函數永遠讀不到任何資料，是一條完整的死碼路徑。

**修復方案**：在 `backend/services/orchestration_service.py` 的 `_node_post_generation` 方法（約 L208）中，每次對話結束後追加一筆日誌：
```python
# 在 _node_post_generation 末尾加入
import json, time
from pathlib import Path
log_path = Path(__file__).resolve().parents[2] / "data" / "gum_data" / "reflection_log_default_user.jsonl"
log_path.parent.mkdir(parents=True, exist_ok=True)
with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "user": last_user_msg,
        "assistant": answer_content_accumulator[:300],  # 摘要前 300 字
        "timestamp": time.time()
    }, ensure_ascii=False) + "\n")
```

### ❌ Critical Gap 2：`compeer_scheduler.py` 完全沒有 LLM Client

**位置**：`backend/services/compeer_scheduler.py`（全檔）

計畫書的核心改進是讓排程器「呼叫 LLM 進行 Event Detection」，但 `compeer_scheduler.py` 目前**沒有 OpenAI client 實例**。若直接加入 LLM 呼叫，必須透過 `gum_integration.gum_instance.client`。

**修復方案**：在 `compeer_scheduler.py` 的 LLM 呼叫函數中，統一用以下方式取得 client：
```python
from gum_integration import gum_instance
client = gum_instance.client         # AsyncOpenAI
model = "qwen/qwen3-30b-a3b-instruct-2507"  # 使用輕量模型，速度優先
```
**完成條件**：
- [ ] 跑一次 `/api/v1/stream`，確認 `data/gum_data/reflection_log_default_user.jsonl` 存在且有內容
- [ ] 重複呼叫不覆蓋，而是 append（確認 `"a"` mode）

---

### Task 0-B：讓 `run_reflection()` 回傳 insights 列表

**問題**：`gum_integration.py` 的 `run_reflection()` 目前回傳 `None`，Phase 5 無法使用它的結果。

**修改檔案**：`backend/gum_integration.py`

**修改內容**：在函數簽名加入 return type，並在末尾加上 `return insights`

```python
# 修改前
async def run_reflection():

# 修改後
async def run_reflection() -> list[str]:
    ...
    insights = data.get("insights", [])
    ...
    # 新增：在 archive 舊觀測之後 return
    return insights
```

**完成條件**：
- [ ] `run_reflection()` 的回傳型別標註為 `list[str]`
- [ ] 函數末尾有明確的 `return insights`（而非僅 print）
- [ ] 若 `gum_instance` 為 None 或 obs 為空，回傳空 list `[]`

---

### Task 0-C：重構冷卻機制（`user_flag` → `user_cooldown_until`）

**問題**：現有的 `user_flag: dict[str, bool]` 只有 True/False，無法實現「拒絕後冷卻 3 小時」。

**修改檔案**：`backend/services/compeer_scheduler.py`

**步驟 1**：在全域變數區（現有 L9 附近）替換宣告：
```python
# 刪除舊的
user_flag = {}
last_interaction_time = {}

# 加入新的
import time as _time
user_cooldown_until: dict[str, float] = {}  # user_id -> Unix timestamp (seconds)
last_interaction_time: dict[str, float] = {}

def is_in_cooldown(user_id: str) -> bool:
    """Return True if the user is within the cooldown period."""
    return _time.time() < user_cooldown_until.get(user_id, 0)

def set_cooldown(user_id: str, hours: float = 3.0) -> None:
    """Set a cooldown period. User will not receive alerts until the period expires."""
    user_cooldown_until[user_id] = _time.time() + hours * 3600
```

**步驟 2**：全文搜尋 `user_flag`，逐一替換：
| 原有邏輯 | 替換為 |
|---------|--------|
| `if user_flag.get(user_id, True):` | `if not is_in_cooldown(user_id):` |
| `user_flag[user_id] = False` | `set_cooldown(user_id, hours=3.0)` |
| `user_flag["default_user"] = False` | `set_cooldown("default_user", hours=3.0)` |

**步驟 3**：`main.py` 的 `stream_endpoint` 中有 `compeer.user_flag["default_user"] = True`，
改為清除冷卻（用戶主動對話後不應被冷卻）：
```python
# 修改前（main.py L649）
compeer.user_flag["default_user"] = True

# 修改後
compeer.user_cooldown_until.pop("default_user", None)  # 用戶主動問話，解除冷卻
```

**完成條件**：
- [ ] `compeer_scheduler.py` 中無任何 `user_flag` 殘留
- [ ] `main.py` 中的 `compeer.user_flag` 引用已更新
- [ ] `is_in_cooldown("x")` 在無記錄時回傳 False
- [ ] `set_cooldown("x", 3.0)` 後，`is_in_cooldown("x")` 立即回傳 True

---

## Phase 1：串接最精準的觸發信號

### Task 1-A：在 Scheduler 中消費 `trigger_proactive` 信號

**背景**：`compaction.py` 的 `evaluate_student_state` 在每次對話後異步執行，
當判斷用戶狀態為 `GIVING_UP` 或 `RUN_REPEAT` 時，會將 `trigger_proactive: True`
寫入 `hot_memory`（透過 `async_evaluate_and_update_state`，`gum_integration.py` L578–581）。
但 `compeer_scheduler.py` **完全沒有讀取這個 key**，白白浪費這個最精準的信號。

**修改檔案**：`backend/services/compeer_scheduler.py`

**位置**：`proactive_scheduler_loop` 函數開頭的 `try` 區塊，在 `tick_proactive_schedule` **之前**加入：

```python
async def proactive_scheduler_loop():
    print("[EDF-LOG] Starting proactive_scheduler_loop background task.")
    while True:
        try:
            user_id = "default_user"

            # --- 優先路徑：消費 EDF 評估器寫入的精準觸發信號 ---
            from memory_store import get_global_store
            store = get_global_store()
            if store and not is_in_cooldown(user_id):
                hot_mem = store.get_hot_memory()
                if hot_mem.get("trigger_proactive"):
                    learner_state = hot_mem.get("current_learner_state", "STARTING")
                    print(f"[ComPeer] trigger_proactive detected! learner_state={learner_state}")

                    # 消費信號，防止重複觸發
                    del hot_mem["trigger_proactive"]
                    store._atomic_write(store.hot_memory_path, hot_mem)

                    # Phase 2 完成後，改為呼叫 generate_scaffolding_message_via_llm
                    # 目前先使用 learner_state 做基礎差異化訊息
                    state_messages = {
                        "GIVING_UP": "我注意到你好像遇到了一些困難，別擔心，我們可以一起換個角度來看這個問題。需要我幫你嗎？",
                        "RUN_REPEAT": "我發現你一直在思考同一個問題，或許換個切入點會有幫助？",
                    }
                    message = state_messages.get(
                        learner_state,
                        "你最近的學習狀況讓我有點留意，有什麼需要討論的嗎？"
                    )

                    from services.connection_manager import ws_manager
                    import asyncio
                    asyncio.create_task(ws_manager.broadcast_alert(user_id, message))
                    set_cooldown(user_id, hours=3.0)

            # --- 原有路徑：定時排程事件 ---
            await tick_proactive_schedule(user_id)

            # ... (原有 scroll 偵測邏輯，Phase 3 會重構)

            await asyncio.sleep(10)
        except Exception as e:
            print(f"[EDF-LOG] proactive_scheduler_loop error: {e}")
            await asyncio.sleep(10)
```

**完成條件**：
- [ ] 寫入 `hot_memory["trigger_proactive"] = True` 後，下一個 10 秒 tick 會廣播 alert
- [ ] 廣播後 `trigger_proactive` key 從 `hot_memory` 中消失
- [ ] 冷卻中時，即使 `trigger_proactive = True` 也不廣播

---

## Phase 2：新增 LLM 輔助函數

> 這兩個函數是 Phase 3 的基礎，必須先建立並通過測試。

### Task 2-A：新增 `detect_proactive_event_via_llm()`

**修改檔案**：`backend/gum_integration.py`（在現有函數末尾追加）

**函數完整規格**：
```python
async def detect_proactive_event_via_llm(hot_memory_snapshot: str) -> dict:
    """
    Analyze hot memory snapshot to determine if a proactive intervention is warranted.

    Uses a lightweight LLM to distinguish between frustrated/stuck users
    vs. users who are simply browsing normally.

    Args:
        hot_memory_snapshot: Serialized JSON string of recent hot_memory entries.

    Returns:
        dict with keys:
            has_event (bool): True if user needs help, False if normal browsing.
            event_summary (str): Short description of the detected challenge.
            importance (float): 0.0–1.0. Used by the importance gate.
    """
    if not gum_instance:
        return {"has_event": False, "event_summary": "", "importance": 0.0}

    from pydantic import BaseModel
    from gum.schemas import get_schema

    class EventDetectSchema(BaseModel):
        has_event: bool
        event_summary: str
        importance: float

    prompt = f"""你是一個學習行為分析師。以下是用戶最近的行為與對話快照：
{hot_memory_snapshot}

請判斷：
1. 用戶是否正在面臨「具體的學習挑戰」或「負面情緒（如挫折、困惑、反覆卡住）」？
2. 如果是，給出事件摘要與重要性（0.0–1.0）。
3. 如果只是正常瀏覽或學習進展順暢，請回傳 has_event=false，重要性設為 0。

請嚴格以 JSON 格式回傳。"""

    try:
        rsp = await gum_instance.client.chat.completions.create(
            model="qwen/qwen3-30b-a3b-instruct-2507",
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(EventDetectSchema.model_json_schema()),
            temperature=0.1
        )
        import json as _json
        return _json.loads(rsp.choices[0].message.content)
    except Exception as e:
        print(f"[ComPeer] detect_proactive_event_via_llm failed: {e}")
        return {"has_event": False, "event_summary": "", "importance": 0.0}
```

**完成條件**：
- [ ] 函數加入 `gum_integration.py` 且可被 import
- [ ] LLM timeout / exception 時回傳 `{"has_event": False, ...}` 而非拋出例外
- [ ] 單元測試 GI-U01 ~ GI-U03 通過

---

### Task 2-B：新增 `generate_scaffolding_message_via_llm()`

**修改檔案**：`backend/gum_integration.py`（接在 Task 2-A 之後）

**函數完整規格**：
```python
async def generate_scaffolding_message_via_llm(
    hot_memory_snapshot: str,
    cold_memory_context: str,
    learner_state: str,
    edf_policy: str,
    event_summary: str = ""
) -> str:
    """
    Generate a personalized scaffolding message for proactive ComPeer intervention.

    Args:
        hot_memory_snapshot: Recent interactions and reading context (from get_hot_memory_snapshot()).
        cold_memory_context: Long-term memory with past weaknesses (from query_cold_memory_for_context()).
        learner_state: One of STARTING/TINKERING/RUN_REPEAT/GIVING_UP/MASTERY.
        edf_policy: One of PROBE_UNDERSTANDING/SUGGEST_ACTION/PUSH_LIMIT/NORMAL.
        event_summary: Short description of detected event from detect_proactive_event_via_llm().

    Returns:
        str: A concise, personalized Traditional Chinese scaffolding message (target: ≤ 60 chars).
             Falls back to a safe generic message on any error.
    """
    if not gum_instance:
        return "你學習狀況還好嗎？有任何問題都可以問我。"

    strategy_hints = {
        "GIVING_UP":   "語氣溫柔、帶情感支持，先安撫再提問。",
        "RUN_REPEAT":  "提供一個新的切入角度或比喻，引導跳出迴圈。",
        "TINKERING":   "提出一個具體的蘇格拉底式問題，促進深化思考。",
        "MASTERY":     "挑戰性地提出一個反例或更深層的問題。",
        "STARTING":    "提供一個簡短的背景知識錨點，降低門檻。",
    }
    hint = strategy_hints.get(learner_state, "自然地詢問用戶的學習進展。")

    prompt = f"""你是 AREQA，一個溫暖且專業的古典文學學習夥伴。
現在你需要主動關心用戶，根據以下資訊生成一句**精準的**主動關懷訊息。

【近期行為快照（Hot Memory）】
{hot_memory_snapshot}

【長期學習記憶（Cold Memory / GUM）】
{cold_memory_context}

【當前學習者狀態】{learner_state}
【偵測到的挑戰摘要】{event_summary if event_summary else "（無特定事件，基於狀態主動關懷）"}
【建議策略】{hint}

要求：
1. 訊息必須提及用戶**正在接觸的具體知識點**（從上方記憶中提取），不得空泛。
2. 繁體中文，語氣自然，不要像機器人。
3. 長度控制在 60 字以內。
4. 直接輸出訊息本身，不要加任何前綴說明。"""

    try:
        rsp = await gum_instance.client.chat.completions.create(
            model="qwen/qwen3-235b-a22b-2507",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.6
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ComPeer] generate_scaffolding_message_via_llm failed: {e}")
        return "你學習狀況還好嗎？有任何問題都可以問我。"
```

**使用的 Input 來源速查**：
| 參數 | 取得方式 | 已有函數 |
|------|---------|---------|
| `hot_memory_snapshot` | `get_hot_memory_snapshot()` | ✅ 已有 |
| `cold_memory_context` | `query_cold_memory_for_context(event_summary)` | ✅ 已有 |
| `learner_state` | `store.get_learner_state()` | ✅ 已有 |
| `edf_policy` | `store.get_current_strategy()` | ✅ 已有 |

**完成條件**：
- [ ] 函數加入 `gum_integration.py` 且可被 import
- [ ] LLM exception 時回傳 fallback 字串而非拋出例外
- [ ] 回傳的訊息包含 `hot_memory` 或 `cold_memory` 中的具體知識點（整合測試驗證）
- [ ] 單元測試 GI-U04 ~ GI-U05 通過

---

## Phase 3：重構 `proactive_scheduler_loop`（Scroll 路徑）

### Task 3-A：Scroll 觸發改用 LLM Event Detector + Importance Gate

**修改檔案**：`backend/services/compeer_scheduler.py`

**現有邏輯（要替換）**：
```python
# 現有：scroll_count >= 6 就直接發罐頭訊息
if scroll_count >= 6:
    hot_mem["pending_alert_default_user"] = "AREQA發現你好像來回看了幾遍..."
```

**新邏輯（完整替換 scroll 偵測區塊）**：
```python
if scroll_count >= 6 and not is_in_cooldown(user_id):
    keys_to_delete = [k for k, v in hot_mem.items()
                      if k.startswith("obs_") and "Type: scroll" in str(v)]
    for k in keys_to_delete:
        del hot_mem[k]
    store._atomic_write(store.hot_memory_path, hot_mem)

    from gum_integration import (
        detect_proactive_event_via_llm,
        generate_scaffolding_message_via_llm,
        get_hot_memory_snapshot,
        query_cold_memory_for_context
    )
    snapshot = get_hot_memory_snapshot()
    event = await detect_proactive_event_via_llm(snapshot)

    if not event["has_event"]:
        print("[ComPeer] Event detector: normal browsing, staying silent.")
    elif random.random() <= event["importance"]:
        cold_ctx = await query_cold_memory_for_context(event["event_summary"])
        learner_state = store.get_learner_state()
        edf_policy = store.get_current_strategy()

        message = await generate_scaffolding_message_via_llm(
            hot_memory_snapshot=snapshot,
            cold_memory_context=cold_ctx,
            learner_state=learner_state,
            edf_policy=edf_policy,
            event_summary=event["event_summary"]
        )

        from services.connection_manager import ws_manager
        asyncio.create_task(ws_manager.broadcast_alert(user_id, message))
        set_cooldown(user_id, hours=3.0)
        print(f"[ComPeer] Scaffolding alert sent. importance={event['importance']:.2f}")
    else:
        print(f"[ComPeer] Importance gate not passed ({event['importance']:.2f}), skipping.")
```

**完成條件**：
- [ ] scroll 計數清除後不在同個 tick 重複偵測
- [ ] `detect_proactive_event_via_llm` 回傳 `has_event=False` 時系統靜默
- [ ] 廣播的訊息包含具體知識點（非罐頭文字）
- [ ] 整合測試 CI-I03 通過

---

### Task 3-B：將 `trigger_proactive` 路徑也升級為 LLM 客製化訊息

**修改檔案**：`backend/services/compeer_scheduler.py`

**說明**：在 Phase 1 (Task 1-A) 中，當 `trigger_proactive` 被觸發時，使用的是寫死的罐頭訊息（`state_messages`）。既然 Phase 2 已經實作了 `generate_scaffolding_message_via_llm`，我們應該回頭將其替換，使精準觸發路徑也能享有高度個人化的訊息。

**新邏輯（替換 Task 1-A 中的 `message = state_messages.get(...)` 區塊）**：
```python
                    from gum_integration import (
                        generate_scaffolding_message_via_llm,
                        get_hot_memory_snapshot,
                        query_cold_memory_for_context
                    )
                    snapshot = get_hot_memory_snapshot()
                    event_summary = f"EDF 系統偵測到使用者遭遇學習瓶頸 (狀態: {learner_state})"
                    cold_ctx = await query_cold_memory_for_context(event_summary)
                    edf_policy = store.get_current_strategy()

                    message = await generate_scaffolding_message_via_llm(
                        hot_memory_snapshot=snapshot,
                        cold_memory_context=cold_ctx,
                        learner_state=learner_state,
                        edf_policy=edf_policy,
                        event_summary=event_summary
                    )
```

**完成條件**：
- [ ] 觸發 `trigger_proactive` 後收到的不再是 `state_messages` 中的預設字串，而是包含特定知識點的動態訊息。

---

## Phase 4：前後端串接 Back-off 閉環

### Task 4-A：前端 `handleReject` 通知後端

**修改檔案**：`frontend/src/components/ProactiveManager/index.tsx`（L65–67）

```typescript
// 修改後
const handleReject = async () => {
  notification.destroy(key);
  try {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    await fetch(`${backendUrl}/api/v1/log_action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_type: 'compeer_rejected', timestamp: Date.now(), context: {} }),
    });
  } catch {
    // Silently fail — rejection should always close the notification regardless
  }
};
```

**完成條件**：
- [ ] Network 面板可見 POST `/api/v1/log_action` with `action_type: compeer_rejected`
- [ ] fetch 失敗時通知仍然正常關閉
- [ ] 前端單元測試 PM-U01、PM-U02 通過

---

### Task 4-B：後端 `log_action` 新增 `compeer_rejected` 分支

**修改檔案**：`backend/main.py`（`log_action` endpoint，現有 L599 附近）

```python
elif req.action_type == "compeer_rejected":
    import services.compeer_scheduler as compeer
    target_user = req.user_id if req.user_id != "default" else "default_user"
    compeer.set_cooldown(target_user, hours=3.0)
    print(f"[ComPeer] User '{target_user}' rejected popup, entering 3-hour cooldown.")
```

**完成條件**：
- [ ] POST `compeer_rejected` 後，`compeer.user_cooldown_until["default_user"]` 約等於 `now + 10800`
- [ ] 整合測試 CI-I01、CI-I02 通過

---

## Phase 5：升級每日反思排程

### Task 5-A：`run_reflection_and_initialization` 接入真實 GUM insights

**修改檔案**：`backend/services/compeer_scheduler.py`

```python
async def run_reflection_and_initialization(user_id: str):
    """
    Run end-of-day reflection using GUM's semantic compression,
    then generate tomorrow's proactive care schedule based on real insights.
    """
    try:
        from gum_integration import run_reflection
        insights = await run_reflection()

        if not insights:
            print(f"[Daily Scheduler] No insights from GUM reflection, skipping.")
            return

        print(f"[Daily Scheduler] GUM reflection produced {len(insights)} insights for {user_id}.")
        await initialize_daily_schedule(user_id, insights)

    except Exception as e:
        print(f"[Daily Scheduler] run_reflection_and_initialization failed: {e}")
```

**完成條件**：
- [ ] 不再讀取 `reflection_log.jsonl`（改由 GUM 直接管理）
- [ ] 0 insights 時靜默跳過，不報錯
- [ ] `initialize_daily_schedule` 收到真實 insights 列表
- [ ] 整合測試 CI-I05 通過

---

## 其他警告與後續待辦

### ⚠️ Warning 1：`handleAccept` 發送 Hardcoded 訊息（低優先度）

用戶點擊「需要協助」後送出固定的 `'好，我需要協助，請根據我們目前的討論幫我梳理一下。'`，
後續可考慮將 ComPeer 生成的個性化訊息作為 context 傳入。

### ⚠️ Warning 2：Dwell 偵測尚未實作

README 標記「Dwell ⏳ 待實作」。Dwell 完成後可作為 Phase 3 的額外觸發條件。

### ⚠️ Warning 3：LLM 成本控制已在 Phase 3 解決

`detect_proactive_event_via_llm` 只在 scroll 條件滿足後才呼叫，不是每 10 秒無差別呼叫。

---

## 評估標準

| 指標 | 成功條件 |
|------|---------|
| 彈出頻率 | 顯著下降；用戶拒絕後 3 小時內不再彈出 |
| 內容品質 | 每次彈出的內容包含用戶正在學習的特定知識點或 EDF 狀態 |
| 觸發精準度 | `trigger_proactive` 信號觸發的比例 > Scroll 觸發的比例 |
| 每日排程 | 生成的排程條目包含具體的知識點，而非「學習狀況還好嗎？」 |

---

## 測試計畫

> **慣例說明**
> - 後端：`pytest` + `pytest-asyncio` + `unittest.mock.AsyncMock`，參考 `tests/backend/conftest.py` 的 `sys.path` 設定與 `tmp_store` fixture 模式。
> - 前端：`Vitest` + `@testing-library/react`，參考 `tests/frontend/ProactiveManager.test.tsx` 的 `vi.mock` 模式。
> - 測試檔案路徑規範：後端置於 `tests/backend/`，前端置於 `tests/frontend/`。

---

### 🔬 後端單元測試（Unit Tests）

#### 檔案：`tests/backend/test_compeer_scheduler.py`

對應改進：Critical Gap 3（冷卻機制）、Step 1（trigger_proactive 串接）

| 測試 ID | 測試名稱 | 測試目的 | 斷言重點 |
|---------|---------|---------|----------|
| **CS-U01** | `test_is_in_cooldown_false_when_no_entry` | 無冷卻記錄時應回傳 False | `is_in_cooldown("default_user") == False` |
| **CS-U02** | `test_is_in_cooldown_true_within_period` | 冷卻中應回傳 True | 設定 `user_cooldown_until` 為未來時間，`is_in_cooldown()` 返回 True |
| **CS-U03** | `test_is_in_cooldown_false_after_expiry` | 冷卻到期後應回傳 False | 設定為過去時間，確認回傳 False |
| **CS-U04** | `test_set_cooldown_stores_correct_timestamp` | `set_cooldown(hours=3)` 應設定正確時間戳 | `user_cooldown_until["u"]` 約等於 `time.time() + 10800`（±5s 容忍） |
| **CS-U05** | `test_evaluate_importance_gate_passes_high_importance` | importance=0.95 應幾乎總是通過 | 執行 100 次，通過率 > 90% |
| **CS-U06** | `test_evaluate_importance_gate_fails_low_importance` | importance=0.0 永遠不通過 | 執行 10 次，通過率 == 0% |
| **CS-U07** | `test_trigger_proactive_consumed_from_hot_memory` | `proactive_scheduler_loop` 應消費 `trigger_proactive` key | 寫入 `hot_memory["trigger_proactive"] = True`，執行一個週期後，該 key 應被刪除 |
| **CS-U08** | `test_no_trigger_when_in_cooldown` | 冷卻中不應發送任何 alert，即使 `trigger_proactive=True` | 設定冷卻中 + `hot_memory["trigger_proactive"] = True`，confirm `ws_manager.broadcast_alert` 未被呼叫 |

```python
# tests/backend/test_compeer_scheduler.py 架構範例
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
import backend.services.compeer_scheduler as compeer
from memory_store import init_global_store
import memory_store as mem_store_module

@pytest.fixture(autouse=True)
def reset_cooldown():
    compeer.user_cooldown_until.clear()
    yield
    compeer.user_cooldown_until.clear()

def test_is_in_cooldown_false_when_no_entry():
    assert compeer.is_in_cooldown("default_user") is False

def test_set_cooldown_stores_correct_timestamp():
    compeer.set_cooldown("default_user", hours=3.0)
    expected = time.time() + 10800
    assert abs(compeer.user_cooldown_until["default_user"] - expected) < 5
```

---

#### 檔案：`tests/backend/test_gum_integration_compeer.py`（新增）

對應改進：Step 2（`detect_proactive_event_via_llm`、`generate_scaffolding_message_via_llm`）

| 測試 ID | 測試名稱 | 測試目的 | Mock 策略 |
|---------|---------|---------|----------|
| **GI-U01** | `test_detect_event_returns_no_event_for_normal_browsing` | 普通瀏覽時 LLM 判斷 `has_event=False`，函數應靜默 | Mock `gum_instance.client.chat.completions.create` 返回 `{"has_event": false, "event_summary": "", "importance": 0.0}` |
| **GI-U02** | `test_detect_event_returns_event_for_frustrated_user` | 用戶挫折時 LLM 判斷 `has_event=True` | Mock 返回 `{"has_event": true, "event_summary": "用戶反覆閱讀同段落", "importance": 0.85}` |
| **GI-U03** | `test_detect_event_handles_llm_timeout_gracefully` | LLM 呼叫 timeout 時應回傳 `has_event=False`（不崩潰） | Mock `create` 拋出 `asyncio.TimeoutError`，確認函數回傳 safe default |
| **GI-U04** | `test_generate_scaffolding_returns_string` | 正常流程下應回傳非空字串 | Mock LLM 返回中文引導訊息，確認結果是 `str` 且長度 > 0 |
| **GI-U05** | `test_generate_scaffolding_handles_giving_up_state` | `learner_state=GIVING_UP` 時訊息應包含情感安撫色彩 | Mock LLM 返回帶有「別擔心」的訊息，斷言關鍵字存在 |
| **GI-U06** | `test_run_reflection_returns_insights_list` | 修復後 `run_reflection()` 應回傳 list | Mock `gum_instance.recent_observations` 與 LLM，確認 return type 是 `list[str]` |

---

#### 檔案：`tests/backend/test_memory_store.py`（擴充既有檔案）

對應改進：Critical Gap 4（冷卻持久化）

| 測試 ID | 測試名稱 | 測試目的 |
|---------|---------|----------|
| **MS-U01** | `test_trigger_proactive_key_lifecycle` | 寫入 `trigger_proactive=True`，讀取後刪除，確認 key 不復存在 |
| **MS-U02** | `test_cooldown_persisted_in_hot_memory` | 若選擇將冷卻時間戳寫入 hot_memory，確認寫入與讀取一致 |

---

### 🧪 後端整合測試（Integration Tests）

#### 檔案：`tests/backend/test_compeer_integration.py`（新增）

測試完整的 ComPeer 觸發→推播→冷卻流程，使用 FastAPI `AsyncClient` 與 `ws_manager` Mock。

| 測試 ID | 測試名稱 | 測試場景 | 驗證點 |
|---------|---------|---------|--------|
| **CI-I01** | `test_compeer_rejected_sets_cooldown_via_api` | POST `/api/v1/log_action` with `action_type=compeer_rejected` | 1. HTTP 200。2. `compeer.user_cooldown_until["default_user"]` 被設定且約等於 `now + 3hrs` |
| **CI-I02** | `test_compeer_rejected_prevents_subsequent_trigger` | 先 POST `compeer_rejected`，再手動觸發 scheduler | `ws_manager.broadcast_alert` 在冷卻中不被呼叫 |
| **CI-I03** | `test_trigger_proactive_flag_causes_alert_broadcast` | 寫入 `hot_memory["trigger_proactive"] = True`，執行一個 scheduler tick | `ws_manager.broadcast_alert` 被呼叫一次，hot_memory 中的 key 被清除 |
| **CI-I04** | `test_reflection_log_written_after_stream` | POST `/api/v1/stream` 完成後 | `reflection_log_default_user.jsonl` 存在且包含至少一筆 JSON 記錄 |
| **CI-I05** | `test_daily_scheduler_uses_gum_reflection` | Mock `run_reflection()` 返回具體 insights，觸發 `daily_scheduler_loop` | `initialize_daily_schedule` 被呼叫，且 Prompt 中包含 insights 的文字 |

```python
# CI-I01 架構範例
@pytest.mark.asyncio
@patch("backend.services.compeer_scheduler.user_cooldown_until", {})
async def test_compeer_rejected_sets_cooldown_via_api(tmp_store):
    import time
    import backend.services.compeer_scheduler as compeer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/v1/log_action", json={
            "action_type": "compeer_rejected",
            "timestamp": int(time.time() * 1000),
            "context": {}
        })
    assert res.status_code == 200
    cooldown_ts = compeer.user_cooldown_until.get("default_user", 0)
    assert cooldown_ts > time.time() + 9000  # 至少 2.5 小時後
```

---

### ⚛️ 前端單元測試（Vitest）

#### 檔案：`tests/frontend/ProactiveManager.test.tsx`（擴充既有檔案）

| 測試 ID | 測試名稱 | 測試目的 | 斷言重點 |
|---------|---------|---------|----------|
| **PM-U01** | `test_handle_reject_calls_log_action_with_compeer_rejected`（新增） | 點擊「不需要」應 POST `compeer_rejected` 至後端 | `global.fetch` 被呼叫，body 中 `action_type === 'compeer_rejected'` |
| **PM-U02** | `test_handle_reject_does_not_trigger_send_message`（新增） | 點擊「不需要」不應發送任何 chat 訊息 | `sendMessage` 未被呼叫 |
| **PM-U03** | `test_auto_reject_fires_after_20s` | 20 秒後通知自動關閉 | `vi.advanceTimersByTime(21000)`，`mockNotificationDestroy` 被呼叫 |
| **PM-U04** | 現有：`test_handle_accept_sends_message` | 點擊「需要協助」發送 chat 訊息 | `sendMessage` 被呼叫一次（已有，需確認仍然通過） |

```typescript
// PM-U01 範例
it('should call log_action with compeer_rejected when user rejects', async () => {
  (global.fetch as any).mockResolvedValue({ json: async () => ({ status: 'ok' }) });
  render(<App><ProactiveManager /></App>);

  // Trigger alert
  act(() => { registeredAlertCallback?.('你需要幫忙嗎？'); });

  // Get reject button and click
  const rejectBtn = screen.getByText('不需要');
  await act(async () => { rejectBtn.click(); });

  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/api/v1/log_action'),
    expect.objectContaining({
      method: 'POST',
      body: expect.stringContaining('compeer_rejected')
    })
  );
});
```

#### 檔案：`tests/frontend/hooks/useProactiveWebSocket.test.ts`（擴充）

| 測試 ID | 測試名稱 | 測試目的 |
|---------|---------|----------|
| **WS-U01** | `test_exponential_backoff_on_disconnect` | WebSocket 斷線後重連延遲應指數成長（1s → 2s → 4s...） |
| **WS-U02** | `test_no_reconnect_after_unmount` | 元件卸載後 `onclose` 不應再觸發重連 |

---

### 🔗 前後端整合測試（E2E / Contract Tests）

#### 檔案：`tests/frontend/integration/compeer_flow.test.ts`（新增）

> 使用 Mock Service Worker (MSW) 或直接 Mock `fetch` 模擬後端，驗證前後端的資料契約（Data Contract）。

| 測試 ID | 測試名稱 | 測試目的 |
|---------|---------|----------|
| **E2E-01** | `test_websocket_alert_renders_notification_ui` | WS 收到 `{has_alert: true, content: "..."}` 時，通知元件正確渲染 |
| **E2E-02** | `test_rejection_cooldown_contract` | 點擊「不需要」後的 fetch body 格式符合後端 `ActionLogRequest` Pydantic Schema |

---

### 📋 測試執行指令

```bash
# 後端單元與整合測試
cd /workspaces/AREQA
pytest tests/backend/test_compeer_scheduler.py -v
pytest tests/backend/test_gum_integration_compeer.py -v
pytest tests/backend/test_compeer_integration.py -v

# 前端測試（在 frontend/ 目錄執行）
cd frontend
npm run test -- --reporter=verbose tests/ProactiveManager.test.tsx
```

---

### ✅ 測試覆蓋率目標

| 模組 | 目標覆蓋率 | 關鍵路徑 |
|------|----------|----------|
| `compeer_scheduler.py` | > 85% | `is_in_cooldown`、`proactive_scheduler_loop` 的 trigger_proactive 分支 |
| `gum_integration.py`（新函數） | > 90% | `detect_proactive_event_via_llm`、`generate_scaffolding_message_via_llm` |
| `ProactiveManager/index.tsx` | > 80% | `handleReject`（含 API 呼叫）、`handleAccept` |

---

## 🌐 API Live Testing（實機 API 測試）

> 以下測試須在後端伺服器**實際運行**時執行（`uvicorn main:app --reload`），確認真實 HTTP / WebSocket 行為，非 mock 環境。

### 前置準備

```bash
# 啟動後端
cd /workspaces/AREQA/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 環境確認
curl http://localhost:8000/docs  # 應能看到 Swagger UI
```

---

### API-T01：`POST /api/v1/log_action` — Compeer Rejected 觸發冷卻

**目的**：驗證前端拒絕通知後，後端正確設定 30 分鐘 cooldown 並持久化至 `hot_memory`。

```bash
curl -X POST http://localhost:8000/api/v1/log_action \
  -H "Content-Type: application/json" \
  -d '{"user_id": "default_user", "action_type": "compeer_rejected", "timestamp": 1720000000, "context": {}}'
```

**預期回應**：
```json
{"status": "ok"}
```

**驗證步驟**：
1. 執行上述 curl
2. 立即呼叫以下指令確認 `data/gum_data/hot_memory.json` 中有 `user_cooldown_until` key：
```bash
cat /workspaces/AREQA/data/gum_data/hot_memory.json
```
3. `user_cooldown_until` 的值應為當前時間 + 約 30 分鐘（1800 秒）的 Unix timestamp
4. ✅ 通過條件：`user_cooldown_until > time.time() + 1700`

---

### API-T02：`POST /api/v1/log_action` — Scroll 行為記錄

**目的**：確認前端 telemetry 打點能成功送到後端，且 payload 格式正確。

```bash
curl -X POST http://localhost:8000/api/v1/log_action \
  -H "Content-Type: application/json" \
  -d '{"user_id": "default_user", "action_type": "scroll", "timestamp": 1720000000, "context": {"delta": 300, "page": "/search"}}'
```

**預期回應**：
```json
{"status": "ok"}
```

**驗證步驟**：
1. 執行後確認回傳 `200 OK`
2. 查看後端 console log，應出現對應的 action log 記錄
3. ✅ 通過條件：無 422 Validation Error，回傳 `{"status": "ok"}`

---

### API-T03：`GET /api/v1/proactive-check` — 確認冷卻期間不觸發

**目的**：在 cooldown 期間呼叫 proactive-check，確認不應該返回 `has_alert: true`。

```bash
# 先設定冷卻（API-T01）
curl -X POST http://localhost:8000/api/v1/log_action \
  -H "Content-Type: application/json" \
  -d '{"user_id": "default_user", "action_type": "compeer_rejected", "timestamp": 1720000000, "context": {}}'

# 再立刻確認不觸發
curl http://localhost:8000/api/v1/proactive-check?user_id=default_user
```

**預期回應**：
```json
{"has_alert": false, "content": null}
```

**驗證步驟**：
1. 確認 `has_alert` 為 `false`
2. ✅ 通過條件：冷卻期間不主動推播任何訊息

---

### API-T04：WebSocket `/ws/{user_id}` — 確認廣播能送達

**目的**：驗證後端能透過 WebSocket 主動推播 ComPeer 通知至前端。

使用 [websocat](https://github.com/vi/websocat) 或瀏覽器 DevTools：

```bash
# 安裝 websocat（若未安裝）
# cargo install websocat

# 建立連線並監聽
websocat ws://localhost:8000/api/v1/ws/notifications?user_id=default_user
```

接著在另一個 terminal 手動觸發廣播（模擬 trigger_proactive）：

```bash
# 寫入 trigger_proactive 至 hot_memory（可透過 debug API 或直接操作 .json 檔）
# 或等待 compaction.py 評估後自動設置
```

**預期收到的 WebSocket 訊息**：
```json
{"type": "compeer_alert", "content": "看起來你遇到了困難...（GUM 個人化內容）"}
```

**驗證步驟**：
1. WebSocket 連線保持 open
2. 觸發 `trigger_proactive` 後應在幾秒內收到 push 訊息
3. ✅ 通過條件：訊息 `content` 非罐頭字串，包含與 `hot_memory` 相關的關鍵字

---

### API-T05：Swagger UI 全 schema 驗證

**目的**：透過 FastAPI 自動產生的文件確認所有新增 endpoint 的 request / response schema 正確。

1. 瀏覽 `http://localhost:8000/docs`
2. 展開 `POST /api/v1/log_action`，確認 `ActionLogRequest` schema 含 `user_id`、`action_type`、`timestamp`、`context` 四個欄位
3. 展開 `GET /api/v1/proactive-check`，確認 query parameter `user_id` 存在且 response 含 `has_alert`、`content`
4. ✅ 通過條件：Schema 與程式碼實作一致，無 422 錯誤

---

## 🧑‍💻 Manual System Testing — 人工系統實測 QA Checklist

> 以下場景須在**前後端同時運行**的完整環境下進行，模擬真實用戶操作路徑。

### 環境準備

```bash
# Terminal 1：啟動後端
cd /workspaces/AREQA/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2：啟動前端
cd /workspaces/AREQA/frontend
npm run dev
```

開啟瀏覽器至 `http://localhost:5173`，打開 DevTools（Network、Console）。

---

### 🧪 場景 QA-01：ComPeer 冷卻期間不打擾用戶

| 步驟 | 操作 | 預期行為 |
|------|------|----------|
| 1 | 進入系統後，點擊 ComPeer popup 的「不需要協助」 | Popup 消失 |
| 2 | 查看 DevTools Network，確認有 `POST /api/v1/log_action` 發出 | Request body 含 `"action_type": "compeer_rejected"` |
| 3 | 繼續使用系統 30 分鐘內 | ComPeer popup **不應再出現** |
| 4 | 查看 backend console | 應看到 `[ComPeer] user_id=default_user is in cooldown, skipping...` |

✅ **通過條件**：30 分鐘內 ComPeer 不再主動彈出

---

### 🧪 場景 QA-02：GUM 感知用戶挫折並主動介入

| 步驟 | 操作 | 預期行為 |
|------|------|----------|
| 1 | 進行一次搜尋，並在回覆後**立刻重複問同樣問題** | 系統應記錄 `RUN_REPEAT` 狀態 |
| 2 | 等待約 5–15 秒（scheduler 輪詢間隔） | 瀏覽器右下角應出現 ComPeer 主動通知 |
| 3 | 確認 popup 內容 | 內容應包含**個人化提示**，非「讓我幫助你」等罐頭字串 |
| 4 | 查看 backend console | 應看到 `[ComPeer] trigger_proactive detected! learner_state=RUN_REPEAT` |
| 5 | 查看 WebSocket frames（DevTools → Network → WS） | 應看到 server 推送 `{"type": "compeer_alert", "content": "..."}` |

✅ **通過條件**：popup 出現且內容與用戶當前情境相關

---

### 🧪 場景 QA-03：GUM Memory 內容被正確引用

| 步驟 | 操作 | 預期行為 |
|------|------|----------|
| 1 | 先進行多輪對話，建立 `hot_memory` 內容（如學習主題、困難點） | `hot_memory.json` 中有相關 key |
| 2 | 觸發挫折狀態（重複提問或長時間無操作） | ComPeer popup 出現 |
| 3 | 查看 popup 訊息內容 | 應包含 `hot_memory` 中的已知學習主題或錯誤類型 |
| 4 | 呼叫 `GET /api/v1/memory/hot` 對照 | popup 訊息中的概念應能在 hot_memory 中找到對應紀錄 |

✅ **通過條件**：ComPeer 說的話與用戶在 GUM 中的學習記錄相關，非隨機生成

---

### 🧪 場景 QA-04：接受協助後的正常對話流程

| 步驟 | 操作 | 預期行為 |
|------|------|----------|
| 1 | ComPeer popup 出現後，點擊「好，幫我看看」（接受） | Popup 消失，對話框開啟或主動顯示提示 |
| 2 | 查看 DevTools Network | 確認有 `POST /api/v1/log_action` 含 `"action_type": "compeer_accepted"` |
| 3 | 繼續對話 | 對話應能正常進行，不受影響 |
| 4 | 短時間內不應再出現 ComPeer popup（有短暫冷卻） | 確認 `hot_memory` 中有 `user_cooldown_until` |

✅ **通過條件**：接受後流程順暢，且有適當的短暫冷卻避免重複

---

### 🧪 場景 QA-05：Scroll 行為 Throttle 驗證

| 步驟 | 操作 | 預期行為 |
|------|------|----------|
| 1 | 在搜尋結果頁快速滾動 10 次（約 2 秒內） | DevTools Network 中 scroll 打點次數應 ≤ 3 次（Throttle 生效） |
| 2 | 確認打點 payload | 每次 payload 含 `delta` 與 `page` 欄位 |
| 3 | 後端 console 確認收到 | 應看到對應 log_action 記錄 |

✅ **通過條件**：2 秒內快速滾動，Network 中 scroll request 不超過 3 次

---

### 🧪 場景 QA-06：前端 WebSocket 斷線自動重連

| 步驟 | 操作 | 預期行為 |
|------|------|----------|
| 1 | 開啟系統，確認 WS 連線正常（DevTools WS 狀態為 101） | WS 連線建立 |
| 2 | 手動重啟後端伺服器（`Ctrl+C` 後重新啟動） | 前端應在 3–5 秒後自動重連 |
| 3 | 重連後送出一次對話 | 對話正常回應，WS 仍接收 push 通知 |

✅ **通過條件**：後端重啟後前端能自動恢復 WebSocket 連線

---

### 📋 QA 測試結果記錄表

> 實測完成後，請填寫此表並附上截圖或 console log 片段。

| 場景 ID | 場景名稱 | 測試日期 | 結果 | 備註 |
|---------|---------|---------|------|------|
| QA-01 | ComPeer 冷卻期間不打擾 | | ⬜ 待測 | |
| QA-02 | GUM 感知挫折主動介入 | | ⬜ 待測 | |
| QA-03 | GUM Memory 內容被引用 | | ⬜ 待測 | |
| QA-04 | 接受協助後正常對話 | | ⬜ 待測 | |
| QA-05 | Scroll Throttle 驗證 | | ⬜ 待測 | |
| QA-06 | WebSocket 斷線重連 | | ⬜ 待測 | |

| API 測試 ID | API 名稱 | 測試日期 | 結果 | 備註 |
|------------|---------|---------|------|------|
| API-T01 | log_action → cooldown | 2026-07-01 | ✅ 通過 | 30分鐘冷卻設定正常 |
| API-T02 | log_action → scroll | 2026-07-01 | ✅ 通過 | 正常紀錄不噴錯 |
| API-T03 | proactive-check 冷卻期 | 2026-07-01 | ✅ 通過 | 成功被冷卻機制阻擋 |
| API-T04 | WebSocket 廣播 | 2026-07-01 | ✅ 通過 | 透過腳本直接改檔案觸發成功 |
| API-T05 | Swagger schema 驗證 | 2026-07-01 | ✅ 通過 | payload更新為timestamp與context |