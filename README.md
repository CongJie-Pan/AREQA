# AREQA: An **A**daptive **R**AG-based **E**ducational **QA** System over Closed-domain Knowledge Bases.

---

發音非常像英文的 "Eureka"（我找到了！），這是一個與「發現知識、學習頓悟」完美契合的發音。而且它唸起來像是一個溫雅的女生名字，帶有前面提到的陪伴感。

---

## 當前系統架構圖

### 路徑 A：對話生成路徑 (Chat Path)
> 實際端點：`POST /api/v1/stream`

```mermaid
flowchart TD
    subgraph FE_A ["🖥️ Frontend"]
        UI_Chat["Chat UI\nChatContainer / MessageList / ChatInput"]
    end

    subgraph MEM ["📦 Memory 模塊（共用）"]
        direction LR
        HotMem["短期熱記憶\nMemStore / hot_memory.json\nmemory_store.py"]
        ColdMem["長期冷記憶\nGUM / STITCH / gum.db\ngum_integration.py"]
    end

    subgraph API_A ["⚡ POST /api/v1/stream  ·  main.py"]
        Step1["① Router LLM\n域外問題過濾\nrouter_service.py"]
        Step2["② HyDE 查詢分解 LLM\nparse_and_decompose_query"]
        Step3["③ Policy Classifier LLM\nclassify_dialogue_policy"]
        Step4["④ System Prompt 組裝\n注入 working_memory + retrieved_memory"]
        Step5["⑤ 主 LLM 生成\nqwen3-235b / OpenRouter"]
        Step1 --> Step2 --> Step3 --> Step4 --> Step5
    end

    subgraph RAG_A ["RAG 模塊"]
        RAG_S["RAG Service\nFAISS + BM25\nrag_service.py"]
    end

    UI_Chat -->|"發送提問"| Step1
    Step2 -->|"use_rag=true"| RAG_S
    RAG_S -->|"注入 context"| Step4
    HotMem -->|"讀取 working_memory"| Step4
    ColdMem -->|"語義搜尋 retrieved_memory"| Step4
    Step5 -->|"串流回傳 SSE"| UI_Chat
    Step5 -.->|"對話結束後寫入"| ColdMem
```

---

### 路徑 B：主動關懷路徑 (ComPeer Proactive Path)

```mermaid
flowchart TD
    subgraph FE_B ["🖥️ Frontend · ProactiveManager/index.tsx"]
        direction LR
        Tracker["Behavior Tracker\nScroll ✅ 已實作 / Dwell ⏳ 待實作"]
        State["Zustand / Dexie\nstore/chat/store.ts + database/db.ts"]
        UI_Hint["Proactive UI\n主動關懷小燈泡"]
    end

    subgraph MEM_B ["📦 Memory 模塊（共用）"]
        direction LR
        HotMem_B["短期熱記憶\nhot_memory.json\nmemory_store.py\n（scroll 日誌 + pending_alert）"]
        ColdMem_B["長期冷記憶\ngum.db\ngum_integration.py\n（非 scroll 互動語義化）"]
    end

    subgraph API_B ["⚡ FastAPI · main.py"]
        LogAPI["POST /api/v1/log_action\nscroll → HotMem\n其他互動 → ColdMem"]
        ProactiveAPI["GET /api/v1/proactive-check\n讀取並清除 pending_alert"]
    end

    subgraph COMPEER ["ComPeer 模塊 · compeer_scheduler.py"]
        ProLoop["proactive_scheduler_loop\n每 10 秒\nscroll ≥ 6 → 寫入 Alert"]
        DailyLoop["daily_scheduler_loop\n每日 23:59\n反思 → 生成隔日排程"]
    end

    Tracker -->|"① Scroll 行為日誌"| LogAPI
    LogAPI -->|"scroll 寫入"| HotMem_B
    LogAPI -->|"其他互動寫入"| ColdMem_B
    HotMem_B -.->|"② 監聽 scroll 累積"| ProLoop
    ProLoop -->|"③ scroll ≥ 6 → 寫入 Alert"| HotMem_B
    DailyLoop -->|"反思後寫入排程"| HotMem_B
    State -->|"④ 每 30 秒輪詢"| ProactiveAPI
    ProactiveAPI -->|"⑤ 讀取並清除 Alert"| HotMem_B
    ProactiveAPI -->|"⑥ 觸發顯示"| UI_Hint
```