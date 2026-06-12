# AREQA 系統學術定位與研究缺口分析報告

> **分析標的：** AREQA — Adaptive Retrieval-Augmented Educational QA System with General User Model, Adaptive Scaffold Fading, and Proactive Companion UX  
> **文獻覆蓋範圍：** 2023–2026 年 AIED、CHI、UIST、L@S、ICLR、NeurIPS、ACL/EMNLP/NAACL 頂會  
> **核心研究問題：** AREQA 的三柱整合架構在學術界是否已有人做過？發表潛力如何評估？

***

## 一、執行摘要

基於廣泛的文獻搜尋，結論是：**AREQA 的三柱整合——持續性 GUM 記憶 × 熟練度量化追蹤 × LLM 鷹架消退 × 主動陪伴 UX——作為一個完整系統，目前尚無公開論文將這三項能力整合在單一教育 QA 系統中**。現有研究在各個單一支柱上均有豐富文獻，但交叉口處（intersection）存在可辨識的研究缺口，具備高度發表潛力。

最接近的競爭者是 **PELICAN（ICLR 2026）** 和 **EDF/Copa（arXiv 2026）**，但兩者均缺少 AREQA 的第三支柱（主動陪伴 UX），且記憶機制也與 AREQA 的跨 Session GUM 架構有根本性差異。[^1][^2]

***

## 二、最相似的現有研究（Top 5 對比論文）

### 論文一：PELICAN — Personalized Education via LLM-powered Cognitive Diagnosis and Adaptive Tutoring（ICLR 2026）

**核心機制：** PELICAN 是迄今最接近 AREQA 第一、二支柱的系統。它分兩階段運作：(1) 透過 LLM 驅動的協作認知診斷（Collaborative Cognitive Diagnosis）建立學生的當前認知狀態（Cognitive State）模型；(2) 依據診斷結果從策略池（Strategy Pool）中以 Slow-Thinking 慢推理選擇教學策略，並持續監控學生回應以追蹤認知狀態變化。在中國高考（Gaokao）資料集上，相比基線模型提升了批判性思維刺激 +18.7% 和任務完成率 +22.4%。[^1]

**AREQA 與之的差異：** PELICAN 的「記憶」是 Session 內的即時認知狀態，**沒有跨 Session 的持久性使用者模型（Persistent GUM）**。一旦對話結束，學生的熟練度資料不會被保留與演化。此外，PELICAN 完全沒有「主動 UX 陪伴」機制——它是純粹被動回答式（reactive-only）的系統。

***

### 論文二：EDF/Copa — Theory-Driven Adaptive Scaffolding for LLM Agents（arXiv 2025/AAAI 2026）

**核心機制：** EDF（Evidence-Decision-Feedback）框架結合了 Vygotsky 的 ZPD 理論與 LLM，透過三個子 Agent 持續評估學生熟練度，動態切換對話策略（`PROBE_UNDERSTANDING` → `SUGGEST_ACTION` → `PUSH_LIMIT`），實現可量化的「鷹架消退（Scaffold Fading）」。在 n=33 dyads 的高中課堂實驗中，驗證了隨熟練度增加鷹架介入頻率顯著下降的效果。[^2][^3]

**AREQA 與之的差異：** Copa 是 AREQA 第二支柱（Adaptive Scaffold Fading）最直接的先行研究。然而，Copa **沒有跨 Session 持久性記憶**——每次啟動 Copa 需要重新累積學生的熟練度狀態，無法讀取上週或上個月的學習軌跡。更關鍵的是，Copa **不具備任何主動陪伴或事件偵測機制**，它完全依賴學生的主動提問。AREQA 的長期 GUM 使得鷹架消退的效果能跨越時間積累，而不是每次歸零。

***

### 論文三：LearnerCompass — Intelligent Tutoring System with Dynamic Cognitive...（ICLR 2026 方向）

