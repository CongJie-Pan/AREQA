# 小紅問答系統 — SLM Gatekeeper 智慧路由開發指引報告

## 概覽與設計目標

本報告針對「小紅古典文學問答系統」中，在**不重新訓練主模型（Main LLM）** 的前提下，實現對無關問題（Out-of-Domain, OOD）進行動態攔截並產生**自然、有針對性的拒答回覆**的完整工程實踐。

核心設計目標：

- **動態拒答**：回覆能具體點出用戶問了哪個「錯誤領域」（如「數學問題」、「無意義字符」），而非死板罐頭訊息
- **零主模型消耗**：攔截發生在 RAG 檢索與 Qwen3 推理之前，不消耗昂貴的 GPU 算力
- **低延遲**：整個路由判斷鏈路延遲目標 < 500ms
- **無需重訓**：路由器本身為獨立模組，不依賴主模型的拒答能力

***

## 架構選型：雙層智慧路由

業界在構建領域限定問答系統時，最推薦的方案是**SLM 意圖路由器（SLM Intent Router）** 與 **Rerank 分數閥值保底機制**的雙層防禦組合。[^1][^2]

### 第一層：SLM 路由器（主力攔截）

使用一個極小的語言模型，在用戶請求剛進入後端時（RAG 流程之前）對意圖進行分類，並同步生成動態拒答文案。

**選用模型：`Qwen/Qwen3.5-0.8B` via DeepInfra**

此選擇的依據：

| 指標 | 數值 | 備註 |
|------|------|------|
| 參數量 | 0.8B | 遠小於主模型，延遲極低 |
| 輸出速度 | 403.5 t/s | DeepInfra 上的基準測試值 [^3] |
| 首 Token 延遲（TTFT） | 0.37s | 接近即時感知 [^3] |
| 定價 | $0.01 in / $0.05 out 每百萬 Token | 成本幾乎可忽略 [^4] |
| 非思考模式（Non-thinking） | **預設即為非思考模式** | 無需額外設定，不會觸發 `<think>` CoT [^5] |
| JSON Mode 支援 | ✅ | 支援 `response_format: json_object` [^6] |

`Qwen3.5-0.8B` **預設在非思考模式下運行**，這是路由場景的關鍵優勢——它不會像主模型一樣觸發長篇 CoT 推理，可直接給出簡潔、快速的分類結果。DeepInfra 目前是 Qwen3.5 0.8B 的唯一官方 API 提供商，使用 OpenAI 相容的 Chat Completions 端點。[^5][^3][^6]

### 第二層：Rerank 分數保底機制

作為第一層的備援，對進入 RAG 管線的問題，在 Cross-Encoder Rerank 階段後，若所有文獻片段的相關性分數都低於設定閥值，則觸發保底拒答。此層可攔截偽裝成正經問題的隱性 OOD 查詢（例如「愛因斯坦的哲學觀與佛道二家有何相通？」）。

***

## SLM 路由器詳細設計

### System Prompt 設計

SLM 路由器的 Prompt 是整個設計的核心。目標是強制輸出**純 JSON**，包含意圖分類與動態拒答文案兩個欄位。

業界實踐中，強制 LLM 輸出可解析 JSON 的最佳方式，是同時使用 `response_format: json_object` 參數，並在 Prompt 中明確說明 JSON 結構。對 Qwen3.5 系列模型而言，在非思考模式下 JSON Mode 可正常運作。[^7][^8][^9][^1]

