# 從「話題建議」走向「主動代理」：HCI 與 AI Agent 主動性 UX 設計深度研究報告

> **研究範疇：** Mixed-Initiative Interfaces、Proactive Agency、使用者畫像驅動的工作流自動化與認知支持設計  
> **文獻覆蓋：** 2020–2026 年 CHI、UIST、NeurIPS、ACL 頂會論文及 Anthropic、Cisco HAX、LlamaIndex、CopilotKit 等業界框架  
> **核心問題：** 如何讓 GUM 型 AI Agent 超越「提議話題」，真正以不干擾的方式預先完成半成品工作？

***

## 一、執行摘要

目前「給建議話題」的互動模式本質上是把認知負擔從系統轉嫁給使用者——使用者仍需判斷哪個話題有用、自己開口提問、從頭組裝脈絡。這個問題根植於「被動反應（Reactive）」與「完全自治（Autonomous）」之間缺少中間地帶。HCI 研究近五年來的核心進展，正是在建構這個中間地帶的系統架構與 UX 設計原則。

本報告從兩個子議題展開：**(1) Mixed-Initiative 與非侵入性主動代理的設計框架**，以及 **(2) 使用者畫像轉化為主動工作流自動化與認知支持的設計模式**。每個議題提供 2-3 種可立即參考的設計模式，並以高引用論文或業界框架佐證。報告最後提出 3 個開發者優先實作的 MVP 功能建議。

***

## 議題一：Mixed-Initiative Interfaces 與主動代理的 UX 設計

### 1.1 理論根基：Horvitz 的期望效用框架（Expected Utility of Interruption）

所有現代主動 Agent 的 UX 設計，皆可追溯至 Eric Horvitz 在 **CHI 1999 的奠基性論文** *Principles of Mixed-Initiative User Interfaces*。Horvitz 的核心論點是：系統應在 **期望效用（EU）大於靜默不作為（inaction）** 時才主動介入，而非依賴固定規則。其決策公式可表達為：[^1][^2]

\[\text{EU}_{\text{interrupt}} = P(G \mid E) \cdot B - (1 - P(G \mid E)) \cdot C_{FP}\]

其中 \(P(G \mid E)\) 是在觀察到證據 \(E\) 後對使用者目標 \(G\) 的後驗機率估計，\(B\) 是建議正確時的收益，\(C_{FP}\) 是誤判介入的代價。這個框架的設計含義是：**系統不應基於單一觸發規則主動打擾，而必須動態估計「中斷的邊際效益」**。[^2]

Gumbo（Shaikh et al., UIST'25）直接實作了此框架——系統計算每條建議的 \(\text{EU}_{\text{interrupt}}\)，並加入 Token Bucket 速率限制（最多 1 條建議 / 分鐘），防止建議轟炸（Suggestion Flooding）。此外，Horvitz 的 12 條 Mixed-Initiative 原則中特別強調「**維持近期互動的工作記憶（Maintaining working memory of recent interactions）**」與「**透過觀察持續學習（Continuous learning via observation）**」，這兩點與 GUM 的 Propose-Retrieve-Revise 管線直接對應。[^3][^2]

***

### 設計模式 A：What-How 雙模組主動代理（感知-傳遞分離架構）

**代表論文：Sensible Agent（Lee et al., UIST 2025）**[^4][^5]

**核心問題：** 以往 AR/桌面主動 Agent 在決定「要提示什麼」和「如何提示」時，往往只最佳化「建議內容的相關性」，而忽略了「當下提示方式的侵入性」——結果是使用者常因不合時宜的打擾而關閉通知。

**運作原理：** Sensible Agent 將主動介入拆分為兩個獨立推理模組：

- **What Module（內容決策）：** 分析使用者即時多模態情境（凝視方向、雙手佔用狀態、位置、高階活動），決定應提供什麼協助，並選擇查詢格式（圖示提示 / 二元 Yes-No / 多選）。
- **How Module（傳遞決策）：** 獨立判斷用「視覺面板」、「音頻提示」還是「兩者兼用」，最小化對使用者當前感官通道的干擾。

