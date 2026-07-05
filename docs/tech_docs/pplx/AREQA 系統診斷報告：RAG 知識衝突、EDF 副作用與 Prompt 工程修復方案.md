# AREQA 系統診斷報告：RAG 知識衝突、EDF 副作用與 Prompt 工程修復方案

***

## 執行摘要

你的 AREQA 系統在處理《西方憑什麼》序章的反事實歷史場景時發生了一個典型的**多層失效疊加（Cascading Failure）**：檢索層的資訊破碎、LLM 的參數偏見、EDF 的認知降載指令，以及蘇格拉底式結尾的輸出格式限制，四個因素同時作用，讓「這是虛構情節」這個最關鍵的事實被過濾掉。你提出的 4 個診斷方向全都成立，但權重並不相等。本報告將逐一評估，並提供 3 個可落地的修復方案，附帶具體 Prompt 範本。

***

## 第一部分：4 個診斷假設的深度評估

### 原因 1：API Snippet vs. 全網頁解析（★★★★☆ 高度成立）

這是**根本原因**中最客觀的一個。Perplexity `search_context_size` 參數決定了從網頁抓取多少內文：`"low"` 適合短事實查詢；`"high"` 才適合「需要引文覆蓋度的研究性問題」。即便你已設為 `"high"`，API 回傳的仍是各網頁的**摘要片段（Snippets）**，而非全文。原生 Perplexity App 在 UI 層可能有後備的全文解析管道，能讀取書籍評論、書摘頁面中明確標注「反事實」的段落。[^1]

此問題在 RAG 社群已有充分記錄：**資訊的關鍵語意（如「虛構」、「假想」）往往集中在段落的前幾句，若 Snippet 截斷點不恰當，這些字眼就會消失**。更根本的是，「這段話是虛構情節」這類**元資訊（meta-information）**很少出現在搜尋結果的標題或摘要，而會藏在文章正文的第二、三段中。[^2][^3]

**結論：** 這是你系統的資訊輸入品質問題，在現有 API 限制下需要用 Query Rewriting 來補償。

***

### 原因 2：模型參數知識與碎片化上下文的衝突（★★★★★ 核心病因）

這是學術界研究最充分的 RAG 失效模式，稱為「**參數知識與上下文知識衝突（Parametric vs. Contextual Knowledge Conflict）**」。[^4][^5]

研究表明，當 RAG 取回的文本片段含有「與 LLM 訓練資料相矛盾」的資訊時，模型傾向於**遵循其參數記憶（訓練資料的常識）**而非外部上下文。在你的案例中：[^6][^4]

- LLM 的參數記憶：「鴉片戰爭 → 清朝戰敗 → 耆英簽署條約（真實歷史）」
- API Snippet 的上下文：「耆英押走英國親王去北京（反事實片段）」

兩者形成直接衝突。LLM 的處理邏輯是：「API 返回的片段可能是一個錯誤的資料」，因此**以參數記憶蓋過了上下文，同時用真實歷史（Looty 的故事）填充了答案的空白**。這並非幻覺，而是模型在資訊不完整時的**理性回退**（rational fallback）——但結果對使用者而言是致命的錯誤。[^7][^8]

更嚴重的是，**小型模型**（如你可能使用的成本考量下的 LLM）在「抵抗上下文干擾」方面更弱，遇到衝突時更容易直接丟棄上下文。這意味著你的問題在使用較小模型時會更加顯著。[^6]

**結論：** 這是 RAG 架構的核心痛點，需要在 Prompt 中**明確指示 LLM 優先信任上下文，並要求它標記上下文中的反常資訊（anomalies）**。

***

### 原因 3：EDF 認知降載指令的副作用（★★★☆☆ 部分成立，但可控）

EDF 框架（Evidence-Decision-Feedback）的設計目標是根據學習者狀態動態調整鷹架支援（adaptive scaffolding），這在學術上有充分理論依據，包含社會認知理論（SCT）和最近發展區（ZPD）。[^9]

