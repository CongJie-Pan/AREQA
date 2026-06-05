#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug Script: Analyze Character Query Hit/Miss Details

Purpose:
    Analyze why character (人物類) queries have 66.7% Hit@1.
    Similar to allusion debug, check if expected chunk IDs are correct.

Usage:
    python scripts/rag/debug_character_queries.py
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

CHUNKS_DIR = PROJECT_ROOT / "data" / "rag" / "chunks"
BM25_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "bm25_index"

# Character test queries from unified_retrieval_eval.py
CHARACTER_QUERIES = [
    {
        "query": "賈寶玉通靈寶玉",
        "expected": ["wiki_賈寶玉_001", "chapter_008"],
        "key_terms": ["賈寶玉", "通靈寶玉", "神瑛侍者"]
    },
    {
        "query": "林黛玉性格",
        "expected": ["wiki_林黛玉_001", "wiki_林黛玉_002"],
        "key_terms": ["林黛玉", "性格", "多愁善感"]
    },
    {
        "query": "薛寶釵金鎖",
        "expected": ["wiki_薛寶釵_001", "chapter_008"],
        "key_terms": ["薛寶釵", "金鎖", "通靈寶玉"]
    },
    {
        "query": "王熙鳳管家",
        "expected": ["wiki_王熙鳳_001", "chapter_013"],
        "key_terms": ["王熙鳳", "管家", "寧國府"]
    },
    {
        "query": "劉姥姥是誰",
        "expected": ["wiki_劉姥姥_001"],
        "key_terms": ["劉姥姥", "賈府", "鄉下"]
    },
    {
        "query": "賈府四春",
        "expected": ["wiki_賈元春_001", "wiki_賈迎春_001"],
        "key_terms": ["元春", "迎春", "探春", "惜春"]
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


def search_bm25(query: str, top_k: int = 5):
    """Perform BM25 search and return top-k results."""
    from rank_bm25 import BM25Okapi
    
    index_path = BM25_INDEX_DIR / "bm25_index.pkl"
    with open(index_path, 'rb') as f:
        index_data = pickle.load(f)
    
    tokenized_docs = index_data['tokenized_docs']
    chunk_ids = [index_data['chunk_id_mapping'][i] for i in range(len(tokenized_docs))]
    bm25 = BM25Okapi(tokenized_docs, k1=1.5, b=0.4)
    
    # Tokenize query (N-gram)
    tokens = list(query)
    for i in range(len(query) - 1):
        tokens.append(query[i:i+2])
    
    scores = bm25.get_scores(tokens)
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    return [(chunk_ids[idx], float(scores[idx])) for idx in top_indices]


def analyze_queries(chunks: dict):
    """Analyze each character query."""
    print("\n" + "=" * 70)
    print("  CHARACTER QUERY DEBUG ANALYSIS")
    print("=" * 70)
    
    hits = 0
    misses = 0
    
    for q in CHARACTER_QUERIES:
        query = q['query']
        expected = q['expected']
        
        print(f"\n{'='*60}")
        print(f"📝 Query: {query}")
        print(f"   Expected: {expected}")
        
        # BM25 search
        bm25_results = search_bm25(query)
        top1_id = bm25_results[0][0] if bm25_results else None
        
        # Check if hit
        hit = False
        for exp in expected:
            for res_id, _ in bm25_results[:1]:
                if exp in res_id or res_id.startswith(exp.split('_')[0] + '_' + exp.split('_')[1] if '_' in exp else exp):
                    hit = True
                    break
        
        if hit:
            hits += 1
            print(f"   ✅ HIT!")
        else:
            misses += 1
            print(f"   ❌ MISS!")
        
        # Show BM25 Top-5
        print(f"\n   BM25 Top-5:")
        for i, (cid, score) in enumerate(bm25_results):
            text = chunks.get(cid, {}).get('text', '')[:60]
            marker = "👈 EXPECTED" if any(exp in cid for exp in expected) else ""
            print(f"   {i+1}. {cid} (score={score:.2f}) {marker}")
            print(f"      {text}...")
        
        # Check expected chunks content
        print(f"\n   Expected Chunks Content:")
        for exp_id in expected:
            found = False
            for cid, chunk in chunks.items():
                if exp_id in cid:
                    found = True
                    text = chunk.get('text', '')[:100]
                    print(f"   📄 {cid}:")
                    print(f"      {text}...")
                    break
            if not found:
                print(f"   ⚠️ {exp_id} NOT FOUND!")
    
    # Summary
    total = hits + misses
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"   Hits: {hits}/{total} ({100*hits/total:.1f}%)")
    print(f"   Misses: {misses}/{total}")
    
    print("\n" + "=" * 70)
    print("  RECOMMENDATIONS")
    print("=" * 70)
    print("""
如果大部分 MISS 是因為：
1. BM25 Top-1 是正確的，但不在 expected 列表 → 修正 expected
2. 預期的 chunk 確實存在但排名較低 → 考慮 Query Rewrite 擴展人物別稱

建議修正方式：
- 將 BM25 Top-1 結果加入 expected 列表
- 加入人物別稱（如「鳳姐」→「王熙鳳」）到 allusion_synonyms.json
""")


def main():
    chunks = load_chunks()
    analyze_queries(chunks)
    print("\n✅ Debug analysis complete!")


if __name__ == "__main__":
    main()
