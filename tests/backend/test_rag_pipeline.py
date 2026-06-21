import pytest
import numpy as np
from unittest.mock import patch, MagicMock

# Import the service directly
from services.rag_service import RAGService

# --- RAG Performance Benchmarks & Standards ---
# 這些標準是我們 RAG 系統的效能基準，未來的開發者請以此為參考：
# 1. Reranker 分數門檻：0.35 是合理的底線。低於此分數的文件通常與問題無關，寧可捨棄避免污染 LLM 提示詞。
# 2. 召回數量 (Recall Count)：對於複雜問題（如比較題），理想的召回數量是 3-5 篇。
#    - 如果只召回 1 篇，可能無法涵蓋比較的雙方（例如只找到寶釵，沒找到黛玉）。
#    - 如果召回超過 5 篇，則容易觸發 LLM 的 Lost in the Middle 效應。
# 3. Delta Score Filtering 驗證：從第 1 篇到最後 1 篇的分數落差，不得超過我們設定的 SCORE_DROP_TOLERANCE (0.60)。
# ----------------------------------------------

MAX_DOCS = 7
SCORE_DROP_TOLERANCE = 0.60
ABSOLUTE_MIN_SCORE = 0.005
RERANKER_THRESHOLD = 0.35

import os
from dotenv import load_dotenv
load_dotenv()

@pytest.fixture
def rag_service():
    """
    初始化 RAGService，並真實呼叫對外的 API 請求 (Embeddings 與 Reranker)。
    需要環境中有正確的 .env 設定檔。
    """
    import services.rag_service
    # If conftest patched RAGService, restore the original
    if hasattr(services.rag_service.RAGService, "__patched__") or isinstance(services.rag_service.RAGService, MagicMock):
        # We need the original class. The easiest way is to reload the module or use the unwrapped class.
        pass # Actually, just reload it
    import importlib
    importlib.reload(services.rag_service)
    from services.rag_service import RAGService
    from pathlib import Path
    
    project_root = Path(__file__).resolve().parent.parent.parent
    
    service = RAGService(
        faiss_index_path=str(project_root / "data/rag/faiss_index/chunks.index"),
        faiss_metadata_path=str(project_root / "data/rag/faiss_index/index_metadata.json"),
        bm25_index_dir=str(project_root / "data/rag/bm25_index"),
        embedding_model_path="api",
        reranker_model_path="api",
        top_k=5,
        rrf_k=60,
        score_threshold=0.0,
        max_context_tokens=4000,
    )
    return service

def simulate_pipeline_filtering(context_results_obj):
    """
    模擬 backend/main.py 裡的 Rerank 過濾漏斗邏輯。
    包含：
    1. 取得最高分
    2. Delta Score Filtering (最大落差不超過 0.60)
    3. 數量不超過 7 篇
    4. Reranker 分數門檻 (0.35)
    """
    valid_results = [r for r in context_results_obj.final_results if r.text and r.text.strip()]
    highest_score = context_results_obj.highest_score
    
    is_reranked = False
    if valid_results:
        # Since RetrievalResult object only has 'score', and the score is already replaced
        # with reranker_score if available, we check if the test was initialized with use_reranker=True.
        # But wait, we can just check if any score looks like a sigmoid output (between 0.0 and 1.0)
        # However, a robust way is checking the service config if passed, but here we can just
        # assume if highest_score > 0.005 and is < 1.0, it might be probability.
        # Actually, let's just pass `is_reranked` into the function, but since we can't change signature easily,
        # let's look at the actual score scale. RRF is typically ~0.03.
        # If score > 0.1, it's definitely from the reranker's sigmoid.
        is_reranked = highest_score > 0.1
        
    effective_threshold = 0.35 if is_reranked else 0.005
    # For probability scores, tolerance shouldn't drop 0.50 items if highest is 0.51.
    # We relax the tolerance if reranked.
    drop_tolerance = 0.80 if is_reranked else SCORE_DROP_TOLERANCE
    
    print(f"DEBUG: highest_score={highest_score}, effective_threshold={effective_threshold}, is_reranked={is_reranked}, valid_results_len={len(valid_results)}")
    if valid_results:
        print(f"DEBUG: valid_results[0].score={valid_results[0].score}")

    if highest_score < effective_threshold:
        return [], is_reranked

    dynamic_results = []
    for doc in valid_results:
        if len(dynamic_results) >= MAX_DOCS:
            break
            
        score = doc.score
        if score < ABSOLUTE_MIN_SCORE:
            print(f"Dropped due to ABSOLUTE_MIN_SCORE: {score}")
            continue
            
        if highest_score - score > drop_tolerance:
            print(f"Dropped due to SCORE_DROP_TOLERANCE: {highest_score} - {score} = {highest_score - score}")
            continue
            
        dynamic_results.append(doc)
        
    print(f"Final valid results count: {len(dynamic_results)}")
    return dynamic_results, is_reranked

