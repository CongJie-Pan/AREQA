# RAG 即時狀態顯示：架構審查與完整修改方案

## 執行摘要

現有程式碼已具備良好的 SSE 骨架 — 後端 `main.py` 已正確透過 `event: status` 推送 RAG 狀態，`event: sources` 推送文獻。**真正的缺口在前端**：`MessageItem-2.tsx` 僅以一個靜態 `<div>📂 RAG 檢索當中</div>` 回應所有 retrieving 狀態，完全沒有消費 `status` 事件流、也沒有對各階段進行差異渲染。因此本方案聚焦三個交付物：

1. **`RAGStatusPanel.tsx`** — 類 Perplexity 的 RAG 進度面板元件
2. **`useStreamingChat.ts`** — 重寫的 React Hook，正確解析所有 SSE 命名事件
3. **`rag_service_patch.py`** — `RAGService.retrieve_with_events()` 補丁，確保後端逐步推送每個階段

***

## 現況審查

### 後端 main.py — 已有但不完整

`main.py` 的 `generate()` 協程已使用 `rag_service.retrieve_with_events()` 迭代器，並將 `type == "status"` 的事件包裝為：

```python
yield f"event: status\ndata: {json.dumps(status_payload, ensure_ascii=False)}\n\n"
```

以及文獻就緒後的：

```python
yield f"event: sources\ndata: {json.dumps(sources_payload, ensure_ascii=False)}\n\n"
```

**問題**：`rag_service.retrieve_with_events()` 實際上能否逐步 yield 各階段事件，取決於 `RAGService` 的實作。若原本只是一個阻塞式同步 `retrieve()` 呼叫的簡單包裝，所有狀態事件會在完成後才一次推出，前端根本看不到進度。

### 前端 MessageItem-2.tsx — 靜態顯示，沒有狀態消費

`ragInfo` prop 的型別定義已包含完整的 `RAGStatus` 枚舉（`searching_dense` / `searching_sparse` / `reranking` 等），但實際 JSX 只做了一個陣列 includes 檢查：

```tsx
{['retrieving', 'searching_dense', 'searching_sparse', 'reranking'].includes(ragInfo?.status || '') && (
  <div>📂 RAG 檢索當中</div>
)}
```

這意味著無論是 FAISS 在跑、BM25 在跑、還是 RRF 重排，使用者永遠只看到同一行文字。

### useStreamingChat（推測）— SSE 命名事件未被解析

從 `MessageItem` 接受的 `ragInfo` 型別推斷，目前的 hook 應有對 `event: status` 做基本解析。但常見問題是 SSE 解析器只抓 `data:` 行、忽略 `event:` 行，導致 `status`、`sources`、`error` 等命名事件全部被丟棄。

***

## 架構缺口總表

| 層 | 問題 | 影響 |
|---|---|---|
| `RAGService.retrieve_with_events()` | 若原本是阻塞呼叫，所有事件在完成後才推出 | 無法看到逐步進度 |
| `main.py generate()` | 結構正確，但依賴 RAGService 是否真正 yield | 若 RAGService 不 yield 則無效 |
| `useStreamingChat` hook | SSE 解析可能丟失 `event:` 行，未追蹤 `status` / `sources` 事件 | ragInfo 狀態不更新 |
| `MessageItem` JSX | 只有靜態文字，無步驟動畫、無文獻預覽 | 使用者體驗停滯 |

***

## 解決方案架構

```
Backend SSE 事件流:
  event: metadata  →  token 計數（可忽略）
  event: status    →  { status: "searching_dense", message: "..." }
  event: status    →  { status: "searching_sparse", message: "..." }
  event: status    →  { status: "reranking", message: "..." }
  event: status    →  { status: "sources_ready", message: "..." }
  event: sources   →  CitationSource[]
  event: status    →  { status: "generating", message: "..." }
  data: {...}      →  OpenAI delta chunk（重複）
  data: [DONE]     →  串流結束

Frontend 狀態機:
  useStreamingChat hook
    ├── 解析所有 SSE 命名事件
    ├── 維護 ragInfo: RAGInfo 狀態
    └── 注入 <RAGStatusPanel ragInfo={ragInfo} />
         ├── 步驟進度列（帶 spinner / checkmark 動畫）
         ├── 文獻卡片（staggered entrance animation）
         └── 展開/收合（完成後自動收合）
```

***

## 交付物 1：RAGStatusPanel.tsx（全新元件）

類 Perplexity 的 RAG 進度面板，功能如下：

- **5 個步驟指示器**：語意向量檢索 → 關鍵詞稀疏檢索 → RRF 融合重排序 → 文獻已載入 → 生成解說
- **每個步驟**：待執行（灰色）→ 執行中（藍色旋轉 spinner）→ 完成（綠色 checkmark）
- **文獻卡片**：`sources_ready` 後展示帶 staggered fade-in 動畫的來源片段
- **可折疊面板**：完成後 2.5 秒自動收合，可點擊重新展開
- **完成狀態**：Header 變為綠色 ✅ 並顯示找到幾筆文獻

**Props 介面**：
```typescript
interface RAGStatusPanelProps {
  ragInfo: RAGInfo;    // { status, message, sources }
  isStreaming?: boolean;
}
```

***

## 交付物 2：useStreamingChat.ts（重寫 Hook）

完整的 SSE 解析狀態機，關鍵設計：

### SSE 解析器 — 正確追蹤 `event:` 行

```typescript
let currentEventType = 'message';
for (const line of lines) {
  if (line.startsWith('event: ')) {
    currentEventType = line.slice(7).trim();
    continue;
  }
  if (!line.startsWith('data: ')) continue;
  // ... 根據 currentEventType 分支處理
}
```

