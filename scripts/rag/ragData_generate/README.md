# RAG Data Generation Scripts

此目錄包含 RA-DIT 訓練資料生成相關腳本，按功能分類組織。

## 目錄結構

```
ragData_generate/
├── generation/          # 資料生成腳本
│   ├── generate_negative_samples.py   # 生成 Negative Sampling
│   ├── generate_pure_qa.py            # 從 RAG 提取 Pure QA
│   ├── backfill_rag_context.py        # 為 QA 補充 RAG context
│   └── convert_to_radit_format.py     # 轉換為 RA-DIT 格式
│
├── validation/          # 驗證與分析腳本
│   ├── validate_radit_format.py       # 驗證 RA-DIT 格式
│   ├── validate_p3_t04_quality.py     # P3-T04 品質驗證
│   ├── audit_traceable_qa.py          # 可追溯 QA 審核
│   └── analyze_training_data.py       # 訓練資料分析
│
├── integration/         # 資料整合腳本
│   └── integrate_final_dataset.py     # 整合最終資料集
│
├── fix/                 # 修復與轉換腳本
│   ├── fix_token_overflow.py          # 修復 token 溢出
│   ├── fix_pure_qa_add_retrieval.py   # S4: Pure QA 補充檢索
│   └── fix_negative_reclassify.py     # S5: Negative 重分類
│
└── README.md            # 本說明文件
```

## 使用說明

### 生成資料 (generation/)

```bash
# 生成 Negative Sampling
python scripts/rag/ragData_generate/generation/generate_negative_samples.py

# 從 RAG 提取 Pure QA
python scripts/rag/ragData_generate/generation/generate_pure_qa.py
```

### 驗證資料 (validation/)

```bash
# 驗證 RA-DIT 格式
python scripts/rag/ragData_generate/validation/validate_radit_format.py

# 分析訓練資料分佈
python scripts/rag/ragData_generate/validation/analyze_training_data.py
```

### 整合資料 (integration/)

```bash
# 整合最終資料集
python scripts/rag/ragData_generate/integration/integrate_final_dataset.py
```

### 修復資料 (fix/)

```bash
# v2.1 修正: Pure QA 補充檢索
python scripts/rag/ragData_generate/fix/fix_pure_qa_add_retrieval.py

# v2.1 修正: Negative 重分類
python scripts/rag/ragData_generate/fix/fix_negative_reclassify.py
```

## 相關文件

- 實施計畫: `docs/Phase03_AboutLLM-Ft/phase03_t04/2026_02_07_v1/`
- 資料集規範: `docs/RA_DIT-ancient-chinese-qa-spec/`
- 輸出位置: `data/training/`

---
**最後更新**: 2026-02-07