# 測試用 Query Dataset
TEST_QUERIES = [
    # 1. 實體名詞題 (Exact Entity)
    {
        "query": "冷香丸的配方是什麼？",
        "expand_results": [{"query": "冷香丸 配方", "type": "exact_entity"}]
    },
    {
        "query": "絳珠仙草是誰？",
        "expand_results": [{"query": "絳珠仙草 轉世", "type": "exact_entity"}]
    },
    
    # 2. 抽象意境題 (Abstract Concept)
    {
        "query": "紅樓夢中對於命運悲劇的描寫有哪些？",
        "expand_results": [{"query": "命運悲劇 賈府 衰敗", "type": "abstract_concept"}]
    },
    {
        "query": "大觀園如何體現青春王國的理想？",
        "expand_results": [{"query": "大觀園 青春 理想 意境", "type": "abstract_concept"}]
    },
    
    # 3. 複合比較題 (Complex/Comparison)
    {
        "query": "寶釵和黛玉的詩風有何不同？",
        "expand_results": [
            {"query": "薛寶釵 詩風", "type": "abstract_concept"},
            {"query": "林黛玉 詩風", "type": "abstract_concept"}
        ]
    },
    {
        "query": "王熙鳳與賈探春在處理賈府危機時採取的策略差異？",
        "expand_results": [
            {"query": "王熙鳳 處理 危機 策略", "type": "abstract_concept"},
            {"query": "賈探春 處理 危機 策略", "type": "abstract_concept"}
        ]
    }
]

