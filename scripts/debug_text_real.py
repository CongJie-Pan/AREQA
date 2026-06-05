import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.main.python.services.rag_service import RAGService
import json

rag_service = RAGService(
    faiss_index_path="data/rag/faiss_index/chunks.index",
    faiss_metadata_path="data/rag/faiss_index/index_metadata.json",
    bm25_index_dir="data/rag/bm25_index",
    embedding_model_path="api",
    reranker_model_path="api",
    top_k=2,
    rrf_k=60,
    score_threshold=0.0
)
expand_results = [{'query': '冷香丸 配方', 'type': 'exact_entity'}]
for event in rag_service.retrieve_with_events(expand_results):
    if event["type"] == "results":
        res = event["data"]
        for i, item in enumerate(res.final_results):
            print(f"[{i}] score={item.score} len(text)={len(item.text)} type={type(item.text)}")
            if len(item.text) > 0:
                print("TEXT: ", item.text[:50])