然而，你的問題在於**Decision Module 的輸出過於粗粒度**。將使用者標記為 `STARTING` 並注入「降低認知負荷、一次講一個重點」，是對 **ZPD 原則的錯誤應用**：ZPD 強調的是在學習者的現有知識之上「適度拉伸（stretch）」，而非**省略關鍵事實**。「這是虛構情節」並不是進階知識，而是理解整個段落的**前提條件**——省略它等於給了學生一個根本性的錯誤地基。[^9]

Copa（EDF 的實驗實作）研究中也發現了類似問題：學生有時對蘇格拉底式的引導感到沮喪，因為他們期待直接答案。這說明**當問題是事實澄清（factual disambiguation）而非概念探索（conceptual exploration）時，Socratic 策略反而適得其反**。[^9]

**結論：** EDF 本身沒錯，但 Decision Module 需要加入**查詢類型偵測（query type detection）**：事實澄清型問題應強制完整輸出，不受認知降載指令的覆蓋。

***

### 原因 4：強制蘇格拉底式結尾的輸出包袱（★★☆☆☆ 次要因素，但可能有疊加效應）

強制以引導式問句結尾會對 LLM 的輸出造成**輸出格式壓力（output format pressure）**。研究顯示，當系統 Prompt 包含過多衝突性約束時，LLM 傾向於**部分合規（partial compliance）**——它會優先滿足格式要求（結尾要有問句），但在這個過程中壓縮了正文中的資訊密度。[^10]

此外，為了讓結尾問句顯得有意義，LLM 傾向於**選擇它能「引導」的內容**（如真實歷史人物，因為可以問「你覺得耆英為何選擇如此行動？」），而不是它無法輕易引導的內容（如「你知道這其實是虛構情節嗎？」——因為這個引導太突兀）。

**結論：** 這是一個**間接影響**，本身不致命，但與原因 2、3 疊加後產生了明顯的惡化效果。解法是為「事實核查型輸出」建立一個**不受蘇格拉底式結尾約束的豁免通道**。

***

## 第二部分：3 個可落地的修復方案

***

### 方案 A：查詢預分類 + 雙軌 Prompt 路由（推薦優先實作）

**核心思路：** 在主模型接收到使用者查詢之後、EDF 評估之前，插入一個輕量級的**查詢類型分類器（Query Classifier）**。當分類結果為「事實澄清」或「文本解析」時，自動進入「完整事實輸出通道」，繞過認知降載指令和蘇格拉底式強制結尾。

**架構變動：**

```
使用者輸入
    ↓
[新增] Query Classifier LLM（輕量，如 GPT-4o-mini）
    ↓ 判斷查詢類型
    ├─ 類型 A：事實澄清 / 文本解析 → 完整事實輸出 Prompt（FP）
    └─ 類型 B：概念探索 / 問題解決 → 原有 EDF 蘇格拉底 Prompt（SP）
    ↓
主模型（根據路由選擇 FP 或 SP）
```

**Query Classifier Prompt 範本：**

```text
你是一個查詢類型分析器。請判斷以下使用者查詢屬於哪種類型，只回答分類代號。

查詢類型定義：
- FACTUAL_CLARIFICATION：使用者在詢問「某段文字/某個場景在講什麼」、「這些人物是誰」、
  「這是真實的還是虛構的」。核心需求是：確認事實，不能省略。
- CONCEPT_EXPLORATION：使用者在探索「為什麼」、「如何應用」、「有什麼影響」等開放性
  概念問題。核心需求是：引導思考。

使用者查詢：{user_query}

分類結果（只回答 FACTUAL_CLARIFICATION 或 CONCEPT_EXPLORATION）：
```

**完整事實輸出 Prompt（FP）的關鍵指令：**

```text
【優先規則 - 此段為最高優先級，覆蓋所有其他教學指令】
使用者的查詢屬於「文本事實澄清」類型。在此類查詢中，你必須：

1. **優先信任以下 RAG 上下文，即使其內容與你的訓練記憶相矛盾**。
   如果上下文中出現「反事實」、「假想」、「虛構」、「alternate history」等跡象，
   你必須明確、完整地告知使用者。
2. **不省略任何關鍵性質判斷**（如：這是小說情節、這是虛構場景、這是反事實歷史）。
3. 本次回答不需要以引導式問句結尾，可以直接平鋪直敘。

RAG 上下文：
{rag_context}

使用者問題：{user_query}
```

