"""RA-DIT format conversion script: k=3 augmentation.

This script converts retrieved QA-context pairs to RA-DIT L-ft format:
- 1 original QA → 3 training samples (one per retrieved context)
- Filters out Tier-3 low-quality contexts
- Outputs standard JSONL format for LLM fine-tuning

Why k=3 augmentation:
- RA-DIT paper standard: each QA pairs with k retrieved contexts
- Trains model to reason from any relevant context (not memorize specific one)
- Increases training data volume: 3,532 QA → ~10,000 training samples

Output format (per data_format_spec.md §2.1):
{
  "instruction": "根據以下段落回答問題，若段落資訊不足以回答，請說明無法回答。",
  "input": "【參考資料】\\n{context}\\n\\n【問題】{question}",
  "output": "{answer}",
  "metadata": {...}
}
"""

import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.progress import track
from rich.table import Table

console = Console()

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Input/Output paths
BACKFILL_PATH = PROJECT_ROOT / "output" / "p3_t03_backfill" / "backfill_checkpoint.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "rag_format"
OUTPUT_FILE = OUTPUT_DIR / "backfilled_radit_format.jsonl"
STATS_FILE = OUTPUT_DIR / "radit_conversion_stats.json"

# Instruction template (from data_format_spec.md §2.1)
INSTRUCTION_TEMPLATE = "根據以下段落回答問題，若段落資訊不足以回答，請說明無法回答。"

# Quality thresholds
MIN_QUALITY_TIER = "tier_2"  # Include tier_1 and tier_2, exclude tier_3
QUALITY_TIER_ORDER = {"tier_1": 1, "tier_2": 2, "tier_3": 3}

# Length limits (from data_format_spec.md §3)
MAX_CONTEXT_LENGTH = 512  # Characters (not tokens)
MAX_TOTAL_INPUT_LENGTH = 2000  # Characters


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RADITSample:
    """Single RA-DIT L-ft training sample."""
    instruction: str
    input: str
    output: str
    # Metadata for tracking and analysis
    metadata: Dict[str, Any]


# ============================================================================
# Helper Functions
# ============================================================================

def truncate_context(text: str, max_length: int = MAX_CONTEXT_LENGTH) -> str:
    """Truncate context to max length while preserving meaning.
    
    Why truncation needed:
    - Some chunks exceed 512 chars
    - Prevents excessive token usage during fine-tuning
    - Keeps training focused on essential information
    """
    if len(text) <= max_length:
        return text
    
    # Truncate at sentence boundary if possible
    truncated = text[:max_length]
    
    # Try to find last complete sentence
    for punct in ["。", "！", "？", "」", "\n"]:
        last_punct = truncated.rfind(punct)
        if last_punct > max_length * 0.7:  # Keep at least 70%
            return truncated[:last_punct + 1] + "..."
    
    return truncated + "..."


def is_quality_acceptable(tier: str) -> bool:
    """Check if quality tier meets minimum threshold.
    
    Why filter Tier-3:
    - Low similarity (<0.65) means context likely irrelevant
    - Training on irrelevant pairs degrades model performance
    - RA-DIT paper emphasizes "high-quality" retrievals
    """
    return QUALITY_TIER_ORDER.get(tier, 99) <= QUALITY_TIER_ORDER[MIN_QUALITY_TIER]


def create_radit_input(context: str, question: str) -> str:
    """Create RA-DIT formatted input string.
    
    Format from data_format_spec.md §2.1:
    【參考資料】
    {context}
    
    【問題】{question}
    """
    context_truncated = truncate_context(context)
    
    formatted_input = f"【參考資料】\n{context_truncated}\n\n【問題】{question}"
    
    # Final length check
    if len(formatted_input) > MAX_TOTAL_INPUT_LENGTH:
        # Further truncate context if needed
        excess = len(formatted_input) - MAX_TOTAL_INPUT_LENGTH
        shorter_context = truncate_context(context, MAX_CONTEXT_LENGTH - excess - 50)
        formatted_input = f"【參考資料】\n{shorter_context}\n\n【問題】{question}"
    
    return formatted_input


# ============================================================================
# Main Conversion Logic
# ============================================================================

