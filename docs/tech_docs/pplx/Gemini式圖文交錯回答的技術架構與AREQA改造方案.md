## 核心結論

Gemini風格的圖文交錯回答並非單純的markdown字串加圖片URL，而是基於**結構化多模態回答規劃（structured multimodal answer planning）**，其底層可分為兩種截然不同的實現路徑：一是Google DeepMind自家的**原生多模態早期融合模型**（如Gemini 3 Pro Image、Gemini 2.5 Flash Image），能在同一次前向傳播中同時輸出文字token與圖片token；二是**Grounding with Google Search / Google Image Search工具調用架構**，讓模型在生成過程中主動呼叫圖片搜尋工具並取得帶有metadata的候選結果，再將其鑄入回答結構中。對於AREQA這類應用而言，第二種路徑（工具調用+結構化輸出）更具現實可行性，也是本報告建議的目標架構。[^1][^2]

## 一、結構化多模態規劃 vs. 純Markdown

Gemini的原生架構採用「早期融合（early fusion）」設計：圖片像素patch、文字token被投影進同一個統一潛在空間，所有模態token在同一序列中被Transformer統一處理，Google將此描述為「Unified Multimodal Token Interleaving」。在生成階段，模型不是「先寫完文字再配圖」，而是在解碼序列中預測到特殊的`<BoI>`（Begin of Image）token時，直接觸發圖片解碼器生成或引用圖片，之後接續文字生成，兩者共享同一份上下文記憶。[^2][^3]

這意味著Gemini的輸出本質上是一個**帶類型標記的內容步驟序列（steps）**，而非普通markdown。開發者若要正確解析，必須手動遍歷`steps`陣列，因為便捷屬性（如`.output_text`）不會捕捉被圖片、思考步驟或工具調用打斷的文字片段。這證實了你的判斷：Gemini背後確實是結構化的answer schema，而非事後拼接的markdown文字串加圖片。[^4][^5]

對於不具備原生圖文生成能力的模型（多數第三方應用場景，包括Gemini走Grounding路徑時），系統改用「**Grounding metadata + inline annotations**」機制：模型文字輸出中每個文字片段都帶有`start_index`與`end_index`標記，對應到`grounding_supports`中連結的圖片或網頁來源，前端依此在特定文字區間後插入對應的圖片卡片。[^6][^7][^8]

## 二、圖片放置時機的決策機制

Gemini決定圖片放置位置有兩種機制路徑，取決於使用的是原生圖片生成模型還是Grounding工具：

**路徑A：原生生成模型的自回歸決策** — 模型在解碼過程中，當上下文語義需要視覺輔助時（如解釋「meta-analysis」需要視覺化森林圖），會自主生成`<BoI>`特殊token，觸發圖片解碼器基於此刻已生成的所有前文特徵來合成或選取圖片，因此圖片位置完全是模型自主決定的，且與周圍文字語義高度耦合。[^9][^3]

**路徑B：Grounding工具調用後的映射** — 模型呼叫`google_search`或`google_image_search`工具取得候選結果後，仍以純文字方式生成回答，但每個文字片段都附帶`groundingSupports`映射，指出哪一段文字對應哪一個`groundingChunks`（其中含圖片URL、landing page URL）；前端渲染層根據這些索引位置，將圖片卡片插入到對應文字之後。[^8][^6]

對於AREQA而言，路徑B更容易實現：**先讓模型輸出結構化的「文字+插槽標記」序列**，插槽標記由模型自己在生成過程中決定放置位置（例如透過特殊token或JSON中的`image_ref`欄位），而非等文字完全生成後再由後處理服務統一決定插槽。

## 三、圖片檢索的時序：前置、併發或工具調用

三種時序策略在業界均有應用，各有取捨：