**優點：** 完整保留 EDF 邏輯的精髓，只在必要時動態解除約束。實作成本低，只需新增一個分類步驟。

***

### 方案 B：RAG 前置查詢增強（Query Augmentation）+ 元資訊標注

**核心思路：** 在送出 Perplexity API 請求之前，用 LLM 將使用者的原始查詢**重寫為多個強化查詢**，其中至少包含一個專門捕捉「文學性質」的查詢。同時，對 API 返回的 Snippets 進行**元資訊標注（metadata tagging）**，讓主模型清楚知道哪些片段是「書籍情節描述」而非「真實歷史敘述」。[^11][^12]

**查詢增強 Prompt 範本：**

```text
你是一個 RAG 查詢優化器，服務於一個教育問答系統。

使用者原始查詢：「{user_query}」

請生成 3 個互補的搜尋查詢，確保覆蓋以下三個維度：
1. 【人物/事件查詢】：針對使用者提到的人名、事件的真實歷史背景。
   範例：「耆英 清朝外交官 歷史」
2. 【文本性質查詢】：專門探索此文本的文學手法、是否為虛構、是否為反事實歷史。
   範例：「Ian Morris Why the West Rules 序章 反事實 虛構 alternate history」
3. 【書籍上下文查詢】：搜尋此書的整體架構和序章目的，以確認引用場景的敘事功能。
   範例：「Why the West Rules for Now prologue counterfactual scenario purpose」

請以 JSON 格式輸出，欄位為 query_1、query_2、query_3。
```

**Snippet 元資訊標注模組（Post-Retrieval Processing）：**

```python
# 在 RAG 返回 Snippets 後，呼叫輕量 LLM 為每個 Snippet 打上標籤
SNIPPET_CLASSIFIER_PROMPT = """
以下是一段從網路搜尋取得的文字片段。請判斷此片段的內容性質。

片段：{snippet}

請回答以下問題（只回答 YES/NO）：
- is_fiction_or_counterfactual: 此片段是否描述虛構情節或反事實歷史場景？
- is_historical_fact: 此片段是否描述真實歷史事件？
- is_book_analysis: 此片段是否在分析一本書的文學手法或結構？

輸出格式（JSON）：{"is_fiction": bool, "is_historical_fact": bool, "is_book_analysis": bool}
"""

# 將標注結果注入主模型 Prompt：
CONTEXT_WITH_METADATA = """
以下是 RAG 系統檢索到的資訊片段，每個片段附有類型標注，請據此判斷其可信度和適用性：

[片段 1] [類型: 書籍虛構情節描述]
{snippet_1}

[片段 2] [類型: 真實歷史事實]
{snippet_2}

[片段 3] [類型: 文學手法分析]
{snippet_3}
"""
```

**優點：** 從資訊輸入端解決問題，讓 RAG 上下文本身就帶有「這是虛構」的明確標記，大幅降低 LLM 的主觀判斷壓力。[^13][^14]

***

### 方案 C：鏈式推理接地（Chain-of-Thought Grounding）+ 事實優先聲明

**核心思路：** 這是一個純 Prompt Engineering 的方案，不改變架構，只修改主模型的系統 Prompt。通過插入一段**強制 CoT 推理步驟**，讓模型在給出最終答案前，先明確「解構 RAG 上下文 → 辨識內容性質 → 與參數記憶對比 → 明確標注異常」。[^15][^16]

**增強型系統 Prompt 核心片段：**

