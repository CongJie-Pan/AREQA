# AREQA 相關學術研究與相似產品全景掃描

> **研究範圍**：針對 AREQA 系統三大核心機制——①自適應 RAG 知識庫（Spaces）②EDF 教育鷹架引導（Evidence-Decision-Feedback）③ComPeer 主動關懷陪伴——進行學術研究成果與市場產品的全面對應分析。

***

## 執行摘要

AREQA 的設計理念高度契合當前 EdTech AI 研究的前沿方向。在學術界，2024–2026 年間出現了多篇直接對應你三大機制的重要論文：EDF 框架本身已被 arXiv 2026 年論文正式命名、ComPeer 的核心論文在 UIST 2024 發表、LOOM 則是與你的長效陪伴願景高度重疊的 2025 年成果。更重要的是，這些研究目前仍主要停留在學術原型階段，市場上尚無整合三者於一體的商業產品——這正是 AREQA 的差異化機會所在。

***

## 第一部分：Adaptive RAG Spaces（自適應文件知識庫）

### 學術研究對應

#### Adaptive-RAG（2024，arXiv）
這是與你 Spaces 機制最直接對應的學術框架。論文提出「根據問題複雜度動態選擇最適檢索策略」——從零檢索、單步檢索到迭代多步檢索三個層次，以一個輕量分類器自動判斷查詢複雜度。這對 EDF 判斷「用戶此時的問題是簡單概念澄清，還是需要跨段落整合的深度問題」有直接的實作參考價值。[^1][^2]

**對 AREQA 的啟示**：在 Spaces 的查詢介面層，可加入複雜度分類器，動態決定是否啟用 Reranker（簡單查詢跳過 Reranker 節省成本，複雜查詢啟用多步檢索）。[^2]

#### OwlMentor：大學生閱讀理解 RAG 系統（2024，Frontiers in Psychology）
這是與 AREQA 最相近的學術產品原型。OwlMentor 是一套 AI 學習環境，讓大學生上傳科學論文並透過 RAG 系統進行文件問答，支援自主提問、自動生成問題與測驗等功能，歷經兩個學期的課程整合評估。關鍵發現：**使用者的一般自我效能感（self-efficacy）強烈影響他們對系統的接受度與實際使用率**，系統設計需降低初始障礙感。[^3][^4]

| OwlMentor 功能 | AREQA 對應設計 |
|---|---|
| 文件上傳 + RAG 問答 | Spaces 機制 |
| 自動生成問題 | EDF 鷹架引導（情境題） |
| 測驗功能 | EDF 形成性評量 |
| 無主動介入 | ❌（AREQA 的 ComPeer 超越此點） |

#### NotebookLM 作為蘇格拉底式物理教師（2025，arXiv）
這篇論文直接研究了以 RAG 配置的 NotebookLM 作為教學工具的效果。研究者透過一份「教學手冊（Training Manual）」將 RAG 系統的行為限定為蘇格拉底式對話，而非直接給答案。核心發現：**RAG 能大幅改善 LLM 的事實準確性，但動機管理（motivation management）是主要的未解挑戰**——這也正是 AREQA ComPeer 機制要解決的問題。[^5][^6]

#### RAG 增強學生學習（2025–2026，arXiv）
另一篇 2025 年的 arXiv 論文《Enhancing Student Learning via RAG-based Retrieval》更系統性地評估了封閉域 RAG 在課程資料上的教學效果，論證了閉域 RAG 相比通用 LLM 在避免幻覺與保持知識一致性上的優勢——支持你「Spaces 是封閉域知識庫」的設計方向。[^7]

### 市場競品分析