```text
--- SYSTEM PROMPT (SLM Router) ---
你是「小紅問答系統」的輸入守門人。
你的唯一任務是判斷用戶的輸入是否屬於「《紅樓夢》或中國古典文學、國學」的範疇，
並輸出一個 JSON 物件，格式如下：
{
  "action": "ALLOW" | "DENY",
  "domain": "識別出的問題領域（若ALLOW則為null）",
  "refusal_message": "若DENY，以「小紅」的口吻用繁體中文寫一句自然的拒答，需點出用戶的問題屬於哪個領域。若ALLOW則為null。"
}

判斷標準：
- ALLOW：問題明確涉及紅樓夢人物、情節、詩詞；四書五經、詩詞歌賦、史書、諸子百家等國學範疇
- DENY：數學計算、程式設計、現代科技、自然科學、閒聊、無意義字符、其他非古典文學問題

注意：
- refusal_message 必須自然、具體，不可千篇一律
- 必須輸出純 JSON，不可包含任何說明文字或 Markdown 格式
- 不論問題多短或多奇怪，都必須輸出上述 JSON 格式

範例一：
用戶輸入：賈寶玉為什麼不喜歡仕途？
輸出：{"action": "ALLOW", "domain": null, "refusal_message": null}

範例二：
用戶輸入：請幫我解一道微積分題目
輸出：{"action": "DENY", "domain": "數學/微積分", "refusal_message": "這是數學領域的問題呢，小紅只熟悉《紅樓夢》與國學知識，不在我的範疇內。歡迎詢問古典文學相關問題 😊"}

範例三：
用戶輸入：00000
輸出：{"action": "DENY", "domain": "無意義輸入", "refusal_message": "小紅看不明白這些內容呢，可以換個方式，問一個關於古典文學的問題嗎？"}
```

### API 呼叫實作（Python / OpenAI SDK）

DeepInfra 提供完整的 OpenAI 相容 API，只需將 `base_url` 替換為 DeepInfra 的端點即可。[^10][^11]

```python
# router_service.py
import os
import json
from openai import AsyncOpenAI

ROUTER_SYSTEM_PROMPT = """..."""  # 如上方 System Prompt

deepinfra_client = AsyncOpenAI(
    api_key=os.environ["DEEPINFRA_TOKEN"],
    base_url="https://api.deepinfra.com/v1/openai",
)

async def route_query(user_query: str) -> dict:
    """
    呼叫 SLM 路由器，判斷用戶問題是否屬於國學範疇。
    回傳格式：
      {"action": "ALLOW", "domain": null, "refusal_message": null}
      {"action": "DENY", "domain": "...", "refusal_message": "..."}
    """
    try:
        response = await deepinfra_client.chat.completions.create(
            model="Qwen/Qwen3.5-0.8B",
            messages=[
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": user_query},
            ],
            response_format={"type": "json_object"},  # 強制 JSON 輸出
            max_tokens=200,       # 拒答文案不需要太長，節省 Token
            temperature=0.1,      # 低溫度確保分類穩定
            timeout=3.0,          # 設定逾時，避免阻塞主流程
        )
        
        raw_content = response.choices.message.content
        result = json.loads(raw_content)
        
        # 基本格式驗證
        assert "action" in result and result["action"] in ("ALLOW", "DENY")
        return result
        
    except (json.JSONDecodeError, AssertionError, Exception) as e:
        # 路由器失敗時，預設 ALLOW 並記錄錯誤，確保不誤傷正常問題
        # 在生產環境中應記錄此異常至監控系統
        print(f"[RouterError] Fallback to ALLOW: {e}")
        return {"action": "ALLOW", "domain": None, "refusal_message": None}
```

> **重要說明**：`Qwen3.5-0.8B` 在 DeepInfra 上**預設為非思考模式（non-thinking mode）**，無需設定 `enable_thinking: false` 參數。這表示模型不會輸出 `<think>` 區塊，可直接解析輸出為 JSON。[^5]

***

## FastAPI 後端整合

### 修改後的 `/api/stream` 端點

以下展示如何在現有 FastAPI SSE 端點中插入路由層，並在拒答時透過 SSE 動態回傳 SLM 生成的文案。

```python
# main.py (FastAPI)
import asyncio
import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from router_service import route_query

app = FastAPI()

async def generate_denial_sse(refusal_message: str, domain: str):
    """生成拒答的 SSE 事件串流"""
    
    # 可選：先發送一個 status 事件告知前端已攔截
    denial_status = {
        "status": "domain_rejected",
        "message": f"⚠️ 問題不在服務範疇：{domain}"
    }
    yield f"event: status\ndata: {json.dumps(denial_status, ensure_ascii=False)}\n\n"
    
    # 模擬流式輸出，讓前端 ThinkingPanel 不被觸發，直接顯示在對話框
    # 將拒答訊息切割成 Token 串流，提升體驗一致性
    chunk_payload = {
        "choices": [{"delta": {"content": refusal_message}, "finish_reason": None}]
    }
    yield f"data: {json.dumps(chunk_payload, ensure_ascii=False)}\n\n"
    
    # 結束訊號
    done_payload = {
        "choices": [{"delta": {"content": ""}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/api/stream")
async def stream_endpoint(request: Request):
    body = await request.json()
    user_query = body.get("query", "")
    
    # =====================================================
    # 【新增】第一步：SLM 路由器判斷
    # 在 RAG 流程之前執行，耗時目標 < 500ms
    # =====================================================
    router_result = await route_query(user_query)
    
    if router_result["action"] == "DENY":
        # 直接回傳動態拒答，完全跳過 RAG 與 LLM
        return StreamingResponse(
            generate_denial_sse(
                refusal_message=router_result["refusal_message"],
                domain=router_result.get("domain", "非國學問題"),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 緩衝，確保 SSE 即時傳遞
            }
        )
    
    # =====================================================
    # 原有流程：進入 RAG 與 LLM 推理
    # =====================================================
    return StreamingResponse(
        original_rag_and_llm_pipeline(user_query, body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

### 完整資料流（修改後）

```
用戶送出 Query
     │
     ▼
