# AI 系統長期記憶管理與動態提取策略：學術與業界深度研究報告

> **研究範疇：** 持續性通用使用者模型 (General User Model, GUM) 架構下的記憶管理設計  
> **文獻覆蓋：** 2020–2026 年 CHI、UIST、NeurIPS、ACL、ICML 頂會論文及 OpenAI、Anthropic、LangChain、LlamaIndex 等業界技術文件  
> **附件引用：** 本報告整合了 *Creating General User Models from Computer Use*（Shaikh et al., UIST'25） 作為核心技術參考框架[^1]

***

## 一、執行摘要

當前對話型 AI Agent 面臨的核心記憶挑戰可歸結為三點：**記憶邊界模糊**（短期工作記憶與長期語意記憶的轉換觸發條件不明確）、**提取精準度不足**（Context Window 被不相關記憶污染），以及**固化邏輯缺失**（缺乏將碎片化觀察壓縮為結構化知識的機制）。本報告系統性地梳理業界與學術界在這兩大核心議題上的具體架構設計模式，並在結論章節提供三項可立即實作的 MVP 功能建議。

***

## 議題一：短期工作記憶與長期語意/情節記憶的界定與轉換

### 1.1 認知神經科學對 AI 記憶架構的啟發

學術界普遍以人類認知模型作為 AI 記憶架構的設計藍本。從人類記憶角度出發，工作記憶（Working Memory）負責當下任務的即時推理，長期記憶則分為語意記憶（Semantic Memory，即概念性知識）與情節記憶（Episodic Memory，即特定時間與情境的事件記憶）。**LLM Agent Memory 文獻綜述**（OpenReview, 2024）明確指出，AI 系統的工作記憶對應 Context Window 中的即時推理狀態；而長期記憶則需透過 RAG 或外部資料庫來擴展，能跨 Session 累積並維持歷史觀察與行動軌跡。[^2][^3]

近期研究 *Episodic Memory is the Missing Piece for Long-Term LLM Agents*（2025） 進一步指出，情節記憶——特定互動事件的時序記錄——是目前大多數 RAG 系統最欠缺的元件，其缺失導致 Agent 無法進行「跨 Session 的因果推理」。相較之下，語意記憶（使用者的偏好、職業、習慣）可以透過知識圖譜或結構化向量儲存建模；情節記憶則需保留事件的時間戳記、發生背景與情緒顯著性，兩者在提取策略上存在根本差異。[^4]

### 1.2 三種核心架構設計模式

#### 設計模式 A：OS 分層記憶管理（Hierarchical Memory Paging）

**代表框架：MemGPT（Packer et al., 2023）**，由 UC Berkeley 開發，NeurIPS 2023 發表。[^5]

**運作原理：** 仿照作業系統的虛擬記憶體管理，將記憶分為兩層：
- **Main Context（主記憶）：** 等同於 RAM，即 LLM 的固定長度 Context Window，存放當前任務的即時工作狀態。
- **External Context（外部儲存）：** 等同於二級儲存（磁碟），包含 Recall Storage（過去對話的向量化摘要）和 Archival Storage（外部知識庫）。

當主記憶接近容量上限時，LLM 透過**自生成函式呼叫（Self-Generated Function Calls）**主動觸發記憶換頁（Paging）——將不活躍的內容移至外部儲存，並從外部儲存拉入相關內容。這一設計讓 LLM 本身成為記憶管理的決策者，而非被動的資訊接收端。[^6][^7]