| 策略 | 說明 | 延遲特性 | 適配場景 |
|---|---|---|---|
| 生成前預檢索 | 先分析query決定圖片需求，檢索候選後再連同結果餵給模型生成 | 首字延遲較高但一次到位 | 已知固定意圖類型（如百科查詢） |
| 生成中工具調用 | 模型自主決定何時呼叫圖片搜尋工具（如`google_search`的`imageSearchQueries`），模型分析prompt後動態產生搜尋詞 | 中等延遲，可精準對應語境 | Gemini Grounding的實際做法[^1][^6] |
| 生成後補強 | 文字生成完畢後才跑圖片檢索並拼接（AREQA目前做法） | 首字延遲最低但圖片與文字脫節 | 簡單MVP，非交錯體驗 |

Gemini Grounding的實際流程是：模型分析prompt→判斷是否需要搜尋→自動產生一或多個搜尋query（文字或圖片搜尋皆可）→執行搜尋→處理結果並綜合成回答，這整個流程都在**同一次模型推理的工具調用循環**中完成，而非外部服務事後介入。這正是你觀察到「圖片像是原生嵌入」而非「附加」的根本原因——因為圖片檢索本身就是模型推理循環的一部分，模型「知道」自己查詢了什麼、拿到了什麼結果，因此能自然地用文字介紹它。[^7][^1]

## 四、圖片候選的搜尋、排序、過濾、授權與歸屬

Google的Grounding with Google Image Search對圖片來源設有嚴格的合規要求，這對任何要合法使用網路圖片的應用都具參考價值：[^1]

- **來源歸屬強制**：必須提供指向圖片「所在網頁（containing page）」的連結，而非直接連向圖片檔案本身，且該連結要讓使用者能明顯識別為連結。
- **直接導航要求**：若同時顯示圖片本身，必須提供從圖片到來源網頁的「單次點擊」直達路徑，不允許使用中介圖片檢視器延遲或抽象化使用者對來源網頁的存取。
- **Metadata結構**：`groundingMetadata`物件包含`imageSearchQueries`（模型使用的搜尋詞）、`groundingChunks`（含`url`即landing page、`image_url`即圖片直連）、`groundingSupports`（將生成內容映射到引用來源）。[^1]

對於AREQA使用Wikimedia/Openverse等開放授權圖庫，建議建立以下排序與過濾管線：語義相關性（embedding cosine相似度）→授權類型過濾（CC0/CC-BY優先，避免不明授權）→解析度與畫質門檢→內容安全過濾（NSFW/暴力偵測）→重複圖片去重→最終按相關性與品質加權排序選出Top-N候選。

Gemini Embedding 2模型示範了另一種可行做法：將文字與圖片映射進同一語義空間，可直接用文字embedding去檢索圖片庫，無需分離的圖片描述生成步驟，這比傳統「先產生圖片描述文字→再用文字搜圖」的兩段式做法效率更高、語境更貼合。[^10][^11]

## 五、模型如何取得圖片Metadata以自然講解

這是實現「模型能自然介紹圖片」的關鍵機制。Gemini File Search工具的多模態RAG示範了具體做法：查詢時傳入`file_search`工具，模型自動從資料庫中檢索相關的文字chunk與視覺chunk，回應中的grounding metadata會包含`media_id`供下載對應圖片，且每個citation都附帶頁碼與上下文描述。[^12]

具體到「模型自然解釋圖片」的prompt層面，關鍵在於**在工具返回結果後，把圖片的結構化metadata（標題、alt text、來源說明、關鍵字標籤）作為文字上下文注入模型的下一輪推理輸入**，而不是把圖片當作黑盒二進位資料丟給模型。模型看到的是類似：

```
[IMAGE_CANDIDATE_1]
title: "Forest plot example"
caption: "森林圖範例，顯示各研究之風險比與信賴區間"
source: Wikimedia Commons
tags: [meta-analysis, statistics, forest-plot]
```

模型基於這段文字metadata在生成主文字時自然地引用、描述這張圖，而非憑空猜測圖片內容。這也解釋了為何Gemini能精確地在解釋「Forest Plot」段落下方插入正確圖片——模型是先「知道」候選圖片的語義標籤，才決定要不要用、用在哪裡、如何介紹它。

