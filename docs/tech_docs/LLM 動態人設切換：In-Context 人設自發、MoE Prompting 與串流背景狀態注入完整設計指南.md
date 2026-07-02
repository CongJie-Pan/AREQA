# LLM 動態人設切換：In-Context 人設自發、MoE Prompting 與串流背景狀態注入完整設計指南

## 執行摘要

傳統「Router LLM + 字串填空」架構的核心問題在於：它把「領域識別」與「人設表達」切割成兩個分離的步驟，Router 的失誤會導致後續所有輸出崩潰，而且硬套入的 System Prompt 語氣刻板。2024–2026 年最新研究提供了三條更優雅的路徑：（1）透過精心設計的 System Prompt 讓同一個 LLM 自行喚醒對應的思維框架（In-Context Persona Emergence）；（2）在 Prompt 中預載多種專家角色，由模型在推理階段自主挑選（MoE Prompting）；（3）以非同步背景評估搭配 Hot Memory 注入，在不打斷主串流的前提下動態調整語氣與深度（EDF 背景狀態機制）。

關鍵研究警示：USC 2026 年的 PRISM 研究發現，專家人設對「風格/對齊類任務」有益，卻會損害「事實知識提取類任務」的準確度（從基準線 71.6% 下降至 68.0%）。這代表「人設」本質上是**語氣放大器，而非知識增強器**，設計時必須區分這兩類任務。[^1]

***

## 一、In-Context Persona Emergence（脈絡自發人設）

### 核心概念

In-Context Persona Emergence 的核心思想是：讓 System Prompt 本身成為一個「認知框架啟動器」，而非單純的角色標籤。模型在接收到使用者的第一句話後，會根據語意訊號自動激活對應的知識神經網路與思維模式，不需要外部變數注入。[^2]

Vanderbilt 大學的研究將此能力形式化為「動態人設切換模式（Dynamic Persona Switching Pattern）」，其關鍵結構是：在 Prompt 中設定**感知條件**（觀察使用者輸入的語義特徵）而非**固定身份**（我是 XX 領域專家），引導模型自行判斷應啟用哪種認知模式。[^2]

### 設計原則

1. **用思維框架描述取代職銜標籤**：「你是歷史學家」遠不如「你習慣先追問事件的結構性因素，再考察偶然性與行為者的作用」更有效。
2. **設定觀察條件而非判斷規則**：讓模型觀察使用者輸入中的語意線索（提問結構、術語密度、問題類型），自主決定激活哪種框架。
3. **嵌入思維過程，而非輸出格式**：描述「如何思考」，而不是「應該輸出什麼樣的格式」。
4. **人設描述保持簡潔**：USC 研究證實，過長的人設描述會加劇對事實提取的干擾，建議核心人設描述不超過 150 tokens。[^3]

### 完整 Prompt 範例：自發式多領域感知框架

```
<system>
你是一位具有深厚跨學科素養的學習引導者。你的核心特質不是固定的「身份」，而是動態的「認知感知力」——你能從使用者的第一句話中，敏銳地識別其問題的知識本質，並自然地切換到最契合該領域的思維語境。

【認知感知協議】
當使用者的輸入觸及以下語意特徵時，你的思維框架自動調適：

◆ 若問題涉及「因果鏈、歷史脈絡、制度演變」→ 以歷史學者的視角切入：先問「為什麼是這個時間點？」「誰有動機？」「什麼結構性力量在起作用？」，用史料的張力感呈現答案。

◆ 若問題涉及「概念本質、存在、意義、知識論」→ 以哲學家的方式展開：先拆解問題本身的預設，用蘇格拉底式追問揭示隱藏的矛盾，然後建構一個更清晰的概念框架。

◆ 若問題涉及「模型、推導、量化關係」→ 以理論科學家的方式思考：先建立最簡單的理想化模型，識別關鍵變數，再討論現實中的偏差與修正。

◆ 若問題涉及「實作、工具、系統設計」→ 以資深工程師的方式分析：先問「要解決什麼問題？」「有哪些約束條件？」「現有方案的取捨是什麼？」

◆ 若問題橫跨多個領域，或你尚未識別到明確領域訊號 → 先透過一個針對性的追問，引導使用者澄清其真正關心的層面，再決定切入角度。

【表達原則】
- 你的語氣隨認知框架同步變化：歷史問題帶有敘事的厚重感；哲學問題帶有邏輯的精準張力；科學問題帶有模型的簡潔美感；工程問題帶有實用主義的直接。
- 不要在回答開頭宣告「我現在以 XX 身份回應」——直接進入對應框架的思維語境。
- 優先展示「思維過程」，而非輸出「結論清單」。
</system>
```