使用者研究（n=10）顯示，相比固定語音提示的基線系統，Sensible Agent 顯著降低了使用者的「侵入感（perceived intrusiveness）」，同時維持同等的實用性（utility）。[^6][^4]

**對 GUM 產品的啟示：** 對話型 Agent 也應實作類似的「傳遞感知層」——例如在使用者正專注打字（高 IO 活動）時以側欄卡片而非對話泡泡傳遞建議；在使用者拋出問題後的空白等待期（低 IO 活動）才主動插入生成的草稿。

***

### 設計模式 B：GUM 驅動的期望效用建議過濾（Suggestion Utility Scoring）

**代表框架：Gumbo（Shaikh et al., UIST'25）**[^3]

**核心問題：** 如何讓系統自動篩選「值得打擾使用者的建議」，而不是所有建議都 push 出去。

**運作原理：** Gumbo 實作了完整的 Mixed-Initiative 建議過濾管線，分三步執行：[^3]

1. **生成候選建議：** 每當一個新 Proposition 被生成，系統調用 GUM 的語意相關 Proposition 集合 \(G\)，使用 LLM 生成 5 條候選建議（附帶個別的 \(P(\tau_i \mid G)\) 信心估計）。

2. **期望效用計算：** 對每條建議，LLM 分別生成四個維度的分數（1-10）——`benefit`（建議對使用者的幫助程度）、`false_positive_cost`（誤觸的干擾代價）、`false_negative_cost`（漏報的損失）、`decay`（建議的時效性）。代入 Horvitz 公式計算 \(\text{EU}_{\text{interrupt}}\) 是否大於 \(\text{EU}_{\overline{\text{interrupt}}}\)。

3. **速率限制（Token Bucketing）：** 即使通過效用門檻，也透過速率限制（預設 1 條/分鐘）防止連續的建議爆發打擾使用者工作流。

在 N=5 參與者的五天縱向評估中，25% 的建議被評為「strong（6/7）」或「excellent（7/7）」，兩位參與者在研究結束後主動要求繼續使用。[^3]

***

### 設計模式 C：HAX 框架的 Agent-SDK + 行為代理層（Behavioral Proxy）

**代表框架：Human-Agent Experience (HAX) Framework，Cisco Outshift，2025**[^7][^8][^9]

**核心問題：** 在多代理（Multi-Agent）或複雜 Agentic 工作流中，如何設計讓使用者「了解 Agent 正在做什麼、有能力接管或回滾」的 UX？

**運作原理：** HAX 框架分三階段解決「主動 Agent 的可信任性設計」問題：[^8]

- **Phase 1 - Design Heuristics（5 原則）：** Control（使用者設定邊界）、Clarity（Agent 暴露推理過程與信心）、Recovery（支持 undo 與糾錯）、Collaboration（Human-Agent 協作貢獻）、Traceability（決策全程稽核）。
- **Phase 2 - Agentic SDK：** Schema-driven 工具呼叫——Agent 僅能使用預先驗證的 UI 元件（不能任意生成 HTML），避免惡意注入或意外的不可逆操作。
- **Phase 3 - Behavioral Proxy（行為代理層）：** 一個介於 Agent 和使用者之間的過濾、排序、個人化層，根據使用者的認知負荷和當前情境，決定哪些 Agent 動作需要立即呈現、哪些可以背景執行、哪些必須請求確認。

HAX 特別為主動代理的「**Intent Preview**（意圖預覽）」模式提供設計規範——Agent 在執行不可逆操作前必須先顯示「即將要做什麼」的卡片，讓使用者可以一鍵確認、拒絕、或修改。[^7]

***

## 議題二：使用者畫像驅動的主動工作流自動化與認知支持設計模式

### 2.1 從「乾巴巴的建議」到「半成品（Pre-Executed Draft）」的關鍵轉變

HCI 與 AI Agent 研究的最新共識是：**「想法很廉價，執行才是一切（Ideas are cheap. Execution is everything）」**——這是 Gumbo 論文中明確點出的設計哲學。當使用者看到「你可能需要寫招募策略文件」這條建議時，認知成本幾乎沒有降低；但當 Agent 已在背景完成了「包含目標族群、招募管道、排程和知情同意書模板的完整草稿」，使用者只需審閱並觸發「Start Chat」即可改善，認知負擔才真正被轉移。[^3]

