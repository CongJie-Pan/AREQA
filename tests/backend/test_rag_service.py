import pytest
from unittest.mock import patch, MagicMock

from services.rag_service import RAGService, RetrievalResult

@pytest.fixture
def mock_rag_service():
    with patch.object(RAGService, '_load_embedding_model'), \
         patch.object(RAGService, '_load_reranker_model'), \
         patch.object(RAGService, '_load_faiss_index'), \
         patch.object(RAGService, '_load_bm25_index'):
         
        service = RAGService(
            faiss_index_path="dummy.index",
            faiss_metadata_path="dummy.json",
            bm25_index_dir="dummy_dir",
            embedding_model_path="dummy_path",
            reranker_model_path="dummy_path",
            use_reranker=False
        )
        
        service._faiss_index = MagicMock()
        service._faiss_index.ntotal = 100
        service._bm25 = MagicMock()
        service._bm25.total_documents = 100
        service._available = True
        
        # Mock dependencies that need heavy lifting
        service._faiss_search = MagicMock(return_value=[])
        service._bm25_search = MagicMock(return_value=[])
        service.encode_query = MagicMock(return_value=[0.1, 0.2, 0.3])
        return service

def test_retrieve_with_events_list_of_queries(mock_rag_service):
    # Setup mock returns for dense and sparse search
    # Query 1
    dense_res_1 = [{"chunk_id": "c1", "score": 0.9, "text": "A", "metadata": {}}]
    sparse_res_1 = [{"chunk_id": "c2", "score": 10.0, "text": "B", "metadata": {}}]
    
    # Query 2
    dense_res_2 = [{"chunk_id": "c1", "score": 0.95, "text": "A", "metadata": {}}] # Higher score for c1
    sparse_res_2 = [{"chunk_id": "c3", "score": 5.0, "text": "C", "metadata": {}}]
    
    # Configure side effects for multiple calls
    mock_rag_service._faiss_search.side_effect = [dense_res_1, dense_res_2]
    mock_rag_service._bm25_search.side_effect = [sparse_res_1, sparse_res_2]
    
    # Mock RRF Fusion
    mock_rag_service._rrf_fusion = MagicMock(return_value=[
        {"chunk_id": "c1", "text": "A", "score": 0.95}, 
        {"chunk_id": "c2", "text": "B", "score": 10.0},
        {"chunk_id": "c3", "text": "C", "score": 5.0}
    ])

    queries = ["Original Query", "Expanded Query"]
    
    events = list(mock_rag_service.retrieve_with_events(queries))
    
    # Verify the sequence of events
    status_events = [e for e in events if e["type"] == "status"]
    assert len(status_events) == 3
    assert status_events[0]["status"] == "searching_dense"
    assert status_events[1]["status"] == "searching_sparse"
    assert status_events[2]["status"] == "reranking"
    
    result_event = next((e for e in events if e["type"] == "results"), None)
    assert result_event is not None
    
    debug_info = result_event["data"]
    
    # Assert _faiss_search and _bm25_search were called twice
    assert mock_rag_service._faiss_search.call_count == 2
    assert mock_rag_service._bm25_search.call_count == 2
    
    # Deduplication test: dense results should have c1 with score 0.95, not 0.9
    c1_dense = next((x for x in debug_info.dense_results if x["chunk_id"] == "c1"), None)
    assert c1_dense is not None
    assert c1_dense["score"] == 0.95