**核心機制：** LearnerCompass 架構透過靜態巨觀知識圖（Static Macro-KG）結合 Graph-RAG 機制為 LLM 提供領域知識錨點，以 RAG 為骨幹進行教育 QA。與 KG-RAG（2023）框架類似，均聚焦於用知識圖譜提升 RAG 的事實準確性，並在 STEM 領域顯示 LLM 推理更可靠（抵抗幻覺）。[^4][^5][^6][^7]

**AREQA 與之的差異：** LearnerCompass 和 KG-RAG 都將 RAG 用於**知識庫的結構化與事實接地**，這是靜態知識的問題。AREQA 的 RAG 針對的是**動態使用者記憶（Dynamic User Memory）**——它要回答的不只是「這個概念正確嗎」，而是「根據這位使用者的長期學習軌跡，他現在在哪個理解層次，接下來應該回應什麼」。這是兩個根本不同的 RAG 使用場景（Knowledge-Grounded vs. User-Grounded）。[^8][^9]

***

### 論文四：Adaptive Scaffolding for Cognitive Engagement in an ITS（arXiv 2026）

**核心機制：** 這是近期最嚴格的鷹架消退實驗之一（n=113 學生），比較 Bayesian Knowledge Tracing（BKT）與 Deep Reinforcement Learning（DRL）作為自適應策略選擇引擎，在邏輯 ITS 中動態選擇「引導範例」（Guided Example, 主動模式）或「錯誤範例」（Buggy Example, 建構模式）。BKT 對低先備知識學生效果最佳，DRL 對高先備知識學生表現更好。[^10]

**AREQA 與之的差異：** 此研究完全在**課堂環境、閉鎖式教材**下進行，記憶是短期 Session 內的狀態向量，不存在跨 Session 持久性。更重要的是，它聚焦在「例題類型的選擇（example selection）」而非「對話風格的鷹架消退（dialogue scaffolding fading）」，且沒有任何 LLM 的自由對話能力與主動 UX。AREQA 面對的是開放式問答場景，技術複雜度與彈性訴求完全不同。

***

### 論文五：ComPeer — A Generative Conversational Agent for Proactive Peer Support（UIST 2024）

**核心機制：** ComPeer 建立了「事件偵測 → 每日反思 → 主動排程」的管線，主動偵測使用者的情緒狀態與壓力事件，並在適當時機傳遞關懷訊息。在 N=24 一週的 Between-subjects 實驗中，顯著優於無主動功能的基線系統。[^11][^12]

**AREQA 與之的差異：** ComPeer 面向**心理健康支持**場景，沒有教育熟練度追蹤、沒有知識 RAG、沒有任何鷹架機制。它只解決了 AREQA 第三支柱（主動陪伴）中的「時機與頻率」問題，而沒有回答「主動推送什麼內容（知識建議、半成品草稿）」的問題。AREQA 的主動性觸發源是學生的「認知卡關事件（Stuck Event）」與「熟練度狀態」，而非情緒事件，這是兩種根本不同的主動觸發機制。

***

## 三、殘酷的差異性與缺口分析（Gap Analysis）

### 3.1 別人已經做過的（Existing Work）

以下是文獻中確實已有清楚貢獻的領域，AREQA **不應**宣稱在這些點上具有原創性：

- **RAG 應用於教育 QA（靜態知識接地）：** KG-RAG（2023）、LearnerCompass（2025）、Graph RAG for MOOCs（2025）均已在此方向有系統性貢獻。[^5][^7][^9]
- **LLM 鷹架策略的單 Session 實作：** CLASS（2023）、EDF/Copa（2025/2026）、PELICAN（ICLR 2026）均在單 Session 或短期實驗中驗證了 LLM 自適應鷹架的有效性。[^13][^2][^1]
- **主動對話 Agent 的排程機制：** ComPeer（UIST 2024）已在主動觸達的時機設計上做出明確貢獻。[^11]
- **跨 Session 持久性記憶框架（通用）：** MemGPT（2023）、A-MEM（2025）、Memori（2025）均在通用 Agent 記憶架構上有系統性貢獻。[^14][^15][^16]
- **認知診斷驅動的教學策略選擇：** PELICAN（ICLR 2026）、BKT-based ITS（多篇）已在認知狀態建模與策略選擇上建立了紮實基礎。[^10][^1]