| 產品 | RAG 方式 | 主動教學引導 | 長效記憶陪伴 | 差異 |
|---|---|---|---|---|
| **Google NotebookLM** | ✅ 全託管，僅 Gemini | ❌ 無 EDF 機制 | ❌ | 被動 Q&A，無教學邏輯[^6] |
| **Anara（原 Unriddle）** | ✅ 文件問答，逐段引用 | ❌ | ❌ | 純研究輔助，無教學互動[^8] |
| **Khanmigo（Khan Academy）** | ❌ 參數知識 | ✅ 蘇格拉底引導 | ⚠️ 有限 | 無法上傳自訂文本[^9] |
| **ChatPDF / AskYourPDF** | ✅ | ❌ | ❌ | 純 Q&A，無鷹架[^10] |
| **Atlas Workspace** | ✅ 多來源 | ❌ | ❌ | 企業定位，非教學[^11] |
| **AREQA（你的系統）** | ✅ 用戶上傳動態建庫 | ✅ EDF 自適應鷹架 | ✅ ComPeer 跨時空 | **三者整合，市場空白** |

***

## 第二部分：EDF 教育鷹架引導機制

### 學術研究對應

#### Evidence-Decision-Feedback（EDF）框架本身（arXiv 2026）
你在系統中使用的「EDF」名稱並非巧合——學術界在 2026 年 2 月正式發表了名為 **Evidence-Decision-Feedback: Theory-Driven Adaptive Scaffolding for LLM Agents** 的論文，發表於 arXiv。論文提出 EDF 框架「整合智能教學系統與代理行為，圍繞證據推理、教學決策和自適應回饋三個環節組織互動」。作者們透過 Copa（一個 STEM 問題解決協作代理）驗證了 EDF 對齊的互動能夠：促進漸進式鷹架消退（scaffold fading）、提供可解釋的以證據為基礎的說明、並避免過度依賴。[^12]

> **這是你系統中 EDF 機制最直接的學術對應來源，強烈建議閱讀原始論文。**

#### Theory of Adaptive Scaffolding for LLM-Based Pedagogical Agents（AAAI 2026）
這篇發表於 AAAI 2026 正式會議的論文，提出結合「以證據為中心的設計（ECD）」、社會認知理論與維果斯基近側發展區（ZPD）的整合鷹架框架。論文透過 Inquizzitor（一個形成性評量代理）驗證：理論驅動的 LLM 教學代理能提供與認知科學原則一致的高品質評量與互動。[^13]

#### 知識學習指導（KLI）框架鷹架定制（arXiv 2026，LAK26）
2026 年 5 月的最新研究提出「不同診斷策略需要不同類型的鷹架支持」——這與你的設計中「EDF 根據不同 Space 領域（法律、技術文件、文學）調整策略」高度吻合。論文引入 KLI 框架對齊策略需求與鷹架方式，並驗證自適應混合代理能帶來更好的學習收益。[^14]

#### Vygotsky ZPD 與 AI 鷹架（2026）
一篇 2026 年的整合評論文章重新詮釋了維果斯基 ZPD 理論在 AI 輔助學習中的應用，強調 AI 作為中介工具如何通過自適應算法鷹架延伸 ZPD 的邊界。這為你的 EDF 設計提供了教育學理論基礎：AREQA 的角色是「使用者與其最近發展區之間的中介者」。[^15]

#### 個性化學習路徑規劃（LLMs）（arXiv 2024）
論文提出以 Prompt Engineering 引導 GPT-4 生成個性化學習路徑，實驗顯示在準確性、用戶滿意度和學習路徑品質上均優於基準方法。這對你的 EDF 中「根據 Space 屬性設計教學策略」的 LLM Prompt 設計具有直接的工程參考價值。[^16]

#### Khanmigo 實地研究（2025）
對 69 名大學生的研究顯示，Khanmigo 的逐步引導和個性化互動獲得了學生好評，但被視為補充工具而非替代品，且短期學習效果與傳統方法無顯著差異。這印證了**AI 鷹架的價值在長期陪伴與降低焦慮，而非短期速成**——這正是 AREQA ComPeer 的設計初衷。[^9]

**事後發現**：Khanmigo 被 Sal Khan 自己承認是「一個不重要的事件（a non-event）」，原因是它未能解決「動機維持」與「情緒陪伴」的問題——AREQA 的 ComPeer 機制正是為了補足這個缺口。[^17]

