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
   - 經典 (Classical Texts): Analects, Mencius, etc.
   - 紅樓夢 (Dream of Red Chamber)
   - 考試 (Examination Questions)
   - 學術分析 (Academic Analysis)
   - 維基 (Wikipedia)
   - 結構化內容 (Structured Content)

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
CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "hybrid_smart_chunks.json"
INDEX_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunks_qwen3.index"
MAPPING_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json"
METADATA_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "index_metadata_qwen3.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "reports" / "retrieval_eval"
MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Embedding-0.6B"

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
    source_type: str  # 經典, 紅樓夢, etc.
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
        for chunk in self.chunks:
            source_type = chunk.get('source_type', 'unknown')
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
        chunk_id = chunk['chunk_id']
        doc_id = chunk.get('doc_id', chunk_id)
        keywords = chunk.get('keywords', [])
        summary = chunk.get('summary', '')
        text = chunk.get('text', '')
        
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
        
        return queries


# ============================================================================
# Retriever (FAISS + Qwen3)
# ============================================================================

class Qwen3Retriever:
    """Retriever using Qwen3 embeddings and FAISS index."""
    
    def __init__(self):
        self.index = None
        self.mapping = None
        self.metadata = None
        self.encoder = None
        self.tokenizer = None
        self.device = "cuda:0" if self._check_cuda() else "cpu"
        
    def _check_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False
    
    def load_index(self):
        """Load FAISS index and mappings."""
        logger.info("Loading FAISS index...")
        
        if not INDEX_PATH.exists():
            raise FileNotFoundError(f"Index not found: {INDEX_PATH}")
        
        self.index = faiss.read_index(str(INDEX_PATH))
        logger.info(f"Loaded index with {self.index.ntotal} vectors")
        
        # Load mapping
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            self.mapping = json.load(f)
            
        # Load metadata
        with open(METADATA_PATH, 'r', encoding='utf-8') as f:
            self.metadata = json.load(f)
            
        logger.info("Index and mappings loaded successfully")
    
    def load_encoder(self):
        """Load Qwen3 encoder for query embedding."""
        logger.info("Loading Qwen3 encoder...")
        
        import torch
        from transformers import AutoModel, AutoTokenizer
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_PATH, 
            trust_remote_code=True
        )
        self.encoder = AutoModel.from_pretrained(
            MODEL_PATH,
            trust_remote_code=True,
            torch_dtype=torch.float16 if self.device != "cpu" else torch.float32
        ).to(self.device)
        self.encoder.eval()
        
        logger.info(f"Encoder loaded on {self.device}")
    
    def encode_query(self, query: str) -> np.ndarray:
        """Encode a single query to embedding."""
        import torch
        
        batch_dict = self.tokenizer(
            [query],
            max_length=512,
            padding=True,
            truncation=True,
            return_tensors="pt"
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.encoder(**batch_dict)
            last_hidden = outputs.last_hidden_state
            attention_mask = batch_dict['attention_mask']
            
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
            sum_embeddings = torch.sum(last_hidden * input_mask_expanded, 1).float()
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9).float()
            embedding = sum_embeddings / sum_mask
            embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
        
        return embedding.cpu().numpy().astype('float32')
    
    def retrieve(self, query: str, top_k: int = 50) -> Tuple[List[str], List[float], float]:
        """
        Retrieve top-k chunks for a query.
        
        Returns:
            chunk_ids: List of retrieved chunk IDs
            scores: List of similarity scores
            latency_ms: Query latency in milliseconds
        """
        start_time = time.perf_counter()
        
        # Encode query
        query_embedding = self.encode_query(query)
        
        # Search
        scores, indices = self.index.search(query_embedding, top_k)
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Map indices to chunk IDs
        chunk_ids = []
        score_list = []
        for idx, score in zip(indices[0], scores[0]):
            if idx >= 0:  # Valid index
                chunk_id = self.mapping.get(str(idx), f"unknown_{idx}")
                chunk_ids.append(chunk_id)
                score_list.append(float(score))
        
        return chunk_ids, score_list, latency_ms


# ============================================================================
# Metrics Calculator
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
        
    def load_data(self):
        """Load chunks data."""
        logger.info(f"Loading chunks from {CHUNKS_PATH}...")
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
        logger.info(f"Loaded {len(self.chunks)} chunks")
        
    def run_evaluation(self) -> Dict[str, Any]:
        """Run the complete evaluation pipeline."""
        
        # Step 1: Load data
        self.load_data()
        
        # Step 2: Initialize retriever
        self.retriever = Qwen3Retriever()
        self.retriever.load_index()
        self.retriever.load_encoder()
        
        # Step 3: Generate queries
        query_generator = QueryGenerator(self.chunks, self.samples_per_type)
        queries = query_generator.generate_queries()
        
        # Step 4: Run retrieval
        logger.info("Running retrieval evaluation...")
        results = []
        
        for query in tqdm(queries, desc="Evaluating"):
            chunk_ids, scores, latency = self.retriever.retrieve(query.query_text, top_k=50)
            results.append(RetrievalResult(
                query_id=query.query_id,
                retrieved_chunk_ids=chunk_ids,
                retrieved_scores=scores,
                latency_ms=latency
            ))
            
            if self.verbose:
                gt_set = set(query.ground_truth_chunk_ids)
                hit = any(c in gt_set for c in chunk_ids[:10])
                logger.debug(f"Query: {query.query_text[:30]}... | Hit@10: {hit}")
        
        # Step 5: Compute metrics
        logger.info("Computing metrics...")
        metrics = self.metrics_calculator.compute_all_metrics(queries, results)
        
        # Step 6: Generate report
        report = self._generate_report(metrics, queries, results)
        
        return report
    
    def _generate_report(
        self, 
        metrics: Dict, 
        queries: List[QuerySample],
        results: List[RetrievalResult]
    ) -> Dict[str, Any]:
        """Generate comprehensive evaluation report."""
        
        report = {
            "report_date": datetime.now().isoformat(),
            "evaluation_config": {
                "samples_per_type": self.samples_per_type,
                "top_k_values": TOP_K_VALUES,
                "total_chunks": len(self.chunks),
                "index_size": self.retriever.index.ntotal,
                "device": self.retriever.device
            },
            "metrics": metrics,
            "analysis": self._generate_analysis(metrics),
            "sample_results": self._get_sample_results(queries, results, n=10)
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
        
        return "\n".join(lines)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Evaluate Qwen3 RAG Retrieval")
    parser.add_argument("--samples-per-type", type=int, default=DEFAULT_SAMPLES_PER_TYPE,
                       help=f"Number of samples per source type (default: {DEFAULT_SAMPLES_PER_TYPE})")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Qwen3 RAG Retrieval Evaluation")
    logger.info("=" * 60)
    
    runner = EvaluationRunner(
        samples_per_type=args.samples_per_type,
        verbose=args.verbose
    )
    
    try:
        report = runner.run_evaluation()
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
