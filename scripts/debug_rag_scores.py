import os
import sys

# Ensure backend can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.main.python.services.rag_service import RAGService

def debug_scores():
    # Initialize RAGService just like in the tests
    rag_service = RAGService(
        faiss_index_path="data/rag/faiss_index/chunks.index",
        faiss_metadata_path="data/rag/faiss_index/index_metadata.json",
        bm25_index_dir="data/rag/bm25_index",
        embedding_model_path="api",
        reranker_model_path="api",
        top_k=7,
        rrf_k=60,
        score_threshold=0.35,
        max_context_tokens=4000
    )

    query = "冷香丸的配方是什麼？"
    expand_results = [{'query': '冷香丸 配方', 'type': 'exact_entity'}]
    
    print(f"\n--- DEBUGGING RAG SCORES FOR: '{query}' ---\n")
    
    # Run the exact retrieval function
    context_results = None
    for event in rag_service.retrieve_with_events(expand_results):
        if event.get("type") == "results":
            context_results = event.get("data")
            
    if not context_results:
        print("No results returned!")
        return
        
    print(f"Highest Score: {context_results.highest_score}")
    print(f"Total Results: {len(context_results.final_results)}")
    print("\nTop chunks before filtering:")
    
    for i, res in enumerate(context_results.final_results):
        print(f"[{i+1}] Score: {res.score:.6f} | Has Text? {'Yes' if res.text else 'No'} | Preview: {res.text[:30]}...")

if __name__ == "__main__":
    debug_scores()
