#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hybrid RAG Search Test (BGE-M3 + BM25)

This script tests the complete Hybrid RAG pipeline combining:
- BGE-M3 FAISS dense retrieval
- BM25 sparse retrieval
- RRF (Reciprocal Rank Fusion) for score combination

Usage:
    python scripts/rag/test_hybrid_rag.py
"""

import os
import json
import pickle
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass

# ============================================================================
# CRITICAL: Set cache directory BEFORE any imports
# ============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

os.environ['HF_HOME'] = str(MODEL_CACHE_DIR)
os.environ['TRANSFORMERS_CACHE'] = str(MODEL_CACHE_DIR)
os.environ['HF_HUB_CACHE'] = str(MODEL_CACHE_DIR)
os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(MODEL_CACHE_DIR)

# Paths
FAISS_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"
BM25_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "bm25_index"
CHUNKS_DIR = PROJECT_ROOT / "data" / "rag" / "chunks"

# ============================================================================
# Test Queries
# ============================================================================

TEST_QUERIES = [
    "林黛玉葬花吟",
    "金陵十二釵",
    "賈寶玉通靈寶玉",
    "王熙鳳協理寧國府",
    "劉姥姥進大觀園",
    "好了歌",
    "木石前盟",
    "金玉良緣",
    "大觀園",
    "秦可卿之死",
]

# ============================================================================
# Load Functions
# ============================================================================

def load_chunks() -> Dict[str, Dict]:
    """Load all chunks for text lookup."""
    chunks = {}
    for json_file in CHUNKS_DIR.glob("*_chunks.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for chunk in data:
                chunks[chunk['chunk_id']] = chunk
    return chunks


def load_bge_m3_model():
    """Load BGE-M3 model for embedding generation."""
    from FlagEmbedding import BGEM3FlagModel
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    return model


def load_faiss_index():
    """Load BGE-M3 FAISS index."""
    import faiss
    
    index_path = FAISS_INDEX_DIR / "chunks_bge_m3.index"
    mapping_path = FAISS_INDEX_DIR / "chunk_mapping_bge_m3.json"
    
    index = faiss.read_index(str(index_path))
    
    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    
    return index, mapping['chunk_ids']


def load_bm25_index():
    """Load BM25 index and reconstruct BM25Okapi object."""
    from rank_bm25 import BM25Okapi
    
    index_path = BM25_INDEX_DIR / "bm25_index.pkl"
    
    with open(index_path, 'rb') as f:
        index_data = pickle.load(f)
    
    # Reconstruct BM25 from tokenized corpus
    tokenized_docs = index_data['tokenized_docs']
    k1 = index_data['config'].get('k1', 1.5)
    b = index_data['config'].get('b', 0.4)
    
    bm25 = BM25Okapi(tokenized_docs, k1=k1, b=b)
    
    # Get chunk IDs from mapping
    chunk_ids = [index_data['chunk_id_mapping'][i] for i in range(len(tokenized_docs))]
    
    return bm25, chunk_ids


def tokenize_query(query: str) -> List[str]:
    """Simple N-gram tokenization for BM25."""
    tokens = []
    # Unigram
    tokens.extend(list(query))
    # Bigram
    for i in range(len(query) - 1):
        tokens.append(query[i:i+2])
    return tokens


# ============================================================================
# Search Functions
# ============================================================================

def search_faiss(query: str, model, index, chunk_ids: List[str], k: int = 10) -> List[Tuple[str, float]]:
    """Search using FAISS dense retrieval."""
    # Generate query embedding
    result = model.encode([query], return_dense=True, return_sparse=False)
    query_embedding = result['dense_vecs'][0].astype(np.float32).reshape(1, -1)
    
    # Search
    distances, indices = index.search(query_embedding, k)
    
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        results.append((chunk_ids[idx], float(dist)))
    
    return results


def search_bm25(query: str, bm25, chunk_ids: List[str], k: int = 10) -> List[Tuple[str, float]]:
    """Search using BM25 sparse retrieval."""
    tokens = tokenize_query(query)
    scores = bm25.get_scores(tokens)
    
    # Get top-k indices
    top_indices = np.argsort(scores)[::-1][:k]
    
    results = []
    for idx in top_indices:
        results.append((chunk_ids[idx], float(scores[idx])))
    
    return results


def rrf_fusion(faiss_results: List[Tuple[str, float]], 
               bm25_results: List[Tuple[str, float]], 
               k: int = 60,
               alpha: float = 0.6) -> List[Tuple[str, float]]:
    """
    Combine results using Reciprocal Rank Fusion (RRF).
    
    Args:
        faiss_results: (chunk_id, score) from FAISS
        bm25_results: (chunk_id, score) from BM25
        k: RRF constant
        alpha: weight for FAISS (1-alpha for BM25)
    
    Returns:
        Combined results sorted by RRF score
    """
    rrf_scores = {}
    
    # FAISS scores
    for rank, (chunk_id, _) in enumerate(faiss_results, 1):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + alpha * (1 / (k + rank))
    
    # BM25 scores
    for rank, (chunk_id, _) in enumerate(bm25_results, 1):
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0) + (1 - alpha) * (1 / (k + rank))
    
    # Sort by RRF score
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_results


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 70)
    print("  Hybrid RAG Search Test (BGE-M3 + BM25)")
    print("=" * 70)
    
    # Load components
    print("\n[1/4] Loading chunks...")
    chunks = load_chunks()
    print(f"  ✓ Loaded {len(chunks)} chunks")
    
    print("\n[2/4] Loading BGE-M3 model...")
    bge_model = load_bge_m3_model()
    print("  ✓ BGE-M3 loaded from project cache")
    
    print("\n[3/4] Loading FAISS index...")
    faiss_index, faiss_chunk_ids = load_faiss_index()
    print(f"  ✓ FAISS index loaded ({faiss_index.ntotal} vectors)")
    
    print("\n[4/4] Loading BM25 index...")
    bm25, bm25_chunk_ids = load_bm25_index()
    print(f"  ✓ BM25 index loaded")
    
    # Run searches
    print("\n" + "=" * 70)
    print("  Hybrid Search Results")
    print("=" * 70)
    
    for query in TEST_QUERIES:
        print(f"\n📝 Query: '{query}'")
        
        # FAISS search
        faiss_results = search_faiss(query, bge_model, faiss_index, faiss_chunk_ids, k=10)
        
        # BM25 search
        bm25_results = search_bm25(query, bm25, bm25_chunk_ids, k=10)
        
        # RRF fusion
        hybrid_results = rrf_fusion(faiss_results, bm25_results, k=60, alpha=0.6)
        
        print(f"\n   {'Method':<12} | {'Rank':<5} | {'Chunk ID':<30} | {'Preview':<40}")
        print(f"   {'-'*12}-+-{'-'*5}-+-{'-'*30}-+-{'-'*40}")
        
        # Show FAISS Top-1
        f_id, f_score = faiss_results[0]
        f_text = chunks.get(f_id, {}).get('text', '')[:35]
        print(f"   {'FAISS':<12} | {'#1':<5} | {f_id:<30} | {f_text}...")
        
        # Show BM25 Top-1
        b_id, b_score = bm25_results[0]
        b_text = chunks.get(b_id, {}).get('text', '')[:35]
        print(f"   {'BM25':<12} | {'#1':<5} | {b_id:<30} | {b_text}...")
        
        # Show Hybrid Top-3
        print(f"\n   🔗 Hybrid Top-3 (RRF α=0.6):")
        for i, (h_id, h_score) in enumerate(hybrid_results[:3], 1):
            h_text = chunks.get(h_id, {}).get('text', '')[:50]
            
            # Mark source
            in_faiss = any(h_id == r[0] for r in faiss_results[:5])
            in_bm25 = any(h_id == r[0] for r in bm25_results[:5])
            source = ""
            if in_faiss and in_bm25:
                source = "[F+B]"
            elif in_faiss:
                source = "[F]"
            elif in_bm25:
                source = "[B]"
            
            print(f"      {i}. {source:<5} [{h_id}] RRF={h_score:.4f}")
            print(f"         {h_text}...")
    
    print("\n" + "=" * 70)
    print("  Hybrid RAG Search Test Complete!")
    print("=" * 70)
    print("\n  Legend: [F]=FAISS, [B]=BM25, [F+B]=Both")


if __name__ == "__main__":
    main()