***

## 第三部分：ComPeer 主動關懷陪伴機制

### 學術研究對應

#### ComPeer 原始論文（UIST 2024，ACM）
你的系統中直接引用的 ComPeer 論文（Liu et al., 2024）發表於 ACM UIST 2024，是 HCI 領域最頂尖的會議之一。系統包含五個核心模組：[^18][^19]
- **Memory Module**：短期 + 長期記憶資料庫，維護對話歷史脈絡
- **Event Detection Module**：偵測對話中的情緒狀態或重要事件，決定介入時機
- **Reflection Module**：每日反思用戶互動以優化後續策略
- **Schedule Module**：綜合 Reflection 與 Event Detection 制定主動關懷排程
- **Dialogue Generation Module**：融合人格設定、記憶與同伴支持策略生成訊息[^20]

**核心實驗結果**：與 24 名參與者進行的一週隨機對照實驗顯示，使用 ComPeer 的用戶感知壓力顯著下降，且更願意主動分享感受；用戶特別欣賞 ComPeer 展現的主動關心。**值得注意的副作用**：ComPeer 的自我揭露（self-disclosure）有時會造成社交壓力，提示主動訊息的頻率與內容需要精心調校。[^20]

#### LOOM：基於每日 LLM 對話的個性化學習（arXiv 2025）
LOOM 是你 AREQA 長效陪伴願景的最近似學術原型。它是一個四階段代理管道：[^21][^22]
1. **對話觀察與摘要**：持續監控用戶與 LLM 的日常對話，提取學習意圖
2. **主題決策與課程大綱生成**：「強化模式」鞏固近期頻現主題；「探索模式」推薦相鄰概念，主動揭示「未知的未知」
3. **動態學習者記憶圖譜**：分層表示學習者知識狀態，跨會話維持連貫性
4. **完整課程生成**：將對話轉化為個性化迷你課程（含多選測驗）[^23]

在 10 名參與者的形成性研究中，用戶高度評價 LOOM 能識別知識空白並與近期對話保持關聯性。LOOM 與 AREQA 的差異在於：LOOM 聚焦長期知識構建，而 AREQA 的 ComPeer 更強調**即時情緒偵測與主動介入**。兩者可互補。[^23]

### AREQA ComPeer 的設計關鍵提示

來自 ComPeer 論文的工程建議，直接適用於你的系統：

- **「Dwell 偵測」的實作方式**：使用 Event Detection Module，以滾動時間窗口監控用戶在某個文本段落的停留時間，並結合查詢行為（如翻查同一詞彙多次）判斷卡關信號[^24][^20]
- **主動訊息的頻率控制**：實驗數據顯示過於頻繁的主動訊息會降低用戶體驗，建議在用戶反應冷淡時逐漸降低介入頻率[^20]
- **跨時空陪伴（Cold Memory）**：使用長期記憶資料庫，在用戶下次登入時根據上次的學習進度生成個性化的歡迎訊息和學習建議[^21]

***

## 第四部分：AREQA 定位矩陣與差異化機會

### 現有產品的核心缺口

| 產品類型 | 代表產品 | 缺少什麼 |
|---|---|---|
| 被動文件 Q&A | NotebookLM、ChatPDF | 無教學引導邏輯，無主動介入 |
| 靜態 AI 家教 | Khanmigo | 無法上傳自訂文本；無情緒陪伴[^17] |
| 純研究助理 | Anara（Unriddle）| 無學習路徑；無陪伴記憶[^8] |
| 學術 RAG 原型 | OwlMentor、LOOM | 尚未商業化；無整合系統[^3][^23] |

### AREQA 的護城河

AREQA 的核心差異化在於整合三個目前分散在不同學術原型中的機制：