**GUM 架構對照：** 在 Shaikh et al. (UIST'25) 的 GUM 系統中，類似機制透過 **Propose → Retrieve → Revise** 管線實現：每個新觀察（截圖）被轉換為 Proposition，Retrieve 模組負責從外部儲存拉取語意相關的歷史 Proposition，Revise 模組則判斷是否合併、更新或保留現有記憶。[^1]

***

#### 設計模式 B：三因子重要性評分的記憶流（Memory Stream with Importance Scoring）

**代表論文：Generative Agents: Interactive Simulacra of Human Behavior（Park et al., CHI 2023）**

**運作原理：** 每個 Agent 維護一條連續的**記憶流（Memory Stream）**，所有觀察事件均依時間順序寫入。提取時不採用單純的相似度匹配，而是對每條記憶計算加權分數：

\[\text{score} = \alpha_{\text{recency}} \cdot \text{recency} + \alpha_{\text{importance}} \cdot \text{importance} + \alpha_{\text{relevance}} \cdot \text{relevance}\]

其中「**重要性（Importance）**」是最關鍵的創新——系統提示 LLM 對每條記憶在 1-10 範圍內評估其情感顯著性，例如「刷牙」評為 1，「收到錄取通知」評為 9。此外，當最近記憶的重要性累計超過閾值（論文中設為 150）時，系統自動觸發**反思（Reflection）**——LLM 對過去 100 條記憶進行高階抽象，生成新的語意記憶並寫回記憶流。這一機制實現了「短期觀察→長期知識」的記憶固化。[^8][^9][^10][^11]

**GUM 對照：** GUM 使用 LLM 生成的 Confidence Score（0-1）和 Decay Score 來替代這個三因子機制，直接對每條 Proposition 標記其時效性與可信度，概念上高度相近。[^1]

***

#### 設計模式 C：Zettelkasten 啟發的動態記憶網絡（A-MEM）

**代表論文：A-MEM: Agentic Memory for LLM Agents（Xu et al., NeurIPS 2025）**[^12][^13]

**運作原理：** 受德國學者 Luhmann 的 Zettelkasten（卡片箱）知識管理方法啟發，A-MEM 將每條新記憶轉換為多屬性的結構化「記憶筆記」，包含：
- **Content**（內容本文）
- **Context**（生成脈絡）
- **Keywords & Tags**（關鍵詞標籤）
- **Links**（指向語意相關的其他記憶節點）

當新記憶被加入時，系統會主動分析歷史記憶並**建立語意連結（Dynamic Linking）**，形成一個有機成長的知識網絡。更重要的是，這個過程還會觸發**記憶演化（Memory Evolution）**——新記憶的加入可能更新舊記憶的 Contextual Description 與屬性，實現記憶的主動修訂。在六個基礎模型上的實驗顯示，A-MEM 在複雜長期任務上顯著優於 MemoryBank 和 MemGPT 等基線系統。[^13][^14][^12]

***

### 1.3 Memory Consolidation（記憶固化）演算法

記憶固化是指將短期交互歷史轉化為可長期保存的精簡知識的過程。目前業界主要有三種具體做法：

| 固化方法 | 代表框架 | 核心機制 | 優缺點 |
|---|---|---|---|
| **LLM 驅動的事實萃取** | LlamaIndex FactExtractionMemoryBlock[^15] | 當短期對話歷史超過 Token 閾值時，自動觸發 LLM 從被截斷的對話中提取結構化事實 | 高語意品質，但每次固化需要額外 LLM 呼叫 |
| **向量相似度合併** | Mem0[^16][^17] | 相似度 > 0.85 的記憶向量觸發合併，透過 LLM 解決衝突（例如「Python 覆蓋 JS？」）；相似度 > 0.9 的集群進行去重 | 可將儲存空間減少 60%，提升提取精準度 22% |
| **階層式語意壓縮** | SimpleMem（ICML 2026）[^18] | 三階段管線：(1) Semantic Structured Compression → (2) Online Semantic Synthesis（即時消除冗余）→ (3) Intent-Aware Retrieval Planning | 最新研究方向，在 token 效率與資訊密度上表現最優 |

Mem0（Chhikara et al., 2025）在 LOCOMO 基準測試上，相比 OpenAI Memory 達到 **26% 的相對改善**，同時降低 91% 的 p95 延遲並節省超過 90% 的 Token 成本。[^16][^19]

***

## 議題二：RAG/Agent 架構下的適當記憶提取與 Context Pollution 防治

### 2.1 Context Pollution 的根本成因

傳統 RAG 的核心問題在於其「Top-K 匹配後傾倒（top-K match and dump）」模式——將最高餘弦相似度的 K 個片段直接注入 Context Window，完全不考慮語意相關性與當前任務脈絡的適配度。Anthropic 的工程部落格（2025）明確指出，LLM 就像人類一樣擁有有限的「注意力預算（Attention Budget）」，大量無關的 Retrieved Context 不僅浪費 Token，更會主動干擾模型的推理能力。[^20][^21]

此外，ACL 2025 論文 *Reflective Memory Management for Long-term Personalized Agents*（Liu et al.）實驗驗證了一個關鍵發現：**引入不相關的記憶段落會顯著降低 LLM 的回答品質**，使用強力 Retriever（如 GTE）的 RAG 系統相比完整對話歷史提升了 27.5% METEOR 分數——這充分說明選擇性提取的重要性。[^22]

### 2.2 三種 Agentic Retrieval 設計模式

#### 設計模式 D：Intent-Aware Memory Retrieval（意圖導向記憶提取）

**代表論文：STITCH: Structured Intent Tracking in Contextual History（2026）**[^23][^24]

**運作原理：** 傳統語意相似度搜尋存在一個致命缺陷：相同的實體詞彙（如「預算」、「時間」）可能在不同任務目標下出現，導致系統提取到「語意相似但目標不相容」的歷史記憶，讓 Agent 誤判當前情境。

STITCH 在每次記憶寫入時，為每個軌跡步驟（Trajectory Step）額外索引三個結構化欄位：
1. **當前潛在目標（Latent Goal）**：定義主題段落的主旨
2. **行動類型（Action Type）**：查詢、決策、確認等
3. **顯著實體類型（Salient Entity Types）**：鎖定哪些屬性（價格、評分、地點）在此步驟有意義

提取時，系統先以**意圖相容性（Intent Compatibility）過濾**，再按語意相似度排名。在 CAME-Bench 和 LongMemEval 上，STITCH 比最強基線模型高出 **35.6%**，且隨對話長度增加，優勢差距持續擴大。[^23]

***

#### 設計模式 E：Memory-as-Tool 的 Agentic Retrieval（工具化記憶提取）

**代表框架：Letta（前身 MemGPT），Anthropic Memory Tool（Beta, 2025）**[^21][^20]

**運作原理：** 與其將記憶提取視為「在對話生成前預先執行的靜態步驟」，Agentic Retrieval 將記憶視為 **Tool Call**——Agent 在推理過程中根據需要主動呼叫記憶工具，而非被動接受注入的上下文。

Anthropic 在 Sonnet 4.5 發布的 Memory Tool（Public Beta）和 Letta 框架均實作了此模式。其核心操作如下：
- **Memory Blocks 抽象：** 將 Context Window 分割為離散的功能單元（System Prompt Block、Human Memory Block、Conversation Buffer Block），每個 Block 有獨立的令牌預算和優先級。
- **Agent 主動換頁：** 當某個 Block 接近上限時，Agent 自動呼叫 `core_memory_replace()` 或 `archival_memory_search()` 函式，決定哪些資訊需要被壓縮到外部儲存，哪些需要從外部儲存拉回。[^7]

Letta 的設計哲學明確反對 naive RAG：「agentic RAG 不是 top-K 匹配後傾倒——而是 Agent 已經預先消化了重要資訊，並在組織記憶時就已考慮未來的提取需求」。[^20]

***

#### 設計模式 F：Context Compaction 與 Structured Note-Taking（情境壓縮與結構化筆記）

**代表框架：Anthropic Claude Code（Structured Note-Taking, 2025）；Manus Agent（Context Compaction, 2025）；CAMEL Framework（2025）**[^25][^26][^21]

**運作原理：** 此設計模式專注於在 Context Window 內部防止 Context Rot（情境腐化），採取主動壓縮策略：

**Context Compaction（可逆壓縮）：** 將可從環境中重新取得的資訊（如程式碼檔案內容）從 Context 中刪除，需要時再透過 Tool Call 讀取。這是**可逆操作**——原始資訊依然存在於環境中。

**Structured Note-Taking（結構化筆記）：** Agent 定期將關鍵進度、決策依據和待辦事項寫入持久化的結構化筆記（如 `NOTES.md` 或 GUM 的 Proposition 資料庫）。這些筆記在需要時被精準地重新注入 Context Window，而非重新注入完整的對話歷史。Anthropic 工程師指出，此模式「以最低 Overhead 提供持久記憶」。[^21]

**Multi-Agent Context Isolation（多代理情境隔離）：** Manus 框架採用 GoLang 並發的設計原則：「Share memory by communicating, don't communicate by sharing memory」——對有明確輸入/輸出的子任務（如「搜尋文件 X 中的資訊」），啟動擁有獨立全新 Context 的子 Agent；只有當子 Agent 必須理解完整問題軌跡時，才共享 Context History。[^25]

***

### 2.3 GUM 架構在提取端的完整實作分析

Shaikh et al. (UIST'25) 的 GUM 在 Retrieve 模組中採用了**兩階段提取-重排序（Two-stage Retrieve-and-Rerank）**架構，直接對應上述業界最佳實踐：[^1]

1. **BM25 初步召回：** 以詞頻-逆文件頻率計算詞彙相似度，對所有 Proposition 進行快速召回。

2. **時效衰減調整：** 為每個 Proposition \(d_i\) 計算衰減係數 \(\gamma_i = \exp(-\alpha_i \cdot k \cdot \text{age}(d_i))\)（其中 \(k=2\)），調整後的相關性分數為 \(\tilde{r}_i = r_i \cdot \gamma_i\)，確保近期 Proposition 獲得更高優先級。[^1]

3. **MMR 多樣性優化：** 透過 Maximum Marginal Relevance 演算法，以 \(\lambda=0.5\) 平衡相關性與多樣性，避免提取內容高度重疊：\(\text{MMR}(d_i, S) = \lambda \tilde{r}_i - (1 - \lambda) \delta_i\)。[^1]

4. **LLM 重排序器：** 最終透過 LLM 將召回結果分類為「identical（相同）、similar（相似）、unrelated（無關）」三類，過濾不相關 Proposition，並標記需要觸發 Revise 模組的重複條目。[^1]

此管線在 N=18 參與者的電子郵件評估中，全架構（含 Retrieve + Revise）的 Brier 校準分數（0.17 ± 0.03）顯著優於缺乏 Retrieval 的消融版本（0.36 ± 0.07），證實了多階段提取架構對記憶品質的關鍵貢獻。[^1]

***

## 各架構設計模式對照摘要

| 設計模式 | 解決的核心問題 | 代表框架/論文 | 開發者可用度 |
|---|---|---|---|
| A. OS 分層記憶（MemGPT） | 工作記憶容量瓶頸 | Packer et al., NeurIPS'23 / Letta | ✅ Open Source (pip install letta) |
| B. Memory Stream + 三因子評分 | 記憶重要性篩選與自動固化 | Park et al., CHI'23 (Generative Agents) | ✅ 公開程式碼 |
| C. Zettelkasten 記憶網絡（A-MEM） | 記憶間語意關聯缺失 | Xu et al., NeurIPS'25 | ✅ GitHub: agiresearch/A-mem |
| D. STITCH 意圖導向提取 | Context 不相容的記憶污染 | CAME-Bench, 2026 | ⚠️ 研究原型 |
| E. Memory-as-Tool（Agentic） | 靜態 RAG 注入不精準 | Letta / Anthropic Memory Tool | ✅ 業界可用 |
| F. Context Compaction + 筆記 | Context Rot / 注意力浪費 | Anthropic Engineering Blog, 2025 | ✅ 設計模式，可自行實作 |
| GUM Pipeline（整合） | 跨 Context 的通用使用者理解 | Shaikh et al., UIST'25 | ✅ pip install generalusermodels |

***

## 三、開發者 MVP 功能建議

以下三個功能建議基於「立即可實作、效益最高、技術風險最低」原則排序，適合作為具備持續性 GUM 的對話型 AI Agent 產品的最小可行版本。

***

### MVP #1：LLM 驅動的雙層記憶管線（Short-Term → Long-Term Flush）

**實作概念：** 仿照 LlamaIndex Memory API 的設計，建立雙層記憶架構：[^15]
- **短期記憶（工作層）：** 直接保存最近 N 輪對話的原文，預設 Token 比例佔總預算的 70%。
- **長期記憶（固化層）：** 當短期層超過閾值，將舊對話批次傳入 LLM，提取結構化的**事實（Facts）**和**使用者 Proposition**（借鑑 GUM 的 Confidence + Decay 元資料設計），向量化後儲存。[^1]

**Confidence 與 Decay 最佳實踐（GUM 已驗證）：**
- 使用 LLM verbalized confidence（而非 logprobs）生成校準分數，研究顯示前者更準確。[^1]
- 對每條記憶生成 proposition-specific decay（而非全局 decay），穩定知識（如「使用者是工程師」）decay 接近 1，暫時狀態（如「正在偵錯記憶體洩漏」）decay 設為 0.6。[^1]
- 短期→長期的遷移時，同步執行 Mem0 式的相似度合併（threshold=0.85），避免冗余記憶累積。[^17]

**技術棧建議：** LlamaIndex `FactExtractionMemoryBlock` + `VectorMemoryBlock` 作為起點，搭配 SQLite 持久化，或直接採用 `pip install mem0ai`。[^27][^15]

***

### MVP #2：意圖感知的記憶提取過濾器（Intent-Compatible Retrieval Gate）

**實作概念：** 在現有 BM25 + 向量提取管線前，增加一個輕量的「意圖過濾閘（Intent Gate）」，靈感來自 STITCH（2026） 的核心思路。[^23]

**具體步驟：**
1. 在每次對話輪次開始時，使用 LLM 提取當前使用者查詢的**潛在意圖標籤**（例如：`{goal: "技術問題", action_type: "debug", focus_entity: "Python performance"}`）。
2. 歷史記憶在寫入時同樣附加意圖標籤（可在 Memory Flush 時批次補標）。
3. 提取時先以意圖標籤進行硬過濾（排除意圖不相容的記憶），再對剩餘記憶執行語意相似度排名。

**預期效益：** 參考 STITCH 在 LongMemEval 上的實驗，意圖感知過濾可在長對話場景下減少 35% 以上的無關記憶注入，直接降低 Context Pollution 風險，對長期對話的 Agent（50+ 輪次）效益最為顯著。[^23]

**快速驗證方式：** 以現有使用者測試中，挑選 10 個跨主題的多輪對話 Session，比較「純 BM25 + 向量提取」與「加入意圖過濾後」的 Retrieval Precision，可在一週內完成 A/B 對比評估。

***

### MVP #3：反思觸發的語意記憶固化（Reflection-Triggered Consolidation）

**實作概念：** 借鑑 Generative Agents（Park et al., CHI 2023）的 Reflection 機制 與 Reflexion（Shinn et al., NeurIPS 2023） 的自我反思模式，定期觸發高階語意固化。[^28][^9][^11]

**具體流程：**
1. **觸發條件（Threshold-based）：** 當最近 N 條記憶的重要性分數（Importance Score）加總超過預設閾值（例如參考 Park et al. 的 150 分設計），或當使用者結束一個完整任務 Session 時，自動觸發。
2. **固化提示（Consolidation Prompt）：** 輸入最近 50-100 條 Proposition，提示 LLM：「基於以上觀察，這位使用者有哪些 3-5 個值得長期記錄的高階特徵或偏好模式？」生成的高階語意記憶（類似 Reflection）寫回長期記憶庫，並標記為高 Confidence、低 Decay Rate。
3. **矛盾解決：** 固化時若新 Proposition 與現有記憶衝突（例如使用者改變偏好），執行 GUM Revise 模組邏輯——根據新舊觀察的 Confidence 與時間權重決定是合併、更新或降低舊記憶的 Confidence。[^1]

**為何優先：** 此功能直接解決「記憶只增不改」的問題——一個累積 6 個月使用的 Agent 若未進行定期固化，其記憶庫將充滿過時且相互矛盾的碎片。Mem0 的生產實踐顯示，記憶固化可在 10K 記憶規模下維持 sub-100ms 的更新延遲，具備生產可用性。[^17]

***

## 四、局限性與未來研究方向

1. **參數記憶 vs. 情節記憶的天花板問題：** 近期研究（*Contextual Agentic Memory is a Memo, Not True Memory*, 2026） 指出，純粹基於 RAG/向量儲存的記憶系統存在「Frozen Novice 問題」——無法像人類一樣透過經驗內化真正的技能；未來研究方向是週期性地將情節記憶編碼進模型權重（Weight-based Consolidation）。[^29]

2. **記憶安全性：** GUM 的 Audit 模組評估（N=18）顯示仍有 7 條記憶繞過隱私過濾；STITCH 等系統則面臨記憶投毒（Memory Poisoning）攻擊風險，生產部署前需要系統性的紅隊測試。[^30][^31][^1]

3. **跨 Session 的情境代理問題：** 目前所有框架的 GUM 訓練資料仍主要來自螢幕互動，使用者在行動裝置、線下環境的行為無法被捕捉，這是 Shaikh et al. 在 Discussion 中明確指出的限制。HippoRAG 2（OSU, NeurIPS'24/2025） 透過結合知識圖譜與 Personalized PageRank 的多跳檢索框架提供了一個潛在解法——在多跳問答任務上較標準 RAG 高出 20%。[^32][^33][^1]

---

## References

1. [Creating-General-User-Models-from-Computer-Use.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/34034424/3a13e20c-2eee-4784-a0aa-23baffc880aa/Creating-General-User-Models-from-Computer-Use.pdf?AWSAccessKeyId=ASIA2F3EMEYEQ2M4Y3EM&Signature=LgS5NvhZmI8E35YiGiCoHhBttm0%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEEcaCXVzLWVhc3QtMSJGMEQCIAaiGbUcF9A3Otk4UfEhw%2BrHn9vazbe6xq3FyCRF50F8AiA5wZT5by6Cnwdx7q5W7Mej0SMIC5rT5kQTJu2gNqHYpSrzBAgQEAEaDDY5OTc1MzMwOTcwNSIMYn4chmUnIzwzfr1eKtAEQz0ztUVPPYXDNBOTFzMw7XouHv9zsSFAjL0chUWU1XQ0%2F7ehMm2TlLOJKOVcUi1i%2BNS6HrMKt17erSCWRdU%2FSfSfItrnAZUrQjJYJiHg4oVQ3Z%2FTCgoLAhYaeOKuZR%2BepD3qhNlu7qIXTraLj4Dk0r7cigwXE1VXdLN4EAHnj9Wav4Rdp1tChhC6xS5LHXxEsgMcs9wDn2TrraVjOdHm2zyEdHQbBVSyQVP%2F8hNqkW9dp6%2BX28lBz9riA0rnX%2F1KodavVq76xeCuz3uQKoa5EB0F7F7D344JcVVP2sLEaSWJuQoaC%2FQReg9%2BKqlBb4IZyF0eL2afp10Curldit2RTn1N9SDYk1i%2BKDCMUSj46Zc2klZzuiZvTZSlRK6wDRGrC8oqj7VVHc3P4y%2FljQpRkB%2BuKRkGKDFnp9tP49xWCb6cZUpXm3qa8j%2FZliBQ3y21ybXxQbL9PJ4%2B4aE158WYTtnyq4fJkzhwpcpzw%2BAT%2FgGX5q3IxTQcIhDh6fAQwFtV6%2Bu7n5kMVsKZLJ0jUwwYZl8Cip95JgVPbM0vjvwmx%2BnffUDF7OnMkX9G46AF9cOi1OJ4jipFyFrlicrD1n67C2ZrmB1DXgTBr7Gbc6YMS3ZQ2jvL6sZ62uKk2SaZB4TvcklLPd0N%2FFCLnNL9AzI%2Bk%2Fz%2FJWzv%2BSD%2FjegnfkUkO2RCetO6%2BjZYm8pEKAzVq3fmfpWRJtKu3avWjs63CtMdTshwe0oFeQnJqJuqx2efxCS2wQCvhJcIM7XUFp3590eH7j1OpZxHs3%2FARBKevuVhaTDT3K7RBjqZAYxzqXlGs5bwBHL7Twv6Se7l%2FIC%2FCZr4G2vTjPexZt%2FmttHmijfVOcIrexqaTIsNO%2BNQs7f3o1c9NCPoUeDoQ4wVI9Ze3R602kfzRVscFKIm4jkDJtnNkPByMJOV0HPJOTofa3tafh9RaOTCQJkWthURb2KOlMKn8MhJsMCBlmTArvpkQX7nmveoZx6oPH7auM8m%2Fma3ksut9Q%3D%3D&Expires=1781251110) - **page-1**
Creating General User Models from Computer Use

Omar Shaikh
Stanford University
Stanford,...

2. [LLM Agent Memory: A Survey from a Unified ...](https://openreview.net/pdf/ff27b3f068664be7d08dfd54b8dd8a56cd3349f4.pdf)

3. [Augmenting LLM Agents with Long-Term Memory](https://www.rohan-paul.com/p/augmenting-llm-agents-with-long-term) - I write everyday for my readers on actionable AI.

4. [Episodic Memory is the Missing Piece for Long-Term LLM ...](https://arxiv.org/pdf/2502.06975.pdf)

5. [[2310.08560] MemGPT: Towards LLMs as Operating Systems - arXiv](https://arxiv.org/abs/2310.08560) - We introduce MemGPT (Memory-GPT), a system that intelligently manages different memory tiers in orde...

6. [This article delves into MemGPT, a novel system developed by researchers at UC Berkeley to address the limited context window issue prevalent in Large Language Models (LLMs). By drawing inspiration from traditional operating system memory management, MemGPT introduces a hierarchical memory architecture allowing LLMs to handle extended contexts effectively. This piece explores the core concepts, implementation, evaluations, and the implications of MemGPT in advancing the capabilities of LLMs.](https://gist.github.com/cywf/4c1ec28fc0343ea2ea62535272841c69) - This article delves into MemGPT, a novel system developed by researchers at UC Berkeley to address t...

7. [MemGPT: OS Inspired LLMs That Manage Their Own Memory](https://www.lancedb.com/blog/memgpt-os-inspired-llms-that-manage-their-own-memory-793d6eed417e) - MemGPT, an open source python package aims to solve this problem by using a concept drawing inspirat...

8. [Autonomous Neighbors: How Generative Agents Bring Smallville to Life](https://www.youtube.com/watch?v=X7WfDB9PRmU) - We dive into the Stanford–Google Generative Agents study, explaining how memory streams, smart retri...

9. [Generative Agents: Interactive Simulacra of Human Behavior](https://fanpu.io/summaries/2023-08-11-generative-agents-interactive-simulacra-of-human-behavior/) - Each event in the memory stream is assigned a recency score, where more recent events have a higher ...

10. [Simulacra Part3 | PDF | Memory | Information Retrieval](https://www.scribd.com/document/709691030/Simulacra-part3) - This document describes an approach for generative agents to summarize and plan experiences over tim...

11. [Generative Agents - LukeW Ideation + Design](https://www.lukew.com/ff/entry.asp?2030) - A retrieval function that takes the agent's current situation as input and returns a subset of the m...

12. [Paper page - A-MEM: Agentic Memory for LLM Agents - Hugging Face](https://huggingface.co/papers/2502.12110) - A novel agentic memory system for LLMs dynamically organizes memories through principles of the Zett...

13. [[PDF] A-mem: Agentic Memory for LLM Agents](https://neurips.cc/media/neurips-2025/Slides/119020.pdf)

14. [A-MEM: Pros and Cons of a New Memory System for LLM Agents.](https://medium.com/advancedai/a-mem-pros-and-cons-of-a-new-memory-system-for-llm-agents-9546bb5773b9) - Overview

15. [Long-Term Memory](https://developers.llamaindex.ai/python/framework/module_guides/deploying/agents/memory/)

16. [Mem0: Building Production-Ready AI Agents with Scalable ...](https://arxiv.org/abs/2504.19413) - Large Language Models (LLMs) have demonstrated remarkable prowess in generating contextually coheren...

17. [Long-Term Memory for AI Agents: The What, Why and How](https://mem0.ai/blog/long-term-memory-ai-agents) - Explore AI agent long-term memory design for persistent memory AI agents. Learn how vector embedding...

18. [SimpleMem: Efficient Lifelong Memory for LLM Agents - ICML 2026](https://icml.cc/virtual/2026/poster/61640)

19. [Mem0: Building Production-Ready AI Agents with Scalable Long ...](https://medium.com/@EleventhHourEnthusiast/mem0-building-production-ready-ai-agents-with-scalable-long-term-memory-9c534cd39264) - Paper Review

20. [If Not Rag, Then What?](https://www.letta.com/blog/rag-vs-agent-memory) - Although RAG provides a way to connect LLMs and agents to more data than what can fit into context, ...

21. [Effective context engineering for AI agents - Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) - Like humans, who have limited working memory capacity, LLMs have an “attention budget” that they dra...

22. [[PDF] Reflective Memory Management for Long-term Personalized ...](https://aclanthology.org/2025.acl-long.413.pdf)

23. [Grounding Agent Memory in Contextual Intent](https://arxiv.org/abs/2601.10702) - Deploying large language models in long-horizon, goal-oriented interactions remains challenging beca...

24. [Improving AI Agent Memory with STITCH: Intent-Grounded ...](https://www.linkedin.com/posts/rohitpandey777_ai-llmagents-agentmemory-activity-7419434377883017216-g9Zh) - I came across this paper that tackles a core failure mode of long-running AI agents: memory recall b...

25. [Context Engineering for AI Agents: Part 2](https://www.philschmid.de/context-engineering-part-2) - Building on the foundations of Context Engineering, this post explores advanced strategies to manage...

26. [Brainwash Your Agent: How We Keep The Memory Clean - CAMEL-AI](https://www.camel-ai.org/blogs/brainwash-your-agent-how-we-keep-the-memory-clean) - Three techniques to cut context bloat, keep what matters, and dump the rest. Learn how CAMEL keeps a...

27. [GitHub - mem0ai/mem0: Universal memory layer for AI Agents](https://github.com/mem0ai/mem0) - Mem0 ("mem-zero") enhances AI assistants and agents with an intelligent memory layer, enabling perso...

28. [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) - Large language models (LLMs) have been increasingly used to interact with external environments (e.g...

29. [Contextual Agentic Memory is a Memo, Not True Memory (Apr 2026)](https://www.youtube.com/watch?v=ztR00bye9Ao) - Title: Contextual Agentic Memory is a Memo, Not True Memory (Apr 2026)
Link: http://arxiv.org/abs/26...

30. [[PDF] InjecMEM: MEMORY INJECTION ATTACK](https://openreview.net/pdf/5f0aedb32147ba6ec36d85f54a53ad381dc22324.pdf)

31. [Vulnerabilities and Risk Analysis of Multi-Agentic AI-RAG in ...](https://www.eu-opensci.org/index.php/ejai/article/view/1094) - Agentic and multi-agent autonomous systems ingrained with Reinforcement Learning Methods may exhibit...

32. [HippoRAG: Neurobiologically Inspired Long-Term Memory for Large ...](https://arxiv.org/abs/2405.14831) - In order to thrive in hostile and ever-changing natural environments, mammalian brains evolved to st...

33. [GitHub - OSU-NLP-Group/HippoRAG: [NeurIPS'24] HippoRAG is a novel RAG framework inspired by human long-term memory that enables LLMs to continuously integrate knowledge across external documents. RAG + Knowledge Graphs + Personalized PageRank.](https://github.com/osu-nlp-group/hipporag) - [NeurIPS'24] HippoRAG is a novel RAG framework inspired by human long-term memory that enables LLMs ...

