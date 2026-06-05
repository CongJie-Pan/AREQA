"""
Direct test of LightweightReranker to identify failure point.
"""

import sys
import json
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "rag" / "evaluation"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("=" * 70)
print("DIRECT LIGHTWEIGHT RERANKER TEST")
print("=" * 70)

# Import after path setup
from bm25_reranker_eval import LightweightReranker, BM25Retriever

# Load chunks
CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"
with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
    chunks = json.load(f)

print(f"\n1. Loaded {len(chunks)} chunks")

# Test BM25 first
print("\n2. Testing BM25Retriever...")
try:
    bm25 = BM25Retriever(chunks)
    test_query = "賈寶玉"
    ids, scores, texts, latency = bm25.retrieve(test_query, top_k=5)
    print(f"   ✅ BM25 working: Retrieved {len(ids)} results")
    print(f"   Top result: {ids[0][:50]}...")
except Exception as e:
    print(f"   ❌ BM25 failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test Reranker
print("\n3. Testing LightweightReranker...")
try:
    reranker = LightweightReranker()
    reranker.load()
    print(f"   ✅ Reranker loaded successfully")
    
    # Test reranking
    print("\n4. Testing rerank()...")
    reranked_ids, reranked_scores, reranked_texts, latency = reranker.rerank(
        test_query, ids[:3], texts[:3], top_k=3
    )
    print(f"   ✅ Reranking successful!")
    print(f"   Reranked {len(reranked_ids)} results")
    print(f"   Latency: {latency:.2f}ms")
    print(f"   Top score: {reranked_scores[0] if reranked_scores else 'N/A'}")
    
    reranker.unload()
    
    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED!")
    print("=" * 70)
    print("BM25 and Reranker are both working correctly.")
    print("The issue must be in the evaluation loop or query generation.")
    print("=" * 70)
    
except Exception as e:
    print(f"\n❌ Reranker failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