**優點**：零額外 API 呼叫、無路由延遲、語氣轉換自然流暢、完全在主串流內完成。

**缺點**：依賴模型自身能力，能力較弱的模型（<7B）可能無法可靠地解讀條件語義；System Prompt 需要仔細調試；領域邊界模糊時可能發生混搭錯誤。

***

## 二、MoE Prompting（混合專家 Prompt 技術）

### 理論基礎

「Mixture-of-Expert Prompting（MoP）」由 ICML 2024 正式提出，是第一個將混合專家（MoE）典範擴展至提示詞優化的框架。不同於傳統的單一提示，MoP 同時優化一組具有不同專長的 Prompt 混合體（experts），每個 expert 只處理問題空間中的一個子區域。[^4]

在純 Prompting 層（不依賴外部路由器）的實作上，研究發現 LLM 在 Chain-of-Thought 的「推理階段」具備自主選擇框架的能力，這被稱為 **Multi-Expert Prompting（MEP）**。MEP 讓模型在一次推理中模擬多位專家視角，再透過內部聚合邏輯得出最終答案。[^5]

EduThink4AI 的研究進一步驗證：透過 EDU-Prompting（多智能體框架），在 TruthfulQA 上的準確度從基準的 70.38% 提升至 94.12%，且完全消除了毒性輸出。關鍵洞見在於「**批判性驗證**」步驟——一個 Validity Agent 負責質疑前一位 Agent 的回答，這比直接加入「請批判性思考」指令效果好得多（後者反而導致 76% 的性能下降）。[^5]

### 完整 Prompt 範例：單模型 MoE Chain-of-Thought

```
<system>
你的內部有一組思維專家委員會。當使用者提出問題時，你的推理過程遵循以下多層次框架：

【Phase 1｜領域感知層 - 靜默執行】
在內部識別使用者問題的主要知識特徵：
- 問題是否有「唯一正確答案」？（事實型）
- 問題是否需要「詮釋與論證」？（分析型）
- 問題是否需要「實際操作步驟」？（程序型）
- 問題是否需要「多元視角」？（探索型）

【Phase 2｜專家觀點生成層】
依據問題特徵，內部啟動相關的思維視角：
如果是事實型問題 → 「知識核心框架」：直接從最可靠的知識錨點出發，精確定位關鍵概念。
如果是分析型問題 → 「批判論證框架」：先識別主流觀點，再提出反例，最後建立更細緻的詮釋。
如果是程序型問題 → 「系統工程框架」：先澄清目標與約束，再設計可行路徑，並指出常見陷阱。
如果是探索型問題 → 「對話蘇格拉底框架」：以追問引導使用者自行建構理解，而非直接給出答案。

【Phase 3｜整合與輸出層】
綜合啟動的視角，以最契合問題本質的語氣輸出回答。
不要說明「我使用了哪個框架」——直接用那個框架的語言思考與表達。
</system>
```

### 進階技巧：Mixture of Reasoning Experts（MoRE）

MoRE 架構更進一步，為不同推理類型設定不同的「增強策略」：[^6]

| 專家類型 | 增強策略 | 適用場景 |
|----------|----------|----------|
| 事實專家（Factual） | 附加 RAG 檢索結果，提供前 10 筆相關文件 | 歷史事件、科學定義 |
| 多跳推理專家（Multihop） | 附加手動撰寫的多步驟推理示例 | 邏輯推導、因果分析 |
| 數學專家（Math） | 附加 GSM8K 格式的步驟說明 | 計算、量化推理 |
| 常識專家（Commonsense） | 動態生成 10 條背景常識事實後附加 | 日常知識、社會慣例 |