## 六、含非文字區塊的串流機制

Gemini的串流架構採用Server-Sent Events（SSE）搭配分塊型別化payload。實際案例顯示，後端以Node.js/Cloud Run透過`generateContentStream`取得非同步迭代器，每個chunk一到達就立即透過SSE推送給前端，前端用Fetch API的`ReadableStream`解析並呼叫`onBlock()`回呼，將新區塊加入React state進而觸發重新渲染。[^13]

對於JSON型結構化串流（含圖片卡片、表格、來源chip等非文字區塊），業界普遍做法是要求模型輸出符合`responseMimeType: "application/json"`的串流chunk，前端搭配**partial JSON parser**逐步解析尚未完整閉合的JSON片段——因為串流中的JSON在完成前並非valid JSON，需要專用的增量解析器（如`json-stream-parser`一類套件）才能安全提取已完成的區塊並渲染，未完成區塊則保持loading狀態。[^14]

## 七、前端資料結構：Block-based Answer Schema

業界通行做法確實是block-based schema，每個block帶有明確的`type`欄位，可獨立渲染、獨立loading狀態、獨立錯誤處理。針對AREQA場景，建議schema如下：

```json
{
  "answer_id": "ans_8f3a2c",
  "blocks": [
    {
      "type": "heading",
      "id": "b1",
      "level": 2,
      "text": "什麼是 Meta-Analysis"
    },
    {
      "type": "paragraph",
      "id": "b2",
      "text": "Meta-analysis 是一種統計方法，用於整合多個獨立研究的結果...",
      "citations": ["c1", "c2"]
    },
    {
      "type": "image",
      "id": "b3",
      "status": "resolved",
      "image_url": "https://upload.wikimedia.org/...",
      "source_url": "https://commons.wikimedia.org/wiki/File:Forest_plot.svg",
      "caption": "森林圖範例：顯示各研究之風險比與信賴區間",
      "alt_text": "Forest plot showing risk ratios across studies",
      "license": "CC-BY-SA-4.0",
      "attribution": "Wikimedia Commons",
      "relevance_score": 0.91,
      "anchor_after_block": "b2"
    },
    {
      "type": "table",
      "id": "b4",
      "headers": ["方法", "優點", "限制"],
      "rows": [["固定效應模型", "計算簡單", "假設研究間無異質性"]]
    },
    {
      "type": "citation_chip_group",
      "id": "b5",
      "citations": [
        {"id": "c1", "title": "...", "url": "..."}
      ]
    }
  ],
  "stream_status": "in_progress"
}
```

每個block獨立帶`id`與`status`（如`pending`/`resolved`/`error`），讓前端可以先渲染文字段落，圖片block以loading skeleton狀態呈現，待圖片檢索完成後原地替換為`resolved`狀態，而不需等待整個回答結束。

## 八、Prompt策略範例

要讓模型在生成過程中自主決定插入圖片插槽，Prompt應明確要求模型輸出結構化的block序列並附上圖片需求描述，而非直接生成圖片URL（模型不該憑空生成URL）：

```
你是一個會產生圖文交錯回答的助理。請以JSON陣列輸出回答，每個元素是一個block：
- {"type":"paragraph","text":"..."}
- {"type":"heading","text":"...","level":2}
- {"type":"image_request","query":"用於圖片搜尋的簡短查詢詞","caption_hint":"這張圖預期要說明的重點","placement":"after_previous_block"}
- {"type":"table","headers":[...],"rows":[...]}

規則：
1. 當某個概念高度依賴視覺理解時（如流程圖、歷史事件、統計圖表），插入image_request block。
2. image_request的query必須是具體、可搜尋的關鍵詞，而非抽象描述。
3. 不要生成圖片URL本身，圖片檢索由後端系統完成。
4. 每個回答最多包含2-4個image_request，避免過度插圖。
```

