#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SikuBERT vs BGE-M3 Retrieval Comparison

This script compares retrieval quality between SikuBERT and BGE-M3 embeddings.

Usage:
    python scripts/rag/compare_retriever_models.py
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
FAISS_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"

# Test queries with expected relevant chunks
TEST_QUERIES = [
    {
        "query": "林黛玉葬花吟",
        "expected_keywords": ["葬花", "黛玉", "花謝花飛"]
    },
    {
        "query": "金陵十二釵",
        "expected_keywords": ["十二釵", "金陵", "判詞"]
    },
    {
        "query": "賈寶玉通靈寶玉",
        "expected_keywords": ["通靈", "寶玉", "神瑛"]
    },
    {
        "query": "王熙鳳協理寧國府",
        "expected_keywords": ["熙鳳", "寧國府", "協理"]
    },
    {
        "query": "劉姥姥進大觀園",
        "expected_keywords": ["劉姥姥", "大觀園"]
    }
]


def load_sikubert_model():
    """Load SikuBERT model for embedding generation."""
    import torch
    from transformers import AutoModel, AutoTokenizer
    
    model_name = "SIKU-BERT/sikubert"
    cache_dir = PROJECT_ROOT / "models" / "huggingface"
    
    tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=str(cache_dir))
    model = AutoModel.from_pretrained(model_name, cache_dir=str(cache_dir))
    model.eval()
    
    def generate_embedding(text: str) -> np.ndarray:
        inputs = tokenizer(text, return_tensors="pt", max_length=512, truncation=True, padding=True)
        with torch.no_grad():
            outputs = model(**inputs)
            embedding = outputs.last_hidden_state[:, 0, :].numpy()
        embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding.flatten().astype(np.float32)
    
    return generate_embedding


def load_bge_m3_model():
    """Load BGE-M3 model for embedding generation."""
    import os
    
    # Set cache directory BEFORE importing FlagEmbedding
    cache_dir = PROJECT_ROOT / "models" / "huggingface"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ['HF_HOME'] = str(cache_dir)
    os.environ['TRANSFORMERS_CACHE'] = str(cache_dir)
    os.environ['HF_HUB_CACHE'] = str(cache_dir)
    
    from FlagEmbedding import BGEM3FlagModel
    
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    
    def generate_embedding(text: str) -> np.ndarray:
        result = model.encode([text], return_dense=True, return_sparse=False)
        return result['dense_vecs'][0].astype(np.float32)
    
    return generate_embedding


def search_index(index_path: Path, mapping_path: Path, chunks_path: Path,
                 query_embedding: np.ndarray, k: int = 5) -> List[Dict]:
    """Search FAISS index and return results."""
    import faiss
    
    index = faiss.read_index(str(index_path))
    
    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    chunk_ids = mapping['chunk_ids']
    
    with open(chunks_path, 'r', encoding='utf-8') as f:
        chunks_data = json.load(f)
    chunks = chunks_data['chunks']
    
    query_embedding = query_embedding.reshape(1, -1)
    distances, indices = index.search(query_embedding, k)
    
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        results.append({
            "chunk_id": chunk_ids[idx],
            "score": float(dist),
            "text": chunks[idx]['text'][:80]
        })
    
    return results


def calculate_relevance_score(results: List[Dict], expected_keywords: List[str]) -> float:
    """Calculate how many expected keywords appear in top-5 results."""
    all_text = " ".join([r['text'] for r in results])
    matches = sum(1 for kw in expected_keywords if kw in all_text)
    return matches / len(expected_keywords) if expected_keywords else 0


def main():
    print("=" * 70)
    print("  SikuBERT vs BGE-M3 Retrieval Comparison")
    print("=" * 70)
    
    # Load models
    print("\n[1/4] Loading SikuBERT model...")
    sikubert_embed = load_sikubert_model()
    print("  ✓ SikuBERT loaded")
    
    print("\n[2/4] Loading BGE-M3 model...")
    bge_m3_embed = load_bge_m3_model()
    print("  ✓ BGE-M3 loaded")
    
    # Index paths
    siku_index = FAISS_INDEX_DIR / "chunks.index"
    siku_mapping = FAISS_INDEX_DIR / "chunk_mapping.json"
    siku_chunks = FAISS_INDEX_DIR / "indexed_chunks.json"
    
    bge_index = FAISS_INDEX_DIR / "chunks_bge_m3.index"
    bge_mapping = FAISS_INDEX_DIR / "chunk_mapping_bge_m3.json"
    bge_chunks = FAISS_INDEX_DIR / "indexed_chunks_bge_m3.json"
    
    # Check indexes exist
    if not siku_index.exists():
        print(f"  ⚠ SikuBERT index not found: {siku_index}")
        return
    if not bge_index.exists():
        print(f"  ⚠ BGE-M3 index not found: {bge_index}")
        return
    
    print("\n[3/4] Running comparison tests...")
    print("-" * 70)
    
    siku_scores = []
    bge_scores = []
    
    for test in TEST_QUERIES:
        query = test["query"]
        expected = test["expected_keywords"]
        
        print(f"\n📝 Query: '{query}'")
        print(f"   Expected keywords: {expected}")
        
        # SikuBERT
        siku_emb = sikubert_embed(query)
        siku_results = search_index(siku_index, siku_mapping, siku_chunks, siku_emb, k=5)
        siku_relevance = calculate_relevance_score(siku_results, expected)
        siku_scores.append(siku_relevance)
        
        # BGE-M3
        bge_emb = bge_m3_embed(query)
        bge_results = search_index(bge_index, bge_mapping, bge_chunks, bge_emb, k=5)
        bge_relevance = calculate_relevance_score(bge_results, expected)
        bge_scores.append(bge_relevance)
        
        print(f"\n   {'Model':<12} | {'Top-1 ID':<25} | {'Score':>8} | {'Relevance':>10}")
        print(f"   {'-'*12}-+-{'-'*25}-+-{'-'*8}-+-{'-'*10}")
        print(f"   {'SikuBERT':<12} | {siku_results[0]['chunk_id']:<25} | {siku_results[0]['score']:>8.4f} | {siku_relevance*100:>9.1f}%")
        print(f"   {'BGE-M3':<12} | {bge_results[0]['chunk_id']:<25} | {bge_results[0]['score']:>8.4f} | {bge_relevance*100:>9.1f}%")
        
        # Show top-3 for each
        print(f"\n   SikuBERT Top-3:")
        for i, r in enumerate(siku_results[:3], 1):
            print(f"     {i}. [{r['chunk_id']}] {r['text'][:50]}...")
        
        print(f"\n   BGE-M3 Top-3:")
        for i, r in enumerate(bge_results[:3], 1):
            print(f"     {i}. [{r['chunk_id']}] {r['text'][:50]}...")
    
    # Summary
    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    
    avg_siku = np.mean(siku_scores) * 100
    avg_bge = np.mean(bge_scores) * 100
    
    print(f"\n  Average Keyword Relevance:")
    print(f"    SikuBERT: {avg_siku:.1f}%")
    print(f"    BGE-M3:   {avg_bge:.1f}%")
    
    if avg_bge > avg_siku:
        print(f"\n  ✅ BGE-M3 outperforms SikuBERT by {avg_bge - avg_siku:.1f}%")
    elif avg_siku > avg_bge:
        print(f"\n  ⚠ SikuBERT outperforms BGE-M3 by {avg_siku - avg_bge:.1f}%")
    else:
        print(f"\n  ➡ Both models perform equally")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