1. **Adaptive RAG Spaces**：任意文本→個人化知識庫（市場上 NotebookLM 做到，但無後兩項）
2. **EDF 鷹架引導**：根據文本領域自動調整教學策略，有理論基礎（市場上 Khanmigo 接近，但無自訂文本能力）
3. **ComPeer 主動關懷**：偵測 Dwell 行為、跨時空記憶（這是市場上所有現有產品的盲點）[^18][^17]

### 可引用的學術支撐

在你的產品說明或後續論文中，以下研究可作為 AREQA 設計的學術背書：

- **EDF 框架**：Cohn et al. (2026). *Evidence-Decision-Feedback: Theory-Driven Adaptive Scaffolding for LLM Agents.* arXiv:2602.01415[^12]
- **ComPeer 機制**：Liu et al. (2024). *ComPeer: A Generative Conversational Agent for Proactive Peer Support.* UIST 2024. DOI: 10.1145/3654777.3676430[^19][^18]
- **LOOM 長效學習**：(2025). *LOOM: Personalized Learning Informed by Daily LLM Conversations.* arXiv:2511.21037[^22][^21]
- **ZPD 與 AI**：Naik (2026). *AI as a Mediational Tool: Reinterpreting Vygotsky's ZPD in AI-Assisted Learning.* IJFMR, 8(1)[^15]
- **OwlMentor（最近似原型）**：Frontiers in Psychology (2024). DOI: 10.3389/fpsyg.2024.1474892[^3]
- **Khanmigo 反面教材**：Slijepcevic & Yaylali (2025). *Leveraging Khanmigo for Personalized Tutoring.* Journal of Teaching and Learning[^9][^17]

***

## 結論：AREQA 的學術定位

目前學術界已有大量研究分別驗證了 AREQA 三大機制的有效性，但**尚無一個商業產品將三者整合於封閉域（用戶自訂文本）的教育互動場景**。你的系統設計正好填補了 NotebookLM（有 RAG 無教學）和 Khanmigo（有教學無自訂文本）之間的空白，且以 ComPeer 的主動關懷解決了所有現有產品的動機維持問題。

從研究角度而言，AREQA 若能收集用戶資料，未來本身具備成為一篇 CHI/UIST 論文的潛力——尤其是「Dwell 偵測→EDF 介入策略→學習成效」這條因果鏈，目前在學術文獻中尚未有人在真實封閉域 RAG 場景下完整驗證。

---

## References