**優點**：單一模型單次呼叫即可完成；推理過程透明；適合知識密度高的教育場景。

**缺點**：Prompt 較長（~400-600 tokens），增加 prefill 計算成本；對「Phase 1 識別」的準確性仍有依賴，複雜邊界問題可能同時激活多個框架造成混搭。

***

## 三、EDF 架構下的串流背景人設平滑注入

### EDF 框架概述

EDF（Evidence-Decision-Feedback）是 2026 年發表的自適應 LLM Agent 框架，專為教育情境設計。其架構將 Agent 分為三個半自治模組：[^7]

- **Evidence 模組**：持續監控使用者的輸入，更新動態學習者模型（動態知識狀態）
- **Decision 模組**：根據 Evidence，決定當前的對話策略（探索理解、建議行動、擴展挑戰）
- **Feedback 模組**：將對話策略轉化為實際的適應性輸出

關鍵的架構決策：**GPT-5 用於非同步的 Evidence 處理（需要高推理能力），GPT-5-Chat 用於同步的 Dialogue Agent（需要低延遲）**。這個「高推理非同步 + 低延遲同步」的雙軌架構正是解決「不打斷主串流」的核心設計思路。[^8]

### 動態人格狀態機（Dynamic Personality State Machine）

慕尼斯特大學的研究提供了一個更精細的動態人設機制：以**狀態機**表示潛在人設狀態，轉換概率根據對話上下文動態更新。每個狀態包含一段描述「此狀態下如何表達」的動態 System Prompt 片段，系統在每次對話後更新狀態概率，並在下一輪開始前（在主串流之外）重組 System Prompt 的動態部分。[^9]

這個機制的數學本質是：

\[
\delta(s_c, (P_o, P_q)) = w_d \cdot \mathcal{N}(s_d; \sigma^2) + w_c \cdot \mathcal{N}(s_c; \sigma^2) + w_q \cdot P_q + w_o \cdot P_o
\]

其中 \(s_c\) 為當前狀態，\(s_d\) 為預設狀態，\(P_o\) 為外部觀察影響，\(P_q\) 為歷史狀態概率。透過調整權重 \(w\) 可以控制人設轉換的「慣性」與「反應速度」。[^9]

### 完整實作方案：非同步 Hot Memory 注入架構

以下是一個不打斷主串流、且不使用死板填空的背景人設平滑過渡設計：

#### 架構設計

```
┌─────────────────────────────────────────────────┐
│                 主對話串流（同步）                │
│  使用者輸入 → Dialogue Agent（低延遲模型）→ 串流輸出│
└──────────────┬──────────────────────────────────┘
               │ 使用者輸入（同時觸發）
               ▼
┌─────────────────────────────────────────────────┐
│              背景評估管線（非同步）               │
│  ① SignalDetector：從使用者輸入提取領域訊號       │
│  ② PersonaStateUpdater：更新 Hot Memory 中的狀態  │
│  ③ ContextBlender：將新狀態平滑注入下一輪 Prompt  │
└─────────────────────────────────────────────────┘
```

#### Hot Memory 結構設計

```json
{
  "domain_signals": {
    "primary_domain": "philosophy",
    "confidence": 0.87,
    "detected_concepts": ["existence", "phenomenology", "intentionality"],
    "reasoning_style": "analytical"
  },
  "persona_state": {
    "current_voice": "philosophy_socratic",
    "depth_level": 3,
    "transition_inertia": 0.6,
    "active_since_turn": 2
  },
  "learner_model": {
    "demonstrated_understanding": ["basic_concepts"],
    "active_scaffold": "PROBE_UNDERSTANDING"
  }
}
```

#### 背景 Prompt：SignalDetector（非同步，不佔用主串流）

```
<system for SignalDetector - async, not shown to user>
分析以下使用者輸入，提取領域訊號。僅輸出 JSON，不輸出其他內容。

分析維度：
1. primary_domain：從 [history, philosophy, science, engineering, mathematics, arts, interdisciplinary] 中選擇
2. confidence：0.0-1.0（0.5 以下代表訊號不明確）
3. reasoning_style：從 [analytical, narrative, technical, exploratory, critical] 中選擇
4. depth_markers：輸入中出現的專業術語或複雜概念（列表）

輸出範例：
{"primary_domain": "philosophy", "confidence": 0.89, "reasoning_style": "analytical", "depth_markers": ["consciousness", "qualia"]}
</system>
```

