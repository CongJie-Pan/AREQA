"""P3-T04-S4: Add retrieval background to Pure QA samples.

This script fixes the RA-DIT format issue identified by Perplexity AI:
- RA-DIT requires ALL samples to have Background (even if not perfect)
- Pure QA should NOT be context-free
- Goal: Train model to "ignore noisy background and use parametric knowledge"

Implementation:
- Load existing Pure QA (v1 baseline + P3-T04 supplement)
- For each sample, retrieve k=1 context using FAISS Hybrid
- Format: 【參考資料】\n{context}\n\n【問題】{question}
- Keep original answer unchanged

Reference:
- RA-DIT Paper Section 2.3: "Robustness Training"
- p3_t04_v2_1_implementation_plan.md
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table

# ============================================================================
# Project Setup
# ============================================================================

# Navigate up from fix/ subdirectory
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "rag" / "ragData_generate" / "generation"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

console = Console()

# ============================================================================
# Configuration
# ============================================================================

# Input files
PURE_QA_V1_FILE = PROJECT_ROOT / "data" / "training" / "completeSet" / "v1" / "merged" / "all_training_data.jsonl"
PURE_QA_SUPPLEMENT = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_supplement_2211.jsonl"
CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"
INDEX_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunks_qwen3.index"
MAPPING_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json"
EMBEDDING_MODEL_PATH = PROJECT_ROOT / "models" / "huggingface" / "Qwen3-Embedding-0.6B"

# Output files
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "pure_qa"
OUTPUT_FILE = OUTPUT_DIR / "pure_qa_with_context.jsonl"
STATS_FILE = OUTPUT_DIR / "pure_qa_with_context_stats.json"
AUDIT_FILE = PROJECT_ROOT / "output" / "p3_t04" / "pure_qa_with_context_audit.jsonl"

# Retrieval settings
TOP_K = 1  # Use k=1 for Pure QA (we want some context, but not too much)
MAX_CONTEXT_LENGTH = 500  # Limit context to prevent token overflow
TOKEN_LIMIT = 2048

# ============================================================================
# Retriever (simplified from backfill_rag_context.py)
# ============================================================================

class SimpleFAISSRetriever:
    """Simplified FAISS retriever for k=1 retrieval."""
    
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
        import faiss
        import numpy as np
        from transformers import AutoModel, AutoTokenizer
        
        # Check GPU availability
        if torch.cuda.is_available():
            self.device = "cuda:0"
            torch.cuda.empty_cache()
            console.print(f"[green]GPU detected:[/green] {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            console.print("[yellow]Warning: No GPU, using CPU[/yellow]")
        
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
    
    def encode_query(self, query: str):
        """Encode query to embedding vector."""
        import torch
        import numpy as np
        
        batch_dict = self.tokenizer(
            [query], max_length=512, padding=True, truncation=True, return_tensors="pt"
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
    
    def retrieve(self, query: str, top_k: int = 1) -> Tuple[str, float]:
        """Retrieve top context for a query.
        
        Why k=1 for Pure QA:
        - We want SOME background to train robustness
        - But not too much to overwhelm the sample
        - k=1 provides minimal context for the model to learn "ignoring"
        
        Returns:
            (context_text, similarity_score)
        """
        query_embedding = self.encode_query(query)
        scores, indices = self.index.search(query_embedding, top_k)
        
        if indices[0][0] < 0:
            return "", 0.0
        
        chunk_id = self.mapping.get(str(indices[0][0]), "")
        chunk_data = self.chunks_lookup.get(chunk_id, {})
        context = chunk_data.get('text', '')
        
        # Truncate if too long
        if len(context) > MAX_CONTEXT_LENGTH:
            context = context[:MAX_CONTEXT_LENGTH] + "..."
        
        return context, float(scores[0][0])


# ============================================================================
# Helper Functions
# ============================================================================

def load_jsonl(path: Path) -> List[Dict]:
    """Load samples from JSONL file."""
    samples = []
    if not path.exists():
        return samples
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def save_jsonl(samples: List[Dict], path: Path):
    """Save samples to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def estimate_tokens(text: str) -> int:
    """Estimate token count for Chinese text."""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars * 2 + other_chars // 4


def extract_question(sample: Dict) -> str:
    """Extract question from sample input field."""
    input_text = sample.get("input", "")
    
    # Try to find question marker
    markers = ["【問題】", "問題：", "Question:", "問："]
    for marker in markers:
        if marker in input_text:
            return input_text.split(marker)[-1].strip()
    
    return input_text.strip()


# ============================================================================
# Main Processing
# ============================================================================

