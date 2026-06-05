#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAISS-Only Retrieval Evaluation Script

This script evaluates RAG retrieval using ONLY FAISS vector search.
No Reranker is used - pure semantic embedding retrieval.

Design Philosophy:
==================
1. **FAISS = Semantic Search** - Uses Qwen3-Embedding to encode queries
2. **No Reranker** - Tests pure vector similarity without cross-encoder
3. **Complement to BM25+Reranker** - Shows semantic vs keyword matching difference

Strategies:
===========
1. **faiss_only**: Pure FAISS vector search (baseline)
2. **faiss_hybrid**: FAISS + BM25 score fusion (no reranking)
3. **faiss_query_expansion**: Query Rewriting + FAISS (enhanced recall)

Comparison with bm25_reranker_eval.py:
=====================================
- BM25+Reranker: Keyword matching → Neural reranking
- FAISS-Only: Pure semantic similarity
- This helps answer: "Is semantic similarity alone sufficient?"

Usage:
    python scripts/rag/evaluation/faiss_retrieval_eval.py
    python scripts/rag/evaluation/faiss_retrieval_eval.py --strategy all
    python scripts/rag/evaluation/faiss_retrieval_eval.py --samples-per-type 5

Author: ML Engineer
Date: 2026-02-02
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
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

# Load environment variables
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

# Import shared modules
from shared.query_generator import SimpleQueryGenerator, QuerySample, RetrievalResult
from shared.score_fusion import reciprocal_rank_fusion

# ============================================================================
# Configuration
# ============================================================================

CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"
INDEX_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunks_qwen3.index"
MAPPING_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "reports" / "retrieval_eval"
EMBEDDING_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Embedding-0.6B"

# OpenRouter API for Query Expansion
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "qwen/qwen-2.5-72b-instruct"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Evaluation Settings
DEFAULT_SAMPLES_PER_TYPE = 5
TOP_K_VALUES = [1, 5, 10, 20]
RANDOM_SEED = 42

# RRF Fusion Constant (k=60 is industry standard)
RRF_K = 60

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress HTTP logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# NOTE: QuerySample and RetrievalResult are imported from shared.query_generator


# ============================================================================
# FAISS Embedding Retriever (GPU-based)
# ============================================================================

