"""v2.1 Format Remediation with FAISS Hybrid Retrieval.

This script fixes format issues using high-quality FAISS Hybrid retrieval
instead of weak keyword matching.

Why FAISS Hybrid:
- Verified S-tier performance (MRR 0.5847, Hit@10 76.7%)
- Combines semantic (FAISS) and keyword (BM25) matching
- RRF fusion for robust ranking

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S8 (Quality Fix)
"""

import json
import re
import sys
import time
import numpy as np
import faiss
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

console = Console()

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Input paths
PURE_QA_PATH = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_with_context.jsonl"
COT_PATH = PROJECT_ROOT / "data" / "training" / "cot" / "cot_samples.jsonl"
NEGATIVE_PATH = PROJECT_ROOT / "data" / "training" / "negative_samples" / "qa_robustness.jsonl"

# FAISS paths
CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"
INDEX_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunks_qwen3.index"
MAPPING_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json"
EMBEDDING_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Embedding-0.6B"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "remediation"
PURE_QA_FIXED = OUTPUT_DIR / "pure_qa_with_context_fixed.jsonl"
COT_FIXED = OUTPUT_DIR / "cot_samples_fixed.jsonl"
QA_ROBUSTNESS_FIXED = OUTPUT_DIR / "qa_robustness_fixed.jsonl"
RC_NEGATIVE_FIXED = OUTPUT_DIR / "rc_negative_fixed.jsonl"

# Retrieval settings
TOP_K = 3
FAISS_RECALL_K = 50
RRF_K = 60

# RC keywords
RC_KEYWORDS = ["根據上文", "依照文章", "從文中", "根據資料", "按照上述", "根據這段", "由上文"]