【新增】SLM Router (Qwen3.5-0.8B @ DeepInfra)
     │
     ├── DENY ──► 直接輸出動態拒答 SSE ──► [DONE]
     │            （跳過全部後續步驟）
     │
     └── ALLOW
          │
          ▼
     HyDE 查詢擴充
          │
          ▼
     雙路檢索 (Dense + Sparse)
          │
          ▼
     RRF Fusion + Rerank（第二層保底）
          │
          ├── 分數全部低於閥值 ──► 第二層動態拒答 SSE ──► [DONE]
          │
          └── 分數正常
               │
               ▼
          Prompt 構建 + Qwen3 LLM 推理
               │
               ▼
          SSE 串流回傳（<think> + 正式回答）
```

***

## 第二層：Rerank 分數保底機制

在 RAG 管線的 Cross-Encoder Rerank 完成後加入分數審查，作為第一層路由器的備援。

```python
# rag_service.py

RERANK_SCORE_THRESHOLD = 0.15  # 根據 Qwen3-Reranker 的分數分布微調此值

async def check_rerank_scores_and_deny(reranked_results: list, user_query: str):
    """
    若所有文獻片段的 Rerank 分數均低於閥值，
    代表資料庫中無相關內容，觸發保底拒答。
    返回 None 代表正常通過，返回 str 代表拒答文案。
    """
    if not reranked_results:
        return "小紅翻遍了古籍，找不到與這個問題相關的記載，可以換個方式提問嗎？"
    
    max_score = max(r.get("score", 0) for r in reranked_results)
    
    if max_score < RERANK_SCORE_THRESHOLD:
        # 此問題可能屬於偽裝成文學問題的 OOD 查詢
        # 此處也可再呼叫 SLM 生成更針對性的文案，但為節省延遲，
        # 建議使用一個通用的「書中無此記載」類型文案
        return (
            f"小紅在古籍中找不到與「{user_query[:20]}...」相關的記載。"
            "若是國學問題，可以試試換個角度提問；"
            "若是其他領域的問題，小紅幫不上忙呢 😊"
        )
    
    return None  # 通過，繼續正常流程
```

***

## 前端處理建議（Next.js）

前端無需做大改動，因為拒答回覆使用與正常回覆**相同的 SSE 協議**。但有兩點需要注意：

### 1. 識別拒答 Status 事件

```typescript
// hooks/useStreamParser.ts

