### Indexer (GPU/CPU 自動選擇)

自動偵測 GPU
`python scripts/rag/indexing/p1_t01_sikubert_indexer.py`

強制使用 CPU
`python scripts/rag/indexing/p1_t01_sikubert_indexer.py --cpu`

自訂 batch size
`python scripts/rag/indexing/p1_t01_sikubert_indexer.py --batch-size 64`