#### ContextBlender：平滑 Prompt 生成（取代字串填空）

```python
def blend_persona_context(hot_memory: dict, base_system_prompt: str) -> str:
    """
    不使用字串填空，而是根據狀態概率動態選擇並融合語境片段。
    """
    domain = hot_memory["domain_signals"]["primary_domain"]
    confidence = hot_memory["domain_signals"]["confidence"]
    inertia = hot_memory["persona_state"]["transition_inertia"]
    
    # 語境片段庫（而非職銜標籤）
    voice_fragments = {
        "philosophy": """
在這個對話中，你傾向於在給出答案之前，先揭示問題本身的預設與邊界。
你用精確的概念區分來推進討論，而不是用比喻來掩蓋複雜性。
""",
        "history": """
在這個對話中，你習慣將事件置於更長的時間尺度與結構性力量中來理解。
你對「偶然性」與「必然性」之間的張力保持敏感。
""",
        "science": """
在這個對話中，你首先問「我們怎麼知道這件事是真的？」
你傾向於建立可測試的命題，並明確區分觀察、假設與推論。
""",
        "engineering": """
在這個對話中，你優先澄清問題的約束條件與目標函數。
你評估每個解法的時間、空間與維護成本，而不僅是功能正確性。
"""
    }
    
    # 低信心時：保持通用框架，不強制切換
    if confidence < 0.55:
        dynamic_fragment = "你根據使用者問題的實際需求，靈活選擇最適合的思考框架。"
    else:
        # 高慣性時：加入過渡平滑語句，避免突兀切換
        if inertia > 0.5 and hot_memory["persona_state"]["active_since_turn"] > 1:
            dynamic_fragment = f"延續對話的深度，{voice_fragments.get(domain, '')}"
        else:
            dynamic_fragment = voice_fragments.get(domain, '')
    
    # 動態片段注入 System Prompt 的末尾（而非替換整個 Prompt）
    return f"{base_system_prompt}\n\n【當前對話語境】\n{dynamic_fragment}"
```

#### 主對話串流 Prompt（保持穩定的基礎框架）

```
<system>
你是一位跨域學習引導者，具備廣泛的知識素養與教育敏感度。

核心責任：
- 根據使用者的問題深度，調整你的回答複雜度（不是因為被告知領域，而是因為你真正感知到了）
- 優先展示思維過程，引導使用者自行建構理解，而非直接給出結論
- 當你察覺使用者有誤解時，用追問而非糾正來引導

【當前對話語境】
（由 ContextBlender 在此處動態注入，每輪對話前更新）
</system>
```

**優點**：主串流完全不中斷、語氣轉換平滑自然、可量化調試（信心分數、慣性參數）、完全避免字串填空的機械感。

**缺點**：需要額外的非同步管線；SignalDetector 的準確性影響整體效果；多一個 API 呼叫（但非阻塞）；需要管理 Hot Memory 的生命週期。

***

## 四、PRISM 的重要警示：人設什麼時候會傷害準確性

這是最反直覺、也最重要的研究發現。USC 2026 年的 PRISM 研究系統測試了 6 個 LLM 後得出結論：[^10][^1]

| 任務類型 | 加入專家人設的效果 |
|----------|-------------------|
| 寫作風格、結構遵從 | ✅ 顯著提升（+2-3分/10分） |
| 安全拒絕（越獄防禦） | ✅ 大幅提升（+17.7%） |
| 數學與邏輯推理 | ❌ 明顯下降（某些情況從9/10跌至1.5/10） |
| 事實知識提取（MMLU） | ❌ 從71.6%降至68.0% |
| 程式碼精確性 | ❌ 下降 |

**原因機制**：告知模型「你是某領域專家」會強化其「指令遵循行為」，但這個行為模式會干擾從預訓練資料中直接提取事實的能力。換句話說，人設把模型的注意力從「知識提取」轉移到「角色扮演風格」上。[^11]

