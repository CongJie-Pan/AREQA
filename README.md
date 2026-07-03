# AREQA: An **A**daptive **R**AG-based **E**ducational **QA** System over Closed-domain Knowledge Bases.

---

發音非常像英文的 "Eureka"（我找到了！），這是一個與「發現知識、學習頓悟」完美契合的發音。而且它唸起來像是一個溫雅的女生名字，帶有前面提到的陪伴感。

---

## 當前系統架構圖

> **最後更新**：2026-07-01（系統架構重構完成，涵蓋 Gate 0A → 3A 全部改動）

### 路徑 A：對話生成路徑 (Chat Path)
> 實際端點：`POST /api/v1/stream`

```mermaid
flowchart TD
    subgraph FE_A ["🖥️ Frontend"]
        UI_Chat["Chat UI\nChatContainer / MessageList / ChatInput\nThinkingPanel / Citations / SuggestedQuestions"]
    end

    subgraph INFRA ["🏗️ Infrastructure"]
        Config["config.py\n集中式設定\n模型名稱 / RAG 參數 / Redis URL"]
        RedisCache["RagCacheService\nservices/cache_service.py\nRedis TTL=1hr"]
    end

    subgraph MEM ["📦 Memory 模塊（共用）"]
        direction LR
        HotMem["短期熱記憶\nMemStore / hot_memory.json\nmemory_store.py"]
        ColdMem["長期冷記憶\nGUM / STITCH / gum.db\ngum_integration.py"]
    end

    subgraph API_A ["⚡ POST /api/v1/stream  ·  main.py"]
        Orchestrator["OrchestrationService\nservices/orchestration_service.py"]

        subgraph ORCH_NODES ["7個節點 (Nodes)"]
            N1["① Fast Domain Check LLM\n快速域外過濾 (目前已停用)"]
            N2["② HyDE 查詢分解 LLM\nparse_and_decompose_query"]
            N3["③ Policy Classifier LLM\nclassify_dialogue_policy\n(EDF 教學策略)"]
            N4["④ RAG Retrieval\nFAISS + BM25 + RRF\n+ Reranker + 注意力重排"]
            N5["⑤ System Prompt 組裝\n注入 working_memory / context\n+ retrieved_memory / learner_state / avatar"]
            N6["⑥ 主 LLM 串流生成\n動態切換 model_main_thinking\n/ model_main_instruct"]
            N7["⑦ Post-generation\nSuggestion / EDF 狀態更新"]
            N1 --> N2 --> N3 --> N4 --> N5 --> N6 --> N7
        end
    end

    UI_Chat -->|"① 發送提問"| Orchestrator
    Orchestrator --- ORCH_NODES
    N2 -->|"cache miss: 呼叫 RAG"| RedisCache
    RedisCache -->|"cache hit: 直接返回"| N5
    N4 -->|"寫入快取"| RedisCache
    HotMem -->|"讀取 working_memory"| N5
    ColdMem -->|"語義搜尋 retrieved_memory"| N5
    N6 -->|"串流回傳 SSE"| UI_Chat
    N7 -.->|"對話結束後寫入"| ColdMem
    Config -.->|"提供模型名稱 / RAG 閾值"| ORCH_NODES
```

---

### 路徑 B：主動關懷路徑 (ComPeer Proactive Path)

```mermaid
flowchart TD
    subgraph FE_B ["🖥️ Frontend · src/components/ProactiveManager/index.tsx"]
        direction LR
        Tracker["Behavior Tracker\nScroll ✅ 已實作 / Dwell ⏳ 待實作"]
        State["Zustand / Dexie\nsrc/store/chat/store.ts + src/database/db.ts"]
        WSHook["useProactiveWebSocket Hook\nsrc/hooks/useProactiveWebSocket.ts\n指數退避自動重連"]
        UI_Hint["Proactive UI\n主動關懷小燈泡\n(手動關閉 / 支援動態冷卻機制)"]
    end

    subgraph MEM_B ["📦 Memory 模塊（共用）"]
        direction LR
        HotMem_B["短期熱記憶\nhot_memory.json\nmemory_store.py\n(scroll 日誌 + pending_alert)"]
        ColdMem_B["長期冷記憶\ngum.db\ngum_integration.py\n(非 scroll 互動語義化)"]
    end

    subgraph API_B ["⚡ FastAPI · main.py"]
        LogAPI["POST /api/v1/log_action\nscroll → HotMem\n其他互動 → ColdMem"]
        WSEndpoint["WebSocket /api/v1/ws/notifications\nConnectionManager\nservices/connection_manager.py"]
    end

    subgraph COMPEER ["ComPeer 模塊 · services/compeer_scheduler.py"]
        ProLoop["proactive_scheduler_loop\n每 10 秒 (動態冷卻機制)\nscroll ≥ 6 + 閒置 60s → 觸發 LLM 判斷"]
        DailyLoop["daily_scheduler_loop\n每日 23:00 後\n反思 → 生成隔日排程"]
    end

    Tracker -->|"① Scroll 行為日誌"| LogAPI
    LogAPI -->|"scroll 寫入"| HotMem_B
    LogAPI -->|"其他互動寫入"| ColdMem_B
    HotMem_B -.->|"② 監聽 scroll 累積"| ProLoop
    ProLoop -->|"③ 條件滿足 → 寫入 Alert"| HotMem_B
    ProLoop -->|"④ 即時 WebSocket 推播"| WSEndpoint
    DailyLoop -->|"反思後寫入排程"| HotMem_B
    State -->|"頁面載入時建立連線"| WSHook
    WSHook <-->|"⑤ 持久 WS 連線 (101)"| WSEndpoint
    WSEndpoint -->|"⑥ 收到推播 → 觸發顯示"| UI_Hint
```