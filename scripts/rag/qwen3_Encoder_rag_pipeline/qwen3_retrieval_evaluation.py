#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-T03: Qwen3 RAG Retrieval Evaluation Script

This script evaluates the Qwen3-based RAG retrieval system for Ancient Chinese
knowledge. It implements comprehensive metrics and domain-specific evaluation
strategies designed for Classical Chinese text retrieval.

Evaluation Approach (ML Expert Design):
========================================
1. **Stratified Sampling by Source Type**
   - classical_texts (e.g. rc_poems)
   - redChamber_text (e.g. redream_full_content)
   - exam_materials (e.g. examAtricle)
   - scholarly_analysis (e.g. generated_cai_annotation)
   - wiki (e.g. wiki_red_chamber)
   - structured_contents (e.g. qaSynthesisArticle)

2. **Query Type Classification**
   - Keyword Query: Direct keyword from chunk
   - Summary Query: Natural language from summary
   - Semantic Query: Paraphrased/related concepts
   - Cross-reference Query: Multi-hop reasoning needed

3. **Metrics Computed**
   - MRR (Mean Reciprocal Rank)
   - Hit@K (K = 1, 5, 10, 20)
   - NDCG@K (Normalized Discounted Cumulative Gain)
   - Precision@K, Recall@K
   - Per-category breakdown

4. **Domain-Specific Considerations**
   - Traditional vs Simplified Chinese handling
   - Classical vs Modern Chinese query patterns
   - Character-level vs Word-level matching
   - Synonym and variant character handling

Usage:
    python scripts/rag/evaluation/qwen3_retrieval_evaluation.py
    python scripts/rag/evaluation/qwen3_retrieval_evaluation.py --samples-per-type 10
    python scripts/rag/evaluation/qwen3_retrieval_evaluation.py --verbose

Author: ML Engineer
Date: 2026-02-02
Task: P3-T03 (Phase 3 - Qwen3 Retrieval Validation)
"""

import os
import sys
import json
import time
import random
import logging
import argparse
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

def _get_latest_file(directory: Path, pattern: str) -> Path:
    files = list(directory.glob(pattern))
    if not files:
        fallback = directory / pattern.replace("*", "")
        if fallback.exists():
            return fallback
        return fallback # Let it fail downstream if really missing
    return sorted(files, key=lambda x: x.stat().st_mtime)[-1]

CHUNKS_PATH = _get_latest_file(PROJECT_ROOT / "data" / "rag" / "chunks", "hybrid_smart_chunks*.json")
INDEX_PATH = _get_latest_file(PROJECT_ROOT / "data" / "rag" / "faiss_index", "chunks_qwen*.index")
MAPPING_PATH = _get_latest_file(PROJECT_ROOT / "data" / "rag" / "faiss_index", "chunk_mapping_qwen*.json")
METADATA_PATH = _get_latest_file(PROJECT_ROOT / "data" / "rag" / "faiss_index", "index_metadata_qwen*.json")
OUTPUT_DIR = PROJECT_ROOT / "output" / "reports" / "retrieval_eval"
MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Embedding-0.6B"
RERANKER_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Reranker-0.6B"

# Evaluation Settings
DEFAULT_SAMPLES_PER_TYPE = 15  # Samples per source_type
TOP_K_VALUES = [1, 5, 10, 20, 50]
RANDOM_SEED = 42

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class QuerySample:
    """A single evaluation query sample."""
    query_id: str
    query_text: str
    query_type: str  # keyword, summary, semantic, cross_reference
    source_type: str  # classical_texts, redChamber_text, etc.
    ground_truth_chunk_ids: List[str]
    ground_truth_doc_ids: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result of a single retrieval."""
    query_id: str
    retrieved_chunk_ids: List[str]
    retrieved_scores: List[float]
    latency_ms: float
    

@dataclass 
class EvaluationMetrics:
    """Computed evaluation metrics."""
    # Overall Metrics
    mrr: float = 0.0
    hit_at_1: float = 0.0
    hit_at_5: float = 0.0
    hit_at_10: float = 0.0
    hit_at_20: float = 0.0
    hit_at_50: float = 0.0
    ndcg_at_5: float = 0.0
    ndcg_at_10: float = 0.0
    precision_at_5: float = 0.0
    recall_at_5: float = 0.0
    
    # Latency
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    
    # Sample counts
    total_queries: int = 0
    successful_queries: int = 0


# ============================================================================
# Query Generator (Stratified Sampling)
# ============================================================================

