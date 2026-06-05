# RAG 檢索評測系統更新說明

**更新日期**: 2026-02-02  
**目的**: 統一評測標準，確保所有腳本遵循相同的設計原則

---

## 📋 更新概述

根據 `qwen3_retrieval_evaluation.py` 的設計標準，更新了兩個新評測腳本：
1. **bm25_reranker_eval.py** - BM25 + Reranker 評測
2. **faiss_retrieval_eval.py** - FAISS 語義檢索評測

---

## 🎯 統一的評測設計 (來自 qwen3_retrieval_evaluation.py)

### 1. **Query 類型分類** (3種核心類型)

| Query Type | 定義 | 範例 | 預期精度 |
|------------|------|------|----------|
| **keyword** | 直接使用關鍵詞 | "賈寶玉 林黛玉" | 最高 (直接匹配) |
| **summary** | 使用摘要作為查詢 | "描述賈寶玉與林黛玉的愛情故事" | 中等 (自然語言) |
| **semantic** | 語義問題格式 | "什麼是賈寶玉？" / "賈寶玉林黛玉的關係" | 低-中 (語義理解) |

### 2. **難度分級** (Difficulty Levels)

- **Easy**: keyword 查詢 (直接關鍵詞)
- **Medium**: summary 查詢 (自然語言摘要)
- **Hard**: semantic 查詢 (語義問題) 或 LLM 改寫

### 3. **評測指標** (Metrics)

- **MRR** (Mean Reciprocal Rank) - 平均倒數排名
- **Hit@K** (K=1, 5, 10, 20) - Top-K 命中率
- **Latency** (avg, p95) - 延遲統計

### 4. **分層分析** (Stratified Analysis)

✅ **by_difficulty**: 按難度分析 (easy, medium, hard)  
✅ **by_source_type**: 按來源分析 (經典, 紅樓夢, 考試, etc.)  
✅ **by_query_type**: 按查詢類型分析 (keyword, summary, semantic)

---

## 🔄 兩個新腳本的實現

### **bm25_reranker_eval.py** (BM25 + Neural Reranker)

**策略**:
1. `bm25_reranker`: BM25 檢索 → Reranker 重排
2. `full_pipeline`: Query Rewriting → 多查詢 BM25 → Reranker

**特點**:
- ✅ 關鍵詞匹配 (精確字符匹配)
- ✅ 神經重排序 (Qwen3-Reranker)
- ✅ Query 擴展 (LLM 改寫)

**Query 生成**:
```python
if difficulty == "easy":
    query_type = "keyword"  # 直接關鍵詞
elif difficulty == "medium":
    query_type = "summary"  # 摘要查詢
elif difficulty == "hard":
    query_type = "semantic"  # 語義問題 (匹配 qwen3 設計)
```

---

### **faiss_retrieval_eval.py** (FAISS Semantic Search)

**策略**:
1. `faiss_only`: 純 FAISS 向量檢索
2. `faiss_hybrid`: FAISS + BM25 混合評分
3. `faiss_query_expansion`: Query 擴展 + FAISS

**特點**:
- ✅ 語義向量搜索 (Qwen3-Embedding)
- ✅ 混合檢索 (FAISS 0.7 + BM25 0.3)
- ✅ 多查詢擴展

**Query 生成**:
```python
# 完全相同的邏輯
if difficulty == "easy":
    query_type = "keyword"
elif difficulty == "medium":
    query_type = "summary"
elif difficulty == "hard":
    query_type = "semantic"  # 統一使用 semantic
```

---

## 📊 評測報告格式 (統一化)

兩個腳本現在都生成相同格式的報告：

```json
{
  "metrics": {
    "strategy_name": {
      "overall": {
        "mrr": 0.xxx,
        "hit@1": 0.xxx,
        "hit@5": 0.xxx,
        "hit@10": 0.xxx,
        "hit@20": 0.xxx,
        "avg_latency_ms": xxx.x,
        "p95_latency_ms": xxx.x
      },
      "by_difficulty": {
        "easy": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx},
        "medium": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx},
        "hard": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx}
      },
      "by_source_type": {
        "經典": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx},
        "紅樓夢": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx},
        ...
      },
      "by_query_type": {
        "keyword": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx},
        "summary": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx},
        "semantic": {"mrr": 0.xxx, "hit@10": 0.xxx, "count": xx}
      }
    }
  }
}
```

---

## 🎓 設計原則的體現

### 來自 qwen3_retrieval_evaluation.py 的核心設計：

1. **✅ Stratified Sampling by Source Type**
   - 按來源類型分層抽樣 (經典、紅樓夢、考試等)
   - 確保各類型數據都被評測

2. **✅ Query Type Classification**
   - keyword, summary, semantic 三種核心類型
   - 對應不同的檢索難度

3. **✅ Domain-Specific Considerations**
   - 古典中文文本特性
   - 字符級 vs 詞級匹配
   - 繁簡體處理

4. **✅ Comprehensive Metrics**
   - MRR, Hit@K, Latency
   - 按難度、來源、查詢類型分層分析

---

## 🚀 運行方式

### 單獨運行
```powershell
# BM25 + Reranker 評測
python scripts/rag/evaluation/bm25_reranker_eval.py

# FAISS 語義檢索評測
python scripts/rag/evaluation/faiss_retrieval_eval.py
```

### 統一對比運行
```powershell
# 一次運行兩個評測並生成對比報告
python scripts/rag/evaluation/run_retrieval_comparison.py
```

---

## 📈 預期評測結果

### BM25 + Reranker
- **Keyword 查詢**: Hit@10 預期 >80% (精確匹配優勢)
- **Summary 查詢**: Hit@10 預期 40-60% (自然語言)
- **Semantic 查詢**: Hit@10 預期 30-50% (依賴 Reranker)

### FAISS Semantic Search
- **Keyword 查詢**: Hit@10 預期 60-70% (可能不如 BM25)
- **Summary 查詢**: Hit@10 預期 50-70% (語義優勢)
- **Semantic 查詢**: Hit@10 預期 50-65% (最強場景)

---

## ✅ 更新檢查清單

- [x] Query 類型統一為 keyword, summary, semantic
- [x] 難度分級統一為 easy, medium, hard
- [x] 添加 by_query_type 分析維度
- [x] 語義問題格式統一 ("什麼是X", "X的含義", "X和Y的關係")
- [x] 評測指標格式統一 (MRR, Hit@K, Latency)
- [x] 分層分析統一 (by_difficulty, by_source_type, by_query_type)

---

**總結**: 兩個新腳本現在完全遵循 `qwen3_retrieval_evaluation.py` 的設計標準，確保評測結果可比較且有意義。