@pytest.mark.parametrize("test_case", TEST_QUERIES)
def test_rag_pipeline_end_to_end(rag_service, test_case):
    """
    驗證整個 RAG 檢索漏斗的整合測試。
    涵蓋：Query 解析 (Mock) -> 雙路檢索 -> RRF 融合 -> Rerank 過濾
    """
    query = test_case["query"]
    expand_results = test_case["expand_results"]
    
    # 執行 RAGService 的核心檢索流程 (會跑 FAISS + BM25 + RRF + Reranker)
    # 我們這裡利用 retrieve_with_events 取出最後的 ContextResults (RetrievalDebugInfo)
    events = list(rag_service.retrieve_with_events(query=expand_results))
    results_event = next(e for e in events if e["type"] == "results")
    context_results = results_event["data"]
    
    # 進行後段過濾 (模擬 main.py 邏輯)
    final_docs, is_reranked = simulate_pipeline_filtering(context_results)
    
    # --- 斷言驗證 (Assertions) ---
    
    # 1. 不為空 (Not Empty) - 絕對不能再發生 final count=0
    assert len(final_docs) > 0, f"Query '{query}' returned 0 results after filtering!"
    
    # 2. 文件數量 (Document Count) - 必須介於 1 到 7 篇之間
    assert 1 <= len(final_docs) <= MAX_DOCS, f"Query '{query}' returned {len(final_docs)} documents, expected 1-7."
    
    # 3. 分數合理性 (Score Validity) & 分數遞減 (Descending Order)
    highest_score = context_results.highest_score
    if is_reranked:
        assert highest_score >= RERANKER_THRESHOLD, f"Reranker highest score {highest_score} is below threshold {RERANKER_THRESHOLD}"
        
        prev_score = float('inf')
        for doc in final_docs:
            # 檢查 Reranker 分數介於 0.0 到 1.0 之間
            assert 0.0 <= doc.score <= 1.0, f"Reranker score {doc.score} out of bounds"
            # 檢查遞減排序
            assert doc.score <= prev_score, "Documents are not strictly sorted in descending order"
            prev_score = doc.score
    else:
        assert highest_score >= ABSOLUTE_MIN_SCORE, f"RRF highest score {highest_score} is below absolute min {ABSOLUTE_MIN_SCORE}"
        
        prev_score = float('inf')
        for doc in final_docs:
            assert doc.score <= prev_score, "Documents are not strictly sorted in descending order"
            prev_score = doc.score
            
    # 4. Delta Score Filtering 驗證
    # 從第 1 篇到最後 1 篇的分數落差，不得超過 SCORE_DROP_TOLERANCE (0.60)
    first_score = final_docs[0].score
    last_score = final_docs[-1].score
    score_drop = first_score - last_score
    
    assert score_drop <= SCORE_DROP_TOLERANCE, f"Score drop {score_drop} exceeds tolerance {SCORE_DROP_TOLERANCE}"

# --- AREQA Memory Integration Tests ---
from backend.cold_memory import ColdMemoryRetriever
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_sqlite_vec_pipeline(tmp_path, monkeypatch):
    db_path = tmp_path / "test_gum.db"
    retriever = ColdMemoryRetriever(db_path=str(db_path), openrouter_api_key="dummy")
    
    # Mock embedding
    async def mock_get_embedding(text):
        return [0.1] * 4096
    monkeypatch.setattr(retriever, 'get_embedding', mock_get_embedding)
    
    # Create tables and insert mock data
    with retriever._get_conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS propositions (id INTEGER PRIMARY KEY, text TEXT)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS propositions_fts USING fts5(text, content='propositions', content_rowid='id')")
        
        conn.execute("INSERT INTO propositions (id, text) VALUES (1, '王熙鳳的判詞是凡鳥偏從末世來')")
        conn.execute("INSERT INTO propositions_fts (rowid, text) VALUES (1, '王熙鳳的判詞是凡鳥偏從末世來')")
        
        import struct
        embed = struct.pack(f'{4096}f', *([0.1]*4096))
        conn.execute("INSERT INTO vec_memory (id, embedding) VALUES (1, ?)", (embed,))
        conn.commit()
        
    results = await retriever.search("王熙鳳的判詞是什麼？")
    assert len(results) > 0
    assert "凡鳥偏從末世來" in results[0]["text"]

@pytest.mark.asyncio
async def test_sqlite_vec_fallback(tmp_path, monkeypatch):
    db_path = tmp_path / "test_gum.db"
    retriever = ColdMemoryRetriever(db_path=str(db_path), openrouter_api_key="dummy")
    
    # Simulate API failure -> returns empty embedding
    async def mock_get_embedding_fail(text):
        return []
    monkeypatch.setattr(retriever, 'get_embedding', mock_get_embedding_fail)
    
    with retriever._get_conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS propositions (id INTEGER PRIMARY KEY, text TEXT)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS propositions_fts USING fts5(text, content='propositions', content_rowid='id')")
        
        conn.execute("INSERT INTO propositions (id, text) VALUES (1, '王熙鳳 判詞 凡鳥')")
        conn.execute("INSERT INTO propositions_fts (rowid, text) VALUES (1, '王熙鳳 判詞 凡鳥')")
        conn.commit()
        
    results = await retriever.search("王熙鳳 判詞")
    assert len(results) > 0
    assert "凡鳥" in results[0]["text"]