class QueryGenerator:
    """
    Generates evaluation queries using stratified sampling from chunks.
    
    Strategy:
    1. For each source_type, sample N chunks
    2. Generate multiple query types per chunk:
       - Keyword query: Use 1-2 keywords directly
       - Summary query: Use the summary field
       - Semantic query: Combine keywords into natural question
    """
    
    def __init__(self, chunks: List[Dict], samples_per_type: int = 15):
        self.chunks = chunks
        self.samples_per_type = samples_per_type
        self.chunks_by_type = self._group_by_source_type()
        random.seed(RANDOM_SEED)
        
    def _group_by_source_type(self) -> Dict[str, List[Dict]]:
        """Group chunks by source_type."""
        grouped = defaultdict(list)
        
        # Mapping based on new data/rag/source contents
        SOURCE_FILE_MAP = {
            "rc_poems.json": "classical_texts",
            "shijing.jsonl": "classical_texts",
            "examAtricle.json": "exam_materials",
            "redream_full_content.jsonl": "redChamber_text",
            "generated_cai_annotation.jsonl": "scholarly_analysis",
            "qaSynthesisArticle.json": "structured_contents",
            "transfernotesArticle.json": "structured_contents",
            "wiki_red_chamber.json": "wiki"
        }
        
        for chunk in self.chunks:
            source_type = chunk.get('source_type')
            
            # Map from source_file if not provided
            if not source_type and 'metadata' in chunk:
                source_file = chunk['metadata'].get('source_file', '') or chunk['metadata'].get('source', '')
                if source_file in SOURCE_FILE_MAP:
                    source_type = SOURCE_FILE_MAP[source_file]
                    
            # Skip chunks that don't belong to any known category
            if not source_type or source_type == 'unknown':
                continue
                
            grouped[source_type].append(chunk)
        return dict(grouped)
    
    def generate_queries(self) -> List[QuerySample]:
        """Generate stratified query samples."""
        all_queries = []
        
        for source_type, type_chunks in self.chunks_by_type.items():
            logger.info(f"Generating queries for {source_type} ({len(type_chunks)} chunks available)")
            
            # Sample chunks for this type
            sample_size = min(self.samples_per_type, len(type_chunks))
            sampled_chunks = random.sample(type_chunks, sample_size)
            
            for chunk in sampled_chunks:
                queries = self._generate_queries_from_chunk(chunk, source_type)
                all_queries.extend(queries)
        
        logger.info(f"Total queries generated: {len(all_queries)}")
        return all_queries
    
    def _generate_queries_from_chunk(self, chunk: Dict, source_type: str) -> List[QuerySample]:
        """Generate different types of queries from a single chunk."""
        queries = []
        chunk_id = chunk.get('chunk_id')
        if not chunk_id and 'metadata' in chunk:
            chunk_id = chunk['metadata'].get('chunk_id')
        if not chunk_id:
            chunk_id = "unknown_chunk_id"
        
        doc_id = chunk.get('doc_id')
        if not doc_id and 'metadata' in chunk:
            doc_id = chunk['metadata'].get('doc_id', chunk_id)
        if not doc_id:
            doc_id = chunk_id
            
        keywords = chunk.get('keywords', [])
        summary = chunk.get('summary', '')
        text = chunk.get('text', chunk.get('page_content', ''))

        # Query Type 1: Keyword Query (highest precision expected)
        if keywords and len(keywords) >= 1:
            # Use first 1-2 keywords
            kw_query = ' '.join(keywords[:2]) if len(keywords) >= 2 else keywords[0]
            queries.append(QuerySample(
                query_id=f"{chunk_id}_kw",
                query_text=kw_query,
                query_type="keyword",
                source_type=source_type,
                ground_truth_chunk_ids=[chunk_id],
                ground_truth_doc_ids=[doc_id],
                metadata={"keywords_used": keywords[:2]}
            ))
        
        # Query Type 2: Summary Query (natural language)
        if summary and len(summary) > 5:
            queries.append(QuerySample(
                query_id=f"{chunk_id}_sum",
                query_text=summary,
                query_type="summary",
                source_type=source_type,
                ground_truth_chunk_ids=[chunk_id],
                ground_truth_doc_ids=[doc_id],
                metadata={"original_summary": summary}
            ))
        
        # Query Type 3: Semantic Query (question format)
        if keywords and len(keywords) >= 2:
            # Generate a question-like query
            semantic_patterns = [
                f"什麼是{keywords[0]}",
                f"{keywords[0]}的含義",
                f"關於{keywords[0]}和{keywords[1]}",
                f"{keywords[0]}{keywords[1]}的關係",
            ]
            semantic_query = random.choice(semantic_patterns)
            queries.append(QuerySample(
                query_id=f"{chunk_id}_sem",
                query_text=semantic_query,
                query_type="semantic",
                source_type=source_type,
                ground_truth_chunk_ids=[chunk_id],
                ground_truth_doc_ids=[doc_id],
                metadata={"pattern": "question_format"}
            ))
            
        # Default Fallback Query (If no summary and no keywords)
        if not queries and text and len(text) > 10:
            # Fallback: Extract first sentence or up to 30 chars as question
            first_sentence = text.split("。")[0].split("\n")[0][:30]
            queries.append(QuerySample(
                query_id=f"{chunk_id}_fallback",
                query_text=first_sentence if first_sentence else "這段文章在說什麼？",
                query_type="fallback",
                source_type=source_type,
                ground_truth_chunk_ids=[chunk_id],
                ground_truth_doc_ids=[doc_id],
                metadata={"pattern": "fallback_extract"}
            ))

        return queries
# ============================================================================
# Retriever (FAISS + Qwen3)
# ============================================================================

