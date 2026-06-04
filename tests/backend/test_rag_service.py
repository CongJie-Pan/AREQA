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