這是最常見的坑：許多實作只處理 `data:` 行而忽略 `event:` 行。

### 狀態分支

| SSE 事件 | 處理邏輯 |
|---|---|
| `event: status` | `setRAGInfo({ status, message })` |
| `event: sources` | `setRAGInfo({ sources, status: 'sources_ready' })` |
| `event: metadata` | 可延伸顯示 token 使用量 |
| `event: error` | `setState({ error, isStreaming: false })` |
| `data: {...}` | OpenAI delta → 更新 assistant message content |
| `data: [DONE]` | 設 `status: 'done'`，將 sources 持久化到 message |

### `<think>` 標籤解析

Hook 內建 `parseThinkingContent()` 函數，在 streaming 過程中即時分離 `<think>...</think>` 段落與最終答案，並追蹤思考時間（秒）供 `ThinkingPanel` 顯示。

***

## 交付物 3：rag_service_patch.py（後端補丁）

若 `RAGService` 目前的 `retrieve_with_events()` 是一次性返回而非逐步 yield，需加入此補丁方法：

```python
def retrieve_with_events(self, query: str) -> Generator[dict, None, None]:
    yield {"type": "status", "status": "searching_dense", "message": "🔍 語意向量檢索中 (FAISS)…"}
    dense_results = self._faiss_search(query, self.top_k)
    
    yield {"type": "status", "status": "searching_sparse", "message": "📚 關鍵詞稀疏檢索中 (BM25)…"}
    sparse_results = self._bm25_search(query, self.top_k)
    
    yield {"type": "status", "status": "reranking", "message": "⚖️ RRF 融合重排序中…"}
    merged = self._rrf_rerank(dense_results, sparse_results, self.rrf_k)
    final = self._filter_by_score(merged)
    
    result = RetrievalResult(final_results=final[:self.top_k])
    yield {"type": "status", "status": "sources_ready", "message": f"✅ 找到 {len(result.final_results)} 筆文獻"}
    yield {"type": "results", "data": result}
```

**重要**：每個 `yield` 必須在下一個耗時操作**之前**發出，不然 SSE 緩衝仍會被批量推送。`main.py` 的 `generate()` 協程目前已是 `async def`，但其中的 `for event in rag_service.retrieve_with_events(...)` 迴圈是**同步**的 — 這會阻塞 event loop。建議在 thread pool 中執行：

```python
# 改用 async generator 版本，或用 run_in_executor 包裝
loop = asyncio.get_event_loop()
events = await loop.run_in_executor(_thread_pool, list, rag_service.retrieve_with_events(query))
for event in events:
    ...
```

或者使用補丁檔中提供的 `retrieve_with_events_async()` 版本（真正的 async generator）。

***

## 整合步驟

### 1. 新增元件檔案

```
frontend/src/components/RAGStatusPanel.tsx   ← 新建
frontend/src/hooks/useStreamingChat.ts       ← 新建（或替換現有）
frontend/src/components/MessageItem/index.tsx ← 替換（用 MessageItem-updated.tsx）
```

### 2. 更新 MessageItem

原本的靜態顯示區塊：
```tsx
// 刪除這段
{['retrieving', 'searching_dense', ...].includes(ragInfo?.status || '') && (
  <div>📂 RAG 檢索當中</div>
)}
```

替換為：
```tsx
// 新增
import { RAGStatusPanel } from '@/components/RAGStatusPanel';

{ragInfo && ragInfo.status !== 'idle' && (
  <RAGStatusPanel ragInfo={ragInfo} isStreaming={isStreaming} />
)}
```

### 3. 更新呼叫端 (Chat Page)

```tsx
const { messages, ragInfo, isStreaming, thinking, sendMessage } = useStreamingChat('/api/stream');

// 在 MessageItem 中傳入 ragInfo
<MessageItem
  message={msg}
  isStreaming={isStreaming && msg.id === lastMsgId}
  thinking={thinking}
  ragInfo={isStreaming && msg.id === lastMsgId ? ragInfo : undefined}
/>
```

### 4. 後端 RAGService 補丁

將 `rag_service_patch.py` 中的 `retrieve_with_events` 方法加入 `src/main/python/services/rag_service.py`。確認方法名稱與 `main.py` 呼叫端一致。

***

## 效能考量

| 考量 | 建議 |
|---|---|
| FAISS/BM25 阻塞 event loop | 確保在 `run_in_executor` 中執行 |
| SSE 緩衝（Nginx/代理） | `X-Accel-Buffering: no` 已設定，正確 ✓ |
| React re-render 頻率 | `RAGStatusPanel` 已用 `memo()` 包裝，`ragInfo` 使用 `Partial<RAGInfo>` 更新避免 full object replace |
| 文獻卡片數量多時 | 使用 CSS animation delay stagger，不用 `setTimeout` 陣列，效能更好 |

***

## 與 Perplexity 設計對比

| 功能 | Perplexity | 本方案 |
|---|---|---|
| 即時步驟指示器 | ✅ "Searching web..." | ✅ FAISS → BM25 → RRF |
| 每步 spinner/checkmark | ✅ | ✅ |
| 來源片段預覽 | ✅ 卡片形式 | ✅ staggered 動畫卡片 |
| 完成後自動收合 | ✅ | ✅ 2.5s 後收合 |
| 可手動展開 | ✅ | ✅ 點擊 toggle |
| 相關性分數顯示 | ❌ | ✅ 右側百分比 |
| 思考面板整合 | N/A | ✅ 與 ThinkingPanel 並存 |