def test_retrieve_with_events_multi_hop_quota(mock_rag_service):
    """
    Test that Multi-Hop Iterative Retrieval enforces the sub_k quota
    and properly deduplicates the global pool.
    """
    # 2 sub-queries -> sub_k = max(20 // 2, 5) = 10 (since default top_k is 20)
    mock_rag_service.top_k = 20
    
    # Query 1
    dense_res_1 = [{"chunk_id": "c1", "score": 0.9, "text": "A", "metadata": {}}]
    sparse_res_1 = [{"chunk_id": "c2", "score": 10.0, "text": "B", "metadata": {}}]
    
    # Query 2
    dense_res_2 = [{"chunk_id": "c1", "score": 0.95, "text": "A", "metadata": {}}] 
    sparse_res_2 = [{"chunk_id": "c3", "score": 5.0, "text": "C", "metadata": {}}]
    
    mock_rag_service._faiss_search.side_effect = [dense_res_1, dense_res_2]
    mock_rag_service._bm25_search.side_effect = [sparse_res_1, sparse_res_2]
    
    # Mock RRF Fusion to return more than sub_k results for the first query to test quota
    # sub_k will be 10. We will return 12 items for query 1, and 3 items for query 2
    q1_rrf_results = [{"chunk_id": f"q1_c{i}", "rrf_score": 1.0/i, "text": f"Q1_{i}"} for i in range(1, 13)]
    q2_rrf_results = [{"chunk_id": f"q2_c{i}", "rrf_score": 1.0/i, "text": f"Q2_{i}"} for i in range(1, 4)]
    
    # Add a duplicate chunk in q2 that was in q1 to test global deduplication
    q2_rrf_results.append({"chunk_id": "q1_c1", "rrf_score": 2.0, "text": "Q1_1_updated"})
    
    mock_rag_service._rrf_fusion = MagicMock(side_effect=[q1_rrf_results, q2_rrf_results])
    
    queries = ["SubQuery 1", "SubQuery 2"]
    events = list(mock_rag_service.retrieve_with_events(queries))
    
    result_event = next((e for e in events if e["type"] == "results"), None)
    debug_info = result_event["data"]
    
    # Assert _rrf_fusion was called twice (once per query)
    assert mock_rag_service._rrf_fusion.call_count == 2
    
    # Assert that fused results are deduplicated and limited by sub_k
    # Q1 should contribute exactly 10 items (sub_k).
    # Q2 should contribute its 4 items.
    # Total before deduplication = 14 items.
    # q1_c1 is in both, so deduplication keeps 13 items.
    assert len(debug_info.fused_results) == 13
    
    # Verify deduplication kept the higher rrf_score for q1_c1
    c1_final = next(item for item in debug_info.fused_results if item["chunk_id"] == "q1_c1")
    assert c1_final["rrf_score"] == 2.0

def test_retrieve_with_events_dynamic_routing(mock_rag_service):
    """
    Test that dynamic routing applies correct alpha and beta weights
    based on the query type (exact_entity vs abstract_concept).
    """
    mock_rag_service.top_k = 20
    
    # 2 sub-queries with different types
    queries = [
        {"query": "冷香丸", "type": "exact_entity"},
        {"query": "命運悲劇", "type": "abstract_concept"}
    ]
    
    dense_res_1 = [{"chunk_id": "c1", "score": 0.9, "text": "A", "metadata": {}}]
    sparse_res_1 = [{"chunk_id": "c2", "score": 10.0, "text": "B", "metadata": {}}]
    
    dense_res_2 = [{"chunk_id": "c3", "score": 0.95, "text": "C", "metadata": {}}] 
    sparse_res_2 = [{"chunk_id": "c4", "score": 5.0, "text": "D", "metadata": {}}]
    
    mock_rag_service._faiss_search.side_effect = [dense_res_1, dense_res_2]
    mock_rag_service._bm25_search.side_effect = [sparse_res_1, sparse_res_2]
    
    # Mock _rrf_fusion to just return empty lists, we only care about call arguments
    mock_rag_service._rrf_fusion = MagicMock(return_value=[])
    
    events = list(mock_rag_service.retrieve_with_events(queries))
    
    assert mock_rag_service._rrf_fusion.call_count == 2
    
    # Call 1: exact_entity -> BM25 heavy (alpha=0.1, beta=0.9)
    call_1_args, call_1_kwargs = mock_rag_service._rrf_fusion.call_args_list[0]
    assert call_1_args[0] == dense_res_1
    assert call_1_args[1] == sparse_res_1
    assert call_1_kwargs.get("alpha") == 0.1
    assert call_1_kwargs.get("beta") == 0.9
    
    # Call 2: abstract_concept -> Dense heavy (alpha=0.8, beta=0.2)
    call_2_args, call_2_kwargs = mock_rag_service._rrf_fusion.call_args_list[1]
    assert call_2_args[0] == dense_res_2
    assert call_2_args[1] == sparse_res_2
    assert call_2_kwargs.get("alpha") == 0.8
    assert call_2_kwargs.get("beta") == 0.2
