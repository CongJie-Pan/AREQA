# AREQA Landing Page 實作計畫 (Implementation Plan)

## 一、 專案概述 (Project Overview)
本計畫旨在開發 **AREQA (Adaptive RAG-based Educational QA System)** 的單頁式網站 (Landing Page)。
有別於一般冷冰冰、AI 感沉重（充斥著發光幾何體、立體 3D 渲染與 generic 機器人）的 AI 工具，AREQA 的核心定位是**「可靠且溫暖的學習學伴」**。
為了打破樣圖中那種「SaaS 假套版 AI 感」，本網站將**完全捨棄通用 AI 的假文案與 generic 圖示**，改以展示 **AREQA 的真實前端元件微縮版 (Mini-UI)** 來呈現我們核心的 RAG 檢索、記憶系統 (GUM)、教育認知策略 (EDF) 與信箱關懷。

## 二、 建議開發技術棧 (Technology Stack)
*   **前端框架**：Vite + React
*   **樣式與排版**：Vanilla CSS (嚴格禁用 TailwindCSS，確保最高度的自定義與精準排版)
*   **字體系統**：
    *   標題與 Slogan：引入 Noto Serif TC (思源宋體，襯線體)，營造古典、沉靜、書香氣息。
    *   內文與程式碼：Noto Sans TC (思源黑體) 與 Roboto Mono (等寬字體)，呈現科技的俐落。

## 三、 UI/UX 設計規範與「去 AI 感」策略 (UI/UX Standards & Anti-AI Vibe)
1.  **色彩計畫 (Color Palette)**
    *   **主背景色**：星空藍 / 深邃藏青 (`Midnight Indigo`, `#0D1321` 或 `#0B0F19`)，提供極致專注的深夜書房氛圍。
    *   **主視覺色 (Accent)**：暖心橘金 (`Eureka Gold`, `#E6A15C` / `#D4AF37`)，非刺眼的發光霓虹金，而是溫潤的書頁邊緣與燭光色，代表頓悟與陪伴。
    *   **文字色**：象牙白 (`Off-white`, `#F4F4F9`) 與溫和灰 (`Muted Grey`, `#A0A5B5`)。
2.  **視覺與去 AI 感策略 (Anti-AI Design Rules)**
    *   **禁用 generic 科技圖標**：不使用「飛行的紙飛機代表傳送」、「盾牌代表安全」、「齒輪代表 AI 處理」等套版圖示。
    *   **採用真實 Mini-UI 代替假插圖**：特色網格卡片中，**直接以 CSS 刻畫簡化版、高精緻度的實際系統元件 (Mini-UI)**，例如帶有黃金引用標籤的訊息框、帶有學伴頭像的對話氣泡等。這能讓使用者立刻明白這是一個「真實的、已開發完成的產品」，而非 AI 繪圖的概念網頁。
    *   **插畫風格統一**：首屏右側的 `logo_謬思女神_微笑_去背.png` 須以純色/單色點陣 (Dithered/Stippled) 蝕刻風格呈現，並加上微妙的 CSS 浮動微動效，拒絕過度飽和的 3D 渲染。

## 四、 頁面佈局與真實功能文案規劃 (Layout & Real Features Copywriting)

### 1. 頂部導覽列 (Header)
*   **左側識別**：置入 `areqa_text_logo_v2.png`。
*   **右側導覽**：`關於學伴`、`陪伴核心`、`思維透明`，以及最右側的 `[ 進入學習大廳 ]` 暖橘金按鈕。

### 2. 首屏主視覺區 (Hero Section)
*   **Slogan 標題**：
    ```markdown
    # AREQA: Adaptive RAG-based Educational QA System
    「AREQA：懂你所學，伴你所讀」
    ```
*   **副標題**：不只是問答，更是你讀書、探索新知時，最溫暖且懂你的專屬學伴。
*   **行動呼籲 (CTA)**：`[ 開始對話 ]` (點擊直接進入 Web App)。
*   **右側視覺**：擺放 `logo_謬思女神_微笑_去背.png`（溫暖微笑的繆思女神，為學習者指引迷津的意象）。

### 3. 學伴價值主張過場 (Value Proposition Quote)
*   大字體排版：「教育，是靈魂的喚醒；AREQA，是旅途的燈塔。」

### 4. 六大真實核心功能網格 (6 Features Grid with Mini-UI Showcase)
此區塊完全對齊 `README.md` 的系統核心開發成果，**用精緻的 Mini-UI 元件模擬圖取代 AI 假插圖**：

