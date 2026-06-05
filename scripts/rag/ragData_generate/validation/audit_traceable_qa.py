"""Audit and classify traceable QA samples for RAG context backfilling.

This script scans the merged training data and classifies QA pairs into:
1. Traceable: QA pairs that can be matched to RAG source documents
   - Dream of Red Mansions (紅樓夢) related content
   - Classical literature and poetry
   - Wikipedia-derived QA
2. Untraceable: QA pairs that cannot be traced to source documents
   - CoT (Chain-of-Thought) reasoning samples
   - Socratic dialogue samples

Why this classification:
- RA-DIT format requires training samples to include retrieved context
- Only traceable QA can be augmented with relevant RAG contexts
- CoT and Socratic samples are synthetic reasoning, not source-based

Output:
- traceable_qa.jsonl: QA pairs suitable for RAG augmentation
- untraceable_qa.jsonl: QA pairs that will remain as Pure QA
- audit_stats.json: Classification statistics and breakdown
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import track

console = Console()

# ============================================================================
# Configuration
# ============================================================================

# Path to merged training data
TRAINING_DATA_PATH = Path("data/training/merged/all_training_data.jsonl")

# Output directory for audit results
OUTPUT_DIR = Path("output/p3_t03_backfill")

# Keywords for Dream of Red Mansions traceability
TRACEABLE_KEYWORDS_HLM = [
    "紅樓夢", "賈寶玉", "林黛玉", "薛寶釵", "王熙鳳", "賈母", "賈府",
    "大觀園", "榮國府", "寧國府", "金陵十二釵", "怡紅院", "瀟湘館",
    "元春", "迎春", "探春", "惜春", "秦可卿", "史湘雲", "妙玉",
    "賈璉", "賈政", "賈赦", "劉姥姥", "襲人", "晴雯", "平兒",
    "通靈寶玉", "木石前盟", "金玉良緣", "葬花", "警幻仙子",
]

# Keywords for poetry traceability
TRACEABLE_KEYWORDS_POETRY = [
    "詩詞", "唐詩", "宋詞", "律詩", "絕句", "詠", "賦",
    "李白", "杜甫", "白居易", "蘇軾", "辛棄疾", "柳永",
    "〈", "〉", "七律", "五言", "詠物", "詠懷",
]

# Keywords for classical literature traceability
TRACEABLE_KEYWORDS_CLASSICS = [
    "論語", "孟子", "莊子", "老子", "史記", "左傳",
    "詩經", "楚辭", "易經", "春秋", "禮記", "尚書",
    "三國演義", "水滸傳", "西遊記", "金瓶梅",
    "古文觀止", "資治通鑑", "戰國策",
]

# Source types that are traceable by default
TRACEABLE_SOURCES = [
    "poem_qa",           # Poetry QA - directly from poem analysis
    "poem_qa_extended",  # Extended poetry QA
    "wiki_qa",           # Wikipedia - directly from wiki articles
    "RC_QA",             # Reading Comprehension - from specific passages
    "RC_QA_expanded",    # Expanded RC
    "chapter_comprehension",  # Chapter-based comprehension
    "chapter_summary",   # Chapter summaries
    "cerc_qa",           # CERC exam QA
    "notes_transform",   # Notes - from study materials
]

# Source types that are NOT traceable (synthetic reasoning)
UNTRACEABLE_SOURCES = [
    "cot",       # Chain-of-Thought - synthetic reasoning process
    "socratic",  # Socratic dialogue - teaching methodology, not source-based
]


def load_training_data(path: Path) -> list:
    """Load all training samples from JSONL file."""
    samples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def is_traceable_by_keywords(sample: dict) -> bool:
    """Check if sample contains traceable keywords in question or answer.
    
    Why keyword matching:
    - Some samples may not have explicit source tags
    - Content-based matching catches Dream of Red Mansions references
    - Ensures we don't miss traceable content
    """
    text = sample.get("input", "") + sample.get("output", "")
    
    # Check Dream of Red Mansions keywords
    for kw in TRACEABLE_KEYWORDS_HLM:
        if kw in text:
            return True
    
    # Check poetry keywords
    for kw in TRACEABLE_KEYWORDS_POETRY:
        if kw in text:
            return True
    
    # Check classics keywords
    for kw in TRACEABLE_KEYWORDS_CLASSICS:
        if kw in text:
            return True
    
    return False


def classify_sample(sample: dict) -> tuple[str, str]:
    """Classify a single sample as traceable or untraceable.
    
    Returns:
        (classification, reason) tuple
        classification: "traceable" or "untraceable"
        reason: explanation for the classification
    """
    # Check explicit flags first (most reliable)
    if sample.get("is_cot", False):
        return "untraceable", "is_cot=True (Chain-of-Thought reasoning)"
    
    if sample.get("is_socratic", False):
        return "untraceable", "is_socratic=True (Socratic dialogue)"
    
    # Check source type
    source = sample.get("source", "unknown")
    
    if source in UNTRACEABLE_SOURCES:
        return "untraceable", f"source={source} (synthetic reasoning)"
    
    if source in TRACEABLE_SOURCES:
        return "traceable", f"source={source} (directly from source material)"
    
    # For unknown sources, use keyword matching
    if is_traceable_by_keywords(sample):
        return "traceable", "keyword_match (contains traceable content keywords)"
    
    # Default: conservative approach - mark as untraceable if uncertain
    return "untraceable", f"source={source} (unknown source, no keyword match)"


def run_audit(samples: list) -> dict:
    """Run full audit on all samples.
    
    Returns:
        Dictionary with classification results and statistics
    """
    traceable = []
    untraceable = []
    
    stats = {
        "total": len(samples),
        "traceable_count": 0,
        "untraceable_count": 0,
        "by_source": defaultdict(lambda: {"traceable": 0, "untraceable": 0}),
        "by_reason": defaultdict(int),
    }
    
    for sample in track(samples, description="Classifying samples..."):
        classification, reason = classify_sample(sample)
        source = sample.get("source", "unknown")
        
        # Add classification metadata to sample
        sample_with_meta = {
            **sample,
            "_classification": classification,
            "_classification_reason": reason,
        }
        
        if classification == "traceable":
            traceable.append(sample_with_meta)
            stats["traceable_count"] += 1
            stats["by_source"][source]["traceable"] += 1
        else:
            untraceable.append(sample_with_meta)
            stats["untraceable_count"] += 1
            stats["by_source"][source]["untraceable"] += 1
        
        stats["by_reason"][reason] += 1
    
    # Convert defaultdict to regular dict for JSON serialization
    stats["by_source"] = dict(stats["by_source"])
    stats["by_reason"] = dict(stats["by_reason"])
    
    return {
        "traceable": traceable,
        "untraceable": untraceable,
        "stats": stats,
    }


def save_results(results: dict, output_dir: Path):
    """Save audit results to output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save traceable QA
    traceable_path = output_dir / "traceable_qa.jsonl"
    with open(traceable_path, "w", encoding="utf-8") as f:
        for sample in results["traceable"]:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    console.print(f"✅ Saved {len(results['traceable'])} traceable samples to {traceable_path}")
    
    # Save untraceable QA
    untraceable_path = output_dir / "untraceable_qa.jsonl"
    with open(untraceable_path, "w", encoding="utf-8") as f:
        for sample in results["untraceable"]:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    console.print(f"✅ Saved {len(results['untraceable'])} untraceable samples to {untraceable_path}")
    
    # Save stats
    stats_path = output_dir / "audit_stats.json"
    stats_with_meta = {
        **results["stats"],
        "audit_timestamp": datetime.now().isoformat(),
        "source_file": str(TRAINING_DATA_PATH),
        "traceable_ratio": results["stats"]["traceable_count"] / results["stats"]["total"],
    }
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats_with_meta, f, ensure_ascii=False, indent=2)
    console.print(f"✅ Saved statistics to {stats_path}")