CMU 的論文 *Completion ≠ Collaboration*（2025）進一步從理論層面論證了這個轉移的邊界——最佳 Agent 設計應讓「使用者效用（utility）隨使用者投入度增加而持續增長」，而非在 5 輪後停滯；只輸出「完成品（completion）」而非「協作草稿（collaboration scaffold）」的 Agent，往往導致使用者喪失控制感與學習機會。[^10][^11]

***

### 設計模式 D：觸發式背景預執行（Trigger-Then-Pre-Execute Pattern）

**代表案例：Gumbo（UIST'25）+ GitHub Copilot 業界實踐**[^12][^3]

**運作原理：** 此設計模式要求系統在將建議呈現給使用者之前，已盡可能地預先執行建議的核心部分——形成「半成品草稿（Pre-Executed Draft）」：

1. **觸發（Trigger）：** GUM 生成新 Proposition，觸發建議生成管線（EU 計算通過門檻）。
2. **Tool-Use 背景執行：** 系統判斷建議是否需要外部工具（`search`、`filesystem`、`reasoning`、`code execution`），若需要則以最小侵入的工具集在後台非同步執行（GUM 的 Tool-Use 提示明確設計為選擇「最少必要工具」）。[^3]
3. **呈現半成品：** 在 UI 上以「Suggestions Card」形式呈現——顯示已執行的結果摘要，並附上「Start Chat（繼續對話精修）」的入口。使用者不需要從頭開始，直接對草稿做 Accept / Reject / Refine 即可。

Gumbo 的評估案例清楚展示此模式的價值：P3 正在準備 Quals 簡報，Gumbo 不只建議「你可以考慮加投影片轉場技巧」，而是直接生成了具體的轉場建議實例；P1 的搬家計劃，Gumbo 不只建議「規劃搬家流程」，而是已知悉室友名字、預算與搬入日期，直接生成了含搬家公司比較的完整行事曆草稿。[^3]

GitHub Copilot 的業界研究進一步驗證，「建議作為起點（useful as a starting point）」比「建議的正確性（correctness）」更是驅動開發者生產力提升的關鍵因子——即使生成的程式碼不完美，只要是可被採用和修改的草稿，開發者的認知節省就已顯著。[^12]

***

### 設計模式 E：ComPeer 的事件偵測-反思-排程主動溝通架構

**代表論文：ComPeer: A Generative Conversational Agent for Proactive Peer Support（Liu et al., UIST 2024）**[^13][^14]

**核心問題：** 在學生或知識工作者場景中，如何讓 Agent 在適當時機（而非使用者發話時）主動提供認知支持與情感關懷，而不是等待被動觸發？

**運作原理：** ComPeer 建立了一條 **偵測 → 反思 → 排程 → 生成** 的主動溝通管線：[^14]

1. **Event Detection Module（事件偵測）：** LLM 持續分析對話歷史，偵測「顯著事件」——包括情緒狀態變化（如表達壓力）、重要計劃（如準備考試），以及值得後續追蹤的承諾（如「明天我要試試這個方法」）。
2. **Reflection Module（每日反思）：** 每天定時觸發，LLM 對當日互動進行反思，生成關於使用者「情緒趨勢、主要挑戰、未解決問題」的結構化摘要，寫入長期記憶。
3. **Schedule Module（主動排程）：** 整合事件偵測與每日反思的輸出，生成個人化的每日主動溝通計劃——決定何時（timing）、傳遞什麼類型的主動訊息（認知提醒 / 情感關懷 / 進度追蹤）。
4. **Proactive Message Control：** 設計了「每日主動訊息上限」防止打擾。

一週的 Between-subjects 研究（N=24）顯示，使用 ComPeer 的使用者比無主動功能基線系統的使用者感受到更顯著的壓力緩解，且隨時間增加使用粘性。關鍵設計發現：建議在使用者剛產生互動事件「之後」呈現（after），比「前」（before）或「同步」（in-sync）更受偏好，且更能提升信任感。[^15][^16][^13]