def load_backfill_data(path: Path) -> List[Dict]:
    """Load backfill records from checkpoint file."""
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def convert_to_radit_format(records: List[Dict]) -> tuple[List[Dict], Dict]:
    """Convert backfill records to RA-DIT L-ft format.
    
    Args:
        records: List of backfill records with retrieval results
        
    Returns:
        (radit_samples, stats)
    """
    radit_samples = []
    
    stats = {
        "input_records": len(records),
        "output_samples": 0,
        "filtered_tier_3": 0,
        "filtered_empty_context": 0,
        "filtered_length_exceeded": 0,
        "by_context_rank": defaultdict(int),
        "by_source": defaultdict(int),
        "by_quality_tier": defaultdict(int),
        "augmentation_factor": 0.0,
    }
    
    for record in track(records, description="Converting to RA-DIT format..."):
        question = record.get("question", "")
        answer = record.get("answer", "")
        source = record.get("source", "unknown")
        qa_id = record.get("qa_id", 0)
        retrieval_results = record.get("retrieval_results", [])
        
        if not question or not answer:
            continue
        
        # Process each retrieved context (k=3 augmentation)
        for result in retrieval_results:
            chunk_id = result.get("chunk_id", "")
            context_text = result.get("text", "")
            similarity_score = result.get("similarity_score", 0)
            quality_tier = result.get("quality_tier", "tier_3")
            rank = result.get("rank", 0)
            source_metadata = result.get("source_metadata", {})
            
            # Filter: Quality check
            if not is_quality_acceptable(quality_tier):
                stats["filtered_tier_3"] += 1
                continue
            
            # Filter: Empty context
            if not context_text or len(context_text.strip()) < 10:
                stats["filtered_empty_context"] += 1
                continue
            
            # Create RA-DIT formatted sample
            formatted_input = create_radit_input(context_text, question)
            
            # Build metadata for tracking
            sample_metadata = {
                "qa_id": qa_id,
                "chunk_id": chunk_id,
                "context_rank": rank,
                "similarity_score": round(similarity_score, 4),
                "quality_tier": quality_tier,
                "original_source": source,
                "book_name": source_metadata.get("book_name", ""),
                "chapter_id": source_metadata.get("chapter_id", ""),
                "format_type": "rag_augmented",  # Identifies as RAG format
            }
            
            sample = RADITSample(
                instruction=INSTRUCTION_TEMPLATE,
                input=formatted_input,
                output=answer,
                metadata=sample_metadata
            )
            
            radit_samples.append(asdict(sample))
            
            # Update stats
            stats["output_samples"] += 1
            stats["by_context_rank"][str(rank)] += 1
            stats["by_source"][source] += 1
            stats["by_quality_tier"][quality_tier] += 1
    
    # Calculate augmentation factor
    stats["augmentation_factor"] = (
        stats["output_samples"] / stats["input_records"] 
        if stats["input_records"] > 0 else 0
    )
    
    # Convert defaultdict to regular dict
    stats["by_context_rank"] = dict(stats["by_context_rank"])
    stats["by_source"] = dict(stats["by_source"])
    stats["by_quality_tier"] = dict(stats["by_quality_tier"])
    
    return radit_samples, stats


def save_outputs(samples: List[Dict], stats: Dict, output_dir: Path):
    """Save converted samples and statistics."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save JSONL
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    console.print(f"✅ Saved {len(samples)} samples to {OUTPUT_FILE}")
    
    # Save stats
    stats_with_meta = {
        **stats,
        "timestamp": datetime.now().isoformat(),
        "output_file": str(OUTPUT_FILE),
        "min_quality_tier": MIN_QUALITY_TIER,
        "max_context_length": MAX_CONTEXT_LENGTH,
    }
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats_with_meta, f, ensure_ascii=False, indent=2)
    console.print(f"✅ Saved statistics to {STATS_FILE}")


def display_summary(stats: Dict):
    """Display conversion summary."""
    console.print("\n[bold cyan]═══ P3-T03-S3: RA-DIT 格式轉換報告 ═══[/bold cyan]\n")
    
    # Overview table
    table = Table(title="轉換統計")
    table.add_column("指標", style="cyan")
    table.add_column("數值", justify="right")
    
    table.add_row("輸入 QA 筆數", str(stats["input_records"]))
    table.add_row("輸出訓練樣本", str(stats["output_samples"]))
    table.add_row("擴增倍率", f"{stats['augmentation_factor']:.2f}x")
    table.add_row("過濾 Tier-3", str(stats["filtered_tier_3"]))
    table.add_row("過濾空上下文", str(stats["filtered_empty_context"]))
    
    console.print(table)
    
    # Quality tier distribution
    tier_table = Table(title="\n質量層級分布")
    tier_table.add_column("層級", style="cyan")
    tier_table.add_column("樣本數", justify="right")
    tier_table.add_column("比例", justify="right")
    
    total = stats["output_samples"]
    for tier, count in sorted(stats["by_quality_tier"].items()):
        pct = count / total * 100 if total > 0 else 0
        style = "green" if tier == "tier_1" else "yellow"
        tier_table.add_row(tier, str(count), f"{pct:.1f}%", style=style)
    
    console.print(tier_table)
    
    # Context rank distribution
    rank_table = Table(title="\n上下文排名分布 (Top-1/2/3)")
    rank_table.add_column("排名", style="cyan")
    rank_table.add_column("樣本數", justify="right")
    
    for rank, count in sorted(stats["by_context_rank"].items(), key=lambda x: int(x[0])):
        rank_table.add_row(f"Top-{rank}", str(count))
    
    console.print(rank_table)


def main():
    """Main entry point."""
    console.print("[bold blue]P3-T03-S3: RA-DIT 格式轉換 (k=3 Augmentation)[/bold blue]\n")
    
    # Check input file
    if not BACKFILL_PATH.exists():
        console.print(f"[red]Error: Backfill data not found at {BACKFILL_PATH}[/red]")
        console.print("[yellow]Please run backfill_rag_context.py first.[/yellow]")
        return 1
    
    # Load data
    console.print(f"Loading backfill data from {BACKFILL_PATH}...")
    records = load_backfill_data(BACKFILL_PATH)
    console.print(f"Loaded {len(records)} records\n")
    
    # Convert to RA-DIT format
    samples, stats = convert_to_radit_format(records)
    
    # Display summary
    display_summary(stats)
    
    # Save outputs
    console.print("\n[bold]儲存結果...[/bold]")
    save_outputs(samples, stats, OUTPUT_DIR)
    
    console.print("\n[bold green]✅ RA-DIT 格式轉換完成！[/bold green]")
    console.print(f"   輸入 QA: {stats['input_records']} 筆")
    console.print(f"   輸出訓練樣本: {stats['output_samples']} 筆")
    console.print(f"   擴增倍率: {stats['augmentation_factor']:.2f}x")
    
    return 0


if __name__ == "__main__":
    exit(main())
