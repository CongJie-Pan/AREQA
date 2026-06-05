#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Score Fusion Algorithms for Hybrid Retrieval

This module provides robust score fusion methods for combining
results from multiple retrieval systems (e.g., BM25 + FAISS).

Algorithms:
===========
1. Reciprocal Rank Fusion (RRF) - Recommended for production
   - Position-based fusion, doesn't require score normalization
   - Robust to different score distributions
   - Industry standard (used by Elastic, Weaviate, etc.)

2. Weighted Score Fusion - Legacy method
   - Requires score normalization (sensitive to outliers)
   - Simple but less robust

Reference:
- Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and 
  individual Rank Learning Methods" (SIGIR 2009)

Author: ML Engineer
Date: 2026-02-02
"""

from typing import List, Dict, Tuple, Optional
from collections import defaultdict


def reciprocal_rank_fusion(
    *rankings: List[Tuple[str, float]],
    k: int = 60,
    top_n: Optional[int] = None
) -> List[Tuple[str, float]]:
    """
    Reciprocal Rank Fusion (RRF) for combining multiple ranked lists.
    
    RRF is a robust method for fusing ranked retrieval results from
    different systems. It uses only rank positions, not scores, making
    it robust to different score distributions.
    
    Formula: RRF(d) = Σ 1 / (k + rank_i(d))
    
    where:
    - d is a document
    - k is a constant (typically 60)
    - rank_i(d) is the rank of document d in ranking i (1-indexed)
    
    Args:
        *rankings: Variable number of ranked lists, each containing
                   (doc_id, score) tuples sorted by score descending
        k: Ranking constant (default 60, higher values favor lower ranks)
        top_n: Return only top N results (None for all)
    
    Returns:
        List of (doc_id, rrf_score) tuples sorted by RRF score descending
    
    Example:
        >>> faiss_results = [("doc1", 0.95), ("doc2", 0.80), ("doc3", 0.75)]
        >>> bm25_results = [("doc2", 25.0), ("doc1", 18.0), ("doc4", 15.0)]
        >>> fused = reciprocal_rank_fusion(faiss_results, bm25_results)
        >>> print(fused[0])  # doc2 likely ranks highest
    """
    rrf_scores: Dict[str, float] = defaultdict(float)
    
    for ranking in rankings:
        if not ranking:
            continue
        
        for rank, (doc_id, _score) in enumerate(ranking, start=1):
            # RRF formula: 1 / (k + rank)
            rrf_scores[doc_id] += 1.0 / (k + rank)
    
    # Sort by RRF score descending
    sorted_results = sorted(
        rrf_scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    if top_n is not None:
        sorted_results = sorted_results[:top_n]
    
    return sorted_results


def weighted_score_fusion(
    scores_list: List[Dict[str, float]],
    weights: List[float],
    normalize: bool = True,
    top_n: Optional[int] = None
) -> List[Tuple[str, float]]:
    """
    Weighted score fusion with optional normalization.
    
    WARNING: This method is sensitive to score distribution differences.
    Consider using reciprocal_rank_fusion for more robust results.
    
    Args:
        scores_list: List of score dictionaries {doc_id: score}
        weights: List of weights for each score dictionary
        normalize: Whether to normalize scores to [0, 1] range
        top_n: Return only top N results (None for all)
    
    Returns:
        List of (doc_id, combined_score) tuples sorted by score descending
    
    Example:
        >>> faiss_scores = {"doc1": 0.95, "doc2": 0.80}
        >>> bm25_scores = {"doc1": 18.0, "doc2": 25.0}
        >>> fused = weighted_score_fusion(
        ...     [faiss_scores, bm25_scores],
        ...     weights=[0.7, 0.3]
        ... )
    """
    if len(scores_list) != len(weights):
        raise ValueError("Number of score dicts must match number of weights")
    
    # Normalize weights
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]
    
    # Collect all document IDs
    all_docs = set()
    for scores in scores_list:
        all_docs.update(scores.keys())
    
    # Normalize scores if requested
    normalized_scores_list = []
    for scores in scores_list:
        if normalize and scores:
            max_score = max(scores.values())
            min_score = min(scores.values())
            score_range = max_score - min_score
            
            if score_range > 0:
                normalized = {
                    doc_id: (score - min_score) / score_range
                    for doc_id, score in scores.items()
                }
            else:
                # All scores are the same
                normalized = {doc_id: 1.0 for doc_id in scores}
            normalized_scores_list.append(normalized)
        else:
            normalized_scores_list.append(scores)
    
    # Combine scores
    combined = {}
    for doc_id in all_docs:
        weighted_sum = 0.0
        for i, scores in enumerate(normalized_scores_list):
            score = scores.get(doc_id, 0.0)
            weighted_sum += normalized_weights[i] * score
        combined[doc_id] = weighted_sum
    
    # Sort by combined score descending
    sorted_results = sorted(
        combined.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    if top_n is not None:
        sorted_results = sorted_results[:top_n]
    
    return sorted_results


def rank_based_fusion(
    *rankings: List[Tuple[str, float]],
    method: str = "borda",
    top_n: Optional[int] = None
) -> List[Tuple[str, float]]:
    """
    Rank-based fusion using various voting methods.
    
    Args:
        *rankings: Variable number of ranked lists
        method: Fusion method ('borda', 'condorcet')
        top_n: Return only top N results
    
    Returns:
        List of (doc_id, fusion_score) tuples
    """
    if method == "borda":
        # Borda count: score = n - rank + 1
        scores: Dict[str, float] = defaultdict(float)
        
        for ranking in rankings:
            n = len(ranking)
            for rank, (doc_id, _) in enumerate(ranking, start=1):
                # Borda score: higher rank gets more points
                scores[doc_id] += n - rank + 1
        
        sorted_results = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        if top_n is not None:
            sorted_results = sorted_results[:top_n]
        
        return sorted_results
    
    else:
        raise ValueError(f"Unknown fusion method: {method}")