***

### 3.2 別人還沒做過的——AREQA 的真正 Novelty

基於對現有文獻的全面檢視，以下三點構成 AREQA 目前最具辨識度的學術新穎性：

**Novelty #1：持久性 GUM 作為教育系統的核心使用者模型（首次整合）**

目前沒有任何 AIED 系統將 Shaikh et al. (UIST'25) 的 GUM 架構（跨 Session、跨 App、多模態觀察、Confidence-weighted Propositions）應用於教育熟練度追蹤。現有的 AIED 記憶系統仍停留在「Session 內的認知狀態向量」或「簡單的學習歷史儲存」，而非「可以觀察學生在螢幕上所有行為（包含課外學習活動）、主動修訂知識命題的動態使用者模型」。這個整合點目前是真空的。[^17][^18]

**Novelty #2：跨 Session 鷹架消退（Cross-Session Scaffold Fading）**

EDF/Copa、BKT-based 系統均在 Single Session 內驗證鷹架消退。然而，真實世界的學習是週期性累積的，學生可能今天理解了概念、一週後遺忘、三週後重新掌握。**沒有任何現有論文實作並評估「跨多個 Session 的鷹架消退」**——即熟練度狀態在多週的學習歷程中動態演化，LLM 的輸出風格（從詳細指引到簡潔挑戰）隨真實的跨 Session 熟練度曲線而自動調整。AREQA 的 GUM 可以為此提供必要的跨 Session 記憶基礎，而這正是所有現有系統都缺乏的。[^2][^10]

**Novelty #3：認知卡關事件驅動的主動介入（Cognitive Stuck Event-Triggered Proactive UX）**

ComPeer 的主動觸發器是「情緒事件」（壓力、情感狀態）；GUM/Gumbo 的主動觸發器是「使用者行為的效用估計」（Utility-based suggestion)；ProactiveBench 的觸發器是「環境狀態感測」。但**沒有現有論文將教育場景中的「認知卡關（Cognitive Stuck Event）」作為主動介入的核心觸發器**——例如：偵測學生在同一個知識點上重複卡關超過 N 次、偵測答題響應時間異常延長（代表高認知負荷）、或在熟練度長時間沒有進展（Plateau Detection）時主動推送鼓勵與重新框架的草稿。這個「認知狀態 → 主動介入觸發」的完整管線是 AREQA 的獨特創新點。[^19][^18][^11]

***

### 3.3 三支柱交叉口的完整 Gap 地圖

| 研究維度 | 現有最強競爭者 | 缺口 | 缺口規模 |
|---|---|---|---|
| 跨 Session 持久記憶（教育場景） | MemGPT[^15], A-MEM[^16]（通用） | 無 AIED 系統整合 GUM 架構 | **大** |
| 熟練度量化追蹤（LLM 驅動） | PELICAN[^1], BKT-ITS[^10] | 均無跨 Session 持久性 | **中-大** |
| 鷹架消退（跨 Session） | EDF/Copa[^2] | 全部只在單 Session 驗證 | **大** |
| 主動陪伴（認知事件觸發） | ComPeer[^11]（情緒觸發） | 無認知卡關 → 主動介入管線 | **大** |
| **三支柱完整整合** | 無 | 整合系統 = 完全空白 | **極大** |

***

## 四、研究設計建議：如何最大化 AREQA 的 Novelty 主張

要讓 AREQA 成為一篇高引用的頂會論文（CHI、UIST、L@S），建議在研究設計上聚焦以下幾點：

### 4.1 明確界定研究貢獻層次

根據上述缺口分析，建議將 AREQA 的貢獻宣稱（Contribution Claims）界定為：