```text
【RAG 上下文處理規則 - 最高優先級】

在回答任何問題之前，你必須按以下步驟進行內部推理（可不在最終答案中顯示）：

步驟 1 - 上下文掃描：
仔細閱讀所有 RAG 片段，列出其中出現的「性質提示詞」：
- 虛構類：「假想」、「如果」、「反事實」、「alternate history」、「counterfactual」、
  「小說開頭」、「作者虛構」
- 真實類：「歷史上」、「實際上」、「根據史料」

步驟 2 - 衝突偵測：
比較上下文與你的訓練記憶。如果兩者描述同一事件卻不一致，優先相信上下文，
並在答案中明確指出衝突：
「根據我搜尋到的資料，這段描述與真實歷史不符，可能是作者使用了反事實的文學手法。」

步驟 3 - 事實性質優先聲明：
如果確認上下文描述的是「虛構/反事實情節」，答案的第一句話必須是：
「⚠️ 這段內容是[書名]中的虛構場景/反事實歷史情節，並非真實發生的歷史事件。」

步驟 4 - 教學模式判斷：
只有在完整傳達步驟 3 的關鍵性質之後，才可根據 EDF 狀態決定後續教學方式。
認知降載指令不得覆蓋步驟 3 的優先聲明。
```

**對比提示（Contrastive Prompting）增強：**

在 RAG 上下文注入段落加入以下指令，可顯著降低模型遵循參數記憶的傾向：[^7]

```text
以下文件包含權威資訊。即使你的訓練記憶與此不符，請以這些文件為準。
如果文件內容與你通常所知相矛盾，請信任文件，並在回答中明確指出這個差異。
```

**優點：** 不需要改動架構，修改量最小，可立即部署。對所有「內容性質辨識」型問題（不限於反事實歷史）都有幫助。[^16][^15]

***

## 第三部分：方案比較與實施建議

| 維度 | 方案 A（雙軌路由） | 方案 B（查詢增強 + 標注） | 方案 C（CoT 接地） |
|------|--------------|---------------------|----------------|
| **解決根本原因** | 原因 3、4 | 原因 1、2 | 原因 2、4 |
| **架構改動幅度** | 中（新增分類器步驟） | 中高（新增前/後處理模組） | 低（純 Prompt 修改） |
| **延遲影響** | +1 LLM 呼叫 | +2~3 API 呼叫 | 幾乎無影響 |
| **EDF 相容性** | 完整保留 EDF | 完整保留 EDF | 需調整 EDF 指令優先級 |
| **對文學性質辨識的效果** | 好（事前路由） | 最佳（上下文已標注） | 好（CoT 強制辨識） |
| **通用性** | 中（需維護查詢類型清單） | 高（標注邏輯可複用） | 高（適用所有查詢） |

**建議的實施順序：**

1. **立即可做**：部署**方案 C**，修改系統 Prompt 加入 CoT 接地規則和對比提示。成本為零，效果立竿見影。
2. **短期優化（1~2 週）**：在方案 C 基礎上疊加**方案 A 的 Query Classifier**，讓 EDF 的認知降載指令只對 `CONCEPT_EXPLORATION` 類型查詢生效。
3. **中期完善**：實作**方案 B 的 Snippet 元資訊標注模組**，從資訊輸入端徹底解決原因 1 和 2。

***

## 第四部分：這些痛點在 RAG 架構中的普遍性

你所遇到的問題並非個案。「**參數知識 vs. 上下文知識衝突**」被稱為 RAG 研究中最棘手的開放問題之一，近年有大量論文嘗試用強化學習框架（如 Knowledgeable-R1）來解決，尚無完美解法。[^17][^5][^6]

「**Prompt 指令過度飽和導致輸出品質下降**」同樣是已知問題：實驗顯示，「飽和型 Prompt」相比「適度型 Prompt」，幻覺率更高、約束遵從率更低。你的系統 Prompt 同時包含 EDF 指令、人設指令、教學策略和格式要求，符合「飽和型」特徵。[^10]

EDF 框架本身的 Copa 實驗也記錄了「蘇格拉底式引導 vs. 學生直接答案需求」的內在張力，說明這不是 AREQA 的特有問題，而是所有教育型 AI 系統的共同挑戰。建議在 EDF 的 Decision Module 中加入一個顯式規則：**當使用者的對話狀態為「文本解析求助（TEXT_INTERPRETATION）」時，強制切換為直接敘述模式，不引導不隱瞞**。[^9]

***

*本報告基於 2026 年 7 月最新 RAG 研究文獻、EDF 框架原始論文（AIED 2026）及 Perplexity API 官方文件撰寫。*

