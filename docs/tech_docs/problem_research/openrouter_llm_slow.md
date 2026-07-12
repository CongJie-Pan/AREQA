最可能原因依序如下：

1. OpenRouter 模型本身首 token 延遲高
    正式紀錄顯示首個文字 token 約 5.56 秒，完整生成約 8.75～9 秒。docs/misc/20260712_demoTest/terminal_logs.md:108
    這通常與模型負載、供應商排隊、模型推理速度有關。

2. 送給模型的 prompt 太大
    主模型會同時注入：
    - 對話歷史
    - 使用者 profile
    - working memory
    - EDF 狀態
    - 搜尋結果
    - 系統規則

    而且程式在 backend/services/orchestration_service.py:690 會組合這些內容。記憶越多，輸入 token 越大，模型首 token 也可能越慢。

3. 每次訊息同時啟動多個 LLM 任務
    一次對話可能包含：
    - EDF 學習狀態分析`
    - GUM 記憶分析
    - 記憶演化判斷
    - 主回答生成
    - 回答後的 suggestions
    - Perplexity 搜尋與 query rewrite

    紀錄中同一回合有多次 OpenRouter 呼叫，docs/misc/20260712_demoTest/terminal_logs.md:9。即使部分是背景任務，也會與主回答共用 Render／OpenRouter 資源。

4. 需要搜尋時一定更慢
    SpaceX 問題額外觸發 Perplexity，搜尋約 2.87～3.90 秒。docs/misc/20260712_demoTest/terminal_logs.md:198

5. 模型可能啟用 reasoning 或輸出上限過高
    程式在 force_think 時把 max_tokens 提高到 3200，可能導致推理時間與完整回答時間增加。backend/services/orchestration_service.py:480

6. render 專案的免費方案的限制，網路慢。

所以延遲問題的核心假說是：

> 主回答模型本身約 5～9 秒，加上過大的 prompt、背景 LLM 呼叫與搜尋，或是render 專案的免費方案的限制，網路慢，造成使用者感覺整體回應很慢。