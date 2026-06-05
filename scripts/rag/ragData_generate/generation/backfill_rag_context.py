"""Batch RAG context backfill using FAISS Hybrid retrieval.

This script retrieves top-3 contexts for each traceable QA sample
using FAISS Hybrid (FAISS + BM25 with RRF Fusion) for RA-DIT data augmentation.

Why FAISS Hybrid:
- Verified S-tier performance (MRR 0.5847, Hit@10 76.7%)
- Combines semantic (FAISS) and keyword (BM25) matching
- RRF fusion is rank-based, robust to score distribution differences

Output:
- backfill_checkpoint.jsonl: Checkpoint file with retrieval results
- backfill_stats.json: Statistics and quality metrics

Reference:
- P3-T02 evaluation results in rag_system_v2_runningData.md
- faiss_retrieval_eval.py for FAISS Hybrid implementation
"""

import os
import sys
import json
import time
import logging
import argparse
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table

# ============================================================================
# Project Setup
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "rag" / "evaluation"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

console = Console()

# Logging config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress verbose logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)

# ============================================================================
# Configuration
# ============================================================================

# Input/Output paths
TRACEABLE_QA_PATH = PROJECT_ROOT / "output" / "p3_t03_backfill" / "traceable_qa.jsonl"
CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"
INDEX_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunks_qwen3.index"
MAPPING_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "p3_t03_backfill"
EMBEDDING_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Embedding-0.6B"

# Retrieval settings
TOP_K = 3  # RA-DIT standard: retrieve k=3 contexts per sample
FAISS_RECALL_K = 50  # FAISS initial recall (for hybrid fusion)
RRF_K = 60  # RRF constant (industry standard)

# Quality tiers based on FAISS similarity scores
QUALITY_TIERS = {
    "tier_1": 0.75,  # High quality: similarity >= 0.75
    "tier_2": 0.65,  # Acceptable: 0.65 <= similarity < 0.75
    "tier_3": 0.0,   # Low quality: similarity < 0.65 (will be filtered)
}

# Checkpoint settings
CHECKPOINT_INTERVAL = 100  # Save every N samples


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RetrievalResult:
    """Single retrieval result with quality metadata."""
    chunk_id: str
    text: str
    similarity_score: float
    quality_tier: str
    rank: int
    source_metadata: Dict[str, Any]


@dataclass
class BackfillRecord:
    """Complete backfill record for one QA sample."""
    qa_id: int
    question: str
    answer: str
    source: str
    original_sample: Dict[str, Any]
    retrieval_results: List[Dict]
    retrieval_time_ms: float
    avg_similarity: float
    quality_summary: Dict[str, int]
    timestamp: str