class FAISSRetriever:
    """FAISS vector retriever using Qwen3-Embedding."""
    
    def __init__(self, chunks_lookup: Dict[str, Dict]):
        self.chunks_lookup = chunks_lookup
        self.index = None
        self.mapping = None
        self.encoder = None
        self.tokenizer = None
        self.device = None
    
    def load(self):
        """Load FAISS index and embedding model."""
        import torch
        from transformers import AutoModel, AutoTokenizer
        
        # Check GPU
        if torch.cuda.is_available():
            self.device = "cuda:0"
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            logger.info(f"GPU available: {torch.cuda.get_device_name(0)}")
            logger.info(f"Total VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            self.device = "cpu"
            logger.warning("No GPU available, using CPU (will be slow)")
        
        # Load FAISS index
        logger.info(f"Loading FAISS index from {INDEX_PATH}...")
        self.index = faiss.read_index(str(INDEX_PATH))
        logger.info(f"FAISS index loaded: {self.index.ntotal} vectors")
        
        # Load mapping
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            self.mapping = json.load(f)
        
        # Load embedding model
        logger.info("Loading Qwen3-Embedding model...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            EMBEDDING_MODEL_PATH, trust_remote_code=True
        )
        
        # Robust padding token handling
        if self.tokenizer.pad_token is None:
            if self.tokenizer.eos_token is not None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            else:
                logger.warning("No PAD or EOS token found. Setting PAD to <|endoftext|> or [PAD].")
                special_tokens = self.tokenizer.all_special_tokens
                if special_tokens:
                    self.tokenizer.pad_token = special_tokens[0]
                else:
                    self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        
        self.encoder = AutoModel.from_pretrained(
            EMBEDDING_MODEL_PATH,
            trust_remote_code=True,
            torch_dtype=torch.float16 if self.device == "cuda:0" else torch.float32,
            low_cpu_mem_usage=True
        ).to(self.device)
        self.encoder.eval()
        
        if self.device == "cuda:0":
            mem_used = torch.cuda.memory_allocated() / 1024**3
            logger.info(f"Embedding model loaded. GPU memory used: {mem_used:.2f} GB")
        
        logger.info("FAISS retriever ready!")
    
    def encode_query(self, query: str) -> np.ndarray:
        """Encode query to embedding vector."""
        import torch
        
        batch_dict = self.tokenizer(
            [query], max_length=512, padding=True, truncation=True, return_tensors="pt"
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.encoder(**batch_dict)
            last_hidden = outputs.last_hidden_state
            attention_mask = batch_dict['attention_mask']
            
            # Mean pooling
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
            sum_embeddings = torch.sum(last_hidden * input_mask_expanded, 1).float()
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9).float()
            embedding = sum_embeddings / sum_mask
            embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
        
        return embedding.cpu().numpy().astype('float32')
    
    def retrieve(self, query: str, top_k: int = 50) -> Tuple[List[str], List[float], List[str], float]:
        """Retrieve documents using FAISS."""
        start_time = time.perf_counter()
        
        # Encode query
        encode_start = time.perf_counter()
        query_embedding = self.encode_query(query)
        encode_time = (time.perf_counter() - encode_start) * 1000
        
        # Search FAISS
        search_start = time.perf_counter()
        scores, indices = self.index.search(query_embedding, top_k)
        search_time = (time.perf_counter() - search_start) * 1000
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        # Map to chunk IDs and texts
        chunk_ids = []
        score_list = []
        texts = []
        
        for idx, score in zip(indices[0], scores[0]):
            if idx >= 0:
                chunk_id = self.mapping.get(str(idx), f"unknown_{idx}")
                chunk_ids.append(chunk_id)
                score_list.append(float(score))
                
                chunk_data = self.chunks_lookup.get(chunk_id, {})
                texts.append(chunk_data.get('text', ''))
        
        return chunk_ids, score_list, texts, total_time
    
    def unload(self):
        """Unload model to free memory."""
        import torch
        
        if self.encoder is not None:
            del self.encoder
            del self.tokenizer
            self.encoder = None
            self.tokenizer = None
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Embedding model unloaded, GPU memory freed")


# ============================================================================
# BM25 Retriever (CPU-based, for hybrid)
# ============================================================================

class BM25Retriever:
    """BM25 retriever for hybrid search."""
    
    def __init__(self, chunks: List[Dict]):
        self.chunks = chunks
        self.chunk_ids = [c['chunk_id'] for c in chunks]
        self.chunk_texts = [c.get('text', '') for c in chunks]
        self.bm25 = None
        self._build_index()
    
    def _build_index(self):
        """Build BM25 index."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank_bm25 not installed. Hybrid search disabled.")
            return
        
        logger.info("Building BM25 index...")
        tokenized_corpus = [list(text) for text in self.chunk_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)
        logger.info(f"BM25 index built with {len(self.chunks)} documents")
    
    def get_scores(self, query: str) -> Dict[str, float]:
        """Get BM25 scores for all documents."""
        if self.bm25 is None:
            return {}
        
        query_tokens = list(query)
        scores = self.bm25.get_scores(query_tokens)
        
        return {cid: float(score) for cid, score in zip(self.chunk_ids, scores)}


# NOTE: SimpleQueryGenerator is imported from shared.query_generator


# ============================================================================
# Evaluation Runner
# ============================================================================

class FAISSEvaluationRunner:
    """Main evaluation runner for FAISS-only strategies."""
    
    def __init__(self, samples_per_type: int = 5, strategies: List[str] = None):
        self.samples_per_type = samples_per_type
        self.strategies = strategies or ["faiss_only", "faiss_hybrid", "faiss_query_expansion"]
        self.chunks = None
        self.chunks_lookup = None
        self.faiss_retriever = None
        self.bm25_retriever = None
        self.llm_client = None
    
    def load_data(self):
        """Load chunks."""
        logger.info(f"Loading chunks from {CHUNKS_PATH}...")
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
        self.chunks_lookup = {c['chunk_id']: c for c in self.chunks}
        logger.info(f"Loaded {len(self.chunks)} chunks")
    
    def initialize(self):
        """Initialize components."""
        # FAISS retriever (GPU-based)
        self.faiss_retriever = FAISSRetriever(self.chunks_lookup)
        self.faiss_retriever.load()
        
        # BM25 retriever for hybrid (CPU-based)
        if "faiss_hybrid" in self.strategies:
            self.bm25_retriever = BM25Retriever(self.chunks)
        
        # LLM client for query expansion
        if "faiss_query_expansion" in self.strategies and OPENROUTER_API_KEY:
            try:
                from openai import OpenAI
                self.llm_client = OpenAI(
                    base_url=OPENROUTER_BASE_URL,
                    api_key=OPENROUTER_API_KEY
                )
                logger.info("LLM client ready for query expansion")
            except Exception as e:
                logger.warning(f"LLM client failed: {e}")
    
    def expand_query(self, query: str) -> List[str]:
        """Generate query variants using LLM."""
        if not self.llm_client:
            return [query]
        
        prompt = f"""將以下查詢改寫成3個不同的搜索查詢：

原始查詢：{query}

每行一個改寫，不要編號："""

        try:
            response = self.llm_client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.5
            )
            variants = response.choices[0].message.content.strip().split('\n')
            variants = [v.strip() for v in variants if v.strip()]
            return [query] + variants[:3]
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")
            return [query]
    
    def run_faiss_only(self, query: str, top_k: int = 10) -> Tuple[List[str], List[float], float, Dict]:
        """Strategy 1: Pure FAISS search."""
        start_time = time.perf_counter()
        
        chunk_ids, scores, _, faiss_time = self.faiss_retriever.retrieve(query, top_k)
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        breakdown = {
            "faiss_ms": faiss_time,
            "total_ms": total_time
        }
        
        return chunk_ids, scores, total_time, breakdown
    
    def run_faiss_hybrid(self, query: str, top_k: int = 10) -> Tuple[List[str], List[float], float, Dict]:
        """
        Strategy 2: FAISS + BM25 hybrid using Reciprocal Rank Fusion (RRF).
        
        RRF is more robust than weighted score fusion because:
        - It uses rank positions, not raw scores
        - No need for score normalization
        - Works well with different score distributions (vector vs keyword)
        
        Reference: Cormack et al., SIGIR 2009
        """
        start_time = time.perf_counter()
        
        # FAISS retrieval (top 50 candidates)
        faiss_start = time.perf_counter()
        faiss_ids, faiss_scores, _, _ = self.faiss_retriever.retrieve(query, top_k=50)
        faiss_time = (time.perf_counter() - faiss_start) * 1000
        
        # BM25 retrieval (get ranked list)
        bm25_start = time.perf_counter()
        if self.bm25_retriever:
            bm25_all_scores = self.bm25_retriever.get_scores(query)
            # Convert to ranked list (top 50)
            bm25_ranked = sorted(bm25_all_scores.items(), key=lambda x: x[1], reverse=True)[:50]
        else:
            bm25_ranked = []
        bm25_time = (time.perf_counter() - bm25_start) * 1000
        
        # Prepare ranked lists for RRF
        faiss_ranking = list(zip(faiss_ids, faiss_scores))
        
        # Apply Reciprocal Rank Fusion
        fusion_start = time.perf_counter()
        fused_results = reciprocal_rank_fusion(
            faiss_ranking,
            bm25_ranked,
            k=60,  # Standard RRF constant
            top_n=top_k
        )
        fusion_time = (time.perf_counter() - fusion_start) * 1000
        
        result_ids = [x[0] for x in fused_results]
        result_scores = [x[1] for x in fused_results]
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        breakdown = {
            "faiss_ms": faiss_time,
            "bm25_ms": bm25_time,
            "rrf_fusion_ms": fusion_time,
            "total_ms": total_time,
            "fusion_method": "RRF (k=60)"
        }
        
        return result_ids, result_scores, total_time, breakdown
    
    def run_faiss_query_expansion(self, query: str, top_k: int = 10) -> Tuple[List[str], List[float], float, Dict]:
        """Strategy 3: Query Expansion + FAISS (multi-query)."""
        start_time = time.perf_counter()
        
        # Expand query
        expand_start = time.perf_counter()
        query_variants = self.expand_query(query)
        expand_time = (time.perf_counter() - expand_start) * 1000
        
        # Multi-query FAISS retrieval
        faiss_start = time.perf_counter()
        all_candidates = {}
        
        for q in query_variants:
            ids, scores, _, _ = self.faiss_retriever.retrieve(q, top_k=30)
            for cid, score in zip(ids, scores):
                if cid not in all_candidates or score > all_candidates[cid]:
                    all_candidates[cid] = score
        
        faiss_time = (time.perf_counter() - faiss_start) * 1000
        
        # Sort and take top-k
        sorted_results = sorted(all_candidates.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        result_ids = [x[0] for x in sorted_results]
        result_scores = [x[1] for x in sorted_results]
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        breakdown = {
            "query_expansion_ms": expand_time,
            "faiss_ms": faiss_time,
            "total_ms": total_time,
            "query_variants": len(query_variants)
        }
        
        return result_ids, result_scores, total_time, breakdown
    
    def compute_metrics(self, queries: List[QuerySample], results: List[RetrievalResult]) -> Dict:
        """Compute evaluation metrics."""
        rr_scores = []
        hit_scores = {k: [] for k in TOP_K_VALUES}
        latencies = []
        
        by_difficulty = defaultdict(lambda: {"rr": [], "hit@10": []})
        by_source = defaultdict(lambda: {"rr": [], "hit@10": []})
        by_query_type = defaultdict(lambda: {"rr": [], "hit@10": []})  # Added for qwen3 compatibility
        
        for query, result in zip(queries, results):
            gt_ids = set(query.ground_truth_chunk_ids)
            retrieved = result.retrieved_chunk_ids
            
            # Find rank
            rank = -1
            for i, cid in enumerate(retrieved):
                if cid in gt_ids:
                    rank = i + 1
                    break
            
            rr = 1.0 / rank if rank > 0 else 0.0
            rr_scores.append(rr)
            
            for k in TOP_K_VALUES:
                hit = 1.0 if 0 < rank <= k else 0.0
                hit_scores[k].append(hit)
            
            latencies.append(result.latency_ms)
            
            by_difficulty[query.difficulty]["rr"].append(rr)
            by_difficulty[query.difficulty]["hit@10"].append(hit_scores[10][-1])
            
            by_source[query.source_type]["rr"].append(rr)
            by_source[query.source_type]["hit@10"].append(hit_scores[10][-1])
            
            # Track by query type (matching qwen3 design)
            by_query_type[query.query_type]["rr"].append(rr)
            by_query_type[query.query_type]["hit@10"].append(hit_scores[10][-1])
        
        # Bootstrap CI for MRR
        def bootstrap_ci(data, n=1000):
            if not data:
                return 0.0, 0.0
            arr = np.array(data)
            means = [np.mean(np.random.choice(arr, len(arr), replace=True)) for _ in range(n)]
            return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
        
        mrr = float(np.mean(rr_scores)) if rr_scores else 0.0
        ci_low, ci_high = bootstrap_ci(rr_scores)
        
        return {
            "overall": {
                "mrr": mrr,
                "mrr_ci_low": ci_low,
                "mrr_ci_high": ci_high,
                "hit@1": float(np.mean(hit_scores[1])) if hit_scores[1] else 0.0,
                "hit@5": float(np.mean(hit_scores[5])) if hit_scores[5] else 0.0,
                "hit@10": float(np.mean(hit_scores[10])) if hit_scores[10] else 0.0,
                "hit@20": float(np.mean(hit_scores[20])) if hit_scores[20] else 0.0,
                "avg_latency_ms": float(np.mean(latencies)) if latencies else 0.0,
                "p95_latency_ms": float(np.percentile(latencies, 95)) if latencies else 0.0,
                "total_queries": len(queries)
            },
            "by_difficulty": {
                d: {
                    "mrr": float(np.mean(v["rr"])) if v["rr"] else 0.0,
                    "hit@10": float(np.mean(v["hit@10"])) if v["hit@10"] else 0.0,
                    "count": len(v["rr"])
                }
                for d, v in by_difficulty.items()
            },
            "by_source_type": {
                s: {
                    "mrr": float(np.mean(v["rr"])) if v["rr"] else 0.0,
                    "hit@10": float(np.mean(v["hit@10"])) if v["hit@10"] else 0.0,
                    "count": len(v["rr"])
                }
                for s, v in by_source.items()
            },
            "by_query_type": {
                qt: {
                    "mrr": float(np.mean(v["rr"])) if v["rr"] else 0.0,
                    "hit@10": float(np.mean(v["hit@10"])) if v["hit@10"] else 0.0,
                    "count": len(v["rr"])
                }
                for qt, v in by_query_type.items()
            }
        }
    
    def run_evaluation(self) -> Dict:
        """Run complete evaluation."""
        # Load data
        self.load_data()
        self.initialize()
        
        # Generate queries
        generator = SimpleQueryGenerator(self.chunks, self.samples_per_type)
        queries = generator.generate_queries()
        
        # Run each strategy
        all_metrics = {}
        
        for strategy in self.strategies:
            logger.info(f"\n{'='*60}")
            logger.info(f"Evaluating: {strategy}")
            logger.info(f"{'='*60}")
            
            results = []
            
            for query in tqdm(queries, desc=f"Evaluating {strategy}"):
                try:
                    if strategy == "faiss_only":
                        ids, scores, latency, breakdown = self.run_faiss_only(query.query_text)
                    elif strategy == "faiss_hybrid":
                        ids, scores, latency, breakdown = self.run_faiss_hybrid(query.query_text)
                    else:  # faiss_query_expansion
                        ids, scores, latency, breakdown = self.run_faiss_query_expansion(query.query_text)
                    
                    results.append(RetrievalResult(
                        query_id=query.query_id,
                        strategy=strategy,
                        retrieved_chunk_ids=ids,
                        retrieved_scores=scores,
                        latency_ms=latency,
                        latency_breakdown=breakdown
                    ))
                    
                except Exception as e:
                    logger.error(f"Error on {query.query_id}: {e}")
                    results.append(RetrievalResult(
                        query_id=query.query_id,
                        strategy=strategy,
                        retrieved_chunk_ids=[],
                        retrieved_scores=[],
                        latency_ms=0.0
                    ))
            
            # Compute metrics
            metrics = self.compute_metrics(queries, results)
            all_metrics[strategy] = metrics
        
        # Generate report
        report = {
            "report_date": datetime.now().isoformat(),
            "config": {
                "samples_per_type": self.samples_per_type,
                "strategies": self.strategies,
                "total_queries": len(queries),
                "total_chunks": len(self.chunks),
                "retrieval_type": "FAISS (Semantic Vector Search)"
            },
            "metrics": all_metrics,
            "comparison": self._compare_strategies(all_metrics)
        }
        
        return report
    
    def _compare_strategies(self, metrics: Dict) -> Dict:
        """Compare strategies."""
        comparison = []
        
        for strategy, data in metrics.items():
            overall = data["overall"]
            comparison.append({
                "strategy": strategy,
                "mrr": overall["mrr"],
                "mrr_ci": f"{overall['mrr_ci_low']:.3f}-{overall['mrr_ci_high']:.3f}",
                "hit@10": overall["hit@10"],
                "latency_ms": overall["avg_latency_ms"]
            })
        
        comparison.sort(key=lambda x: x["mrr"], reverse=True)
        return {"ranking": comparison}
    
    def save_report(self, report: Dict):
        """Save report."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON
        json_path = OUTPUT_DIR / f"faiss_eval_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Report saved: {json_path}")
        
        # Markdown
        md_path = OUTPUT_DIR / f"faiss_eval_{timestamp}.md"
        md_content = self._generate_markdown(report)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        logger.info(f"Markdown saved: {md_path}")
        
        return json_path
    
    def _generate_markdown(self, report: Dict) -> str:
        """Generate markdown report."""
        lines = [
            "# FAISS-Only Retrieval Evaluation Report",
            "",
            f"**Date**: {report['report_date']}",
            f"**Retrieval Type**: {report['config']['retrieval_type']}",
            f"**Total Queries**: {report['config']['total_queries']}",
            f"**Strategies**: {', '.join(report['config']['strategies'])}",
            "",
            "---",
            "",
            "## Strategy Comparison",
            "",
            "| Strategy | MRR (95% CI) | Hit@10 | Avg Latency |",
            "|----------|--------------|--------|-------------|"
        ]
        
        for item in report["comparison"]["ranking"]:
            lines.append(
                f"| {item['strategy']} | {item['mrr']:.4f} ({item['mrr_ci']}) | "
                f"{item['hit@10']:.1%} | {item['latency_ms']:.0f}ms |"
            )
        
        # Details by strategy
        for strategy, data in report["metrics"].items():
            overall = data["overall"]
            lines.extend([
                "",
                f"## {strategy}",
                "",
                f"- **MRR**: {overall['mrr']:.4f} (95% CI: {overall['mrr_ci_low']:.3f}-{overall['mrr_ci_high']:.3f})",
                f"- **Hit@1**: {overall['hit@1']:.1%}",
                f"- **Hit@5**: {overall['hit@5']:.1%}",
                f"- **Hit@10**: {overall['hit@10']:.1%}",
                f"- **Avg Latency**: {overall['avg_latency_ms']:.1f}ms",
                "",
                "### By Difficulty",
                "",
                "| Difficulty | MRR | Hit@10 | Count |",
                "|------------|-----|--------|-------|"
            ])
            
            for diff, info in data.get("by_difficulty", {}).items():
                lines.append(f"| {diff} | {info['mrr']:.4f} | {info['hit@10']:.1%} | {info['count']} |")
        
        return "\n".join(lines)
    
    def cleanup(self):
        """Cleanup resources."""
        if self.faiss_retriever:
            self.faiss_retriever.unload()


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="FAISS-Only Retrieval Evaluation")
    parser.add_argument(
        "--strategy",
        choices=["faiss_only", "faiss_hybrid", "faiss_query_expansion", "all"],
        default="all",
        help="Strategy to evaluate"
    )
    parser.add_argument(
        "--samples-per-type",
        type=int,
        default=DEFAULT_SAMPLES_PER_TYPE,
        help=f"Samples per source type (default: {DEFAULT_SAMPLES_PER_TYPE})"
    )
    args = parser.parse_args()
    
    # Determine strategies
    if args.strategy == "all":
        strategies = ["faiss_only", "faiss_hybrid", "faiss_query_expansion"]
    else:
        strategies = [args.strategy]
    
    logger.info("=" * 70)
    logger.info("FAISS-Only Retrieval Evaluation (Semantic Vector Search)")
    logger.info("=" * 70)
    logger.info(f"Strategies: {strategies}")
    logger.info(f"Samples per type: {args.samples_per_type}")
    
    runner = FAISSEvaluationRunner(
        samples_per_type=args.samples_per_type,
        strategies=strategies
    )
    
    try:
        report = runner.run_evaluation()
        runner.save_report(report)
        
        # Print summary
        print("\n" + "=" * 70)
        print("EVALUATION COMPLETE")
        print("=" * 70)
        
        for item in report["comparison"]["ranking"]:
            print(f"\n{item['strategy'].upper()}:")
            print(f"  MRR:      {item['mrr']:.4f} ({item['mrr_ci']})")
            print(f"  Hit@10:   {item['hit@10']:.1%}")
            print(f"  Latency:  {item['latency_ms']:.0f}ms")
        
        print("=" * 70)
        
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        runner.cleanup()


if __name__ == "__main__":
    main()
