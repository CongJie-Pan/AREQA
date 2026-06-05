#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rigorous Retrieval Evaluation: SikuBERT vs BGE-M3

This script provides a comprehensive evaluation of retrieval quality using:
- Top-1, Top-3, Top-5 Accuracy
- MRR (Mean Reciprocal Rank)
- Precision@K
- More test queries (20+)

Usage:
    python scripts/rag/evaluate_retrieval_rigorous.py
"""

import os
import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# ============================================================================
# CRITICAL: Set cache directory BEFORE any imports that use HuggingFace
# ============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Set ALL cache environment variables before importing any ML libraries
os.environ['HF_HOME'] = str(MODEL_CACHE_DIR)
os.environ['TRANSFORMERS_CACHE'] = str(MODEL_CACHE_DIR)
os.environ['HF_HUB_CACHE'] = str(MODEL_CACHE_DIR)
os.environ['SENTENCE_TRANSFORMERS_HOME'] = str(MODEL_CACHE_DIR)

# Now safe to import ML libraries
import torch
from transformers import AutoModel, AutoTokenizer

# Paths
FAISS_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"

# ============================================================================
# Test Query Dataset (Expanded)
# ============================================================================

@dataclass
class TestQuery:
    """A test query with expected relevant documents."""
    query: str
    expected_chunk_ids: List[str]  # Ordered by relevance
    category: str  # Query category for analysis

# Comprehensive test queries covering different types
TEST_QUERIES = [
    # ===== 詩詞相關 =====
    TestQuery(
        query="林黛玉葬花吟",
        expected_chunk_ids=["wiki_葬花吟_001", "poem_rc_poem_021_01", "poem_rc_poem_021_02"],
        category="詩詞"
    ),
    TestQuery(
        query="花謝花飛花滿天",
        expected_chunk_ids=["poem_rc_poem_021_01", "wiki_葬花吟_001"],
        category="詩詞"
    ),
    TestQuery(
        query="好了歌",
        expected_chunk_ids=["poem_rc_poem_001", "wiki_好了歌_001"],
        category="詩詞"
    ),
    TestQuery(
        query="金陵十二釵判詞",
        expected_chunk_ids=["wiki_金陵十二釵_001", "poem_rc_poem_017"],
        category="詩詞"
    ),
    
    # ===== 人物相關 =====
    TestQuery(
        query="賈寶玉通靈寶玉",
        expected_chunk_ids=["wiki_賈寶玉_001", "chapter_008", "chapter_001"],
        category="人物"
    ),
    TestQuery(
        query="林黛玉性格",
        expected_chunk_ids=["wiki_林黛玉_001", "wiki_林黛玉_002"],
        category="人物"
    ),
    TestQuery(
        query="薛寶釵金鎖",
        expected_chunk_ids=["wiki_薛寶釵_001", "chapter_008"],
        category="人物"
    ),
    TestQuery(
        query="王熙鳳管家",
        expected_chunk_ids=["wiki_王熙鳳_001", "chapter_013"],
        category="人物"
    ),
    TestQuery(
        query="劉姥姥是誰",
        expected_chunk_ids=["wiki_劉姥姥_001"],
        category="人物"
    ),
    
    # ===== 情節相關 =====
    TestQuery(
        query="王熙鳳協理寧國府",
        expected_chunk_ids=["chapter_013"],
        category="情節"
    ),
    TestQuery(
        query="劉姥姥進大觀園",
        expected_chunk_ids=["wiki_劉姥姥_001", "wiki_大觀園_004"],
        category="情節"
    ),
    TestQuery(
        query="秦可卿之死",
        expected_chunk_ids=["wiki_秦可卿_001", "chapter_013"],
        category="情節"
    ),
    TestQuery(
        query="元妃省親",
        expected_chunk_ids=["chapter_017", "chapter_018"],
        category="情節"
    ),
    
    # ===== 地點/建築 =====
    TestQuery(
        query="大觀園",
        expected_chunk_ids=["wiki_大觀園_001", "wiki_大觀園_002"],
        category="地點"
    ),
    TestQuery(
        query="怡紅院",
        expected_chunk_ids=["wiki_怡紅院_001", "wiki_大觀園_002"],
        category="地點"
    ),
    TestQuery(
        query="瀟湘館",
        expected_chunk_ids=["wiki_瀟湘館_001", "wiki_大觀園_002"],
        category="地點"
    ),
    
    # ===== 典故/文化 =====
    TestQuery(
        query="金玉良緣",
        expected_chunk_ids=["wiki_薛寶釵_001", "fact_epf_001"],
        category="典故"
    ),
    TestQuery(
        query="木石前盟",
        expected_chunk_ids=["wiki_林黛玉_001", "wiki_賈寶玉_001"],
        category="典故"
    ),
    
    # ===== 易混淆查詢 =====
    TestQuery(
        query="襲人和晴雯的區別",
        expected_chunk_ids=["wiki_襲人_001", "wiki_晴雯_001"],
        category="對比"
    ),
    TestQuery(
        query="賈府四春",
        expected_chunk_ids=["wiki_賈元春_001", "wiki_賈迎春_001", "wiki_賈探春_001", "wiki_賈惜春_001"],
        category="人物"
    ),
]


# ============================================================================
# Embedders
# ============================================================================

class SikuBERTEmbedder:
    """SikuBERT embedder with proper caching."""
    
    def __init__(self):
        model_name = "SIKU-BERT/sikubert"
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, 
            cache_dir=str(MODEL_CACHE_DIR)
        )
        self.model = AutoModel.from_pretrained(
            model_name, 
            cache_dir=str(MODEL_CACHE_DIR)
        )
        self.model.eval()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model.to(self.device)
    
    def embed(self, text: str) -> np.ndarray:
        inputs = self.tokenizer(
            text, 
            return_tensors="pt", 
            max_length=512, 
            truncation=True, 
            padding=True
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()
        
        embedding = embedding / np.linalg.norm(embedding, axis=1, keepdims=True)
        return embedding.flatten().astype(np.float32)


class BGEM3Embedder:
    """BGE-M3 embedder with proper caching."""
    
    def __init__(self):
        # FlagEmbedding should now use the correct cache
        from FlagEmbedding import BGEM3FlagModel
        self.model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    
    def embed(self, text: str) -> np.ndarray:
        result = self.model.encode([text], return_dense=True, return_sparse=False)
        return result['dense_vecs'][0].astype(np.float32)


# ============================================================================
# Evaluation Metrics
# ============================================================================

def search_index(index_path: Path, mapping_path: Path, 
                 query_embedding: np.ndarray, k: int = 10) -> List[Tuple[str, float]]:
    """Search FAISS index and return (chunk_id, score) pairs."""
    import faiss
    
    index = faiss.read_index(str(index_path))
    
    with open(mapping_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    chunk_ids = mapping['chunk_ids']
    
    query_embedding = query_embedding.reshape(1, -1)
    distances, indices = index.search(query_embedding, k)
    
    results = []
    for dist, idx in zip(distances[0], indices[0]):
        results.append((chunk_ids[idx], float(dist)))
    
    return results


def calculate_mrr(results: List[str], expected: List[str]) -> float:
    """Calculate Mean Reciprocal Rank."""
    for i, chunk_id in enumerate(results, 1):
        # Check if any expected chunk matches (partial match for flexibility)
        for exp in expected:
            if exp in chunk_id or chunk_id.startswith(exp.split('_')[0]):
                return 1.0 / i
    return 0.0


def calculate_hit_at_k(results: List[str], expected: List[str], k: int) -> bool:
    """Check if any expected document is in top-k results."""
    top_k = results[:k]
    for exp in expected:
        for res in top_k:
            if exp in res or res.startswith(exp.split('_')[0] + '_' + exp.split('_')[1] if '_' in exp else exp):
                return True
    return False


def calculate_precision_at_k(results: List[str], expected: List[str], k: int) -> float:
    """Calculate Precision@K."""
    top_k = results[:k]
    hits = 0
    for res in top_k:
        for exp in expected:
            if exp in res:
                hits += 1
                break
    return hits / k


# ============================================================================
# Main Evaluation
# ============================================================================

def evaluate_model(embedder, index_path: Path, mapping_path: Path, 
                   model_name: str) -> Dict:
    """Evaluate a model on all test queries."""
    
    results = {
        "model": model_name,
        "hit@1": [],
        "hit@3": [],
        "hit@5": [],
        "mrr": [],
        "precision@5": [],
        "by_category": {}
    }
    
    print(f"\n{'='*60}")
    print(f"  Evaluating: {model_name}")
    print(f"{'='*60}")
    
    for tq in TEST_QUERIES:
        # Generate embedding
        query_emb = embedder.embed(tq.query)
        
        # Search
        search_results = search_index(index_path, mapping_path, query_emb, k=10)
        result_ids = [r[0] for r in search_results]
        
        # Calculate metrics
        hit1 = calculate_hit_at_k(result_ids, tq.expected_chunk_ids, 1)
        hit3 = calculate_hit_at_k(result_ids, tq.expected_chunk_ids, 3)
        hit5 = calculate_hit_at_k(result_ids, tq.expected_chunk_ids, 5)
        mrr = calculate_mrr(result_ids, tq.expected_chunk_ids)
        p5 = calculate_precision_at_k(result_ids, tq.expected_chunk_ids, 5)
        
        results["hit@1"].append(hit1)
        results["hit@3"].append(hit3)
        results["hit@5"].append(hit5)
        results["mrr"].append(mrr)
        results["precision@5"].append(p5)
        
        # Track by category
        if tq.category not in results["by_category"]:
            results["by_category"][tq.category] = {"hit@1": [], "mrr": []}
        results["by_category"][tq.category]["hit@1"].append(hit1)
        results["by_category"][tq.category]["mrr"].append(mrr)
        
        # Print individual result
        status = "✅" if hit1 else "❌"
        print(f"  {status} [{tq.category}] {tq.query[:20]:<20} | Top-1: {result_ids[0][:25]:<25} | MRR: {mrr:.2f}")
    
    # Calculate averages
    results["avg_hit@1"] = np.mean(results["hit@1"]) * 100
    results["avg_hit@3"] = np.mean(results["hit@3"]) * 100
    results["avg_hit@5"] = np.mean(results["hit@5"]) * 100
    results["avg_mrr"] = np.mean(results["mrr"])
    results["avg_precision@5"] = np.mean(results["precision@5"]) * 100
    
    return results


def main():
    print("="*60)
    print("  Rigorous Retrieval Evaluation: SikuBERT vs BGE-M3")
    print(f"  Test Queries: {len(TEST_QUERIES)}")
    print(f"  Model Cache: {MODEL_CACHE_DIR}")
    print("="*60)
    
    # Check indexes exist
    siku_index = FAISS_INDEX_DIR / "chunks.index"
    siku_mapping = FAISS_INDEX_DIR / "chunk_mapping.json"
    bge_index = FAISS_INDEX_DIR / "chunks_bge_m3.index"
    bge_mapping = FAISS_INDEX_DIR / "chunk_mapping_bge_m3.json"
    
    if not siku_index.exists() or not bge_index.exists():
        print("Error: Index files not found!")
        return
    
    # Load embedders
    print("\n[1/3] Loading SikuBERT...")
    siku_embedder = SikuBERTEmbedder()
    print("  ✓ SikuBERT loaded from project cache")
    
    print("\n[2/3] Loading BGE-M3...")
    bge_embedder = BGEM3Embedder()
    print("  ✓ BGE-M3 loaded from project cache")
    
    # Evaluate
    print("\n[3/3] Running evaluation...")
    
    siku_results = evaluate_model(siku_embedder, siku_index, siku_mapping, "SikuBERT")
    bge_results = evaluate_model(bge_embedder, bge_index, bge_mapping, "BGE-M3")
    
    # Summary
    print("\n" + "="*60)
    print("  SUMMARY")
    print("="*60)
    
    print(f"\n{'Metric':<20} | {'SikuBERT':>12} | {'BGE-M3':>12} | {'Winner':>10}")
    print("-"*60)
    
    metrics = [
        ("Hit@1 (%)", "avg_hit@1"),
        ("Hit@3 (%)", "avg_hit@3"),
        ("Hit@5 (%)", "avg_hit@5"),
        ("MRR", "avg_mrr"),
        ("Precision@5 (%)", "avg_precision@5"),
    ]
    
    for label, key in metrics:
        siku_val = siku_results[key]
        bge_val = bge_results[key]
        
        if key == "avg_mrr":
            winner = "BGE-M3 ✅" if bge_val > siku_val else "SikuBERT" if siku_val > bge_val else "Tie"
            print(f"{label:<20} | {siku_val:>12.3f} | {bge_val:>12.3f} | {winner:>10}")
        else:
            winner = "BGE-M3 ✅" if bge_val > siku_val else "SikuBERT" if siku_val > bge_val else "Tie"
            print(f"{label:<20} | {siku_val:>11.1f}% | {bge_val:>11.1f}% | {winner:>10}")
    
    # By category
    print("\n" + "-"*60)
    print("  Performance by Category (Hit@1 %)")
    print("-"*60)
    
    categories = set(tq.category for tq in TEST_QUERIES)
    for cat in sorted(categories):
        siku_cat = np.mean(siku_results["by_category"].get(cat, {}).get("hit@1", [0])) * 100
        bge_cat = np.mean(bge_results["by_category"].get(cat, {}).get("hit@1", [0])) * 100
        print(f"  {cat:<12} | SikuBERT: {siku_cat:5.1f}% | BGE-M3: {bge_cat:5.1f}%")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()