---

## References

1. [Search Context Size - Perplexity](https://perplexity.mintlify.app/guides/search-context-size-guide)

2. [RAG hallucinations: Why retrieval augmented generation can give ...](https://www.contentful.com/blog/rag-hallucinations-structured-data-fix/) - The post explains why RAG systems produce inaccurate answers and argues that unstructured source dat...

3. [RAG hallucinations explained: Causes, risks, and fixes - Mindee](https://www.mindee.com/blog/rag-hallucinations-explained) - Discover how hallucinations arise in Retrieval-Augmented Generation (RAG) models and learn practical...

4. [When Retrieved Evidence Conflicts with Model Memory - yAI](https://yaihq.com/research/knowledge-conflicts-rag) - RAG assumes models prioritize retrieved evidence over parametric memory. Empirical studies show this...

5. [Knowledge Conflicts for LLMs: A Survey](https://aclanthology.org/2024.emnlp-main.486.pdf) - by R Xu · 2024 · Cited by 347 — Contextual knowledge (context, including user prompts, dia- logue hi...

6. [Resisting Contextual Interference in RAG via Parametric- ...](https://openreview.net/forum?id=6Qc6sO1jh9) - by C Lin · Cited by 6 — It explicitly trains large language models (LLMs) to leverage parametric kno...

7. [Hallucination Mitigation: RAG, Decoding, and Training](https://mbrenndoerfer.com/writing/hallucination-mitigation) - RAG is excellent at preventing knowledge-gap hallucinations about specific, retrievable facts. Calib...

8. [Reducing Hallucinations in LLMs with Grounded Memory - Mem0](https://mem0.ai/blog/reducing-hallucinations-llms-with-grounded-memory) - Learn how grounded memory and RAG architectures reduce LLM hallucinations by 95%+. Explore retrieval...

9. [Theory-Driven Adaptive Scaffolding for LLM Agents](https://www.themoonlight.io/en/review/evidence-decision-feedback-theory-driven-adaptive-scaffolding-for-llm-agents) - This paper introduces Evidence-Decision-Feedback (EDF), a novel theoretical framework designed for a...

10. [Prompt Complexity vs Output Quality: When More ...](https://dev.to/jasrandhawa/prompt-complexity-vs-output-quality-when-more-instructions-hurt-performance-2hi5) - Why over-engineering your prompts might be the silent killer of LLM performance - and what to do...

11. [Metadata for RAG: Improve Contextual Retrieval | Unstructured](https://unstructured.io/insights/how-to-use-metadata-in-rag-for-better-contextual-results) - The process begins with identifying key metadata attributes relevant to the dataset, such as date, a...

12. [Leveraging LLM-Generated Metadata to Enhance RAG Systems](https://arxiv.org/html/2512.05411v1) - This research presents a systematic framework for metadata enrichment using large language models (L...

13. [What Types of Metadata Can Self-Querying RAG Models Use?](https://www.gigaspaces.com/question/what-types-of-metadata-can-self-querying-rag-models-use) - Learn what types of metadata self-querying RAG models use to improve search relevance, context filte...

14. [Improving RAG Models with Metadata - Deasy Labs](https://www.deasylabs.com/post/improving-rag-models-with-metadata) - In RAG models, metadata can encompass a wide range of information such as document timestamps, autho...

15. [Mitigating Hallucinations in RAG Outputs - ApX Machine Learning](https://apxml.com/courses/optimizing-rag-for-production/chapter-3-optimizing-rag-generation/mitigating-hallucinations-rag) - Apply various strategies to detect and mitigate hallucinations, enhancing the factual accuracy of RA...

16. [Improving the Reliability of LLMs: Combining Chain-of- ...](https://arxiv.org/html/2505.09031v1) - In this work, we investigate how combining CoT with retrieval-augmented generation (RAG), as well as...

17. [Large Language Models Meet Knowledge Conflicts in ...](https://arxiv.org/html/2410.15737v1) - Retrieval augmented generation (RAG) methods provide contextual knowledge to address this, but confl...