模型輸出`image_request`後，後端立即（並行於後續文字生成）觸發圖片搜尋工具鏈，取得候選後將完整metadata的`image`block替換原本的`image_request`占位block，再透過SSE推送更新給前端。

## 九、四種架構的取捨比較

| 架構 | 圖文語境貼合度 | 實現難度 | 延遲表現 | 授權/品質可控性 |
|---|---|---|---|---|
| 生成後補強（AREQA現況） | 低——圖片與段落語境脫鉤 | 低 | 首token延遲最快 | 高（獨立審核關卡） |
| 生成前規劃插槽 | 中——插槽位置固定但缺乏動態調整 | 中 | 需等規劃完成才開始生成 | 高 |
| 模型工具調用（推薦） | 高——圖片查詢由模型基於上下文動態產生 | 中高 | 中等，可並行處理 | 中高（仍可加審核層） |
| 全結構化生成（原生多模態） | 最高——圖文同一次推理決定 | 最高（需底層模型支援） | 依模型能力 | 需依賴模型內建圖片來源合規性 |

對於資源有限的小型產品，**模型工具調用架構**是效益最高的選擇：既能達到接近Gemini的語境貼合度，又不需要自建或微調原生多模態生成模型。

## 十、AREQA的MVP推薦架構與實施步驟

**整體管線（Pipeline）：**

1. 使用者送出query，後端建立`answer_id`並開啟SSE連線。
2. LLM以工具調用模式生成回答，模型在生成文字block的同時，遇到需要視覺輔助的段落時主動呼叫`request_image`工具（結構化function call，非plain text）。
3. 後端接收到`request_image`工具調用後，立即並行執行：(a) 繼續讓模型生成後續文字block；(b) 觸發圖片搜尋管線（Wikimedia/Openverse API查詢→embedding相關性排序→授權過濾→安全過濾）。
4. 圖片候選確定後，後端將該block的`status`從`pending`更新為`resolved`，並把選中圖片的metadata（title、caption、license、source_url）透過SSE推送給前端，同時可選擇性地把metadata送回模型context供其在稍後段落自然引用（例如「如上圖所示...」）。
5. 前端依block的`anchor_after_block`欄位，在對應段落緊接著插入圖片卡片，loading狀態顯示skeleton，resolved後平滑替換。
6. 全部block生成完畢後，`stream_status`標記為`completed`，前端關閉loading UI。

**後端建議：**
- FastAPI中以`StreamingResponse`搭配`async generator`實現SSE，每個yield對應一個完整的JSON block（用換行分隔的NDJSON格式最穩健，避免partial JSON解析複雜度）。
- 圖片搜尋以獨立的`asyncio.create_task`並行執行，不阻塞文字生成的token流。
- 為每個image block記錄唯一`request_id`，方便debug追蹤該圖片查詢的完整生命週期。

**前端建議：**
- 使用block-based狀態管理（如按`id`索引的Map），每個block獨立訂閱更新，避免整個訊息重新渲染造成閃爍。
- 圖片block在`pending`狀態顯示與最終圖片相同aspect ratio的skeleton，減少layout shift。

**失敗模式與應加入的除錯日誌：**

| 失敗模式 | 徵狀 | 建議日誌 |
|---|---|---|
| 圖片查詢詞過於抽象 | 檢索結果不相關或空結果 | 記錄`image_request.query`與檢索結果數、top相關性分數 |
| 授權過濾後無合格候選 | image block永久卡在pending或降級為無圖 | 記錄過濾前候選數 vs. 過濾後候選數，標記過濾原因（授權/畫質/安全） |
| 模型過度插圖 | 一則回答出現5個以上圖片請求 | 加入硬性上限與監控告警 |
| SSE連線中斷 | 前端block永久pending | 加入心跳(heartbeat)機制與逾時重試 |
| 圖片URL失效（403/404） | 前端顯示破圖 | 圖片代理層加上定期健康檢查與fallback圖片 |
| 圖片與段落語境不符 | 使用者回報圖文不搭 | 記錄`relevance_score`與人工抽樣審核log，建立離線評估集 |

