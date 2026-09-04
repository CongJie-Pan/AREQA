## Interactions API 與 Managed Agents（託管智能體）
Google 在 2026 年 6 月正式將原有的 generateContent API 列為舊版（Legacy），並推出了全新的 [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview) 作為預設的開發介面。 [6, 7] 

* 
* 伺服器端狀態管理（State Management）：它天然具備記憶與對話狀態管理能力，不需要開發者自己在後端寫複雜的快取來維持上下文。 [5, 6, 7] 
* 雲端沙盒與 MCP 伺服器整合：在 Managed Agents 模式下，Gemini 可以在隔離的雲端沙盒中運行程式碼、安裝套件和管理文件。甚至在 2026 年 7 月加入了 [Model Context Protocol (MCP)](https://blog.google/innovation-and-ai/technology/developers-tools/expanding-managed-agents-gemini-api/) 遠端伺服器整合，讓 AI Agent 可以直接安全地調用你後端的私有資料庫或第三方工具，而不需要你寫一堆代理中間件。 [8] 
*  

---

## Google Interactions API 技術文件要點

Google 在 2026 年中正式將 Interactions API 提升至 GA (正式版)，全面取代舊有的 generateContent 接口，成為所有 Gemini 3.5/3.6/3.7 模型與 Agents 的標準預設入口。 [2, 4, 5] 

* 
* 官方文件首頁：Google AI for Developers - Interactions API Overview [2] 
* 核心物件與架構：
* API 資源核心為 Interaction，代表對話中的完整「一回合（Turn）」。
   * 伺服器端狀態託管（Server-side State Management）：它是有狀態的（Stateful）。開發者呼叫 interactions.create 時，只需帶入上一次的 previous_interaction_id，Google 雲端會自動進行 Context Caching（上下文快取），大幅省去每次死塞十幾輪對話的 Token 成本。 [2, 6, 7] 
* 時間軸 Steps 解析格式：
API 回傳不再只是純文字，而是一個依時間順序記錄的陣列，這對你的資教所「學習分析學」量化數據極有價值：
* ThoughtStep：模型的內部推理歷程（CoT 思考鏈），可用於渲染你的 ThinkingPanel。
   * ToolCallStep / ToolResultStep：模型自主呼叫工具（如 RAG、Web Search）與回傳結果。
   * ModelOutputStep：最終生成的文字或語音。 [7]

------

[1] [https://ai.google.dev](https://ai.google.dev/gemini-api/docs/changelog)
[2] [https://blog.google](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-agentic-video-in-gemini/)
[3] [https://ai.google.dev](https://ai.google.dev/gemini-api/docs)
[4] [https://www.facebook.com](https://www.facebook.com/googlecloud/posts/were-launching-agentic-video-understanding-across-our-latest-models-gemini-37-fl/1398738142403509/)
[5] [https://ai.google.dev](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5)
[6] [https://ai.google.dev](https://ai.google.dev/gemini-api/docs/interactions-overview)
[7] [https://ai.google.dev](https://ai.google.dev/gemini-api/docs)
[8] [https://blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/expanding-managed-agents-gemini-api/)
[9] [https://docs.cloud.google.com](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api)
[10] [https://ai.google.dev](https://ai.google.dev/gemini-api/docs/live-api)
[11] [https://ai.google.dev](https://ai.google.dev/gemini-api/docs/models)
[12] [https://cloud.google.com](https://cloud.google.com/blog/products/ai-machine-learning/gemini-live-api-available-on-vertex-ai)
[13] [https://github.com](https://github.com/google-gemini/gemini-live-api-examples)