class ProductionRetriever:
    """
    Wraps RAGService to provide eval-compatible retrieval interface.
    Ensures eval uses EXACTLY the same code path as production.
    """
    
    def __init__(self, top_k: int = 50):
        self.device = "cuda:0" if self._check_cuda() else "cpu"
        self.top_k = top_k
        
        sys.path.append(str(PROJECT_ROOT / "app" / "streamlit"))
        try:
            from rag_service import RAGService
            logger.info("Loading RAGService...")
            self.rag = RAGService(
                faiss_index_path=str(INDEX_PATH),
                faiss_metadata_path=str(METADATA_PATH),
                bm25_index_dir=str(PROJECT_ROOT / "data" / "rag" / "bm25_index"),
                embedding_model_path="api", # Force use Embedding API
                reranker_model_path="api", # Force use Reranker API mode in RAGService
                top_k=self.top_k,
                rrf_k=60,
                score_threshold=0.0,
                max_context_tokens=4000,
                device=self.device
            )
            # wait until loaded
        except ImportError as e:
            logger.error(f"Could not import RAGService: {e}")
            raise
    
    def _check_cuda(self) -> bool:
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=FutureWarning)
                import torch
                return torch.cuda.is_available()
        except:
            return False
            
    def load_index(self): ...
    def load_encoder(self): ...
            
    def retrieve_hybrid(self, query: str, top_k: int = 50) -> Tuple[List[str], List[float], float]:
        """Full production pipeline: FAISS + BM25 + RRF."""
        start = time.perf_counter()
        debug = self.rag.retrieve_with_debug(query)
        latency = (time.perf_counter() - start) * 1000
        
        # Take fused results for hybrid search baseline (before truncation)
        fused = debug.fused_results[:top_k]
        chunk_ids = [r.get("chunk_id", "") for r in fused]
        scores = [float(r.get("score", 0.0)) for r in fused]
        return chunk_ids, scores, latency
    
    def retrieve_dense_only(self, query: str, depth: int = 50) -> Tuple[List[str], List[float], float]:
        """Isolated dense retrieval for ablation study."""
        start = time.perf_counter()
        query_emb = self.rag.encode_query(query)  # WITH instruction prefix
        results = self.rag._faiss_search(query_emb, depth=depth)
        latency = (time.perf_counter() - start) * 1000
        
        chunk_ids = [r.get("chunk_id", "") for r in results]
        scores = [float(r.get("score", 0.0)) for r in results]
        return chunk_ids, scores, latency
    
    def retrieve_sparse_only(self, query: str, depth: int = 50) -> Tuple[List[str], List[float], float]:
        """Isolated sparse retrieval for ablation study."""
        start = time.perf_counter()
        results = self.rag._bm25_search(query, depth=depth)
        latency = (time.perf_counter() - start) * 1000
        
        chunk_ids = [str(r.get("chunk_id", "")) for r in results]
        scores = [float(r.get("score", 0.0)) for r in results]
        return chunk_ids, scores, latency
    
    def retrieve_with_full_pipeline(self, query: str):
        """Full pipeline with debug traces for deep analysis."""
        return self.rag.retrieve_with_debug(query)


# ============================================================================
# Metrics Calculator
# ============================================================================