1. **架構貢獻（System Architecture）：** 第一個將 GUM 架構整合到教育 QA Agent 的系統設計，定義三支柱的整合介面（GUM Proposition → Proficiency Score → Scaffold Level → Proactive Trigger）。
2. **機制貢獻（Novel Mechanism）：** Cross-Session Scaffold Fading 的定義與量化評估指標（e.g., 跨 N 個 Session 的鷹架強度衰退曲線）。
3. **互動設計貢獻（UX Design Pattern）：** Cognitive Stuck Event-Triggered Proactive Intervention 的設計模式，包含觸發條件的規格化（stuck threshold、plateau window、CL proxy signal）。

### 4.2 評估設計的建議

現有競爭研究普遍的弱點是**缺乏長期縱向評估**——大多數 ITS 研究只做單次課堂實驗（1-3 小時）。AREQA 若能設計一個 **4-8 週的縱向使用者研究（Longitudinal Study）**，測量跨 Session 熟練度曲線的演化、鷹架強度的自動調整軌跡、以及主動介入時機的使用者滿意度，這本身就是一個主要的方法學創新，遠超現有文獻的評估深度。[^10][^1]

此外，可參考 EDF/Copa 的可解釋性評估方法（Grounding、Alignment、Faithfulness 三連結），為 AREQA 的鷹架決策建立類似的透明度量化框架——這對 AIED 審稿委員特別有吸引力，因為他們關注「系統行為是否與教育理論對齊」。[^3][^2]

### 4.3 最需要防禦的審稿挑戰

預期 AREQA 在頂會審稿時最可能遭遇的挑戰有三個：

- **「GUM 只是 MemGPT 的 AIED 版本」：** 必須清楚展示 GUM 的教育特化設計——例如熟練度 Proposition 的結構（`domain`, `concept`, `mastery_level`, `evidence_type`）與一般用途 GUM 的差異，以及如何與 BKT / IRT 等教育認知診斷理論接軌。[^18][^15]
- **「跨 Session 鷹架消退缺乏因果驗證」：** 需要設計 Ablation Study——分別比較有跨 Session 記憶 vs. 無跨 Session 記憶（每次 Session 重置）的鷹架消退效果，量化持久記憶的實際收益。[^2][^10]
- **「主動介入可能打擾使用者」：** 必須設計評估「主動介入的干擾度（Perceived Intrusiveness）」的量表，並與 Gumbo 的效用評分框架和 ComPeer 的每日上限設計對應。[^18][^11]

***

## 五、結論判定

**結論：AREQA 的三支柱整合是一個學術界尚未有人完整實作的系統架構，具備高度的發表潛力。**

以下是評估的完整依據：

| 評估向度 | 評級 | 說明 |
|---|---|---|
| **單一支柱的先行研究密度** | 高（已飽和） | 每個支柱各自都有 3-5 篇紮實的頂會論文[^2][^1][^11] |
| **三支柱的整合系統** | 空白（未被探索） | 未發現任何論文同時整合三支柱 |
| **Cross-Session Scaffold Fading** | 高度 Novel | 現有文獻全部在單 Session 驗證，跨 Session 是明確缺口[^2][^10] |
| **Cognitive Stuck Event Trigger** | 高度 Novel | ComPeer 只做情緒觸發，無教育認知事件觸發管線[^11] |
| **適合投稿的頂會** | CHI、UIST、L@S（首選） | L@S 對「學習系統的創新架構與縱向評估」特別親切；CHI/UIST 對主動 UX 設計的新穎性評價高 |
| **整體發表潛力評級** | **★★★★☆（高）** | 主要風險在於評估設計的嚴謹性，而非 Novelty 本身 |

AREQA 的最大優勢是：它站在三個各自成熟的研究社群（LLM 記憶架構、AIED 自適應鷹架、主動代理 UX）的交叉點，以一個整合系統填補了交叉口的真空。這種「跨領域整合 + 系統驗證」的研究策略在 CHI 和 L@S 都有清楚的先例並被肯定——困難在於執行，而非論點。