***

### 設計模式 F：EDF 自適應鷹架的 ZPD 認知支持（適用知識工作者/學生）

**代表論文：Evidence-Decision-Feedback (EDF)（Cohn et al., 2025/2026）**[^17][^18][^19]

**核心問題：** 如何讓 Agent 不只「提供答案」，而是根據使用者當前的知識狀態（Mastery Level）動態調整支持力度——避免「過度依賴（Over-reliance）」與「支持不足（Under-support）」這兩個極端？

**理論基礎：** EDF 整合了 Vygotsky 的**最近發展區（Zone of Proximal Development, ZPD）**——Agent 的介入強度應剛好在使用者「無法獨立完成但在協助下可完成」的區間內。如果使用者的熟練度上升，Agent 應自動「鷹架消退（Scaffold Fading）」——減少主動提示，增加挑戰性問題。[^18][^20]

**三模組架構：**

1. **Evidence Module（持續評估）：** 監控使用者的行動日誌與對話，提取可觀察的「熟練度證據」（如正確回答 PROBE 問題的比率、主動尋求幫助的頻率），動態更新使用者的知識狀態。
2. **Decision Module（教學意圖決策）：** 根據熟練度證據選擇當前對話策略（`PROBE_UNDERSTANDING` / `SUGGEST_ACTION` / `PUSH_LIMIT`），使用者越熟練，策略從前者依序轉向後者。
3. **Feedback Module（適應性輸出）：** 依據選定策略生成 Agent 回應——可能是蘇格拉底式反問（「你認為這個步驟為什麼會失敗？」），也可能是直接操作建議（「試著把 X 改成 Y」），或邊界挑戰（「你可以在不用 API 的情況下達成同樣效果嗎？」）。

高中課堂實驗（n=33 dyads）顯示，Copa（EDF 的具體實作）成功展現了「鷹架消退」——隨著學生熟練度上升，`PROBE_UNDERSTANDING` 策略使用頻率顯著下降（Spearman's ρ = -0.34），而 `PUSH_LIMIT` 策略使用頻率顯著增加（ρ = 0.42）。[^20]

**對知識工作者場景的延伸：** 在 GUM 驅動的 Agent 中，EDF 的邏輯可對應為：根據使用者過去對建議的採納率與修改行為，推斷其當前對某類任務的熟練度，動態決定「要不要提供更多脈絡」或「直接給出執行草稿」——初次接觸某類工作時提供更多解釋，熟練後縮減為簡潔的 Action Card。

***

### 設計模式 G：PersonaAgent 的動態 Persona 驅動主動行動模組

**代表論文：PersonaAgent（ACL 2026）** 與 **PersonalAgent（EMNLP 2025）**[^21][^22]

**運作原理：** PersonaAgent 引入了「Persona 作為使用者意圖中介（Persona as intermediary）」的架構——透過情節記憶與語意記憶的結合，為每個使用者維護一個動態系統提示（Dynamic System Prompt，即「Persona Prompt」）。[^22]

關鍵機制是**Test-Time User Preference Alignment（測試時使用者偏好對齊）**：系統模擬最近 n 次互動，比較模擬回應與真實使用者回應之間的「文字損失（Textual Loss）」，以此為梯度訊號優化 Persona Prompt，使 Agent 的主動行動（Proactive Actions）持續向個人偏好靠攏。[^22]

此架構的 UX 意涵：**Persona 是連接記憶（Memory）與主動行動（Proactive Action）的樞紐**——若 GUM 的 Proposition 庫是原材料，Persona Prompt 就是對記憶的「行動化提煉」，讓後續的每一次工具呼叫和草稿生成都自動反映個人偏好。

***

## 三、不干擾設計的核心原則對照

以下列出研究中反覆出現的「不干擾主動代理」UX 設計準則：