# ============================================================================
# FAISS Retriever (adapted from faiss_retrieval_eval.py)
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
        
        # Check GPU availability
        if torch.cuda.is_available():
            self.device = "cuda:0"
            torch.cuda.empty_cache()
            console.print(f"[green]GPU detected:[/green] {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            console.print("[yellow]Warning: No GPU, using CPU (slower)[/yellow]")
        
        # Load FAISS index
        console.print(f"Loading FAISS index from {INDEX_PATH}...")
        self.index = faiss.read_index(str(INDEX_PATH))
        console.print(f"FAISS index loaded: {self.index.ntotal} vectors")
        
        # Load ID mapping
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            self.mapping = json.load(f)
        
        # Load embedding model
        console.print("Loading Qwen3-Embedding model...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            EMBEDDING_MODEL_PATH, trust_remote_code=True
        )
        
        # Handle padding token
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        self.encoder = AutoModel.from_pretrained(
            EMBEDDING_MODEL_PATH,
            trust_remote_code=True,
            torch_dtype=torch.float16 if self.device == "cuda:0" else torch.float32,
            low_cpu_mem_usage=True
        ).to(self.device)
        self.encoder.eval()
        
        console.print("[green]✅ FAISS Retriever ready![/green]")
    
    def encode_query(self, query: str) -> np.ndarray:
        """Encode query to embedding vector using mean pooling."""
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
    
    def retrieve(self, query: str, top_k: int = 50) -> Tuple[List[str], List[float], float]:
        """Retrieve documents using FAISS.
        
        Returns:
            (chunk_ids, scores, latency_ms)
        """
        start_time = time.perf_counter()
        
        query_embedding = self.encode_query(query)
        scores, indices = self.index.search(query_embedding, top_k)
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        chunk_ids = []
        score_list = []
        
        for idx, score in zip(indices[0], scores[0]):
            if idx >= 0:
                chunk_id = self.mapping.get(str(idx), f"unknown_{idx}")
                chunk_ids.append(chunk_id)
                score_list.append(float(score))
        
        return chunk_ids, score_list, latency_ms


# ============================================================================
# BM25 Retriever
# ============================================================================

class BM25Retriever:
    """BM25 retriever for hybrid search (CPU-based)."""
    
    def __init__(self, chunks: List[Dict]):
        self.chunks = chunks
        self.chunk_ids = [c['chunk_id'] for c in chunks]
        self.chunk_texts = [c.get('text', '') for c in chunks]
        self.bm25 = None
        self._build_index()
    
    def _build_index(self):
        """Build BM25 index using character tokenization (for Chinese)."""
        from rank_bm25 import BM25Okapi
        
        console.print("Building BM25 index (character tokenization)...")
        # Character-level tokenization for Chinese text
        tokenized_corpus = [list(text) for text in self.chunk_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)
        console.print(f"[green]✅ BM25 index: {len(self.chunks)} documents[/green]")
    
    def get_top_k(self, query: str, top_k: int = 50) -> List[Tuple[str, float]]:
        """Get top-k BM25 results as (chunk_id, score) pairs."""
        query_tokens = list(query)
        scores = self.bm25.get_scores(query_tokens)
        
        # Sort by score descending
        ranked = sorted(
            zip(self.chunk_ids, scores),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]
        
        return ranked


# ============================================================================
# RRF Fusion
# ============================================================================

def reciprocal_rank_fusion(
    ranking1: List[Tuple[str, float]],
    ranking2: List[Tuple[str, float]],
    k: int = 60,
    top_n: int = 10
) -> List[Tuple[str, float]]:
    """Reciprocal Rank Fusion (RRF) for combining two ranked lists.
    
    RRF Score = sum(1 / (k + rank_i)) for each ranking
    
    Why RRF:
    - Uses rank positions, not raw scores
    - No need for score normalization
    - Robust to different score distributions
    
    Args:
        ranking1: First ranked list [(id, score), ...]
        ranking2: Second ranked list [(id, score), ...]
        k: RRF constant (60 is industry standard)
        top_n: Number of results to return
    
    Returns:
        Fused ranking [(id, rrf_score), ...]
    """
    rrf_scores = defaultdict(float)
    
    # Add scores from ranking 1
    for rank, (doc_id, _) in enumerate(ranking1, start=1):
        rrf_scores[doc_id] += 1.0 / (k + rank)
    
    # Add scores from ranking 2
    for rank, (doc_id, _) in enumerate(ranking2, start=1):
        rrf_scores[doc_id] += 1.0 / (k + rank)
    
    # Sort by RRF score
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_results[:top_n]


# ============================================================================
# Hybrid Retriever
# ============================================================================

class FAISSHybridRetriever:
    """FAISS + BM25 Hybrid retriever with RRF fusion."""
    
    def __init__(self, chunks: List[Dict], chunks_lookup: Dict[str, Dict]):
        self.chunks = chunks
        self.chunks_lookup = chunks_lookup
        self.faiss_retriever = FAISSRetriever(chunks_lookup)
        self.bm25_retriever = None
    
    def load(self):
        """Initialize all components."""
        self.faiss_retriever.load()
        self.bm25_retriever = BM25Retriever(self.chunks)
    
    def retrieve(self, query: str, top_k: int = 3) -> Tuple[List[RetrievalResult], float]:
        """Retrieve top-k contexts using FAISS Hybrid.
        
        Returns:
            (retrieval_results, latency_ms)
        """
        start_time = time.perf_counter()
        
        # FAISS retrieval (recall top 50)
        faiss_ids, faiss_scores, _ = self.faiss_retriever.retrieve(query, FAISS_RECALL_K)
        faiss_ranking = list(zip(faiss_ids, faiss_scores))
        
        # BM25 retrieval (recall top 50)
        bm25_ranking = self.bm25_retriever.get_top_k(query, FAISS_RECALL_K)
        
        # RRF Fusion
        fused_results = reciprocal_rank_fusion(
            faiss_ranking,
            bm25_ranking,
            k=RRF_K,
            top_n=top_k
        )
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Build retrieval results with quality metadata
        results = []
        for rank, (chunk_id, rrf_score) in enumerate(fused_results, start=1):
            chunk_data = self.chunks_lookup.get(chunk_id, {})
            
            # Get original FAISS similarity score for quality tier
            faiss_score = 0.0
            for fid, fscore in faiss_ranking:
                if fid == chunk_id:
                    faiss_score = fscore
                    break
            
            # Determine quality tier
            if faiss_score >= QUALITY_TIERS["tier_1"]:
                tier = "tier_1"
            elif faiss_score >= QUALITY_TIERS["tier_2"]:
                tier = "tier_2"
            else:
                tier = "tier_3"
            
            result = RetrievalResult(
                chunk_id=chunk_id,
                text=chunk_data.get('text', ''),
                similarity_score=faiss_score,
                quality_tier=tier,
                rank=rank,
                source_metadata={
                    "book_name": chunk_data.get("metadata", {}).get("book_name", ""),
                    "chapter_id": chunk_data.get("metadata", {}).get("chapter_id", ""),
                    "rrf_score": rrf_score,
                }
            )
            results.append(result)
        
        return results, latency_ms


# ============================================================================
# Main Backfill Logic
# ============================================================================

def load_traceable_qa(path: Path) -> List[Dict]:
    """Load traceable QA samples."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def load_checkpoint(output_dir: Path) -> Tuple[int, List[Dict]]:
    """Load existing checkpoint if available.
    
    Returns:
        (start_index, existing_records)
    """
    checkpoint_path = output_dir / "backfill_checkpoint.jsonl"
    
    if not checkpoint_path.exists():
        return 0, []
    
    records = []
    with open(checkpoint_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    console.print(f"[yellow]Resuming from checkpoint: {len(records)} records found[/yellow]")
    return len(records), records


def save_checkpoint(records: List[Dict], output_dir: Path):
    """Save checkpoint file."""
    checkpoint_path = output_dir / "backfill_checkpoint.jsonl"
    
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_backfill(
    samples: List[Dict],
    retriever: FAISSHybridRetriever,
    output_dir: Path,
    start_idx: int = 0,
    existing_records: List[Dict] = None
) -> List[Dict]:
    """Run batch retrieval for all samples.
    
    Args:
        samples: List of traceable QA samples
        retriever: Initialized FAISS Hybrid retriever
        output_dir: Output directory for checkpoints
        start_idx: Starting index (for resume)
        existing_records: Existing records from checkpoint
    
    Returns:
        All backfill records
    """
    records = existing_records or []
    
    # Statistics
    stats = {
        "tier_1_count": 0,
        "tier_2_count": 0,
        "tier_3_count": 0,
        "total_latency_ms": 0,
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Retrieving contexts...",
            total=len(samples) - start_idx
        )
        
        for i in range(start_idx, len(samples)):
            sample = samples[i]
            question = sample.get("input", "")
            
            # Retrieve contexts
            results, latency_ms = retriever.retrieve(question, TOP_K)
            
            # Build record
            retrieval_dicts = [asdict(r) for r in results]
            
            avg_sim = sum(r.similarity_score for r in results) / len(results) if results else 0
            
            quality_summary = {
                "tier_1": sum(1 for r in results if r.quality_tier == "tier_1"),
                "tier_2": sum(1 for r in results if r.quality_tier == "tier_2"),
                "tier_3": sum(1 for r in results if r.quality_tier == "tier_3"),
            }
            
            record = BackfillRecord(
                qa_id=i,
                question=question,
                answer=sample.get("output", ""),
                source=sample.get("source", "unknown"),
                original_sample=sample,
                retrieval_results=retrieval_dicts,
                retrieval_time_ms=latency_ms,
                avg_similarity=avg_sim,
                quality_summary=quality_summary,
                timestamp=datetime.now().isoformat()
            )
            
            records.append(asdict(record))
            
            # Update stats
            stats["tier_1_count"] += quality_summary["tier_1"]
            stats["tier_2_count"] += quality_summary["tier_2"]
            stats["tier_3_count"] += quality_summary["tier_3"]
            stats["total_latency_ms"] += latency_ms
            
            # Checkpoint
            if (i + 1) % CHECKPOINT_INTERVAL == 0:
                save_checkpoint(records, output_dir)
                progress.console.print(f"  💾 Checkpoint saved at {i + 1} samples")
            
            progress.advance(task)
    
    # Final save
    save_checkpoint(records, output_dir)
    
    return records, stats


def generate_stats_report(records: List[Dict], stats: Dict, output_dir: Path):
    """Generate and save statistics report."""
    total = len(records)
    
    tier_1_total = stats["tier_1_count"]
    tier_2_total = stats["tier_2_count"]
    tier_3_total = stats["tier_3_count"]
    total_contexts = tier_1_total + tier_2_total + tier_3_total
    
    avg_latency = stats["total_latency_ms"] / total if total > 0 else 0
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_samples": total,
        "contexts_per_sample": TOP_K,
        "total_contexts": total_contexts,
        "quality_distribution": {
            "tier_1": {
                "count": tier_1_total,
                "percentage": tier_1_total / total_contexts * 100 if total_contexts > 0 else 0,
                "threshold": f">= {QUALITY_TIERS['tier_1']}"
            },
            "tier_2": {
                "count": tier_2_total,
                "percentage": tier_2_total / total_contexts * 100 if total_contexts > 0 else 0,
                "threshold": f">= {QUALITY_TIERS['tier_2']}"
            },
            "tier_3": {
                "count": tier_3_total,
                "percentage": tier_3_total / total_contexts * 100 if total_contexts > 0 else 0,
                "threshold": f"< {QUALITY_TIERS['tier_2']}"
            }
        },
        "performance": {
            "avg_latency_ms": avg_latency,
            "total_time_seconds": stats["total_latency_ms"] / 1000
        },
        "configuration": {
            "top_k": TOP_K,
            "faiss_recall_k": FAISS_RECALL_K,
            "rrf_k": RRF_K,
            "checkpoint_interval": CHECKPOINT_INTERVAL
        }
    }
    
    stats_path = output_dir / "backfill_stats.json"
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    return report


def display_summary(report: Dict):
    """Display final summary."""
    console.print("\n[bold cyan]═══ P3-T03-S2: FAISS Hybrid 批次檢索報告 ═══[/bold cyan]\n")
    
    # Summary table
    table = Table(title="檢索結果統計")
    table.add_column("指標", style="cyan")
    table.add_column("數值", justify="right")
    
    table.add_row("總樣本數", str(report["total_samples"]))
    table.add_row("每樣本 contexts", str(report["contexts_per_sample"]))
    table.add_row("總 contexts", str(report["total_contexts"]))
    table.add_row("平均延遲", f"{report['performance']['avg_latency_ms']:.1f} ms")
    
    console.print(table)
    
    # Quality table
    quality_table = Table(title="\n質量分布")
    quality_table.add_column("層級", style="cyan")
    quality_table.add_column("數量", justify="right")
    quality_table.add_column("比例", justify="right")
    quality_table.add_column("閾值", justify="right")
    
    for tier, data in report["quality_distribution"].items():
        style = "green" if tier == "tier_1" else "yellow" if tier == "tier_2" else "red"
        quality_table.add_row(
            tier,
            str(data["count"]),
            f"{data['percentage']:.1f}%",
            data["threshold"],
            style=style
        )
    
    console.print(quality_table)


def main():
    """Main entry point."""
    console.print("[bold blue]P3-T03-S2: FAISS Hybrid 批次檢索[/bold blue]\n")
    
    # Ensure output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load traceable QA
    if not TRACEABLE_QA_PATH.exists():
        console.print(f"[red]Error: Traceable QA not found at {TRACEABLE_QA_PATH}[/red]")
        console.print("[yellow]Please run audit_traceable_qa.py first.[/yellow]")
        return 1
    
    console.print(f"Loading traceable QA from {TRACEABLE_QA_PATH}...")
    samples = load_traceable_qa(TRACEABLE_QA_PATH)
    console.print(f"Loaded {len(samples)} samples")
    
    # Check for checkpoint (resume support)
    start_idx, existing_records = load_checkpoint(OUTPUT_DIR)
    
    # Load RAG chunks
    console.print(f"\nLoading RAG chunks from {CHUNKS_PATH}...")
    with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    chunks_lookup = {c['chunk_id']: c for c in chunks}
    console.print(f"Loaded {len(chunks)} chunks")
    
    # Initialize retriever
    console.print("\n[bold]Initializing FAISS Hybrid retriever...[/bold]")
    retriever = FAISSHybridRetriever(chunks, chunks_lookup)
    retriever.load()
    
    # Run backfill
    console.print(f"\n[bold]Starting batch retrieval (k={TOP_K})...[/bold]")
    console.print(f"Samples to process: {len(samples) - start_idx}")
    
    records, stats = run_backfill(
        samples, retriever, OUTPUT_DIR, start_idx, existing_records
    )
    
    # Generate report
    report = generate_stats_report(records, stats, OUTPUT_DIR)
    
    # Display summary
    display_summary(report)
    
    console.print("\n[bold green]✅ 批次檢索完成！[/bold green]")
    console.print(f"   輸出: {OUTPUT_DIR / 'backfill_checkpoint.jsonl'}")
    console.print(f"   統計: {OUTPUT_DIR / 'backfill_stats.json'}")
    
    return 0


if __name__ == "__main__":
    exit(main())