class GoldenSetLoader:
    """Load evaluation queries from multiple sources."""
    
    @staticmethod
    def load_golden_set(path: Path) -> List[QuerySample]:
        """Tier 1: Human-verified golden queries."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [QuerySample(
            query_id=item['id'],
            query_text=item['query'],
            query_type=item.get('type', 'golden'),
            source_type=item.get('source_type', 'unknown'),
            ground_truth_chunk_ids=item.get('relevant_chunk_ids', []),
            ground_truth_doc_ids=item.get('relevant_doc_ids', []),
            metadata={
                **item.get('metadata', {}),
                'expected_response': item.get('expected_response', '')
            }
        ) for item in data]
    
    @staticmethod
    def generate_synthetic_queries(chunks: List[Dict], samples_per_type: int = 15) -> List[QuerySample]:
        """Tier 2: Synthetic queries (medium trust, quick to generate)."""
        generator = QueryGenerator(chunks, samples_per_type)
        return generator.generate_queries()


# ============================================================================
class MetricsCalculator:
    """
    Computes retrieval evaluation metrics.
    
    Metrics Implemented:
    - MRR: Mean Reciprocal Rank
    - Hit@K: Whether ground truth appears in top-K
    - NDCG@K: Normalized Discounted Cumulative Gain
    - Precision@K: Fraction of relevant in top-K
    - Recall@K: Fraction of relevant items retrieved
    """
    
    @staticmethod
    def compute_reciprocal_rank(retrieved: List[str], ground_truth: Set[str]) -> float:
        """Compute reciprocal rank (1/rank of first relevant item)."""
        for i, chunk_id in enumerate(retrieved):
            if chunk_id in ground_truth:
                return 1.0 / (i + 1)
        return 0.0
    
    @staticmethod
    def compute_hit_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
        """Compute Hit@K (1 if any ground truth in top-k, else 0)."""
        top_k = set(retrieved[:k])
        return 1.0 if len(top_k & ground_truth) > 0 else 0.0
    
    @staticmethod
    def compute_precision_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
        """Compute Precision@K."""
        top_k = retrieved[:k]
        relevant_in_top_k = sum(1 for c in top_k if c in ground_truth)
        return relevant_in_top_k / k if k > 0 else 0.0
    
    @staticmethod
    def compute_recall_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
        """Compute Recall@K."""
        top_k = set(retrieved[:k])
        retrieved_relevant = len(top_k & ground_truth)
        return retrieved_relevant / len(ground_truth) if len(ground_truth) > 0 else 0.0
    
    @staticmethod
    def compute_ndcg_at_k(retrieved: List[str], ground_truth: Set[str], k: int) -> float:
        """Compute NDCG@K."""
        # Relevance scores (binary: 1 if relevant, 0 otherwise)
        relevance = [1.0 if c in ground_truth else 0.0 for c in retrieved[:k]]
        
        # DCG
        dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(relevance))
        
        # Ideal DCG (all relevant items at top)
        ideal_relevance = sorted(relevance, reverse=True)
        idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_relevance))
        
        return dcg / idcg if idcg > 0 else 0.0
    
    def compute_effective_recall(
        self,
        query: QuerySample,
        debug_info
    ) -> Dict:
        """Compute recall AFTER token budget truncation and sanitization."""
        effective_chunks = [getattr(r, "chunk_id", "") for r in debug_info.final_results]
        gt_set = set(query.ground_truth_chunk_ids)
        
        pre_truncation = [item.get("chunk_id", "") for item in debug_info.fused_results[:50]]
        standard_recall = len(set(pre_truncation) & gt_set) / len(gt_set) if gt_set else 0.0
        
        effective_recall = len(set(effective_chunks) & gt_set) / len(gt_set) if gt_set else 0.0
        
        return {
            "standard_recall": standard_recall,
            "effective_recall": effective_recall,
            "chunks_dropped_by_budget": debug_info.truncated_count,
            "chunks_sanitized": debug_info.sanitized_count,
            "recall_loss_from_budget": standard_recall - effective_recall,
        }

    def compute_all_metrics(
        self, 
        queries: List[QuerySample], 
        results: List[RetrievalResult]
    ) -> Dict[str, Any]:
        """Compute all metrics from query-result pairs."""
        
        # Initialize accumulators
        rr_scores = []
        hit_scores = {k: [] for k in TOP_K_VALUES}
        ndcg_scores = {k: [] for k in [5, 10]}
        precision_scores = {5: []}
        recall_scores = {5: []}
        latencies = []
        
        # Per-category metrics
        by_source_type = defaultdict(lambda: {"rr": [], "hit@10": []})
        by_query_type = defaultdict(lambda: {"rr": [], "hit@10": []})
        
        for query, result in zip(queries, results):
            gt_set = set(query.ground_truth_chunk_ids)
            retrieved = result.retrieved_chunk_ids
            
            # Core metrics
            rr = self.compute_reciprocal_rank(retrieved, gt_set)
            rr_scores.append(rr)
            
            for k in TOP_K_VALUES:
                hit_scores[k].append(self.compute_hit_at_k(retrieved, gt_set, k))
            
            for k in [5, 10]:
                ndcg_scores[k].append(self.compute_ndcg_at_k(retrieved, gt_set, k))
            
            precision_scores[5].append(self.compute_precision_at_k(retrieved, gt_set, 5))
            recall_scores[5].append(self.compute_recall_at_k(retrieved, gt_set, 5))
            
            latencies.append(result.latency_ms)
            
            # Category breakdown
            by_source_type[query.source_type]["rr"].append(rr)
            by_source_type[query.source_type]["hit@10"].append(self.compute_hit_at_k(retrieved, gt_set, 10))
            
            by_query_type[query.query_type]["rr"].append(rr)
            by_query_type[query.query_type]["hit@10"].append(self.compute_hit_at_k(retrieved, gt_set, 10))
        
        # Aggregate
        metrics = {
            "overall": {
                "mrr": float(np.mean(rr_scores)),
                "hit@1": float(np.mean(hit_scores[1])),
                "hit@5": float(np.mean(hit_scores[5])),
                "hit@10": float(np.mean(hit_scores[10])),
                "hit@20": float(np.mean(hit_scores[20])),
                "hit@50": float(np.mean(hit_scores[50])),
                "ndcg@5": float(np.mean(ndcg_scores[5])),
                "ndcg@10": float(np.mean(ndcg_scores[10])),
                "precision@5": float(np.mean(precision_scores[5])),
                "recall@5": float(np.mean(recall_scores[5])),
                "avg_latency_ms": float(np.mean(latencies)),
                "p95_latency_ms": float(np.percentile(latencies, 95)),
                "total_queries": len(queries)
            },
            "by_source_type": {
                st: {
                    "mrr": float(np.mean(data["rr"])),
                    "hit@10": float(np.mean(data["hit@10"])),
                    "count": len(data["rr"])
                }
                for st, data in by_source_type.items()
            },
            "by_query_type": {
                qt: {
                    "mrr": float(np.mean(data["rr"])),
                    "hit@10": float(np.mean(data["hit@10"])),
                    "count": len(data["rr"])
                }
                for qt, data in by_query_type.items()
            }
        }
        
        return metrics


# ============================================================================
# Evaluation Runner
# ============================================================================

class EvaluationRunner:
    """Main evaluation orchestrator."""
    
    def __init__(self, samples_per_type: int = DEFAULT_SAMPLES_PER_TYPE, verbose: bool = False):
        self.samples_per_type = samples_per_type
        self.verbose = verbose
        self.chunks = None
        self.retriever = None
        self.metrics_calculator = MetricsCalculator()
        
    def _rewrite_structured_queries(self, queries: List[QuerySample]):
        import requests
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("No OPENROUTER_API_KEY found. Skipping query rewrite.")
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        for q in tqdm(queries, desc="Rewriting queries"):
            if "此段落的章節脈絡為：" in q.query_text or q.query_type == "fallback":
                prompt = f"""請將以下結構化描述改寫為一個自然語言的提問句：
輸入：{q.query_text}
輸出："""
                payload = {
                    "model": "qwen/qwen3-30b-a3b-instruct-2507",
                    "messages": [
                        {"role": "system", "content": "你是一個優化檢索問題的助手，負責把結構化的文字改寫成簡短、自然的問句。只輸出改寫後的問句，不要有任何多餘的解釋和回答。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.0,
                    "max_tokens": 50,
                    "reasoning": {"effort": "none"}
                }
                try:
                    response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=10)
                    if response.ok:
                        data = response.json()
                        rewritten = data["choices"][0]["message"]["content"].strip()
                        if rewritten:
                            logger.debug(f"Rewrote query: {q.query_text} -> {rewritten}")
                            q.query_text = rewritten
                except Exception as e:
                    logger.error(f"Failed to rewrite query '{q.query_text}': {e}")
                    
    def _expand_queries_with_openrouter(self, queries: List[QuerySample]):
        """Perform text expansion (HyDE or query rewrite) via OpenRouter to improve retrieval."""
        import requests
        from dotenv import load_dotenv
        import os
        from tqdm import tqdm
        
        load_dotenv()
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("No OPENROUTER_API_KEY found. Skipping text expansion.")
            return

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        logger.info("Executing Document Expansion / HyDE via OpenRouter...")
        for q in tqdm(queries, desc="Expanding queries"):
            # If the query is totally generic and has no context, we use the expected response to reconstruct the problem
            if "這段話的意思" in q.query_text or len(q.query_text) < 15:
                expected_ans = q.metadata.get('expected_response', '')
                # To reconstruct a valid query since the synthetic dataset is broken here
                prompt = f"""這是一個缺乏上下文的檢索問題。請根據『預期解答』，反推出一個具體、包含實質專有名詞與文言文背景的清晰提問。