| 設計原則 | 來源 | 具體實踐 |
|---|---|---|
| **漸進式介入（Graded Interruption）** | Horvitz CHI 1999[^1]；HAX 2025[^8] | 先圖示 → 再卡片 → 再對話，從低侵入到高侵入逐步升級 |
| **事後傳遞優於事前（Post-Event Timing）** | UX Eval CHI 2024[^15] | 在使用者剛完成某個操作後呈現相關建議，比打斷前最受歡迎 |
| **預執行半成品（Pre-Executed Draft）** | Gumbo UIST'25[^3]; Copilot CACM'24[^12] | 呈現已執行草稿，而非純建議，使用者直接 Accept/Modify |
| **透明推理鏈（Transparent Reasoning）** | GUM Audit[^3]; HAX Clarity[^8]; EDF Interpretability[^18] | 顯示「為什麼提這個建議」，維持使用者的 Locus of Control |
| **速率限制（Rate Limiting）** | Gumbo Token Bucket[^3]; ComPeer Daily Limit[^14] | 硬性限制每單位時間最多 N 條主動建議 |
| **情境代理（Contextual Agency）** | Gumbo 使用者反饋[^3] | 對使用者享受自己做決策的任務，只提供 Ideas 而不替換完成品 |

***

## 四、三項立即可實作的 MVP 功能建議

以下三個功能建議以「最快改善使用者體驗、最低技術風險、最直接對應現有 GUM 架構」為原則排序。

***

### MVP #1：GUM 驅動的背景預執行建議卡片（Pre-Executed Suggestion Cards）

**解決的問題：** 把「乾巴巴的建議話題」升級為「附帶半成品草稿的可操作卡片」，讓使用者不再是建議的被動接收者，而是「草稿的審閱者」。

**具體實作流程（基於 Gumbo 架構）：**[^3]

1. 在現有 GUM Proposition 管線後，加入「建議生成器」：當 Proposition 的重要性達到閾值，以最相關的前 5 條 Proposition 為輸入，生成 3 條候選建議。
2. 對每條建議，以 LLM 評估 `benefit`（1-10）、`false_positive_cost`（1-10），計算期望效用（EU）篩選。
3. 通過 EU 門檻的建議，**非同步執行工具呼叫**（web search、file lookup、LLM 草稿生成），組裝成「Suggestion Card」：標題（建議摘要）+ 草稿預覽（前 3 段）+ Start Chat 按鈕。
4. 速率限制：使用者當下活躍時，最多推送 1 張卡片 / 15 分鐘；背景模式（使用者不活躍時）可提高到 1 張 / 5 分鐘。

**關鍵 UX 細節（來自 Gumbo 評估）：** 卡片標題應附上「依據理由（Grounding）」——例如「基於你昨天和 Alex 的討論，我幫你草擬了...」，這樣使用者可以即時驗證建議的來源，維持透明度與信任感。[^3]

***

### MVP #2：ComPeer 式的顯著事件偵測與定時關懷提醒（Significant Event Detection + Scheduled Outreach）

**解決的問題：** 對於學生或知識工作者使用情境，純粹的「建議話題」缺乏時效性與個人關懷；使用者需要在關鍵時刻（如截止日前、剛解決困難問題後）被適時提醒或鼓勵。

**具體實作流程（基於 ComPeer 與 GUM Propositions）：**[^13]

1. 在 GUM 的每日記憶固化（Memory Consolidation）流程結束後，額外執行「**Significant Event Extractor**」：從當日新增 Proposition 中，LLM 抽取出三類顯著事件——`deadline_signal`（截止日相關）、`struggle_signal`（困難 / 卡關跡象）、`milestone_signal`（達成進展）。
2. 對每個顯著事件，生成對應的「主動觸達計劃」：`deadline_signal` → 截止日前 24h 和 2h 各發一次提醒；`struggle_signal` → 偵測到 2 次類似卡關，主動提供解法；`milestone_signal` → 立即以鼓勵語氣 + 下一步建議的「慶祝卡片」回應。
3. 所有主動觸達前，先評估「使用者當前是否在活躍工作狀態（IO 頻率高）」，若是則延後 5-10 分鐘再傳遞（對應 Post-Event Timing 原則）。[^15]

