#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug Script: Analyze Allusion Query Hit/Miss Details

Purpose:
    Analyze why allusion queries are not hitting expected chunks after rewrite.
    Also diagnose RAM usage issues.

Usage:
    python scripts/rag/debug_allusion_queries.py
"""

import os
import sys
import json
import pickle
import numpy as np
from pathlib import Path

# Set paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface"

os.environ['HF_HOME'] = str(MODEL_CACHE_DIR)
os.environ['TRANSFORMERS_CACHE'] = str(MODEL_CACHE_DIR)

# Add src to path
src_path = PROJECT_ROOT / "src" / "main" / "python"
sys.path.insert(0, str(src_path))

FAISS_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"
BM25_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "bm25_index"
CHUNKS_DIR = PROJECT_ROOT / "data" / "rag" / "chunks"

# Allusion test queries
ALLUSION_QUERIES = [
    {
        "query": "金玉良緣",
        "expected": ["wiki_薛寶釵_001", "fact_epf_001"],
        "expansion_terms": ["金鎖", "通靈寶玉", "薛寶釵", "賈寶玉"]
    },
    {
        "query": "木石前盟",
        "expected": ["wiki_林黛玉_001", "wiki_賈寶玉_001"],
        "expansion_terms": ["神瑛侍者", "絳珠仙草", "林黛玉", "賈寶玉"]
    },
]


def load_chunks():
    """Load all chunks to analyze content."""
    chunks = {}
    for json_file in CHUNKS_DIR.glob("*_chunks.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for chunk in data:
                chunks[chunk['chunk_id']] = chunk
    print(f"✓ Loaded {len(chunks)} chunks")
    return chunks


def analyze_expected_chunks(chunks: dict, queries: list):
    """Analyze if expected chunks contain expansion terms."""
    print("\n" + "=" * 70)
    print("  EXPECTED CHUNK CONTENT ANALYSIS")
    print("=" * 70)
    
    for q in queries:
        print(f"\n📝 Query: {q['query']}")
        print(f"   Expected chunks: {q['expected']}")
        print(f"   Expansion terms: {q['expansion_terms']}")
        
        for chunk_id in q['expected']:
            # Try exact match or prefix match
            found_chunk = None
            for cid, chunk in chunks.items():
                if chunk_id in cid or cid.startswith(chunk_id.rsplit('_', 1)[0]):
                    found_chunk = (cid, chunk)
                    break
            
            if found_chunk:
                cid, chunk = found_chunk
                text = chunk.get('text', '')[:300]
                keywords = chunk.get('keywords', [])
                
                print(f"\n   📄 Chunk: {cid}")
                print(f"   Keywords: {keywords[:5]}...")
                print(f"   Text preview: {text[:150]}...")
                
                # Check if expansion terms appear in chunk
                matches = [term for term in q['expansion_terms'] if term in text]
                if matches:
                    print(f"   ✅ Found expansion terms in chunk: {matches}")
                else:
                    print(f"   ❌ NO expansion terms found in chunk!")
            else:
                print(f"\n   ⚠️ Chunk '{chunk_id}' NOT FOUND in dataset!")


def test_query_rewrite():
    """Test QueryRewriter on allusion queries."""
    print("\n" + "=" * 70)
    print("  QUERY REWRITE TEST")
    print("=" * 70)
    
    try:
        from rag.query.query_rewriter import QueryRewriter
        rewriter = QueryRewriter()
        print(f"✓ QueryRewriter loaded ({len(rewriter.allusion_map)} allusions)")
        
        for q in ALLUSION_QUERIES:
            original = q['query']
            
            # Rule-based rewrite
            rewritten_rules = rewriter.rewrite(original, use_llm=False)
            print(f"\n📝 Original: {original}")
            print(f"   Rule-based: {rewritten_rules}")
            
            # Check expansion
            added_terms = [t for t in q['expansion_terms'] if t in rewritten_rules and t not in original]
            print(f"   Added terms: {added_terms}")
            
    except Exception as e:
        print(f"❌ Failed to load QueryRewriter: {e}")


def search_with_debug(query: str, chunks: dict):
    """Perform search and show detailed results."""
    print(f"\n🔍 Searching for: {query}")
    
    # Load BM25
    try:
        from rank_bm25 import BM25Okapi
        index_path = BM25_INDEX_DIR / "bm25_index.pkl"
        with open(index_path, 'rb') as f:
            index_data = pickle.load(f)
        
        tokenized_docs = index_data['tokenized_docs']
        chunk_ids = [index_data['chunk_id_mapping'][i] for i in range(len(tokenized_docs))]
        bm25 = BM25Okapi(tokenized_docs, k1=1.5, b=0.4)
        
        # Tokenize query
        tokens = list(query)
        for i in range(len(query) - 1):
            tokens.append(query[i:i+2])
        
        scores = bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:5]
        
        print("   BM25 Top-5:")
        for i, idx in enumerate(top_indices):
            cid = chunk_ids[idx]
            text = chunks.get(cid, {}).get('text', '')[:50]
            print(f"   {i+1}. {cid} (score={scores[idx]:.3f}) - {text}...")
            
    except Exception as e:
        print(f"   BM25 error: {e}")


def main():
    print("\n" + "=" * 70)
    print("  ALLUSION QUERY DEBUG ANALYSIS")
    print("=" * 70)
    
    # Step 1: Load chunks
    chunks = load_chunks()
    
    # Step 2: Analyze expected chunks
    analyze_expected_chunks(chunks, ALLUSION_QUERIES)
    
    # Step 3: Test query rewrite
    test_query_rewrite()
    
    # Step 4: Search with rewritten queries
    print("\n" + "=" * 70)
    print("  SEARCH RESULTS COMPARISON")
    print("=" * 70)
    
    try:
        from rag.query.query_rewriter import QueryRewriter
        rewriter = QueryRewriter()
        
        for q in ALLUSION_QUERIES:
            original = q['query']
            rewritten = rewriter.rewrite(original, use_llm=False)
            
            print(f"\n{'='*50}")
            print(f"Query: {original} → {rewritten}")
            search_with_debug(rewritten, chunks)
            
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "=" * 70)
    print("  RAM USAGE NOTES")
    print("=" * 70)
    print("""
原因：評估腳本 RAM 使用量高是因為：

1. BGE-M3 模型 (~2GB)
   - FlagEmbedding 會載入完整模型到記憶體

2. SikuBERT 模型 (~400MB)
   - 評估腳本會同時載入多個模型

3. FAISS 索引 (2MB each)
   - 兩個索引同時在記憶體

4. BM25 索引 + tokenized docs

建議解決方案：
- 使用 --skip-siku 參數跳過 SikuBERT 測試
- 使用 lazy loading，只載入需要的模型
- 測試完成後手動觸發 garbage collection
""")
    
    print("\n✅ Debug analysis complete!")


if __name__ == "__main__":
    main()