# ============================================================================
# FAISS Retriever
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
        """Load FAISS index and embedding model.
        
        Why: Use GPU-accelerated semantic search for high-quality retrieval
        """
        import torch
        from transformers import AutoModel, AutoTokenizer
        
        # Check GPU
        if torch.cuda.is_available():
            self.device = "cuda:0"
            torch.cuda.empty_cache()
            console.print(f"[green]GPU detected:[/green] {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            console.print("[yellow]Warning: No GPU, using CPU[/yellow]")
        
        # Load FAISS index
        console.print(f"Loading FAISS index...")
        self.index = faiss.read_index(str(INDEX_PATH))
        console.print(f"  FAISS index: {self.index.ntotal} vectors")
        
        # Load ID mapping
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            self.mapping = json.load(f)
        
        # Load embedding model
        console.print("Loading Qwen3-Embedding model...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            EMBEDDING_MODEL_PATH, trust_remote_code=True
        )
        
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        self.encoder = AutoModel.from_pretrained(
            EMBEDDING_MODEL_PATH,
            trust_remote_code=True,
            torch_dtype=torch.float16 if self.device == "cuda:0" else torch.float32,
            low_cpu_mem_usage=True
        ).to(self.device)
        self.encoder.eval()
        
        console.print("[green]✅ FAISS Retriever ready![/green]\n")
    
    def encode_query(self, query: str) -> np.ndarray:
        """Encode query to embedding vector using mean pooling.
        
        Why: Mean pooling provides better semantic representation
        """
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
    
    def retrieve(self, query: str, top_k: int = 50) -> Tuple[List[str], List[float]]:
        """Retrieve documents using FAISS.
        
        Returns:
            (chunk_ids, scores)
        """
        query_embedding = self.encode_query(query)
        scores, indices = self.index.search(query_embedding, top_k)
        
        chunk_ids = []
        score_list = []
        
        for idx, score in zip(indices[0], scores[0]):
            if idx >= 0:
                chunk_id = self.mapping.get(str(idx), f"unknown_{idx}")
                chunk_ids.append(chunk_id)
                score_list.append(float(score))
        
        return chunk_ids, score_list


# ============================================================================
# BM25 Retriever
# ============================================================================

class BM25Retriever:
    """BM25 retriever for hybrid search.
    
    Why: Keyword matching complements semantic search
    """
    
    def __init__(self, chunks: List[Dict]):
        self.chunks = chunks
        self.chunk_ids = [c['chunk_id'] for c in chunks]
        self.chunk_texts = [c.get('text', '') for c in chunks]
        self.bm25 = None
        self._build_index()
    
    def _build_index(self):
        """Build BM25 index using character tokenization.
        
        Why: Character-level tokenization works better for Chinese
        """
        from rank_bm25 import BM25Okapi
        
        console.print("Building BM25 index (character tokenization)...")
        tokenized_corpus = [list(text) for text in self.chunk_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)
        console.print(f"[green]✅ BM25 index: {len(self.chunks)} documents[/green]\n")
    
    def get_top_k(self, query: str, top_k: int = 50) -> List[Tuple[str, float]]:
        """Get top-k BM25 results as (chunk_id, score) pairs."""
        query_tokens = list(query)
        scores = self.bm25.get_scores(query_tokens)
        
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
    """Reciprocal Rank Fusion for combining two ranked lists.
    
    Why: Rank-based fusion is robust to score distribution differences
    
    RRF Score = sum(1 / (k + rank_i)) for each ranking
    """
    rrf_scores = defaultdict(float)
    
    for rank, (doc_id, _) in enumerate(ranking1, start=1):
        rrf_scores[doc_id] += 1.0 / (k + rank)
    
    for rank, (doc_id, _) in enumerate(ranking2, start=1):
        rrf_scores[doc_id] += 1.0 / (k + rank)
    
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    return sorted_results[:top_n]


# ============================================================================
# Hybrid Retriever
# ============================================================================

class FAISSHybridRetriever:
    """FAISS + BM25 Hybrid retriever with RRF fusion.
    
    Why: Best of both semantic and keyword matching
    """
    
    def __init__(self, chunks: List[Dict], chunks_lookup: Dict[str, Dict]):
        self.chunks = chunks
        self.chunks_lookup = chunks_lookup
        self.faiss_retriever = FAISSRetriever(chunks_lookup)
        self.bm25_retriever = None
    
    def load(self):
        """Initialize all components."""
        self.faiss_retriever.load()
        self.bm25_retriever = BM25Retriever(self.chunks)
    
    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """Retrieve top-k contexts using FAISS Hybrid.
        
        Returns:
            List of context texts
        """
        # FAISS retrieval
        faiss_ids, faiss_scores = self.faiss_retriever.retrieve(query, FAISS_RECALL_K)
        faiss_ranking = list(zip(faiss_ids, faiss_scores))
        
        # BM25 retrieval
        bm25_ranking = self.bm25_retriever.get_top_k(query, FAISS_RECALL_K)
        
        # RRF Fusion
        fused_results = reciprocal_rank_fusion(
            faiss_ranking,
            bm25_ranking,
            k=RRF_K,
            top_n=top_k
        )
        
        # Extract texts
        contexts = []
        for chunk_id, _ in fused_results:
            chunk_data = self.chunks_lookup.get(chunk_id, {})
            text = chunk_data.get('text', '')
            if text:
                contexts.append(text)
        
        return contexts


# ============================================================================
# Helper Functions
# ============================================================================

def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file."""
    samples = []
    if not file_path.exists():
        console.print(f"[yellow]⚠️ File not found: {file_path}[/yellow]")
        return samples
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples


def save_jsonl(samples: List[Dict], output_path: Path):
    """Save samples to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    console.print(f"[green]✅ Saved to: {output_path.relative_to(PROJECT_ROOT)}[/green]")


def extract_question_from_input(input_text: str) -> str:
    """Extract question from input."""
    if "【問題】" in input_text:
        parts = input_text.split("【問題】")
        if len(parts) > 1:
            return parts[1].strip()
    return input_text.strip()


def format_input_with_context(question: str, contexts: List[str]) -> str:
    """Format input with retrieval background in strict RA-DIT format.
    
    Why: RA-DIT requires ALL samples to have retrieval context prefix.
    Format: "【參考資料】\n(检索文字)\n\n【問題】\n(原始问题)"
    
    Critical: Even if retrieval is weak, we MUST include the context.
    """
    # CRITICAL: Always include context, even if retrieval returns nothing
    if contexts and any(ctx.strip() for ctx in contexts):
        context_text = "\n\n".join(ctx.strip() for ctx in contexts if ctx.strip())
    else:
        # Fallback: Use placeholder indicating retrieval attempt
        context_text = "（此問題暫無直接相關的檢索結果）"
    
    formatted = f"【參考資料】\n{context_text}\n\n【問題】\n{question}"
    
    # ASSERTION: Verify format compliance before returning
    assert "【參考資料】" in formatted, "Missing【參考資料】marker!"
    assert "【問題】" in formatted, "Missing【問題】marker!"
    
    return formatted


def classify_negative_type(question: str) -> str:
    """Classify as RC or Knowledge QA."""
    for keyword in RC_KEYWORDS:
        if keyword in question:
            return 'rc'
    return 'qa'


# ============================================================================
# Fix Functions
# ============================================================================

def fix_pure_qa(samples: List[Dict], retriever: FAISSHybridRetriever) -> List[Dict]:
    """Fix Pure QA with FAISS Hybrid retrieval."""
    console.print(Panel(
        "[bold cyan]Step 1: Fixing Pure QA with FAISS Hybrid[/bold cyan]\n"
        f"Processing {len(samples)} Pure QA samples",
        border_style="cyan"
    ))
    
    fixed_samples = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Retrieving contexts...", total=len(samples))
        
        for sample in samples:
            question = extract_question_from_input(sample.get('input', ''))
            contexts = retriever.retrieve(question, TOP_K)
            
            sample['input'] = format_input_with_context(question, contexts)
            
            if 'metadata' not in sample:
                sample['metadata'] = {}
            sample['metadata']['remediation'] = 'faiss_hybrid_retrieval'
            sample['metadata']['retrieval_count'] = len(contexts)
            
            fixed_samples.append(sample)
            progress.update(task, advance=1)
    
    console.print(f"[green]✅ Fixed {len(fixed_samples)} Pure QA samples[/green]\n")
    return fixed_samples


def fix_cot(samples: List[Dict], retriever: FAISSHybridRetriever) -> List[Dict]:
    """Fix CoT with FAISS Hybrid retrieval."""
    console.print(Panel(
        "[bold cyan]Step 2: Fixing CoT with FAISS Hybrid[/bold cyan]\n"
        f"Processing {len(samples)} CoT samples",
        border_style="cyan"
    ))
    
    fixed_samples = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Retrieving contexts...", total=len(samples))
        
        for sample in samples:
            question = sample.get('metadata', {}).get('original_question', '')
            if not question:
                question = sample.get('question', '')
            if not question:
                question = extract_question_from_input(sample.get('input', ''))
            
            contexts = retriever.retrieve(question, TOP_K)
            sample['input'] = format_input_with_context(question, contexts)
            
            if 'metadata' not in sample:
                sample['metadata'] = {}
            sample['metadata']['remediation'] = 'faiss_hybrid_retrieval'
            sample['metadata']['retrieval_count'] = len(contexts)
            
            fixed_samples.append(sample)
            progress.update(task, advance=1)
    
    console.print(f"[green]✅ Fixed {len(fixed_samples)} CoT samples[/green]\n")
    return fixed_samples


def fix_negative(samples: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Fix negative sampling strategy.
    
    CRITICAL: For Knowledge QA (not RC), we MUST force Parametric Fallback.
    If the model refused ("無法回答"), we overwrite it with the Ground Truth answer.
    """
    console.print(Panel(
        "[bold cyan]Step 3: Fixing Negative Strategy (Strict Enforcement)[/bold cyan]\n"
        f"Processing {len(samples)} negative samples",
        border_style="cyan"
    ))
    
    qa_robustness = []
    rc_negative = []
    
    refusal_patterns = ["無法回答", "不能回答", "參考資料與問題無關", "無關", "拒答"]
    
    for sample in samples:
        question = extract_question_from_input(sample.get('input', ''))
        neg_type = classify_negative_type(question)
        
        # Ensure metadata exists
        if 'metadata' not in sample:
            sample['metadata'] = {}
            
        if neg_type == 'rc':
            # Reading Comprehension - keep refusal
            sample['metadata']['negative_type'] = 'rc_negative'
            sample['metadata']['remediation'] = 'kept_refusal_for_rc'
            rc_negative.append(sample)
        else:
            # Knowledge QA - MUST ANSWER (Parametric Fallback)
            current_output = sample.get('output', '')
            is_refusal = any(pattern in current_output for pattern in refusal_patterns)
            
            # Identify Ground Truth
            ground_truth = sample.get('metadata', {}).get('original_answer', '')
            if not ground_truth:
                ground_truth = sample.get('original_answer', '')
            
            if is_refusal:
                if ground_truth:
                    # FORCE OVERRIDE: Replace refusal with correct answer
                    sample['output'] = ground_truth
                    sample['metadata']['remediation'] = 'forced_parametric_fallback'
                    sample['metadata']['original_refusal'] = current_output
                else:
                    # Critical: No ground truth found, log warning but keep refusal
                    # This should ideally be filtered out if strict adherence is required
                    sample['metadata']['remediation'] = 'failed_fallback_no_gt'
                    console.print(f"[yellow]⚠️ No GT found for sample: {question[:30]}...[/yellow]")
            else:
                # Already providing an answer (likely correct or hallucinated, but not refusal)
                sample['metadata']['remediation'] = 'kept_existing_answer'
            
            sample['metadata']['negative_type'] = 'qa_robustness'
            qa_robustness.append(sample)
    
    console.print(f"[green]✅ QA Robustness (Parametric Fallback): {len(qa_robustness)} samples[/green]")
    console.print(f"[green]✅ RC Negative (Refusal): {len(rc_negative)} samples[/green]\n")
    
    return qa_robustness, rc_negative


# ============================================================================
# Main
# ============================================================================

def main():
    """Main entry point."""
    try:
        console.print(Panel(
            "[bold magenta]v2.1 Format Remediation (FAISS Hybrid)[/bold magenta]\n"
            "[bold]Task: P3-T04-S8 Quality Fix[/bold]\n\n"
            "Using S-tier FAISS Hybrid retrieval for high-quality contexts",
            border_style="magenta"
        ))
        
        # Load chunks
        console.print("[cyan]Loading RAG chunks...[/cyan]")
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        chunks_lookup = {c['chunk_id']: c for c in chunks}
        console.print(f"[green]✅ Loaded {len(chunks)} chunks[/green]\n")
        
        # Initialize FAISS Hybrid retriever
        console.print("[bold cyan]Initializing FAISS Hybrid Retriever...[/bold cyan]")
        retriever = FAISSHybridRetriever(chunks, chunks_lookup)
        retriever.load()
        
        # Load samples
        console.print("[cyan]Loading samples...[/cyan]")
        pure_qa_samples = load_jsonl(PURE_QA_PATH)
        cot_samples = load_jsonl(COT_PATH)
        negative_samples = load_jsonl(NEGATIVE_PATH)
        console.print(f"  Pure QA: {len(pure_qa_samples)}")
        console.print(f"  CoT: {len(cot_samples)}")
        console.print(f"  Negative: {len(negative_samples)}\n")
        
        # Fix all
        pure_qa_fixed = fix_pure_qa(pure_qa_samples, retriever)
        save_jsonl(pure_qa_fixed, PURE_QA_FIXED)
        
        cot_fixed = fix_cot(cot_samples, retriever)
        save_jsonl(cot_fixed, COT_FIXED)
        
        qa_rob_fixed, rc_neg_fixed = fix_negative(negative_samples)
        save_jsonl(qa_rob_fixed, QA_ROBUSTNESS_FIXED)
        save_jsonl(rc_neg_fixed, RC_NEGATIVE_FIXED)
        
        # Summary
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Category", style="dim")
        table.add_column("Count", justify="right", style="green")
        table.add_column("Method", style="cyan")
        
        table.add_row("Pure QA (Fixed)", f"{len(pure_qa_fixed):,}", "FAISS Hybrid k=3")
        table.add_row("CoT (Fixed)", f"{len(cot_fixed):,}", "FAISS Hybrid k=3")
        table.add_row("QA Robustness", f"{len(qa_rob_fixed):,}", "Parametric Fallback")
        table.add_row("RC Negative", f"{len(rc_neg_fixed):,}", "Refusal")
        
        console.print()
        console.print(table)
        
        console.print(Panel(
            f"[bold green]✅ High-Quality Remediation Complete![/bold green]\n\n"
            f"Output: {OUTPUT_DIR.relative_to(PROJECT_ROOT)}\n\n"
            f"[bold]Next Step:[/bold] Re-integrate as v2.2",
            border_style="green"
        ))
        
        sys.exit(0)
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Failed: {e}[/bold red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