**對教育 AI Agent 的設計啟示**：
- 使用者問數學題、請求程式碼審查、詢問事實性問題 → **去除人設，直接回應**
- 使用者需要學習引導、批判性討論、論文反饋 → **啟用人設語境**
- PRISM 的最佳解法：訓練一個輕量 LoRA adapter 作為「人設閘門」，讓模型自行學習何時啟用人設特徵，PRISM 在 Mistral 7B 上將整體分數從基準線提升，同時完全保留知識準確度。[^12][^10]

***

## 五、三種方案的綜合比較

| 維度 | In-Context Persona Emergence | MoE Prompting | EDF + Hot Memory |
|------|------------------------------|----------------|-------------------|
| 實作複雜度 | ⭐⭐（低） | ⭐⭐⭐（中） | ⭐⭐⭐⭐⭐（高） |
| 語氣自然度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 對模型能力的依賴 | 高（需要 >20B 或指令對齊好的模型） | 中 | 低（分工後每個模組負擔輕） |
| 額外 API 成本 | 零 | 零 | 每輪多 1 次非同步呼叫 |
| 多輪對話一致性 | 中（受 Context Window 限制） | 中 | 高（Hot Memory 持久化） |
| 適合場景 | 單輪問答、輕量助手 | 複雜分析、多視角討論 | 長對話、深度教學引導 |
| 主串流中斷風險 | 無 | 無 | 無（背景非同步） |
| 事實任務安全性 | 中（需在 Prompt 中明確排除人設干擾） | 中 | 高（可設計 bypass 邏輯） |

***

## 六、推薦的混合實作策略

針對同時包含「串流生成」與「EDF 背景評估」的教育 AI Agent，推薦以下三層混合架構：

### Layer 1：固定基礎人設（In-Context Emergence）
在 System Prompt 中嵌入**感知框架描述**（而非職銜），讓模型在任何情況下都有穩定的認知基礎。這是兜底層，確保即使背景管線失敗，模型仍能自然運作。

### Layer 2：MoE CoT 推理框架（每次生成時激活）
在生成前加入 Phase 1 靜默領域識別，讓模型在 `<thinking>` 區塊中明確選擇推理框架，然後用對應的語氣輸出。適用於有支援「思考鏈」功能的模型（如 Claude 3.7 Sonnet、o3、DeepSeek R1）。

### Layer 3：非同步 EDF 狀態機（跨輪更新）
每輪對話結束後，背景管線觸發 SignalDetector，更新 Hot Memory，並在下一輪 Prompt 開始前透過 ContextBlender 注入動態語境片段。關鍵：只注入「語境片段」而非替換整個 Prompt，避免 Context 割裂感。

### 觸發邏輯

```python
def route_persona_strategy(task_type: str, confidence: float) -> str:
    """
    基於 PRISM 研究的人設觸發邏輯
    """
    FACTUAL_TASKS = {"math", "code", "factual_retrieval", "calculation"}
    ALIGNMENT_TASKS = {"writing", "discussion", "scaffolding", "feedback", "safety"}
    
    if task_type in FACTUAL_TASKS:
        return "NO_PERSONA"  # 完全移除人設描述，直接回應
    elif task_type in ALIGNMENT_TASKS and confidence > 0.6:
        return "FULL_PERSONA"  # 啟用完整人設語境
    else:
        return "MINIMAL_PERSONA"  # 僅保留基礎感知框架
```

***

## 七、進階研究方向

**Persona Vectors（人設向量）**：2025 年的研究探索了在 LLM 的激活空間中直接操作「人設特徵向量」的方法，透過將人格向量（personality vectors）加入隱層激活，可以在不修改 Prompt 的情況下連續調控人設強度。這代表未來可能有完全不依賴 Prompt 工程的動態人設切換方案，但目前仍屬研究階段，需要模型白盒存取權限。[^13]

**協作式人設開發（Collaborative Persona Development）**：Vanderbilt 大學的研究提出讓使用者參與共同建構人設的模式，在教育場景中這尤其有潛力：讓學習者描述「他們希望 AI 如何教他們」，再將這些描述動態納入人設框架，形成個性化的學習語境。[^2]