**預期效益：** 參考 ComPeer（N=24 一週研究），主動關懷的對話型 Agent 比無主動功能基線顯著提升使用者回訪率和情感滿意度；在學生族群中尤為顯著。[^13]

***

### MVP #3：EDF 啟發的熟練度感知輸出調整（Proficiency-Aware Output Calibration）

**解決的問題：** 對不同熟練度的使用者，Agent 應自動調整輸出的「指導程度」——新使用者需要更多解釋和步驟化指引；熟練使用者則需要更少廢話、更多挑戰性輸出。

**具體實作流程（基於 EDF 與 PersonaAgent）：**[^18][^22]

1. **熟練度指標建立：** 追蹤三個信號：(a) 使用者對 Agent 建議的「修改幅度」——幾乎不改 = 高熟練，大幅改寫 = 低熟練；(b) 使用者主動提問的詳細程度——高度具體 = 高熟練；(c) 建議採納率（Accept 率）在特定任務類型上的趨勢。
2. **動態輸出策略映射：** 基於熟練度得分選擇三種輸出策略：
   - **低熟練（0-0.4）：** 提供帶完整解釋的逐步指引 + 使用者可直接提交的完整模板
   - **中熟練（0.4-0.7）：** 提供含結構的半成品草稿 + 少量關鍵提示（不過度解釋）
   - **高熟練（0.7-1.0）：** 直接輸出精簡的 Action Card 或挑戰性問題（「你能在不依賴外部 API 的情況下達成同樣效果嗎？」）
3. **Scaffold Fading 觸發條件：** 參考 EDF 的設計，當使用者在同一任務類型上連續 3 次採納建議且修改幅度 < 10%，自動提升熟練度等級、降低指導詳細度。[^20][^18]

**技術實作建議：** 將熟練度得分與任務類型標籤一起儲存進 GUM 的長期 Proposition（`domain: coding, proficiency: 0.75`），每次生成回應時依此動態切換 System Prompt 風格。PersonaAgent 的 Test-Time 偏好對齊機制可進一步確保這些調整真正反映個人偏好而非假設。[^22]

***

## 五、主動代理設計模式全景對照

| 設計模式 | 解決的核心 UX 問題 | 代表框架/論文 | 開發者可用度 |
|---|---|---|---|
| A. What-How 雙模組（Sensible Agent） | 建議侵入性 vs. 內容相關性的 trade-off | Lee et al., UIST'25[^4] | ⚠️ 研究原型 |
| B. GUM Suggestion Utility Scoring | 建議轟炸 / 主動介入時機 | Gumbo, UIST'25[^3] | ✅ pip install generalusermodels |
| C. HAX 框架（Behavioral Proxy + SDK） | 多 Agent 可信任性與 Undo 設計 | Cisco Outshift, 2025[^8] | ✅ 公開設計規範 + SDK |
| D. 觸發式背景預執行（Pre-Execute Draft） | 建議只說不做，使用者仍需自行啟動 | Gumbo UIST'25[^3]; Copilot[^12] | ✅ 設計模式，可自行實作 |
| E. ComPeer 偵測-反思-排程管線 | 主動關懷缺乏時效性與個人化 | Liu et al., UIST'24[^13] | ✅ GitHub: liutj9/ComPeer |
| F. EDF 自適應鷹架（ZPD 認知支持） | 一刀切輸出，忽略熟練度差異 | Cohn et al., 2025/2026[^18] | ⚠️ Copa 研究原型 |
| G. PersonaAgent 動態 Persona 驅動 | 記憶與主動行動的橋接 | ACL 2026[^22] | ✅ 設計架構可移植 |

---

## References