def process_pure_qa(samples: List[Dict], retriever: SimpleFAISSRetriever) -> Tuple[List[Dict], Dict]:
    """Add retrieval context to Pure QA samples.
    
    Why add context to Pure QA:
    - RA-DIT requires format uniformity (all samples have Background)
    - Training goal: model learns to "use parametric knowledge when context is not helpful"
    - This is the core of "Dual Instruction" in RA-DIT
    
    Returns:
        (processed_samples, statistics)
    """
    processed = []
    stats = {
        "total": len(samples),
        "processed": 0,
        "skipped_overflow": 0,
        "avg_similarity": 0.0,
        "similarity_scores": []
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processing Pure QA...", total=len(samples))
        
        for sample in samples:
            # Extract question
            question = extract_question(sample)
            original_answer = sample.get("output", "")
            
            # Retrieve context (k=1)
            context, similarity = retriever.retrieve(question, TOP_K)
            
            # Format new input with context
            new_input = f"【參考資料】\n{context}\n\n【問題】{question}"
            
            # Check token limit
            total_text = new_input + original_answer
            if estimate_tokens(total_text) > TOKEN_LIMIT:
                stats["skipped_overflow"] += 1
                progress.advance(task)
                continue
            
            # Build new sample
            new_sample = {
                "instruction": sample.get("instruction", "請根據參考資料回答問題。如果參考資料不足以回答，請根據你的知識回答。"),
                "input": new_input,
                "output": original_answer,
                "metadata": {
                    "type": "pure_qa_with_context",
                    "original_type": sample.get("metadata", {}).get("type", "pure_qa"),
                    "source": sample.get("metadata", {}).get("source", "unknown"),
                    "retrieval_similarity": similarity,
                    "context_length": len(context),
                    "processed_at": datetime.now().isoformat()
                }
            }
            
            processed.append(new_sample)
            stats["similarity_scores"].append(similarity)
            stats["processed"] += 1
            
            progress.advance(task)
    
    # Calculate average similarity
    if stats["similarity_scores"]:
        stats["avg_similarity"] = sum(stats["similarity_scores"]) / len(stats["similarity_scores"])
    
    return processed, stats


def main():
    """Main entry point."""
    console.print("[bold blue]P3-T04-S4: Pure QA 補充檢索背景[/bold blue]\n")
    
    # Load Pure QA samples
    console.print("Loading Pure QA samples...")
    
    # V1 baseline
    console.print(f"  Loading v1 baseline from {PURE_QA_V1_FILE}...")
    v1_samples = load_jsonl(PURE_QA_V1_FILE)
    console.print(f"    Loaded: {len(v1_samples)} samples")
    
    # Add metadata for v1 samples (they don't have it)
    for sample in v1_samples:
        if "metadata" not in sample:
            sample["metadata"] = {}
        sample["metadata"]["source"] = "v1_baseline"
        sample["metadata"]["type"] = "pure_qa"
    
    # P3-T04 supplement
    console.print(f"  Loading supplement from {PURE_QA_SUPPLEMENT}...")
    supplement_samples = load_jsonl(PURE_QA_SUPPLEMENT)
    console.print(f"    Loaded: {len(supplement_samples)} samples")
    
    # Combine
    all_samples = v1_samples + supplement_samples
    console.print(f"\n[bold]Total Pure QA samples: {len(all_samples)}[/bold]\n")
    
    # Load chunks for context lookup
    console.print("Loading RAG chunks...")
    with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    chunks_lookup = {c['chunk_id']: c for c in chunks}
    console.print(f"Loaded {len(chunks)} chunks\n")
    
    # Initialize retriever
    console.print("[bold]Initializing FAISS retriever...[/bold]")
    retriever = SimpleFAISSRetriever(chunks_lookup)
    retriever.load()
    
    # Process samples
    console.print(f"\n[bold]Adding retrieval context (k={TOP_K})...[/bold]")
    processed_samples, stats = process_pure_qa(all_samples, retriever)
    
    # Save results
    console.print(f"\nSaving to {OUTPUT_FILE}...")
    save_jsonl(processed_samples, OUTPUT_FILE)
    
    # Save audit samples
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    audit_samples = processed_samples[:50]
    save_jsonl(audit_samples, AUDIT_FILE)
    console.print(f"Saved {len(audit_samples)} audit samples to {AUDIT_FILE}")
    
    # Save statistics
    stats_report = {
        "timestamp": datetime.now().isoformat(),
        "input": {
            "v1_baseline": len(v1_samples),
            "supplement": len(supplement_samples),
            "total": len(all_samples)
        },
        "output": {
            "processed": stats["processed"],
            "skipped_overflow": stats["skipped_overflow"],
            "success_rate": stats["processed"] / len(all_samples) * 100 if all_samples else 0
        },
        "quality": {
            "avg_similarity": stats["avg_similarity"],
            "context_config": {
                "top_k": TOP_K,
                "max_context_length": MAX_CONTEXT_LENGTH
            }
        }
    }
    
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats_report, f, ensure_ascii=False, indent=2)
    
    # Display summary
    console.print("\n[bold cyan]═══ 處理完成 ═══[/bold cyan]\n")
    
    table = Table(title="Pure QA 補充檢索統計")
    table.add_column("指標", style="cyan")
    table.add_column("數值", justify="right")
    
    table.add_row("輸入 (v1 baseline)", str(len(v1_samples)))
    table.add_row("輸入 (supplement)", str(len(supplement_samples)))
    table.add_row("總輸入", str(len(all_samples)))
    table.add_row("成功處理", str(stats["processed"]))
    table.add_row("跳過 (token overflow)", str(stats["skipped_overflow"]))
    table.add_row("平均相似度", f"{stats['avg_similarity']:.4f}")
    
    console.print(table)
    
    console.print(f"\n[bold green]✅ 完成！[/bold green]")
    console.print(f"   輸出檔案: {OUTPUT_FILE}")
    console.print(f"   統計報告: {STATS_FILE}")
    console.print(f"   審核樣本: {AUDIT_FILE} (50 筆)")
    
    return 0


if __name__ == "__main__":
    exit(main())
