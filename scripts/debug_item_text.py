import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.main.python.services.rag_service import RAGService
service = RAGService(
    faiss_index_path="data/rag/faiss_index/chunks.index",
    faiss_metadata_path="data/rag/faiss_index/index_metadata.json",
    bm25_index_dir="data/rag/bm25_index",
    embedding_model_path="api",
    reranker_model_path="api",
    top_k=5, rrf_k=60, score_threshold=0.0
)
import json
print("Metadata index 0 text length:", len(service._faiss_metadata[0].get("text", "")))
print("Metadata index 0 page_content length:", len(service._faiss_metadata[0].get("page_content", "")))