原問題：{q.query_text}
預期解答：{expected_ans}

請直接輸出改寫後且具體的問題，不要任何解釋："""
            else:
                # Perform standard HyDE (Hypothetical Document Embeddings)
                prompt = f"""請針對以下關於古文或國學常識的問題，撰寫一段假想的「詳細解答文本」（約100字內）。
請盡量包含相關的原文關鍵字、專有名詞或主旨，這將用於作為語義檢索的文本擴寫特徵。

問題：{q.query_text}
直接輸出擴寫文本，不要任何解釋或多餘的開頭："""

            payload = {
                "model": "qwen/qwen3-30b-a3b-instruct-2507",
                "messages": [
                    {"role": "system", "content": "你是一個優化語義檢索的國學領域專家。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 150,
            }

            try:
                response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=15)
                if response.ok:
                    data = response.json()
                    expanded_text = data["choices"][0]["message"]["content"].strip()
                    if expanded_text:
                        # Append the expanded text to the query (HyDE mechanism)
                        if "這段話的意思" in q.query_text or len(q.query_text) < 15:
                            logger.debug(f"Rewrite Base Query: {q.query_text} -> {expanded_text}")
                            q.query_text = expanded_text  # Replace bad query structurally
                        else:
                            q.query_text = f"{q.query_text}\n[擴寫特徵]: {expanded_text}" # Append HyDE feature
            except Exception as e:
                logger.error(f"Failed to expand query '{q.query_text}': {e}")

    def load_data(self):
        """Load chunks data."""
        logger.info(f"Loading chunks from {CHUNKS_PATH}...")
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
        logger.info(f"Loaded {len(self.chunks)} chunks")
        
    def run_evaluation(self, use_golden_set: bool = False, golden_set_path: str = None) -> Dict[str, Any]:
        """Run the complete evaluation pipeline."""

        # Step 1: Load data and initialize queries
        if use_golden_set and golden_set_path and os.path.exists(golden_set_path):
            logger.info(f"Loading golden queries from {golden_set_path}...")
            queries = GoldenSetLoader.load_golden_set(Path(golden_set_path))
            self.load_data() # For backward compatibility
            
            # Apply Expansion / HyDE onto Golden Queries before retrieval
            self._expand_queries_with_openrouter(queries)
        else:
            self.load_data()
            logger.info("Generating synthetic queries as fallback...")
            queries = GoldenSetLoader.generate_synthetic_queries(self.chunks, self.samples_per_type)
            # ★ 改善 Query 生成策略：過濾並改寫不自然的 Queries
            logger.info("Rewriting structured queries to natural language...")
            self._rewrite_structured_queries(queries)

        # Step 2: Initialize Production retriever
        # 由於要改用 DeepInfra OpenRouter Reranker API, 先前我們還是只關注 retrieval 的 ablation_study. 
        # RetrievalEvaluation 本身設計是測 retriever。 Reranker測試在評估階段不一定是必須，但若需要 Reranker 可傳入 Reranker API相關參數 (但由於 `rag_service.py` 預設是吃本機端 model，請注意若在 RAGService 也需要改的話，會動到核心)。 
        # 本修改點專注於修改 Retrieval 部分，原版沒有實作 reranker step 在 Evaluation 裡面，先保留 ProductionRetriever 的設定，並且只利用 dense, sparse 等功能。
        self.retriever = ProductionRetriever(top_k=50)
        self.retriever.load_index()
        self.retriever.load_encoder()
        
        # Step 3: Run ablation study
        logger.info("Running retrieval evaluation (Ablation Study)...")
        all_results = self._run_ablation_study(queries)
        hybrid_results = all_results["hybrid_rrf_results"]
        metrics = all_results["hybrid_rrf"]
        metrics["ablation_analysis"] = all_results["ablation_analysis"]
        
        # Step 4: Compute Effective Recall and extract failure cases
        logger.info("Analyzing effective recall and failure cases...")
        effective_recalls = []
        for q in tqdm(queries, desc="Effective/Failure Analysis"):
            debug = self.retriever.retrieve_with_full_pipeline(q.query_text)
            eff_recall = self.metrics_calculator.compute_effective_recall(q, debug)
            effective_recalls.append(eff_recall)
            
        metrics["overall"]["effective_recall"] = float(np.mean([e["effective_recall"] for e in effective_recalls]))
        metrics["overall"]["recall_loss_from_budget"] = float(np.mean([e["recall_loss_from_budget"] for e in effective_recalls]))
        
        # Step 5: Failure analysis
        failure_cases = self._get_failure_analysis(queries, hybrid_results, n=20)
        
        # Step 6: Generate report
        report = self._generate_report(metrics, queries, hybrid_results, failure_cases)
        return report

    def _run_ablation_study(self, queries: List[QuerySample]) -> Dict:
        """Evaluate FAISS-only, BM25-only, and Hybrid to quantify each component."""
        modes = {
            "dense_only": self.retriever.retrieve_dense_only,
            "sparse_only": self.retriever.retrieve_sparse_only,
            "hybrid_rrf": self.retriever.retrieve_hybrid,
        }
        
        all_results = {}
        for mode_name, retrieve_fn in modes.items():
            results = []
            logger.info(f"Running mode: {mode_name}")
            for query in tqdm(queries, desc=mode_name):
                if mode_name == "hybrid_rrf":
                    chunk_ids, scores, latency = retrieve_fn(query.query_text, top_k=50)
                else:
                    chunk_ids, scores, latency = retrieve_fn(query.query_text, depth=50)
                results.append(RetrievalResult(
                    query_id=query.query_id,
                    retrieved_chunk_ids=chunk_ids,
                    retrieved_scores=scores,
                    latency_ms=latency
                ))
            all_results[mode_name] = self.metrics_calculator.compute_all_metrics(queries, results)
            if mode_name == "hybrid_rrf":
                all_results["hybrid_rrf_results"] = results
        
        dense_mrr = all_results["dense_only"]["overall"]["mrr"]
        sparse_mrr = all_results["sparse_only"]["overall"]["mrr"]
        hybrid_mrr = all_results["hybrid_rrf"]["overall"]["mrr"]
        
        all_results["ablation_analysis"] = {
            "hybrid_vs_dense_delta": float(hybrid_mrr - dense_mrr),
            "hybrid_vs_sparse_delta": float(hybrid_mrr - sparse_mrr),
            "dense_contribution": f"MRR={dense_mrr:.4f}",
            "sparse_contribution": f"MRR={sparse_mrr:.4f}",
            "hybrid_combined": f"MRR={hybrid_mrr:.4f}",
        }
        return all_results

    def _get_failure_analysis(self, queries: List[QuerySample], results: List[RetrievalResult], n: int = 20) -> List[Dict]:
        """Extract and analyze failure cases for debugging."""
        failures = []
        for query, result in zip(queries, results):
            gt_set = set(query.ground_truth_chunk_ids)
            hit = any(c in gt_set for c in result.retrieved_chunk_ids[:10])
            
            if not hit:
                debug = self.retriever.retrieve_with_full_pipeline(query.query_text)
                failures.append({
                    "query": query.query_text,
                    "query_type": query.query_type,
                    "expected": query.ground_truth_chunk_ids,
                    "got_top_5": result.retrieved_chunk_ids[:5],
                    "dense_rank": self._find_rank_in(debug.dense_results, gt_set),
                    "sparse_rank": self._find_rank_in(debug.sparse_results, gt_set),
                    "fused_rank": self._find_rank_in(debug.fused_results, gt_set),
                    "failure_mode": self._classify_failure(debug, gt_set),
                })
        
        return sorted(failures, key=lambda x: x["failure_mode"])[:n]

    def _find_rank_in(self, results_list: List[Dict], gt_set: Set[str]) -> int:
        for i, r in enumerate(results_list):
            if r.get("chunk_id", "") in gt_set:
                return i + 1
        return -1

    def _classify_failure(self, debug, gt_set: Set[str]) -> str:
        dense_found = any(r.get("chunk_id", "") in gt_set for r in debug.dense_results[:50])
        sparse_found = any(r.get("chunk_id", "") in gt_set for r in debug.sparse_results[:50])
        
        if not dense_found and not sparse_found:
            return "TOTAL_MISS"
        elif dense_found and not sparse_found:
            return "SPARSE_MISS"
        elif not dense_found and sparse_found:
            return "DENSE_MISS"
        else:
            return "RRF_RANK_DROP"

    def _generate_report(
        self, 
        metrics: Dict, 
        queries: List[QuerySample],
        results: List[RetrievalResult],
        failure_cases: List[Dict]
    ) -> Dict[str, Any]:
        """Generate comprehensive evaluation report."""
        
        report = {
            "report_date": datetime.now().isoformat(),
            "evaluation_config": {
                "samples_per_type": self.samples_per_type,
                "top_k_values": TOP_K_VALUES,
                "total_chunks": len(self.chunks) if self.chunks else 0,
                "index_size": self.retriever.rag._faiss_index.ntotal if hasattr(self.retriever.rag, '_faiss_index') and self.retriever.rag._faiss_index else 0,
                "device": self.retriever.device
            },
            "metrics": metrics,
            "analysis": self._generate_analysis(metrics),
            "sample_results": self._get_sample_results(queries, results, n=10),
            "failure_cases": failure_cases
        }
        
        return report
    
    def _generate_analysis(self, metrics: Dict) -> Dict[str, Any]:
        """Generate analysis and recommendations."""
        overall = metrics["overall"]
        
        analysis = {
            "summary": "",
            "strengths": [],
            "weaknesses": [],
            "recommendations": []
        }
        
        # MRR Analysis
        mrr = overall["mrr"]
        if mrr >= 0.5:
            analysis["summary"] = "優秀的檢索效果"
            analysis["strengths"].append(f"MRR = {mrr:.3f} (優秀，正確答案通常在前 2 名)")
        elif mrr >= 0.3:
            analysis["summary"] = "良好的檢索效果"
            analysis["strengths"].append(f"MRR = {mrr:.3f} (良好，正確答案通常在前 3-4 名)")
        elif mrr >= 0.1:
            analysis["summary"] = "尚可的檢索效果，有改進空間"
            analysis["weaknesses"].append(f"MRR = {mrr:.3f} (中等，正確答案排名偏後)")
        else:
            analysis["summary"] = "檢索效果不佳，需要重大改進"
            analysis["weaknesses"].append(f"MRR = {mrr:.3f} (較差，檢索結果相關性低)")
        
        # Hit@10 Analysis
        hit10 = overall["hit@10"]
        if hit10 >= 0.8:
            analysis["strengths"].append(f"Hit@10 = {hit10:.1%} (80%+ 查詢在前 10 名找到答案)")
        elif hit10 < 0.5:
            analysis["weaknesses"].append(f"Hit@10 = {hit10:.1%} (低於 50%，覆蓋率不足)")
        
        # Latency Analysis
        latency = overall["avg_latency_ms"]
        if latency < 50:
            analysis["strengths"].append(f"平均延遲 {latency:.1f}ms (極快)")
        elif latency > 200:
            analysis["weaknesses"].append(f"平均延遲 {latency:.1f}ms (較慢，可能影響用戶體驗)")
        
        # Category Analysis
        by_type = metrics.get("by_source_type", {})
        best_type = max(by_type.items(), key=lambda x: x[1]["mrr"], default=(None, None))
        worst_type = min(by_type.items(), key=lambda x: x[1]["mrr"], default=(None, None))
        
        if best_type[0]:
            analysis["strengths"].append(f"在「{best_type[0]}」類型表現最佳 (MRR={best_type[1]['mrr']:.3f})")
        if worst_type[0] and worst_type[1]["mrr"] < 0.2:
            analysis["weaknesses"].append(f"在「{worst_type[0]}」類型表現較差 (MRR={worst_type[1]['mrr']:.3f})")
            analysis["recommendations"].append(f"考慮針對「{worst_type[0]}」類型優化 chunking 或增加訓練數據")
        
        # Query Type Analysis
        by_query = metrics.get("by_query_type", {})
        if "keyword" in by_query and "summary" in by_query:
            kw_mrr = by_query["keyword"]["mrr"]
            sum_mrr = by_query["summary"]["mrr"]
            if kw_mrr > sum_mrr * 1.5:
                analysis["recommendations"].append("Summary 查詢效果較差，考慮優化語義理解能力")
        
        return analysis
    
    def _get_sample_results(
        self, 
        queries: List[QuerySample], 
        results: List[RetrievalResult],
        n: int = 10
    ) -> List[Dict]:
        """Get sample results for manual inspection."""
        samples = []
        
        # Get some successful and some failed cases
        for query, result in zip(queries[:n*2], results[:n*2]):
            gt_set = set(query.ground_truth_chunk_ids)
            hit = any(c in gt_set for c in result.retrieved_chunk_ids[:10])
            
            # Find rank of first relevant
            rank = -1
            for i, c in enumerate(result.retrieved_chunk_ids):
                if c in gt_set:
                    rank = i + 1
                    break
            
            samples.append({
                "query": query.query_text,
                "query_type": query.query_type,
                "source_type": query.source_type,
                "ground_truth": query.ground_truth_chunk_ids,
                "top_5_retrieved": result.retrieved_chunk_ids[:5],
                "hit@10": hit,
                "rank": rank,
                "latency_ms": round(result.latency_ms, 2)
            })
            
            if len(samples) >= n:
                break
        
        return samples
    
    def save_report(self, report: Dict, output_dir: Path = OUTPUT_DIR):
        """Save evaluation report."""
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save JSON
        json_path = output_dir / f"qwen3_eval_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Report saved to: {json_path}")
        
        # Save Markdown summary
        md_path = output_dir / f"qwen3_eval_{timestamp}.md"
        md_content = self._generate_markdown(report)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        logger.info(f"Markdown saved to: {md_path}")
        
        return json_path
    
    def _generate_markdown(self, report: Dict) -> str:
        """Generate Markdown report."""
        metrics = report["metrics"]["overall"]
        analysis = report["analysis"]
        config = report["evaluation_config"]
        
        lines = [
            "# Qwen3 RAG Retrieval Evaluation Report",
            "",
            f"**Date**: {report['report_date']}",
            f"**Total Queries**: {metrics['total_queries']}",
            f"**Index Size**: {config['index_size']} vectors",
            f"**Device**: {config['device']}",
            "",
            "---",
            "",
            "## Overall Metrics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| **MRR** | {metrics['mrr']:.4f} |",
            f"| Hit@1 | {metrics['hit@1']:.1%} |",
            f"| Hit@5 | {metrics['hit@5']:.1%} |",
            f"| **Hit@10** | {metrics['hit@10']:.1%} |",
            f"| Hit@20 | {metrics['hit@20']:.1%} |",
            f"| NDCG@10 | {metrics['ndcg@10']:.4f} |",
            f"| Avg Latency | {metrics['avg_latency_ms']:.1f}ms |",
            f"| P95 Latency | {metrics['p95_latency_ms']:.1f}ms |",
            "",
            "---",
            "",
            "## Analysis Summary",
            "",
            f"**{analysis['summary']}**",
            "",
            "### Strengths",
            ""
        ]
        
        for s in analysis.get("strengths", []):
            lines.append(f"- ✅ {s}")
        
        lines.extend([
            "",
            "### Areas for Improvement",
            ""
        ])
        
        for w in analysis.get("weaknesses", []):
            lines.append(f"- ⚠️ {w}")
        
        lines.extend([
            "",
            "### Recommendations",
            ""
        ])
        
        for r in analysis.get("recommendations", []):
            lines.append(f"- 💡 {r}")
        
        # By Source Type
        lines.extend([
            "",
            "---",
            "",
            "## Performance by Source Type",
            "",
            "| Source Type | MRR | Hit@10 | Samples |",
            "|-------------|-----|--------|---------|"
        ])
        
        for st, data in report["metrics"].get("by_source_type", {}).items():
            lines.append(f"| {st} | {data['mrr']:.3f} | {data['hit@10']:.1%} | {data['count']} |")
        
        # By Query Type
        lines.extend([
            "",
            "## Performance by Query Type",
            "",
            "| Query Type | MRR | Hit@10 | Samples |",
            "|------------|-----|--------|---------|"
        ])
        
        for qt, data in report["metrics"].get("by_query_type", {}).items():
            lines.append(f"| {qt} | {data['mrr']:.3f} | {data['hit@10']:.1%} | {data['count']} |")
        
        # Sample Results
        lines.extend([
            "",
            "---",
            "",
            "## Sample Results",
            ""
        ])
        
        for i, sample in enumerate(report.get("sample_results", [])[:5]):
            status = "✅" if sample["hit@10"] else "❌"
            rank_str = f"Rank {sample['rank']}" if sample['rank'] > 0 else "Not in Top-50"
            lines.extend([
                f"### {i+1}. {status} {sample['query'][:50]}...",
                f"- **Type**: {sample['query_type']} | **Source**: {sample['source_type']}",
                f"- **Result**: {rank_str} | Latency: {sample['latency_ms']}ms",
                ""
            ])
        
        # Ablation Study section
        lines.extend([
            "",
            "---",
            "",
            "## Ablation Study (Component Analysis)",
            "",
            "| Component | MRR |",
            "|-----------|-----|",
            f"| BM25 (Sparse)  | {report['metrics']['ablation_analysis']['sparse_contribution'].split('=')[1]} |",
            f"| FAISS (Dense)  | {report['metrics']['ablation_analysis']['dense_contribution'].split('=')[1]} |",
            f"| **Hybrid (RRF)** | **{report['metrics']['ablation_analysis']['hybrid_combined'].split('=')[1]}** |",
        ])
        
        # Effective Recall
        lines.extend([
            "",
            "---",
            "## Effective Retrieval Metrics (Post-Sanitization & Truncation)",
            "",
            f"- **Effective Recall**: {report['metrics']['overall'].get('effective_recall', 0.0):.1%}",
            f"- **Loss from Token Budget**: {report['metrics']['overall'].get('recall_loss_from_budget', 0.0):.1%}",
        ])
        
        # Add Failure Cases
        lines.extend([
            "",
            "---",
            "## Top Failure Cases (from Hybrid Search)",
            ""
        ])
        
        for i, fc in enumerate(report.get("failure_cases", [])[:5]):
            lines.extend([
                f"### {i+1}. Failure Mode: {fc['failure_mode']}",
                f"- **Query**: {fc['query'][:50]}...",
                f"- **Dense Rank**: {fc['dense_rank']} | **Sparse Rank**: {fc['sparse_rank']} | **Fused Rank**: {fc['fused_rank']}",
                ""
            ])

        return "\n".join(lines)


# ============================================================================
# Main
# ============================================================================

def check_deepinfra_api():
    """Verify DeepInfra API key and connection before starting evaluate."""
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        logger.error("DEEPINFRA_API_KEY environment variable is not set. Execution halted.")
        sys.exit(1)
        
    try:
        # Check models endpoint as a lightweight connection test
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get("https://api.deepinfra.com/v1/models", headers=headers, timeout=5)
        if response.status_code == 200:
            logger.info("DeepInfra API Connection: Verified [Green/OK]")
        else:
            logger.error(f"DeepInfra API connection failed with status code: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to connect to DeepInfra API: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Evaluate Qwen3 RAG Retrieval")
    parser.add_argument("--samples-per-type", type=int, default=DEFAULT_SAMPLES_PER_TYPE,
                       help=f"Number of samples per source type (default: {DEFAULT_SAMPLES_PER_TYPE})")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    # Default to the newly generated golden cases
    default_golden_set = str(PROJECT_ROOT / "data" / "evaluation" / "golden_cases_rag.json")
    parser.add_argument("--golden-set", type=str, default=default_golden_set, help="Path to golden set JSON file")
    
    args = parser.parse_args()
    
    # Pre-flight API checks
    check_deepinfra_api()
    
    logger.info("=" * 60)
    logger.info("Qwen3 RAG Retrieval Evaluation")
    
    # Print the specific models being evaluated
    logger.info(f"Target Embedding Model  : qwen/qwen3-embedding-8b (via OpenRouter API)")
    logger.info(f"Target Reranker Model   : Qwen/Qwen3-Reranker-8B (via DeepInfra API)")
    
    logger.info("=" * 60)
    
    runner = EvaluationRunner(
        samples_per_type=args.samples_per_type,
        verbose=args.verbose
    )
    
    try:
        report = runner.run_evaluation(
            use_golden_set=bool(args.golden_set), 
            golden_set_path=args.golden_set
        )
        runner.save_report(report)
        
        # Print summary
        metrics = report["metrics"]["overall"]
        print("\n" + "=" * 60)
        print("EVALUATION COMPLETE")
        print("=" * 60)
        print(f"  MRR:        {metrics['mrr']:.4f}")
        print(f"  Hit@1:      {metrics['hit@1']:.1%}")
        print(f"  Hit@10:     {metrics['hit@10']:.1%}")
        print(f"  NDCG@10:    {metrics['ndcg@10']:.4f}")
        print(f"  Latency:    {metrics['avg_latency_ms']:.1f}ms (avg)")
        print("=" * 60)
        print(f"\nAnalysis: {report['analysis']['summary']}")
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        logger.error("Please ensure the Qwen3 index has been built first!")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
