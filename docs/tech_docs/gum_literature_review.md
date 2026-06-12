# AI 代理的長期記憶與主動式 UX 設計：文獻與實務回顧

這份清單整理了近期人機互動（HCI）與 AI 領域針對「**記憶管理**」與「**主動代理 (Proactive Agency)**」的核心文獻，並淬鍊出針對開發 AREQA 系統的具體可執行策略 (Takeaway)。

---

## 🧠 主題一：長期記憶管理與動態提取策略 (Memory Management)

探討如何避免記憶污染，讓 AI 將碎片的對話轉化為長期的結構化知識，並在適當時機精準調用。

| 文獻 / 框架 | 核心機制與概念 (Key Idea) | 給 AREQA 的產品啟發 (Takeaway) |
| :--- | :--- | :--- |
| **Generative Agents**<br>*(Park et al., CHI '23)* | **三因子重要性評分與反思：** <br>基於「近期度、相關度、重要度」計算記憶權重。累積一定數量的短期記憶後，觸發 LLM 進行「反思 (Reflection)」生成高階摘要。 | **實作自動記憶固化：**<br>不要永遠只查對話 Log，應設定每晚或每累積 N 筆對話後，自動將短期除錯細節壓縮成「高階技能特徵」寫入長期 GUM 庫。 |
| **MemGPT**<br>*(Packer et al., NeurIPS '23)* | **OS 分層記憶 (Hierarchical Memory)：** <br>將記憶分作 Main Context (RAM) 與 External Storage (硬碟)。賦予 Agent 主動呼叫 `archival_memory_search()` 的工具權限，自主決定何時換頁。 | **Agentic Retrieval (工具化提取)：**<br>不要每次對話都把記憶硬塞進 System Prompt。讓模型自己決定「我現在需要回想使用者背景嗎？」再來觸發記憶搜尋工具。 |
| **A-MEM**<br>*(Xu et al., NeurIPS '25)* | **卡片箱記憶網絡 (Zettelkasten)：** <br>將記憶視為網狀節點，新記憶加入時會主動建立與舊記憶的「語意連結」，動態更新舊記憶的上下文。 | **記憶網絡化：**<br>將孤立的 Proposition 加上 Tag，建立互相關聯，有助於系統在推論時找出使用者興趣的根本原因。 |
| **MemoryBank**<br>*(Zhong et al., 2023)* | **艾賓浩斯遺忘曲線 (Forgetting Curve)：** <br>記憶的權重會隨時間自然衰減，但如果反覆被「提取或強化」，其衰減率就會變慢。 | **動態衰減率 (Dynamic Decay)：**<br>現有 GUM 的 Decay 是生成時固定的。可以實作：當某個低信心記憶被您反覆驗證後，系統自動降低它的衰減率（變為長期知識）。 |
| **STITCH**<br>*(2026)* | **意圖導向提取 (Intent-Aware Retrieval)：** <br>記憶寫入時標記「潛在意圖」。提取時先比對當下意圖，避免撈出「字面相關但目標相違背」的污染記憶。 | **意圖過濾閘門：**<br>在 BM25 檢索前，加一層「當前意圖比對」，避免在您想寫正式報告時，系統撈出您私下聊天時的玩笑記憶。 |

---

## 🤖 主題二：主動代理與 UX 設計 (Proactive Agency & UX)

探討系統何時該打擾使用者？如何把乾巴巴的「話題建議」升級為「不具侵入性且有幫助的輔助」？

| 文獻 / 框架 | 核心機制與概念 (Key Idea) | 給 AREQA 的產品啟發 (Takeaway) |
| :--- | :--- | :--- |
| **GUM (GUMBO)**<br>*(Shaikh et al., UIST '25)* | **期望效用過濾與預執行草稿：** <br>計算 `[幫助機率] - [打擾代價]`。過檻的建議會在「背景預先執行工具 (Pre-Executed Draft)」，而非只給純文字話題。 | **半成品取代純建議：**<br>目前的 Suggestion 應直接變成一張「已產生程式碼草稿」或「已查好資料」的 Action Card，您只需點擊修改，大幅降低認知成本。 |
| **Sensible Agent**<br>*(Lee et al., UIST '25)* | **What-How 雙模組分離：** <br>將「要建議什麼」與「如何傳遞 (語音/視覺/閃爍)」分開決策，減少對當前感官通道的干擾。 | **漸進式 UI：**<br>當您正在快速打字時，建議只在右下角顯示微小圖示；當您停頓發呆時，才展開完整的建議卡片。 |
| **ComPeer**<br>*(Liu et al., UIST '24)* | **事件偵測與排程關懷：** <br>持續偵測對話中的「死線/壓力」訊號。不立即打擾，而是排程在適當的時機 (如隔天早上) 發送協助計畫。 | **事後或延遲主動協助：**<br>在您剛解決一個大 Bug 後，系統主動跳出：「辛苦了，我幫您把剛剛的解法整理成筆記存起來了。」 |
| **EDF (Copa)**<br>*(Cohn et al., 2025/2026)* | **自適應鷹架 (Scaffold Fading & ZPD)：** <br>根據使用者採納建議的修改幅度，動態評估其「熟練度」。新手給完整解釋，老手只給極簡提示或挑戰。 | **動態 Prompt 調整：**<br>系統記憶若判定您已是該領域專家，Agent 往後的回答會自動切換為「精簡、單刀直入」模式，不再贅述基礎知識。 |
| **ProMemAssist / ProactiveVA**<br>*(Pu et al., UIST '25 / Zhao et al., 2025)* | **認知負荷與防呆時機 (Cognitive Timing)：** <br>藉由滑鼠/鍵盤停留時間、錯誤輸入頻率來評估「工作記憶負載」，在使用者卡關時主動提供「錯誤檢查」。 | **即時防呆機制：**<br>結合前端行為監測。當系統發現您輸入參數與過去 GUM 偏好相違背，適時彈出防呆提示，提供認知支持。 |
| **HAX Framework**<br>*(Cisco Outshift, 2025)* | **意圖預覽與可信任代理層 (Intent Preview)：** <br>Cisco 提出的規範。主動代理執行不可逆動作前，必須展示推理鏈並提供一鍵 Undo。 | **保持透明度與控制感：**<br>主動生成的卡片上，務必註明「基於您的ＯＯ記憶，我為您準備了...」，讓您知道它為什麼這麼做。 |

---

## 🎯 核心綜合 Takeaway (下一步行動藍圖)

1. **底層架構：實作記憶固化 (Consolidation)**
   不再讓短期的繁雜對話無限膨脹。設計一個排程，每晚總結當日對話，提煉出高 Confidence 的「使用者偏好特徵」，這能大幅提升檢索精準度。
2. **觸發機制：引入「行為感知」閾值**
   把前端的 `停頓時間`、`修改頻率` 作為觸發 Suggestion 的依據。不要隨時隨地給建議，在使用者需要靈感時（認知空檔）才溫柔遞上。
3. **介面呈現：將 Suggestion 升級為「可互動的預執行卡片」**
   停止推薦「您可以問我ＯＯ話題」。讓系統自動在背景呼叫 LLM 把話題轉化為「草稿大綱」，使用者看到的是一份半成品，點擊即可無縫接續編輯。

---

## 📚 完整文獻與作者引用 (References)

1. **GUM / GUMBO:** Shaikh, O., et al. (2025). *"Creating General User Models from Computer Use."* Proceedings of the ACM Symposium on User Interface Software and Technology (UIST '25).
2. **Generative Agents:** Park, J. S., et al. (2023). *"Generative Agents: Interactive Simulacra of Human Behavior."* Proceedings of the 2023 CHI Conference on Human Factors in Computing Systems (CHI '23).
3. **MemGPT / Letta:** Packer, C., et al. (2023). *"MemGPT: Towards LLMs as Operating Systems."* Advances in Neural Information Processing Systems (NeurIPS '23).
4. **A-MEM:** Xu, X., et al. (2025). *"A-MEM: Agentic Memory for LLM Agents."* Advances in Neural Information Processing Systems (NeurIPS '25).
5. **MemoryBank:** Zhong, W., et al. (2023). *"MemoryBank: Enhancing Large Language Models with Long-Term Memory."* arXiv preprint.
6. **STITCH:** (2026). *"Grounding Agent Memory in Contextual Intent."* (CAME-Bench, LongMemEval).
7. **Sensible Agent:** Lee, et al. (2025). *"Sensible Agent: A Framework for Unobtrusive Interaction with Proactive AR Agent."* Proceedings of the ACM Symposium on User Interface Software and Technology (UIST '25).
8. **ComPeer:** Liu, et al. (2024). *"ComPeer: A Generative Conversational Agent for Proactive Peer Support."* Proceedings of the ACM Symposium on User Interface Software and Technology (UIST '24).
9. **EDF (Copa):** Cohn, et al. (2025/2026). *"Theory-Driven Adaptive Scaffolding for LLM Agents."* arXiv preprint / Conference Proceedings.
10. **ProactiveVA:** Zhao, et al. (2025). *"Proactive Visual Analytics"* / Behavior-Aware Assistance Research.
11. **ProMemAssist:** Pu, et al. (2025). *"ProMemAssist"* (Cognitive State-Aware Timing). Proceedings of the ACM Symposium on User Interface Software and Technology (UIST '25).
12. **HAX Framework:** Cisco Outshift (2025). *"Human-Agent Experience (HAX) Framework."* Cisco Research / Design Guidelines.
