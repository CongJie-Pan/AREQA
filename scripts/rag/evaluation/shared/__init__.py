# -*- coding: utf-8 -*-
"""
Shared components for RAG evaluation scripts.

This module provides common utilities to avoid code duplication across
bm25_reranker_eval.py and faiss_retrieval_eval.py.
"""

from .query_generator import SimpleQueryGenerator, QuerySample
from .score_fusion import reciprocal_rank_fusion, weighted_score_fusion

__all__ = [
    "SimpleQueryGenerator",
    "QuerySample",
    "reciprocal_rank_fusion",
    "weighted_score_fusion",
]
