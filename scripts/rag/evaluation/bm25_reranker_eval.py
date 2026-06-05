#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lightweight Reranker Evaluation Script (GPU-Friendly)

This script evaluates RAG retrieval WITHOUT loading Embedding model.
Designed for 4GB VRAM GPUs (GTX 1650).

Key Design Decisions:
====================
1. **No Embedding Model** - Uses BM25 (CPU-based) for candidate retrieval
2. **Single GPU Model** - Only Qwen3-Reranker loaded on GPU
3. **Memory-Efficient** - Small batch sizes, aggressive cache clearing
4. **Two Strategies**:
   - bm25_reranker: BM25 → Reranker
   - full_pipeline: Query Rewriting → BM25 → Reranker

Why BM25 instead of FAISS?
==========================
- FAISS needs query embeddings → requires Embedding model
- BM25 uses keyword matching → no GPU needed
- For ancient Chinese text, BM25 actually works well due to character-level matching

Usage:
    python scripts/rag/evaluation/lightweight_reranker_eval.py
    python scripts/rag/evaluation/lightweight_reranker_eval.py --strategy all
    python scripts/rag/evaluation/lightweight_reranker_eval.py --samples-per-type 5

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

# ============================================================================
# Configuration
# ============================================================================

CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "reports" / "retrieval_eval"
RERANKER_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Reranker-0.6B"

# OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "qwen/qwen-2.5-72b-instruct"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Evaluation Settings
DEFAULT_SAMPLES_PER_TYPE = 5
TOP_K_VALUES = [1, 5, 10, 20]
RANDOM_SEED = 42

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
# BM25 Retriever (CPU-based, no GPU needed)
# ============================================================================

class BM25Retriever:
    """BM25-based retriever using character-level tokenization for Chinese."""
    
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
            logger.error("rank_bm25 not installed. Run: pip install rank-bm25")
            raise
        
        logger.info("Building BM25 index...")
        
        # Character-level tokenization for Chinese text
        tokenized_corpus = [list(text) for text in self.chunk_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        logger.info(f"BM25 index built with {len(self.chunks)} documents")
    
    def retrieve(self, query: str, top_k: int = 50) -> Tuple[List[str], List[float], List[str], float]:
        """Retrieve top-k candidates using BM25."""
        start_time = time.perf_counter()
        
        # Handle empty or whitespace-only queries
        query = query.strip() if query else ""
        if not query:
            logger.warning("Empty query received, returning empty results")
            return [], [], [], 0.0
        
        # Character-level tokenization
        query_tokens = list(query)
        
        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)
        
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        # Collect results
        chunk_ids = [self.chunk_ids[i] for i in top_indices]
        score_list = [float(scores[i]) for i in top_indices]
        texts = [self.chunk_texts[i] for i in top_indices]
        
        latency = (time.perf_counter() - start_time) * 1000
        
        return chunk_ids, score_list, texts, latency


# ============================================================================
# Reranker (GPU-based, memory-efficient)
# ============================================================================