---

## References

1. [PELICAN: Personalized Education via LLM-powered Cognitive ...](https://openreview.net/forum?id=NIvqiJ8R4J) - TL;DR: A novel adaptive tutoring framework that combines collaborative cognitive diagnosis with dyna...

2. [Theory-Driven Adaptive Scaffolding for LLM Agents - arXiv](https://arxiv.org/html/2602.01415v4)

3. [[논문 리뷰] Evidence-Decision-Feedback: Theory-Driven Adaptive ...](https://www.themoonlight.io/ko/review/evidence-decision-feedback-theory-driven-adaptive-scaffolding-for-llm-agents) - 이 연구는 LLM(Large Language Model) 에이전트가 학생들에게 도메인 지식과 비판적 사고 능력을 함양하도록 돕는 데 있어 '획일적인(one-size-fits-all...

4. [[PDF] LEARNERCOMPASS: Intelligent Tutoring System ... - OpenReview](https://openreview.net/pdf/2ae70929350714eeb36ec80e4ce0eaab9895adbc.pdf)

5. [How to Build an Adaptive AI Tutor for Any Course Using Knowledge Graph-Enhanced Retrieval-Augmented Generation (KG-RAG)](https://arxiv.org/abs/2311.17696) - Integrating Large Language Models (LLMs) in Intelligent Tutoring Systems (ITS) presents transformati...

6. [[PDF] How to Build an Adaptive AI Tutor for Any Course Using Knowledge ...](https://arxiv.org/pdf/2311.17696.pdf) - This paper introduces Knowledge. Graph-enhanced Retrieval-Augmented Generation (KG-RAG), a novel fra...

7. [Intelligent Tutoring System with Dynamic Cognitive ...](https://openreview.net/forum?id=B65QAl38dr) - Existing adaptive learning systems struggle to simultaneously achieve deep personalization, dynamic ...

8. [[PDF] arXiv:2405.04645v1 [cs.HC] 7 May 2024](https://arxiv.org/pdf/2405.04645v1.pdf)

9. [Leveraging Graph Retrieval-Augmented Generation to Support Learners' Understanding of Knowledge Concepts in MOOCs](https://www.arxiv.org/abs/2505.10074) - Massive Open Online Courses (MOOCs) lack direct interaction between learners and instructors, making...

10. [Adaptive Scaffolding for Cognitive Engagement in an Intelligent Tutoring System](https://arxiv.org/abs/2602.07308) - The ICAP framework defines four cognitive engagement levels: Passive, Active, Constructive, and Inte...

11. [ComPeer: A Generative Conversational Agent for Proactive ...](https://arxiv.org/abs/2407.18064) - Conversational Agents (CAs) acting as peer supporters have been widely studied and demonstrated bene...

12. [[Revue de papier] ComPeer: A Generative Conversational Agent for Proactive Peer Support](https://www.themoonlight.io/fr/review/compeer-a-generative-conversational-agent-for-proactive-peer-support) - **ComPeer: A Generative Conversational Agent for Proactive Peer Support** ### Overview "ComPeer" is ...

13. [CLASS: A Design Framework for Building Intelligent Tutoring Systems Based on Learning Science Principles](https://ar5iv.labs.arxiv.org/html/2305.13272) - We present a design framework called Conversational Learning with Analytical Step-by-Step Strategies...

14. [Memori: A Persistent Memory Layer for Efficient, Context-Aware LLM Agents](https://arxiv.org/pdf/2603.19935v1.pdf)

15. [MemGPT: Towards LLMs as Operating Systems - UPDF AI](https://ai.updf.com/paper-detail/memgpt-towards-llms-as-operating-systems-packer-fang-908dad62c0e43d80e3e3cb3c0402f7c71c70499c) - This work introduces MemGPT (Memory-GPT), a system that intelligently manages different memory tiers...

16. [[2502.12110] A-MEM: Agentic Memory for LLM Agents - arXiv](https://arxiv.org/abs/2502.12110) - Advances in Neural Information Processing Systems (NeurIPS 2025) Subjects: Cite as: arXiv:2502.12110...

17. [[2505.10831] Creating General User Models from Computer Use](https://arxiv.org/abs/2505.10831) - This paper presents an architecture for a general user model (GUM) that learns about you by observin...

18. [Creating-General-User-Models-from-Computer-Use.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/34034424/3a13e20c-2eee-4784-a0aa-23baffc880aa/Creating-General-User-Models-from-Computer-Use.pdf?AWSAccessKeyId=ASIA2F3EMEYEQN6EIZXV&Signature=6%2BHDND2C5FHkhGpcQxPp8Q76ai0%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEEoaCXVzLWVhc3QtMSJIMEYCIQDdOXrdyAiu1XcnUgr%2BEQKWty%2Fy5OGHPIWKZR6irDnCAAIhAPrPqaf1z4YaoiKiFA3xywOuA0Ixv5oY%2FubJswjediAmKvMECBIQARoMNjk5NzUzMzA5NzA1IgyqZhIYWyJTa5hjbD8q0ARcB4wDa%2BSO3ORJ5AwGuOZ6UA%2BYbc7%2BMLgy1KCE1Ot0oIvMowMtxvwLywHTxkHBBGMdU%2FSiAZv4DbnS4sxPzVGbKDDbghtWRzq%2BTbb8l8PffRmpxfAcu%2BAfV%2BvUbOBIMQj6tpkqMhhO6J%2BMn9IX%2B1BOz%2F4i9AP%2BgUC9TiZ050LsA%2BIIfX24IffdiNbtaXO2px0s3jxXDwP85pIOtAQx9k5VDpZ3haEqgzqqL4Y76SnISSTKinm%2Fok%2B1Iogl96sa3dfEPdKWEGUT6P6tyRH5raOp%2F4dod0wVd4XfCm4tbIRI1AvR4sWfU5DFT487oCYPqx6eIngPryTee1pg%2FCXbt5UXNgrN4JHDV49FDGwxej03y5%2BHiY8PEYxnxGCzk%2BUj6JJfDbuN3RNZwg2Nx6rqytYK8L%2FqRfMcI8fxKslyQdUmj67qOUlIyb%2BORVQ14rv%2BhjpLIzLKL%2Fq86BWTeXGep1pja%2FTfIhaiwx3KZxB1XRtgYbanENpxc4rTzRJw71OihOKAbniRvpBEdfGDnsYzdzbUA%2FDo224aWXQXhednH7uvqIlmqR7aJz3hkZ3Poa9pn6GyOlMNQprYegogxR%2F9do%2FqKsPaeEvSvRwqUAnJdbG0uUfBAfOYqZoGfc%2B%2BGKrxnBAQn9UKuH5FDLRcQ0rar0zsxqPsGjx7FuXjg%2FVPRbQXigeASw%2BLkcW3MJJAl2BKpbHpdEF2G2GsC%2FsuPvyzyNCt0nxL7Jcgs84FTDrpOuXmTjqEb27ZxZ6AkyGEYPM%2B6k0OWGbQxJr1EiBjhAyvdOMJMOubr9EGOpcBTQ7dB0UoQBagZgoVCfYEfx3oXiswQgRmud2gelStR41D5BUH2QQyJ7rUDhM92aXqerGOTXdtSZCltlLUs6RgLekGJl%2BniSVtVw9%2FHGL2gvxRYoVsumML4ctubB%2FIw82bBTgEQLNJZq9Rj%2Baf09KR%2BfbP03rSMBVoQTkAE4frHQjHkGkCZq6YqVZ4wMplDZdR35H1B5kfWQ%3D%3D&Expires=1781259198) - 3.2 Interfacing with the GUM Here, we outline core functions to interface with the GUM, high-lightin...

19. [Published as a conference paper at ICLR 2025](https://openreview.net/pdf/ba670e591dd33509822a7a0360e6a84be1debcd5.pdf)