1. [Learning to Adapt Retrieval-Augmented Large Language Models ...](https://arxiv.org/html/2403.14403v1) - We propose a novel adaptive QA framework, that can dynamically select the most suitable strategy for...

2. [Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity](https://arxiv.org/abs/2403.14403) - Retrieval-Augmented Large Language Models (LLMs), which incorporate the non-parametric knowledge fro...

3. [Exploring generative AI in higher education: a RAG system to ...](https://pubmed.ncbi.nlm.nih.gov/39463458/) - This study explores the implementation and evaluation of OwlMentor, an AI-powered learning environme...

4. [Exploring generative AI in higher education: a RAG system to ...](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2024.1474892/full) - OwlMentor, named after our wise university mascot, includes features to enhance scientific text comp...

5. [This study shows how NotebookLM, using RAG, acts ...](https://x.com/rohanpaul_ai/status/1916336501366927409)

6. [[2504.09720] NotebookLM as a Socratic physics tutor - arXiv](https://arxiv.org/abs/2504.09720) - This study explores NotebookLM, a Google Gemini - powered AI platform that integrates Retrieval-Augm...

7. [Enhancing Student Learning via RAG-based Retrieval - arXiv](https://arxiv.org/html/2506.23026v1)

8. [Looking for an Unriddle AI alternative? Start here - Anara](https://anara.com/blog/unriddle-ai-alternative) - If you're searching for Unriddle AI alternatives, you might not realize that Unriddle has rebranded ...

9. [EJ1487444 - Leveraging "Khanmigo" Generative AI-Powered ... - ERIC](https://eric.ed.gov/?id=EJ1487444) - This mixed-methods study investigated the effectiveness of Generative AI (GenAI) powered intelligent...

10. [Unriddle - Trending AI tool for Document Q&A and best alternatives](https://www.tipseason.com/ai-tool/intellecs_ai) - Simplified PDF retrieval through questioning.

11. [8 Best NotebookLM Alternatives (2026): AI-Powered Research - Atlas](https://www.atlasworkspace.ai/blog/notebooklm-alternatives) - NotebookLM alternatives compared: Atlas, Elicit, Claude Projects, and Perplexity scored on source ha...

12. [Theory-Driven Adaptive Scaffolding for LLM Agents - arXiv](https://arxiv.org/abs/2602.01415) - To address this, we introduce Evidence-Decision-Feedback (EDF), a theoretical framework for adaptive...

13. [A Theory of Adaptive Scaffolding for LLM-Based Pedagogical Agents](https://arxiv.org/abs/2508.01503) - Abstract page for arXiv paper 2508.01503: A Theory of Adaptive Scaffolding for LLM-Based Pedagogical...

14. [Tailoring Scaffolding to Diagnostic Strategies: Theory-Informed LLM-Based Agents](https://arxiv.org/abs/2605.04996) - Learning analytics systems increasingly integrate large language models (LLMs) to provide adaptive s...

15. [Reinterpreting Vygotsky's Zone of Proximal Development in AI ...](https://www.ijfmr.com/research-paper.php?id=70040) - The research explores how AI supports learners in tasks they cannot complete inde-pendently but can ...

16. [Educational Personalized Learning Path Planning with Large Language Models](https://www.arxiv.org/abs/2407.11773) - Educational Personalized Learning Path Planning (PLPP) aims to tailor learning experiences to indivi...

17. [Khanmigo Was 'a Non-Event.' What's Next for AI Tutors - AgentConn](https://agentconn.com/blog/ai-tutoring-agents-post-khanmigo-mytutor-2026/) - Sal Khan admitted Khanmigo was 'a non-event.' Quizlet killed Q-Chat. The teacher tools won. Here's w...

18. [A Generative Conversational Agent for Proactive Peer Support](https://dl.acm.org/doi/abs/10.1145/3654777.3676430) - In this paper, we develop ComPeer, a generative CA that can proactively offer adaptive peer support ...

19. [ComPeer: A Generative Conversational Agent for Proactive ...](https://duruofei.com/cites/Liu2024ComPeer.html)

20. [[Revue de papier] ComPeer: A Generative Conversational Agent for Proactive Peer Support](https://www.themoonlight.io/fr/review/compeer-a-generative-conversational-agent-for-proactive-peer-support) - **ComPeer: A Generative Conversational Agent for Proactive Peer Support** ### Overview "ComPeer" is ...

21. [LOOM: Personalized Learning Informed by Daily LLM ... - arXiv](https://arxiv.org/html/2511.21037v1) - We present LOOM, an agentic pipeline that infers evolving learner needs from recent LLM conversation...

22. [LOOM: Personalized Learning Informed by Daily LLM Conversations Toward Long-Term Mastery via a Dynamic Learner Memory Graph](https://arxiv.org/abs/2511.21037v1)

23. [[论文评述] LOOM: Personalized Learning Informed by Daily LLM ...](https://www.themoonlight.io/zh/review/loom-personalized-learning-informed-by-daily-llm-conversations-toward-long-term-mastery-via-a-dynamic-learner-memory-graph) - 该论文介绍了LOOM系统，一个通过日常大型语言模型（LLM）对话来个性化学习，并利用动态学习者记忆图谱实现长期掌握的智能代理管道。传统LLM聊天助手虽然能回答问题，但缺乏主动引导学习和识别学习者“未知...

24. [A Generative Conversational Agent for Proactive Peer Support - arXiv](https://arxiv.org/html/2407.18064v1) - In this paper, we develop ComPeer, a generative CA that can proactively offer adaptive peer support ...