1. [[PDF] Mixed Initiative Interaction](https://www.cl.cam.ac.uk/teaching/2324/HCAI/HCAI-2023-mixed-initiative.pdf)

2. [Outlook/Mica](https://www.cs.ubc.ca/~conati/522/532b-2022/Slides/Horvitz-Spring-21-22.pdf)

3. [Creating-General-User-Models-from-Computer-Use.pdf](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/34034424/3a13e20c-2eee-4784-a0aa-23baffc880aa/Creating-General-User-Models-from-Computer-Use.pdf?AWSAccessKeyId=ASIA2F3EMEYE7KWIODAH&Signature=TZ2LHrekfivr0L9Tqs4EN9bFTbU%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEEgaCXVzLWVhc3QtMSJHMEUCIG5tx20NuaGLSngysgD0RJXz13cuorq7umqnSPMlcV3bAiEA7iJRQJJh2f9FSRwJiOqELIX1RR4YCNVbIcyHqLBWMokq8wQIEBABGgw2OTk3NTMzMDk3MDUiDF5N9EytQfRWPl8acirQBD5pmdYzfyentq8aYe5v4VCXKcxy4fIUqPh1AKqp2lCpvu4kPDLTWvx9QbEdw16f9PZAatmGM%2B%2Bplun6fTXWOGiTq2XWmkfPaBRBKSWO38kovy9Zu%2Bqf%2FMTp4w2gAljRGzk3w3ulhOfF52Bjpr6wgnnD7uhPKlDJ8uzXOzP%2BeuFDufsNuhTRes%2B%2FnnYWfpSblRZQ37oPFjB5cQXnTkPN8oBgHhjj0eFHZVZE7EVIe%2BHwBbHLtNs4wExwTEuY8vF7xKAqx%2FYB5DajLHM%2FjanEIsMKF%2Fs56nKOmgjmJ1%2FdanFGKxYsASzuNs1pdBtDap5aYbs%2BY7Br5FOygvG7Ids%2FHEVqEPhdp17pzv6O4g3d%2FV1MPK3EBamNlPciIjsrj01XbeuFIEttJGAevjGaba2bfiS0NARqG0hENFxfp%2FsIUgfrH8juldQgTcmdvL7pqaLNmRvwCOeReJGFT1dR4LrVkxZy7ZWwXcjyFx2e0ta63tYxOv967e5vaN3JoiO7HZx%2BXLa2fryL2ZP4Xjrg9KEe1VAKYKYBTuGcMKlgHiZ6q%2FiFZrfFe8EN4go3sEFGxq3m9LugsGfgmU0HrmT4APAPAzcF13QS8QyXcm0PRauJjnSX2cz5ptxxPCeL18Gzk9lbLFeKHL%2BMkM9EgYaoAY8ZWC2MgnYsdpU24epMFyv2npkZY5%2BmH1JJ9CZ7DDwqopStrwrFxMTXAFGU%2BZS1YFgoCEZC3JelNxT%2FXlkMftxvIHt9pGP2hEQlSGUzAvBWtIku7KDUxBAgwBAswEXJzPXN1qcwqt%2Bu0QY6mAEZAqGdr4qocoyb%2BV%2Bp6T2rM0sMBmXS%2BuHudNn3VzUENn1xOEjp4ooPWfVmNuYZhZlUHiWfIAbus0lCjAP67UaRQAqdHosiAtV5OJV6CFr17sTEJAtZ4Gt6vnChZLS0iYc%2BdN2R9ypCapfLYC1JNDWQr870VlaXyctCeXxRxItSPEMDu5XWNjc9YeN43b65GiMzmJKJTJ4w7g%3D%3D&Expires=1781251453) - **page-1**
Creating General User Models from Computer Use

Omar Shaikh
Stanford University
Stanford,...

4. [A Framework for Unobtrusive Interaction with Proactive AR Agent](https://research.google/pubs/sensible-agent-a-framework-for-unobtrusive-interaction-with-proactive-ar-agent/)

5. [New UMD Research Brings Smarter, More Subtle Assistance ...](https://www.cs.umd.edu/article/2025/10/new-umd-research-brings-smarter-more-subtle-assistance-ar-glasses) - Recent innovations, such as Google's Project Astra, exemplify the potential of proactive agents embe...

6. [When AR Knows Before You Ask](https://www.cs.umd.edu/article/2026/02/when-ar-knows-you-ask) - When digital assistants first appeared on personal computers, they often waited for users to type a ...

7. [[2512.11979] Designing The Internet of Agents](https://arxiv.org/abs/2512.11979) - The rise of generative and autonomous agents marks a fundamental shift in computing, demanding a ret...

8. [Deep Stack—Advancing multi -agent systems through research](https://www.linkedin.com/pulse/shift-deep-stackadvancing-multi-agent-systems-through-siake) - Welcome to The Shift: Deep Stack, where we explore one technical topic in depth each quarter. This e...

9. [Trustworthy Agent Interactions with HAX Framework | Vijoy Pandey ...](https://www.linkedin.com/posts/vijoy_design-is-how-things-look-design-is-how-activity-7406741845508009984-TdCA) - Design is how things look. Design is how things behave. Multi-agent systems are changing both. When ...

10. [[PDF] Task Completion Agents are Not Ideal Collaborators - OpenReview](https://openreview.net/pdf?id=JMblCtvaDH) - ingredient in agent design: the ability to sustain engagement and scaffold user understanding. Colla...

11. [Collaborative Effort Scaling for LLM Agents](https://www.youtube.com/watch?v=oAQ0n9fUU7s) - In this AI Research Roundup episode, Alex discusses the paper:
'Completion $\neq$ Collaboration: Sca...

12. [Settings](https://cacm.acm.org/research/measuring-github-copilots-impact-on-productivity/)

13. [ComPeer: A Generative Conversational Agent for Proactive ...](https://arxiv.org/abs/2407.18064) - Conversational Agents (CAs) acting as peer supporters have been widely studied and demonstrated bene...

14. [[Revue de papier] ComPeer: A Generative Conversational Agent for Proactive Peer Support](https://www.themoonlight.io/fr/review/compeer-a-generative-conversational-agent-for-proactive-peer-support) - **ComPeer: A Generative Conversational Agent for Proactive Peer Support** ### Overview "ComPeer" is ...

15. [[PDF] Enhancing UX Evaluation Through Collaboration with Conversational AI Assistants: Effects of Proactive Dialogue and Timing | Semantic Scholar](https://www.semanticscholar.org/paper/Enhancing-UX-Evaluation-Through-Collaboration-with-Kuang-Li/f2498e15456e0d0e5d715b45508b84840f282ffb) - This study investigated the potential of proactive conversational assistants to aid UX evaluators th...

16. [ComPeer: A Generative Conversational Agent for Proactive Peer Support | AI Research Paper Details](https://www.aimodels.fyi/papers/arxiv/compeer-generative-conversational-agent-proactive-peer-support) - Conversational Agents (CAs) acting as peer supporters have been widely studied and demonstrated bene...

17. [[PDF] Theory-Driven Adaptive Scaffolding for LLM Agents - arXiv.org](https://www.arxiv.org/pdf/2602.01415.pdf)

18. [Theory-Driven Adaptive Scaffolding for LLM Agents - arXiv](https://arxiv.org/html/2602.01415v4) - In response, we introduce a theoretical framework for adaptive scaffolding—Evidence-Decision-Feedbac...

19. [A Theory of Adaptive Scaffolding for LLM-Based Pedagogical Agents](http://www.arxiv.org/abs/2508.01503) - Large language models (LLMs) present new opportunities for creating pedagogical agents that engage i...

20. [[논문 리뷰] Evidence-Decision-Feedback: Theory-Driven Adaptive ...](https://www.themoonlight.io/ko/review/evidence-decision-feedback-theory-driven-adaptive-scaffolding-for-llm-agents) - 이 연구는 LLM(Large Language Model) 에이전트가 학생들에게 도메인 지식과 비판적 사고 능력을 함양하도록 돕는 데 있어 '획일적인(one-size-fits-all...

21. [Towards Proactive Personalization of LLMs through Profile...](https://openreview.net/forum?id=dapG1wYvUL) - The deployment of Large Language Models (LLMs) in interactive systems necessitates a deep alignment ...

22. [[2506.06254] PersonaAgent: When Large Language Model Agents ...](https://arxiv.org/abs/2506.06254) - Large Language Model (LLM) empowered agents have recently emerged as advanced paradigms that exhibit...