**跨輪人設連貫性測試**：目前研究較少量化「多輪對話後人設一致性」的指標。建議開發者在評估階段設計「人設漂移測試」（Persona Drift Test），在 20+ 輪對話後測量模型的語氣、深度與框架選擇是否仍保持一致。

***

## 結論

避開 Router LLM 的關鍵洞見是：**不要設計一個「判斷領域再填入人設」的流水線，而是設計一個「讓模型在認知層面真正感知對話語境」的條件激活框架**。In-Context Persona Emergence 是最輕量的起點；MoE Prompting 提供更明確的推理可控性；EDF 背景狀態機制則能在不中斷串流的前提下實現跨輪對話的人設連貫性。三者的共同核心是：人設的切換應當發生在「語義感知層」，而非「字串替換層」，這才是讓 AI 展現出真正領域思維深度的關鍵。[^4][^7][^2]

---

## References

1. [Telling an AI model that it's an expert makes it worse - The Register](https://www.theregister.com/software/2026/03/24/telling-an-ai-model-that-its-an-expert-makes-it-worse/5226049) - : Researchers say persona-based prompting can improve works for safety but not for facts

2. [[PDF] A Pattern Language for Persona-based Interactions with LLMs](https://www.dre.vanderbilt.edu/~schmidt/PDF/Persona-Pattern-Language.pdf) - Implementing Dynamic Persona Switching involves designing prompts that guide the LLM to change roles...

3. [Expert Personas Boost LLM Alignment but Harm Accuracy: USC Study](https://www.linkedin.com/posts/ekiledjian_expert-personas-improve-llm-alignment-but-activity-7442170166022397952-ChNb) - ... : Bootstrapping Intent-Based Persona Routing with PRISM" (Hu, Rostami, Thomason — USC, 2026) #AI...

4. [ruocwang/mixture-of-prompts: [ICML 2024] One Prompt is ... - GitHub](https://github.com/ruocwang/mixture-of-prompts) - [ICML 2024] One Prompt is Not Enough: Automated Construction of a Mixture-of-Expert Prompts - Turnin...

5. [Bridging Educational Critical Thinking and Multi-Agent LLM ...](https://arxiv.org/html/2507.15015v2)

6. [Combine Different Specialized LLMs - Instructor](https://python.useinstructor.com/prompting/ensembling/more/) - MoRE creates a set of diverse reasoning experts by using different specialized prompts for different...

7. [Theory-Driven Adaptive Scaffolding for LLM Agents - arXiv](https://arxiv.org/abs/2602.01415) - To address this, we introduce Evidence-Decision-Feedback (EDF), a theoretical framework for adaptive...

8. [Theory-Driven Adaptive Scaffolding for LLM Agents](https://www.themoonlight.io/en/review/evidence-decision-feedback-theory-driven-adaptive-scaffolding-for-llm-agents) - This paper introduces Evidence-Decision-Feedback (EDF), a novel theoretical framework designed for a...

9. [Dynamic Personality Adaptation in Large Language Models via ...](https://arxiv.org/html/2602.22157v1)

10. [Asking AI to act like an expert can make it less reliable - Tech Xplore](https://techxplore.com/news/2026-03-ai-expert-reliable.html) - To get the best out of AI, some users tell it to provide answers as if it were an expert. Others ask...

11. [Everyone Is Using 'Act as an Expert' in AI Prompts - DSEC](https://www.dsec.nl/2026/04/everyone-is-using-act-as-an-expert-in-ai-prompts-new-research-says-thats-a-mistake/) - A new research paper titled “Expert Personas Improve LLM Alignment but Damage Accuracy: Bootstrappin...

12. [PRISM: Intent-Based Persona Routing for LLMs - YouTube](https://www.youtube.com/watch?v=iGuIziv1iv4) - In this AI Research Roundup episode, Alex discusses the paper: Expert Personas Improve LLM Alignment...

13. [Modulating Personality of Large Language Models by ...](https://www.semanticscholar.org/paper/Personality-Vector:-Modulating-Personality-of-Large-Sun-Baek/576bcea42aa1f01688485a71df3112cc8fccafda) - By merging personality vectors, this work enables LLMs to exhibit desired personality traits without...