class LightweightReranker:
    """Memory-efficient Qwen3-Reranker for 4GB VRAM."""
    
    def __init__(self):
        self.reranker = None
        self.tokenizer = None
        self.device = None
    
    def load(self):
        """Load reranker with memory optimization."""
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        
        # Check GPU
        if torch.cuda.is_available():
            self.device = "cuda:0"
            # Clear GPU memory first
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            logger.info(f"GPU available: {torch.cuda.get_device_name(0)}")
            logger.info(f"Total VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
        else:
            self.device = "cpu"
            logger.warning("No GPU available, using CPU (will be slow)")
        
        logger.info("Loading Qwen3-Reranker...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            RERANKER_MODEL_PATH, 
            trust_remote_code=True
        )
        
        # Robust padding token handling
        if self.tokenizer.pad_token is None:
            if self.tokenizer.eos_token is not None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
                self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
            else:
                # Fallback: try common special tokens or add one
                logger.warning("No PAD or EOS token found. Setting PAD to <|endoftext|> or first special token.")
                special_tokens = self.tokenizer.all_special_tokens
                if special_tokens:
                    self.tokenizer.pad_token = special_tokens[0]
                    # Manually set pad_token_id
                    self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids(special_tokens[0])
                else:
                    self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
        
        # Force pad_token_id update if still None
        if self.tokenizer.pad_token_id is None and self.tokenizer.pad_token is not None:
            self.tokenizer.pad_token_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.pad_token)
                    
        # CRITICAL: Verify pad_token_id is actually set
        if self.tokenizer.pad_token_id is None:
            raise ValueError(
                f"Failed to set pad_token_id for tokenizer. "
                f"Available special tokens: {self.tokenizer.all_special_tokens}"
            )
        
        logger.info(f"✅ Padding token configured: '{self.tokenizer.pad_token}' (ID: {self.tokenizer.pad_token_id})")
        
        # Set padding side (important for some models)
        self.tokenizer.padding_side = 'right'
        
        # Load model with memory optimization
        # CRITICAL FIX: Pass pad_token_id to from_pretrained to set model.config.pad_token_id
        self.reranker = AutoModelForSequenceClassification.from_pretrained(
            RERANKER_MODEL_PATH,
            trust_remote_code=True,
            torch_dtype=torch.float16 if self.device == "cuda:0" else torch.float32,
            low_cpu_mem_usage=True,  # Memory optimization
            pad_token_id=self.tokenizer.pad_token_id  # CRITICAL: Set on model config
        ).to(self.device)
        
        # Double-check: Ensure model.config.pad_token_id is set
        # (Some models may not respect the from_pretrained argument)
        if self.reranker.config.pad_token_id is None:
            self.reranker.config.pad_token_id = self.tokenizer.pad_token_id
            logger.info(f"Force set model.config.pad_token_id = {self.reranker.config.pad_token_id}")
        
        logger.info(f"✅ Model config pad_token_id: {self.reranker.config.pad_token_id}")
        
        # Resize token embeddings if we added new tokens
        original_vocab_size = self.reranker.config.vocab_size
        current_vocab_size = len(self.tokenizer)
        if current_vocab_size > original_vocab_size:
            logger.info(f"Resizing model embeddings from {original_vocab_size} to {current_vocab_size}...")
            self.reranker.resize_token_embeddings(current_vocab_size)
        
        self.reranker.eval()
        
        if self.device == "cuda:0":
            mem_used = torch.cuda.memory_allocated() / 1024**3
            logger.info(f"Reranker loaded. GPU memory used: {mem_used:.2f} GB")
        
        logger.info("Reranker ready!")
    
    def rerank(
        self, 
        query: str, 
        chunk_ids: List[str], 
        texts: List[str], 
        top_k: int = 10
    ) -> Tuple[List[str], List[float], List[str], float]:
        """Rerank candidates with OOM protection."""
        import torch
        
        if not texts:
            return [], [], [], 0.0
        
        # Double-check padding token is set (defensive programming)
        if self.tokenizer.pad_token_id is None:
            logger.error("CRITICAL: pad_token_id is None in rerank method!")
            logger.error(f"Tokenizer state: pad_token={self.tokenizer.pad_token}, eos_token={self.tokenizer.eos_token}")
            # Emergency fix
            if self.tokenizer.eos_token_id is not None:
                self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
                logger.warning(f"Emergency fix: set pad_token_id to eos_token_id ({self.tokenizer.eos_token_id})")
            else:
                raise ValueError("Cannot proceed without a valid pad_token_id")
        
        start_time = time.perf_counter()
        
        # Prepare pairs
        pairs = [[query, text[:1000]] for text in texts]  # Truncate long texts
        
        scores = []
        batch_size = 2  # Very small batch for 4GB VRAM
        
        with torch.no_grad():
            for i in range(0, len(pairs), batch_size):
                batch_pairs = pairs[i:i+batch_size]
                
                try:
                    inputs = self.tokenizer(
                        batch_pairs,
                        padding=True,
                        truncation=True,
                        max_length=512,
                        return_tensors="pt"
                    ).to(self.device)
                    
                    outputs = self.reranker(**inputs)
                    
                    # Extract logits
                    if hasattr(outputs, 'logits'):
                        logits = outputs.logits.cpu().numpy()
                    else:
                        logits = outputs[0].cpu().numpy()
                    
                    # Handle different output shapes:
                    # - Shape [batch, 1]: regression/single score -> squeeze to [batch]
                    # - Shape [batch, 2]: binary classification -> take positive class (index 1)
                    # - Shape [batch]: already 1D scores
                    if logits.ndim == 2:
                        if logits.shape[1] == 1:
                            # Single score per sample, squeeze
                            batch_scores = logits.squeeze(-1)
                        elif logits.shape[1] == 2:
                            # Binary classification: use positive class logit (index 1)
                            # Or use softmax difference: logits[:, 1] - logits[:, 0]
                            batch_scores = logits[:, 1]  # Positive class score
                        else:
                            # Multi-class: take max or first
                            batch_scores = logits[:, 0]
                    else:
                        # Already 1D
                        batch_scores = logits
                    
                    # Convert to list and handle NaN
                    if batch_scores.ndim == 0:
                        # Single scalar
                        score_val = float(batch_scores)
                        scores.append(0.0 if np.isnan(score_val) else score_val)
                    else:
                        # Array of scores
                        for s in batch_scores:
                            score_val = float(s)
                            scores.append(0.0 if np.isnan(score_val) else score_val)
                    
                    # Clean up to prevent memory accumulation
                    del batch_scores, logits
                    
                    # Aggressive memory cleanup
                    del inputs, outputs
                    if self.device == "cuda:0":
                        torch.cuda.empty_cache()
                        
                except (RuntimeError, ValueError) as e:
                    error_msg = str(e).lower()
                    if "out of memory" in error_msg:
                        logger.warning(f"OOM at batch {i}, assigning zero scores")
                        scores.extend([0.0] * len(batch_pairs))
                        if self.device == "cuda:0":
                            torch.cuda.empty_cache()
                    elif "padding token" in error_msg or "batch sizes" in error_msg:
                        logger.error(f"Padding token error at batch {i}: {e}")
                        logger.error("This should not happen. Tokenizer pad_token_id might not be properly set.")
                        raise  # Re-raise to fail fast
                    else:
                        raise
        
        latency = (time.perf_counter() - start_time) * 1000
        
        # Sort by scores
        scored_items = list(zip(chunk_ids, scores, texts))
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        reranked_ids = [x[0] for x in scored_items[:top_k]]
        reranked_scores = [float(x[1]) for x in scored_items[:top_k]]
        reranked_texts = [x[2] for x in scored_items[:top_k]]
        
        return reranked_ids, reranked_scores, reranked_texts, latency
    
    def unload(self):
        """Unload model to free memory."""
        import torch
        
        if self.reranker is not None:
            del self.reranker
            del self.tokenizer
            self.reranker = None
            self.tokenizer = None
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Reranker unloaded, GPU memory freed")


