Yijia 會這樣說，是因為 Omar Shaikh（和他所在的 Stanford 團隊）在 2025 年 UIST 發表的研究 **《Creating General User Models from Computer Use》** 中，所提出來的 General User Model (GUM) **並不是一個孤立的聊天機器人或單一應用程式，而是整合進整個作業系統環境的架構** 。 [arxiv](https://arxiv.org/abs/2505.10831)

## 為什麼說它「和整個系統整合」？

根據這篇論文與相關資料，Omar 設計的 GUM 是這樣運作的：

1. **全域觀察（System-wide observation）：**
   這個模型不是只看你在 ChatGPT 裡打了什麼字，它是**直接擷取你電腦螢幕的截圖（device screenshots）**，觀察你在任何應用程式（Word、瀏覽器、通訊軟體等）上的所有互動 。 [youtube](https://www.youtube.com/watch?v=XcZ5cGJ4hVs)

2. **跨應用推理（Cross-app reasoning）：**
   因為它能看到整個系統，所以它能跨應用程式去理解你在幹嘛。例如：
   - 它看到你在通訊軟體跟朋友討論婚禮，就知道你在準備參加婚禮 。 [arxiv](https://arxiv.org/abs/2505.10831)
   - 它看到你反覆修改一份草稿，然後切換去讀相關文獻，它就能推斷「你卡關了」，甚至幫你預判需求 。 [youtube](https://www.youtube.com/watch?v=XcZ5cGJ4hVs)

3. **支援多種下游應用（Enabling downstream applications）：**
   Omar 的研究不只是建了一個觀察模型，他們還展示了這個模型如何與系統功能整合 ： [arxiv](https://arxiv.org/abs/2505.10831)
   - **智慧通知管理：** 根據你現在的工作狀態，決定要不要把系統通知（OS notifications）推播給你 。 [youtube](https://www.youtube.com/watch?v=XcZ5cGJ4hVs)
   - **主動助理 (GUMBOs)：** 不是等你下指令，而是模型自己發現需求，然後主動替你執行有用的建議 。 [arxiv](https://arxiv.org/abs/2505.10831)

## 總結

Yijia 想表達的意思是：Omar 不是只做了一個「比較聰明的聊天視窗」，而是做了一個**「住在你的作業系統裡，能夠看懂你所有軟體操作，並主動調度系統功能來幫你」的底層整合架構**。這就是為什麼她會強調「它還是和整個系統去做整合」，因為這種全域整合（System-level integration）正是突破現有 AI 侷限（只能在單一 App 裡發揮作用）的關鍵！