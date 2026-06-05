import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.main.python.services.rag_service import RAGService

def debug():
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
    query = "冷香丸的配方是什麼？"
    expand_results = [{'query': '冷香丸 配方', 'type': 'exact_entity'}]
    
    dense = rag_service._faiss_search(rag_service.encode_query(query), depth=2)
    print("DENSE [0] text length:", len(dense[0]['text']) if dense else 0)
    
    fused = rag_service._rrf_fusion(dense, [])
    print("FUSED [0] text length:", len(fused[0]['text']) if fused else 0)

if __name__ == "__main__":
    debug()