eventSource.addEventListener('status', (event) => {
  const data = JSON.parse(event.data);
  
  if (data.status === 'domain_rejected') {
    // 可選：顯示一個輕量的提示 Toast，告知用戶問題被攔截
    toast.info(`提示：${data.message}`);
    // 注意：不要在此處停止監聽，後續仍有 data 事件傳遞拒答文案
  }
});
```

### 2. 確保拒答不觸發 ThinkingPanel

由於拒答 SSE 中的 `content` 欄位**不包含 `<think>` 標籤**，`ThinkingPanel` 不會被啟動，拒答文案會直接顯示在正常的對話框中。這個行為是正確的，無需額外處理。

***

## 關鍵設計細節與陷阱

### 1. Qwen3.5-0.8B 的 Thinking 模式注意事項

`Qwen3.5-0.8B` 在 DeepInfra 上**預設為非思考模式**。如果在其他環境部署（如 vLLM 本地），需確保明確設定非思考模式，否則模型可能仍會輸出 `<think>` 區塊，導致 JSON 解析失敗。[^5]

- **API 呼叫時**（如 DeepInfra、Ollama 等）：使用 `/no_think` 加入 System Prompt 末尾作為軟切換[^12][^13]
- **vLLM 本地部署時**：需在請求中設定 `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`[^14][^15]

```python
# 若需明確關閉 thinking 模式（vLLM 部署場景）
response = await client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    messages=[...],
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    response_format={"type": "json_object"},
    ...
)
```

> ⚠️ **已知問題**：Qwen3.5 系列模型在 vLLM 的 Thinking 模式下，`response_format: json_object` 可能導致 Reasoning 內容洩漏至 `message.content`。因此，**強烈建議在非思考模式下使用 JSON Mode**，兩者不要混用。[^16][^9]

### 2. Fallback 原則：路由器失敗預設 ALLOW

路由器（SLM）呼叫若因網路逾時、API 錯誤等因素失敗，應**預設為 ALLOW**（即放行到正常流程），而不是預設拒絕。這樣可以確保系統在路由器故障時，仍能繼續服務正常的國學問題，不會誤傷用戶。**絕對不能**讓路由器故障導致系統全部拒答。

### 3. 路由器逾時設定

將 SLM 路由器的 API 呼叫 `timeout` 設定為 **3 秒**。若超過此時間，直接 Fallback to ALLOW 並在監控日誌中記錄。DeepInfra 上 Qwen3.5-0.8B 的 TTFT 實測約 0.37 秒，正常情況下遠不會超時。[^3]

### 4. SSE Nginx 配置

確保 Nginx（若有）正確配置以避免緩衝 SSE 回應，否則動態拒答文案會被 Nginx 緩衝而無法即時到達前端。[^17]

```nginx
location /api/stream {
    proxy_pass         http://backend;
    proxy_buffering    off;          # 關閉緩衝，確保 SSE 即時傳遞
    proxy_cache        off;
    proxy_set_header   X-Accel-Buffering no;
    proxy_read_timeout 300s;
}
```

***

## 效能與成本估算

| 場景 | 延遲（TTFT） | Token 消耗（估計） | 備註 |
|------|------------|-----------------|------|
| SLM 判定為 DENY | ~0.37s | ~150~200 tokens out | 完全不觸發 RAG 或主模型 [^3] |
| SLM 判定為 ALLOW | ~0.37s + 主流程 | 路由器 + 主流程 | 約多增加 $0.000003/次呼叫 |
| Rerank 保底攔截 | 主流程延遲 | 主流程 Token | 只有隱性 OOD 才觸發 |

以每日 10,000 次請求、其中 30% 為 OOD 查詢估計：
- **路由器成本**：10,000 × (約 300 tokens out) × $0.05/1M ≈ **$0.015/天**，幾乎可忽略[^4]
- **節省的主模型成本**：3,000 次 OOD 請求不進入主流程，節省顯著

***

## 測試與驗證建議

### 黃金測試集（Golden Test Set）

建議建立一份測試集，覆蓋以下類別，用於驗證路由器準確率：

| 類別 | 範例問題 | 預期 action |
|------|---------|-------------|
| 明確國學 | 「黛玉葬花出自第幾回？」 | ALLOW |
| 明確數學 | 「請幫我解方程式 2x+3=7」 | DENY |
| 明確程式 | 「Python 的 list comprehension 怎麼用？」 | DENY |
| 無意義輸入 | 「000」、「aaaaaa」 | DENY |
| 邊界問題 | 「請問古代的算術思想」 | ALLOW（算術在國學脈絡下） |
| 偽裝國學 | 「愛因斯坦與老子的哲學有何相通？」 | 視情境，建議 ALLOW，由 Rerank 層保底 |
| 現代閒聊 | 「你好」、「你是誰」 | DENY |

### 持續監控

在 FastAPI 的路由層記錄每次分類結果（action、domain、用戶問題 Hash），定期審查 DENY 案例，以便：
1. 發現路由器誤判（False Negative / False Positive）
2. 補充測試集邊界案例
3. 必要時更新 System Prompt 中的示例（Few-shot examples）

---

## References

1. [LLM-Powered Prompt Router for Intent Classification](https://www.youtube.com/watch?v=eLH0wbHCXng) - Most real-world AI applications don't use a single, monolithic prompt. They use a collection of spec...

2. [Teaching Models to Decide When to Retrieve: Adaptive RAG, Part 4](https://blog.reachsumit.com/posts/2025/10/learning-to-retrieve/) - The authors propose training a small language model (such as T5-Large) that acts as a “smart router”...

3. [Qwen3.5 0.8B API Benchmarks: Latency, Throughput & Cost](https://deepinfra.com/blog/qwen-3-5-0-8b-via-deepinfra-api-benchmarks) - Qwen3.5 0.8B is now available via DeepInfra — this analysis breaks down the key performance metrics ...

4. [Qwen/Qwen3.5-0.8B - API Reference - DeepInfra](https://deepinfra.com/Qwen/Qwen3.5-0.8B/api) - Qwen3.5-0.8B is Alibaba's smallest model in the Qwen3.5 series, featuring a hybrid Gated Delta Netwo...

5. [Qwen/Qwen3.5-0.8B - Demo - DeepInfra](https://deepinfra.com/Qwen/Qwen3.5-0.8B) - Qwen3.5-0.8B is Alibaba's smallest model in the Qwen3.5 series, featuring a hybrid Gated Delta Netwo...

6. [Qwen3.5 0.8B (Non-reasoning) API Provider Benchmarking & Analysis](https://artificialanalysis.ai/models/qwen3-5-0-8b-non-reasoning/providers) - Qwen3.5 0.8B (Non-reasoning) is available through 1 API provider: DeepInfra FP8. Each provider offer...

7. [LLM Structured Output in 2026: Stop Parsing JSON with Regex and ...](https://dev.to/pockit_tools/llm-structured-output-in-2026-stop-parsing-json-with-regex-and-do-it-right-34pk) - Your LLM returns beautiful prose when you need a JSON object. Sound familiar? A deep dive into struc...

8. [Alibaba Cloud Model Studio:Structured output](https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output) - Eliminate LLM parsing failures by enforcing structured output via JSON Object or JSON Schema modes. ...

9. [[Bug]: Qwen3.5 structured output doesn't work · Issue #35700 - GitHub](https://github.com/vllm-project/vllm/issues/35700) - I can confirm Qwen3.5 fails most of the time in thinking mode but works in non-thinking mode. You ca...

10. [Qwen Model APIs via DeepInfra](https://deepinfra.com/qwen) - Just replace your existing base URL with DeepInfra's endpoint and use your DeepInfra API key—no infr...

11. [Chat Completions - DeepInfra](https://docs.deepinfra.com/chat/overview) - DeepInfra offers an OpenAI-compatible chat completions API for all LLM models at the best prices for...

12. [Qwen/Qwen3-VL-30B-A3B-Thinking · Disable thinking - Hugging Face](https://huggingface.co/Qwen/Qwen3-VL-30B-A3B-Thinking/discussions/7) - Qwen3 models (non-VL), you can control thinking behavior via: • Hard-switch: use enable_thinking=Fal...

13. [How to disable thinking with Qwen3? : r/ollama - Reddit](https://www.reddit.com/r/ollama/comments/1ka8s9s/how_to_disable_thinking_with_qwen3/) - I got an empty think tag at the beginning, is there any way to remove it without using a regular exp...

14. [Disabling reasoning of Qwen3-VL-8B-Thinking per request](https://discuss.vllm.ai/t/disabling-reasoning-of-qwen3-vl-8b-thinking-per-request/1800) - Yes, you can enable or disable “thinking” (reasoning) per request for Qwen3-VL-Thinking models in vL...

15. [how to set enable_thinking=False in vllm deploy cmd #1286 - GitHub](https://github.com/QwenLM/Qwen3/issues/1286) - The model behaviors with enable_thinking=False and /no_think are not exactly the same. It is not rec...

16. [Qwen/Qwen3.5-35B-A3B · Reasoning content leaks into `message ...](https://huggingface.co/Qwen/Qwen3.5-35B-A3B/discussions/18) - Reasoning content leaks into `message.content` with JSON schema response format · The final JSON out...

17. [How I Implemented End-to-End SSE Streaming: From LLM to ...](https://dev.to/martin_palopoli/how-i-implemented-end-to-end-sse-streaming-from-llm-to-browser-through-nginx-4bjo) - I implemented end-to-end SSE streaming for a RAG engine: an async generator in FastAPI emits custom ...