## 十一、圖片授權與法律注意事項

使用網路圖片時必須注意以下幾點：

- **歸屬與連結義務**：即便是CC授權圖片，多數授權條款（CC-BY、CC-BY-SA）仍要求標明作者與授權類型，並提供指向原始來源頁面的可點擊連結，這與Google對Grounding Image Search的合規要求一致。[^1]
- **避免使用不明授權圖片**：優先使用Wikimedia Commons、Openverse等有明確授權標記的圖庫，避免直接爬取Google圖片搜尋結果或未經授權的商業圖庫縮圖，此類圖片版權風險高。
- **不可用中介檢視器隱藏來源**：Google明確要求「單次點擊直達來源網頁」，不允許使用會延遲或抽象化來源存取的圖片檢視器，這對設計圖片放大檢視功能時需特別留意，應保留清晰的來源連結。
- **商用場景的額外審慎**：若AREQA未來走向商業化，需針對每張圖片的授權條款（CC0、CC-BY、CC-BY-SA、CC-BY-NC）做分級管理，NC（非商業）授權圖片不應用於任何營利性場景，建議建立授權白名單機制在檢索管線中自動過濾。

---

## References

1. [Generate images with Gemini](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/image-generation) - Generate images with Gemini, using Google's image generation AI.

2. [Google Gemini — Multimodal LLM Family ...](https://systems-analysis.ru/eng/Gemini_(Google)) - Google Gemini — a family of large language and multimodal models by Google DeepMind: Sparse MoE arch...

3. [Interleaved Image-Text Generative Modeling via Multi ...](https://arxiv.org/html/2401.10208v1)

4. [יצירת תמונות באמצעות Nano Banana - Interactions API](https://ai.google.dev/gemini-api/docs/image-generation) - Get started generating images with the Gemini API using Nano Banana and Nano Banana Pro

5. [Text generation](https://ai.google.dev/gemini-api/docs/text-generation) - Get started building text generation and multi-turn interaction apps with the Gemini API

6. [Grounding with Google Search | Gemini Enterprise Agent ...](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search) - This page explains how to ground Gemini responses using results from Google's search engine, which u...

7. [Grounding with Google Search - Interactions API](https://ai.google.dev/gemini-api/docs/google-search) - Ground your model's responses in real-time information from Google Search to improve factual accurac...

8. [Grounding & Citations - GCP Cloud AI — Tutorial & Reference](https://sundante.github.io/sun-course-cloud/01-Gen-AI/06-Grounding-Citations/) - A structured tutorial covering GCP Cloud AI PaaS services — Generative AI, ML, Data Analytics, and D...

9. [Native Image Generation with Multimodal Context in ...](https://www.zenml.io/llmops-database/native-image-generation-with-multimodal-context-in-gemini-2-5-flash) - Google DeepMind released an updated native image generation capability in Gemini 2.5 Flash that repr...

10. [Building with Gemini Embedding 2](https://developers.googleblog.com/building-with-gemini-embedding-2/) - This blog post explores the general availability of Gemini Embedding 2, a unified multimodal model t...

11. [Get multimodal embeddings | Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/embeddings/get-multimodal-embeddings) - Learn how to generate multimodal embeddings using Gemini Enterprise Agent Platform models for image,...

12. [Multimodal RAG with the Gemini API File Search Tool](https://dev.to/googleai/multimodal-rag-with-the-gemini-api-file-search-tool-a-developer-guide-5878) - The File Search tool in the Gemini API now supports multimodal retrieval by adding support for Gemin...

13. [Building with Google Vertex multimodal AI - DEV Community](https://dev.to/farzankk/building-with-google-vertex-multimodal-ai-3o68) - How We Built Toon World: An AI-Powered Interactive Learning App for Kids Using Google Gemini...

14. [LLM Structured Outputs: Schema Validation for Real Pipelines ...](https://collinwilkins.com/articles/structured-output) - All major platforms support “function calls” or “tools.” You provide a schema-like signature, and th...