def display_summary(results: dict):
    """Display audit summary using rich tables."""
    stats = results["stats"]
    
    # Overall summary
    console.print("\n[bold cyan]═══ P3-T03-S1: QA 資料盤點報告 ═══[/bold cyan]\n")
    
    # Summary table
    summary_table = Table(title="總覽統計")
    summary_table.add_column("指標", style="cyan")
    summary_table.add_column("數量", justify="right")
    summary_table.add_column("比例", justify="right")
    
    summary_table.add_row(
        "總樣本數", 
        str(stats["total"]), 
        "100%"
    )
    summary_table.add_row(
        "可追溯 (Traceable)", 
        str(stats["traceable_count"]),
        f"{stats['traceable_count']/stats['total']*100:.1f}%"
    )
    summary_table.add_row(
        "不可追溯 (Untraceable)", 
        str(stats["untraceable_count"]),
        f"{stats['untraceable_count']/stats['total']*100:.1f}%"
    )
    console.print(summary_table)
    
    # By source breakdown
    source_table = Table(title="\n按來源分類")
    source_table.add_column("來源", style="cyan")
    source_table.add_column("可追溯", justify="right", style="green")
    source_table.add_column("不可追溯", justify="right", style="red")
    source_table.add_column("總計", justify="right")
    
    for source, counts in sorted(stats["by_source"].items()):
        total = counts["traceable"] + counts["untraceable"]
        source_table.add_row(
            source,
            str(counts["traceable"]),
            str(counts["untraceable"]),
            str(total)
        )
    console.print(source_table)
    
    # Validation check
    console.print("\n[bold]驗證檢查:[/bold]")
    total_check = stats["traceable_count"] + stats["untraceable_count"]
    if total_check == stats["total"]:
        console.print(f"  ✅ 總數驗證通過: {stats['traceable_count']} + {stats['untraceable_count']} = {stats['total']}")
    else:
        console.print(f"  ❌ 總數驗證失敗: {stats['traceable_count']} + {stats['untraceable_count']} ≠ {stats['total']}")


def main():
    """Main entry point for the audit script."""
    console.print("[bold blue]P3-T03-S1: 可追溯 QA 資料盤點與分類[/bold blue]\n")
    
    # Check input file exists
    if not TRAINING_DATA_PATH.exists():
        console.print(f"[red]Error: Training data not found at {TRAINING_DATA_PATH}[/red]")
        return 1
    
    # Load data
    console.print(f"Loading training data from {TRAINING_DATA_PATH}...")
    samples = load_training_data(TRAINING_DATA_PATH)
    console.print(f"Loaded {len(samples)} samples\n")
    
    # Run audit
    results = run_audit(samples)
    
    # Display summary
    display_summary(results)
    
    # Save results
    console.print("\n[bold]儲存結果...[/bold]")
    save_results(results, OUTPUT_DIR)
    
    console.print("\n[bold green]✅ 盤點完成！[/bold green]")
    console.print(f"   可追溯樣本: {results['stats']['traceable_count']} 筆 → 可進行 RAG 上下文回填")
    console.print(f"   不可追溯樣本: {results['stats']['untraceable_count']} 筆 → 保留為 Pure QA")
    
    return 0


if __name__ == "__main__":
    exit(main())
