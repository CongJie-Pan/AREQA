這篇在 Agent 記憶領域具有里程碑意義的經典論文 《MemGPT: Towards LLMs as Operating Systems》（UC Berkeley，發布於 2023 年尾）。
  這篇論文將電腦科學中最經典的「作業系統 (OS)」概念搬到了 LLM 上，可以說是真正讓 Agent 具備「自主管理記憶能力」的開山之作。以下是核心精華：
  ### 1. 研究動機 (Research Motivation)
  • LLM 的金魚腦瓶頸： 所有大語言模型都有「上下文視窗 (Context Window)」的硬性長度限制。當面對超長對話或巨量文件時，模型會忘記前面的內容。
  • 無限擴充 Context 不是解法： 雖然業界試圖把 Context 拉長到 128K 甚至百萬 token，但這會導致運算成本呈平方級暴增。更糟的是，模型在處理超長文本時會發生「Lost in the middle」效應（首尾記得住，中間全忘光）。
  • 核心目標： 作者希望能借鑒傳統作業系統中的「虛擬記憶體 (Virtual Memory) 分頁技術」，讓 Agent 能夠在有限的 Context Window 內，創造出「無限上下文」的錯覺。
  ### 2. 研究方法 (Methodology)

  MemGPT 建立了一個類似電腦記憶體階層（RAM vs. 硬碟）的架構，並賦予 LLM 自己呼叫函數 (Function Calling) 來管理記憶的權力：

  • 主上下文 (Main Context = RAM)： 這是 LLM 每次推論時實際看到的 Prompt，容量有限。包含三個區塊：
      1. 系統指令 (System Instructions)：寫死的基本規則。
      2. 工作上下文 (Working Context)：LLM 可以隨時讀寫的「便條紙」，用來記錄使用者的人設、喜好、核心事實。
      3. FIFO 佇列 (對話歷史)：最近的幾輪對話。
  • 外部上下文 (External Context = 硬碟)：
      1. 回想儲存 (Recall Storage)：以時間軸存放過去「所有」的歷史對話紀錄。
      2. 檔案儲存 (Archival Storage)：透過向量資料庫存放的無上限文件或外部知識。
  • 記憶分頁與中斷 (Paging & Interrupts)：
  當對話太長，RAM 快要爆滿時，系統會發出「Memory Pressure (記憶體壓力)」的警告。LLM 收到警告後，必須自己決定：要把哪些對話濃縮丟進硬碟？要把哪些關於使用者的重要事實寫入便條紙 (Working
  Context)？當使用者問起過去的事情時，LLM 也能自己下 Query 指令去硬碟 (Archival) 裡把資料撈回 RAM 裡回答。

  ### 3. 實驗設計 (Experiments)

  作者在兩個「極度考驗長文本能力」的領域測試了 MemGPT，並與傳統的 GPT-3.5 / GPT-4 進行對比：

  • 多輪對話伴侶 (Conversational Agents)： 使用 MSC (Multi-Session Chat) 資料集。測試 Agent
  能否在好幾次（跨越多天）的對話後，精準回答過去提過的瑣碎問題（Consistency）；以及能否根據過去的人設，主動講出極具吸引力的開場白（Engagement）。
  • 巨量文件分析 (Document Analysis)： 包含讓 Agent 在極龐大的 Wikipedia 資料庫中找答案，以及設計了一個極端困難的「巢狀 Key-Value 檢索任務」（找出 Key A 對應的 Value B，發現 B 其實是另一個
  Key，要再繼續往下找），測試 Agent 的多步推論與反覆翻找資料的能力。

  ### 4. 研究結果 (Results)

  • 對話記憶力突破天際： 在深層記憶檢索任務中，傳統 GPT-4 的準確率大約只有 32%（因為舊對話早就被截斷遺忘了）；而加上 MemGPT 架構後，GPT-4 的準確率飆升到 92.5%！
  • 生成更像人類的開場白： 因為 MemGPT 的「便條紙 (Working Context)」裡隨時記著使用者的喜好，它生成的對話開場白（例如：「你上次去夏威夷買的貝殼項鍊還有戴嗎？」）在評分上甚至超越了人類寫手。
  • 克服多步推論極限： 在巢狀 KV 檢索任務中，一般的 LLM 只要往下巢狀 1~2 層就完全崩潰放棄了。但 MemGPT 因為可以「不斷下指令去硬碟翻找，把結果帶回 RAM
  再繼續找下一層」，所以無論巢狀多深，它都能穩穩地解出答案。