1.  **混合知識檢索 (Hybrid RAG & Citations)**
    *   *文案*：結合 FAISS + BM25 檢索與 Perplexity 聯網搜尋，為你梳理知識脈絡。
    *   *Mini-UI 視覺*：微型的對話框，底部帶有精緻的金色圓角文獻晶片 `[1] 蘇格拉底對話錄` 點擊氣泡效果。
2.  **學習者認知策略 (EDF Pedagogical Policy)**
    *   *文案*：即時判斷你的學習狀態（從 `STARTING 嘗試` 到 `GIVING_UP 挫折`），動態調整說明難度與語氣。
    *   *Mini-UI 視覺*：一個小巧的狀態指示器，顯示目前學伴對你的觀察評估：`狀態：挫折 (Giving Up) ➜ 切換為關懷引導模式`。
3.  **英靈附體對話 (Active Avatar Mode)**
    *   *文案*：當你探討特定學術問題時，可召喚歷史大師（蘇格拉底、柏拉圖）以第一人稱語氣與你深度思辨。
    *   *Mini-UI 視覺*：兩個堆疊的圓形頭像（蘇格拉底、柏拉圖），點選會亮起，下方顯示一句：「我是蘇格拉底，讓我們一起探討這件事...」。
4.  **長期冷熱記憶系統 (GUM Memory System)**
    *   *文案*：利用 GUM 記憶框架，將每一次對話自動濃縮，持續更新你的偏好畫像，下次聊天不必重頭說起。
    *   *Mini-UI 視覺*：微型的 GumPanel 記憶面板卡片，上方有 `#學習偏好`、`#不喜歡艱澀術語` 的標籤雲 (Tags)。
5.  **主動關懷信箱 (Mailbox System)**
    *   *文案*：學習之路不孤單。離線時，大師會整理你的問題並寄送延遲信件，透過 WebSocket 在你上線時主動遞上關懷。
    *   *Mini-UI 視覺*：一個精緻的信封通知氣泡，右上角顯示 `未讀信件 (1)`，並帶有一小段「來自蘇格拉底的一封信...」的預覽。
6.  **思維透明化 (Transparent Thinking Panel)**
    *   *文案*：完整呈現 LLM 串流生成的 CoT (Chain of Thought) 思考過程，讓你不只得到答案，更學會思考邏輯。
    *   *Mini-UI 視覺*：一個帶有 `<think>` 標記的折疊面板，呈現微縮的程式碼與思考步驟文字。

### 5. 巨大字體過場區 (Giant Logotype Section)
*   背景顯示巨大的半透明「A R E Q A」襯線體，隨滾動產生微妙的視差。

### 6. 頁尾 (Footer)
*   底部置中置入 `areqa_icon_v3.png`。
*   底部版權宣告與簡單的 sitemap。

---

## 五、 多 Agent 協作發派策略 (Multi-Agent Delegation Plan)

1.  **Root Agent (總編排者)**
    *   **任務**：初始化專案、統合 Subagents 的 React 元件，進行最終 Code Review 與 RWD 破版檢查。
2.  **Subagent A (資產與樣式開發 Agent - Asset & Style Specialist)**
    *   **任務**：
        1. 建立 `src/styles/variables.css` 的設計變數，定義 `Midnight Indigo` 與 `Eureka Gold`。
        2. 從專案現有的 `frontend/src/components` 中提取設計線索，為 6 大功能的 Mini-UI 刻畫基礎 CSS 樣式。
3.  **Subagent B (Hero 區塊開發 Agent - Hero & Header Developer)**
    *   **任務**：實作包含 `areqa_text_logo` 與 `logo_謬思女神` 的首頁首屏。確保 Noto Serif TC 字體載入正常，大標題與副標題排版大氣、優雅，CTA 按鈕有溫和的光暈過場效果。
4.  **Subagent C (真實功能元件 Agent - Features & Mini-UI Developer)**
    *   **任務**：使用 Vanilla CSS 繪製 6 個功能卡片中的 Mini-UI (例如 Citations chips, EDF 狀態顯示器, Mailbox 提示, Thinking 摺疊等)，確保用**真實程式碼渲染出的介面**取代 AI 生成的虛假圖片。
5.  **Subagent D (體驗打磨 Agent - Motion & SEO Specialist)**
    *   **任務**：為 Mini-UI 添加微小的動態互動（例如滑鼠懸停在信封上時，信封微微開啟；點擊思考摺疊面板時，順暢展開）。加入 RAG 元件的防閃爍邏輯 (Deferred CSS)，並補齊 Traditional Chinese 的 SEO 標籤。
