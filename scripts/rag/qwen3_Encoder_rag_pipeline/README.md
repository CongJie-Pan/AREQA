# Qwen3 Encoder RAG Pipeline

本資料夾包含了基於 `Qwen/Qwen2.5-14B-Instruct` 進行 Contextual Chunking，並利用 `Qwen/Qwen2.5-32B-Instruct` (或同等模型) 與自訂的 Pooling 策略建立知識庫庫索引的完整 RAG 處理流程腳本。

## 核心流程

整體 Pipeline 包含以下 4 個主要步驟：

1. **Step 1: Hybrid Chunking (`chunking/run_hybrid_batch.py`)**  
   進行文件切分。結合了傳統正則表達式、RecursiveCharacterTextSplitter，並調用 LLM 增加「Contextual 脈絡前綴」與關鍵字提取。

2. **Step 1.5: Quality Gate Verification (`chunking/verify_llm_chunking.py`)**  
   針對切分好的 Chunks 進行多維度品質把關，透過 Rich 套件實時顯示：Fidelity (還原度)、Artifacts (人工痕跡)、Length Distribution (長度分佈) 等驗證指標。

3. **Step 2: Rebuild Index (`rebuild_index_qwen3.py`)**  
   使用 Qwen3-Embedding 搭配 **Last Token Pooling** 策略進行文本向量化，並將結果建立為 FAISS Dense Index 以及保留 BM25 所需的語料。

4. **Step 3: Retrieval Evaluation (`qwen3_retrieval_evaluation.py`)**  
   針對重新建構的向量索引與 BM25 進行混合檢索檢驗，並透過 Cross-Encoder (`Qwen3-Reranker-0.6B`) 進行重排序，驗證 Retrieval 階段的準確率 (如 Pass@10)。

---

## 如何使用主控腳本 (Master Pipeline)

這四個步驟已經由 `qwen3_rag_chunking_indexing_pipeline.py` 進行了自動化串接。

### 基本指令 (執行完整流程)

預設情況下，執行此腳本會依序完成 `Step 1 -> 1.5 -> 2 -> 3`：

```powershell
python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py
```

### 測試模式 ( `--limit`)

如果您只想先以少量的資料進行測試以節省時間與 API 成本，可以使用 `--limit` 參數（例如僅處理前 10 筆）：

```powershell
python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --limit 10
```

### 功能模式切換 ( `--mode`)

您可以使用 `--mode` 參數選擇只跑特定的單一步驟或部分流程，這在進行調試 (Debugging) 或是遭遇中斷後需要接續執行時非常有用：

1. **單純 Step 1 模式** (只進行 Hybrid Chunking)
   ```powershell
   python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 1
   ```
2. **單純 Step 1.5 模式** (只進行 Quality Gate)
   ```powershell
   python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 1.5
   ```
3. **單純 Step 2 模式** (只進行 Rebuild Index)
   ```powershell
   python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 2
   ```
4. **單純 Step 3 模式** (只進行 Retrieval Evaluation)
   ```powershell
   python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 3
   ```
5. **Step 1 到 1.5 模式** (Chunking + Quality Gate)
   ```powershell
   python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 1-1.5
   ```
6. **Step 1 到 2 模式** (Chunking + Quality Gate + Rebuild Index)
   ```powershell
   python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 1-2
   ```
7. **Step 2 到 3 模式** (跳過切塊，只直接做 Index 建構與評估)
   ```powershell
   python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 2-3
   ```

### 強制重新執行機制 ( `--retry`)

腳本底層（例如 Step 1）原生具備 `JSONL Checkpoint` 斷點接續功能。也就是說，當程序意外中斷時，再次執行主程式即可自動跳過已完成的檔案，從斷線點繼續處理。

若您需要**強制清除所有歷史進度並從頭開始處理**，請加上 `--retry` 旗標參數。這將會刪除既有的 checkpoint 與輸出檔案，完全重新啟動處理流程：

```powershell
python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --mode 1-1.5 --retry
```

清空所有的進度並完整重新執行整個流程（包含完整的 Step 1 到 Step 3）
```powershell
python scripts\rag\qwen3_Encoder_rag_pipeline\qwen3_rag_chunking_indexing_pipeline.py --retry
```

*(註：`--mode`, `--limit`, `--retry` 可以配合使用)*

---

## 依賴需求

- 必須在專案根目錄下有正確設置的 `.env` 檔案，且包含有效的 `OPENROUTER_API_KEY` (將會在前置檢查中自動檢驗)。
- 輸入來源必須存在於 `data/processed/GAOKAO_chinese` (或相關文件定義路徑) 內。