# NOTE: SimpleQueryGenerator is imported from shared.query_generator


# ============================================================================
# Evaluation Runner
# ============================================================================

class LightweightEvaluationRunner:
    """Main evaluation runner."""
    
    def __init__(self, samples_per_type: int = 5, strategies: List[str] = None):
        self.samples_per_type = samples_per_type
        self.strategies = strategies or ["bm25_reranker", "full_pipeline"]
        self.chunks = None
        self.bm25_retriever = None
        self.reranker = None
        self.llm_client = None
    
    def load_data(self):
        """Load chunks."""
        logger.info(f"Loading chunks from {CHUNKS_PATH}...")
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
        logger.info(f"Loaded {len(self.chunks)} chunks")
    
    def initialize(self):
        """Initialize components."""
        # BM25 (CPU-based, can stay in memory)
        self.bm25_retriever = BM25Retriever(self.chunks)
        
        # Reranker (GPU-based)
        self.reranker = LightweightReranker()
        self.reranker.load()
        
        # LLM client for query rewriting
        if "full_pipeline" in self.strategies and OPENROUTER_API_KEY:
            try:
                from openai import OpenAI
                self.llm_client = OpenAI(
                    base_url=OPENROUTER_BASE_URL,
                    api_key=OPENROUTER_API_KEY
                )
                logger.info("LLM client ready for query rewriting")
            except Exception as e:
                logger.warning(f"LLM client failed: {e}")
    
    def rewrite_query(self, query: str) -> List[str]:
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
                temperature=0.5,
                timeout=30.0  # Add timeout to prevent hanging
            )
            variants = response.choices[0].message.content.strip().split('\n')
            variants = [v.strip() for v in variants if v.strip()]
            return [query] + variants[:3]
        except TimeoutError:
            logger.warning(f"Query rewrite timed out, using original query")
            return [query]
        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}")
            return [query]
    
    def run_bm25_reranker(self, query: str, top_k: int = 10) -> Tuple[List[str], List[float], float, Dict]:
        """Strategy 1: BM25 + Reranker"""
        start_time = time.perf_counter()
        
        # BM25 retrieval
        bm25_start = time.perf_counter()
        chunk_ids, _, texts, _ = self.bm25_retriever.retrieve(query, top_k=30)
        bm25_time = (time.perf_counter() - bm25_start) * 1000
        
        # Reranking
        rerank_start = time.perf_counter()
        reranked_ids, reranked_scores, _, rerank_time = self.reranker.rerank(
            query, chunk_ids, texts, top_k
        )
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        breakdown = {
            "bm25_ms": bm25_time,
            "rerank_ms": rerank_time,
            "total_ms": total_time
        }
        
        return reranked_ids, reranked_scores, total_time, breakdown
    
    def run_full_pipeline(self, query: str, top_k: int = 10) -> Tuple[List[str], List[float], float, Dict]:
        """Strategy 2: Query Rewriting + BM25 + Reranker"""
        start_time = time.perf_counter()
        
        # Query rewriting
        rewrite_start = time.perf_counter()
        query_variants = self.rewrite_query(query)
        rewrite_time = (time.perf_counter() - rewrite_start) * 1000
        
        # Multi-query BM25
        bm25_start = time.perf_counter()
        all_candidates = {}  # chunk_id -> best_score
        
        for q in query_variants:
            ids, scores, texts, _ = self.bm25_retriever.retrieve(q, top_k=20)
            for cid, score in zip(ids, scores):
                if cid not in all_candidates or score > all_candidates[cid]:
                    all_candidates[cid] = score
        
        # Sort and get top candidates
        sorted_candidates = sorted(all_candidates.items(), key=lambda x: x[1], reverse=True)[:30]
        candidate_ids = [x[0] for x in sorted_candidates]
        
        # Get texts for reranking
        chunk_lookup = {c['chunk_id']: c.get('text', '') for c in self.chunks}
        candidate_texts = [chunk_lookup.get(cid, '') for cid in candidate_ids]
        
        bm25_time = (time.perf_counter() - bm25_start) * 1000
        
        # Reranking
        rerank_start = time.perf_counter()
        reranked_ids, reranked_scores, _, rerank_time = self.reranker.rerank(
            query, candidate_ids, candidate_texts, top_k
        )
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        breakdown = {
            "query_rewrite_ms": rewrite_time,
            "bm25_ms": bm25_time,
            "rerank_ms": rerank_time,
            "total_ms": total_time,
            "query_variants": len(query_variants)
        }
        
        return reranked_ids, reranked_scores, total_time, breakdown
    
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
            by_difficulty[query.difficulty]["hit@10"].append(hit_scores[10][-1] if 10 in hit_scores else 0)
            
            by_source[query.source_type]["rr"].append(rr)
            by_source[query.source_type]["hit@10"].append(hit_scores[10][-1] if 10 in hit_scores else 0)            
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
                    if strategy == "bm25_reranker":
                        ids, scores, latency, breakdown = self.run_bm25_reranker(query.query_text)
                    else:  # full_pipeline
                        ids, scores, latency, breakdown = self.run_full_pipeline(query.query_text)
                    
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
                    logger.error(f"Query text: {query.query_text[:100]}")
                    import traceback
                    logger.error(f"Traceback:\n{traceback.format_exc()}")
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
                "total_chunks": len(self.chunks)
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
        json_path = OUTPUT_DIR / f"lightweight_eval_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Report saved: {json_path}")
        
        # Markdown
        md_path = OUTPUT_DIR / f"lightweight_eval_{timestamp}.md"
        md_content = self._generate_markdown(report)
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        logger.info(f"Markdown saved: {md_path}")
        
        return json_path
    
    def _generate_markdown(self, report: Dict) -> str:
        """Generate markdown report."""
        lines = [
            "# Lightweight Reranker Evaluation Report",
            "",
            f"**Date**: {report['report_date']}",
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
        if self.reranker:
            self.reranker.unload()


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Lightweight Reranker Evaluation")
    parser.add_argument(
        "--strategy",
        choices=["bm25_reranker", "full_pipeline", "all"],
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
        strategies = ["bm25_reranker", "full_pipeline"]
    else:
        strategies = [args.strategy]
    
    logger.info("=" * 70)
    logger.info("Lightweight Reranker Evaluation (GPU-Friendly)")
    logger.info("=" * 70)
    logger.info(f"Strategies: {strategies}")
    logger.info(f"Samples per type: {args.samples_per_type}")
    
    runner = LightweightEvaluationRunner(
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
