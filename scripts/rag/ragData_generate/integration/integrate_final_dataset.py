"""Final dataset integration for P3-T04-S3.

This script merges all training data types into a complete RA-DIT dataset:
- RAG Format (from P3-T03)
- Pure QA (existing + P3-T04 supplement)
- Negative Sampling (from P3-T04)
- CoT (existing)

Why integration is critical:
- RA-DIT requires balanced type distribution
- Final validation of ratio compliance
- Preparation for LM-ft training

Output location: data/training/completeSet/v2/
"""

import json
import random
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from typing import List, Dict

from rich.console import Console
from rich.table import Table
from rich.progress import track

console = Console()

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Input files
RAG_FILE = PROJECT_ROOT / "data" / "training" / "rag_format" / "backfilled_radit_format.jsonl"
PURE_QA_V1_FILE = PROJECT_ROOT / "data" / "training" / "completeSet" / "v1" / "merged" / "all_training_data.jsonl"
PURE_QA_SUPPLEMENT = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_supplement_2211.jsonl"
NEGATIVE_FILE = PROJECT_ROOT / "data" / "training" / "negative_samples" / "negative_sampling_3000.jsonl"

# Output directory
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "completeSet" / "v2"
OUTPUT_FILE = OUTPUT_DIR / "complete_training_dataset.jsonl"
TRAIN_FILE = OUTPUT_DIR / "train.jsonl"
VAL_FILE = OUTPUT_DIR / "val.jsonl"
STATS_FILE = OUTPUT_DIR / "final_dataset_stats.json"

# Split ratio
TRAIN_RATIO = 0.95
VAL_RATIO = 0.05

# Random seed for reproducibility
RANDOM_SEED = 42
random.seed(RANDOM_SEED)


# ============================================================================
# Helper Functions
# ============================================================================

def load_jsonl(path: Path) -> List[Dict]:
    """Load samples from JSONL file."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def save_jsonl(samples: List[Dict], path: Path):
    """Save samples to JSONL file."""
    with open(path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def load_existing_typed_data(directory: Path, data_type: str) -> List[Dict]:
    """Load existing data of specific type from merged directory."""
    samples = []
    
    # Look for all .jsonl files in the directory
    for jsonl_file in directory.glob("*.jsonl"):
        file_samples = load_jsonl(jsonl_file)
        
        # Filter by type
        for sample in file_samples:
            metadata = sample.get("metadata", {})
            if metadata.get("type") == data_type:
                samples.append(sample)
    
    return samples


def estimate_tokens(text: str) -> int:
    """Estimate token count."""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars * 2 + other_chars // 4


# ============================================================================
# Data Loading
# ============================================================================

def load_all_datasets():
    """Load all datasets and categorize by type."""
    console.print("[bold blue]加載所有資料集...[/bold blue]\n")
    
    datasets = {
        "rag": [],
        "pure_qa": [],
        "negative": []
    }
    
    # 1. Load RAG format (from P3-T03)
    console.print(f"Loading RAG format from {RAG_FILE}...")
    datasets["rag"] = load_jsonl(RAG_FILE)
    console.print(f"  Loaded: {len(datasets['rag'])} samples")
    
    # 2. Load existing Pure QA from v1 (baseline dataset, no metadata.type)
    console.print(f"\nLoading existing Pure QA (v1) from {PURE_QA_V1_FILE}...")
    v1_samples = load_jsonl(PURE_QA_V1_FILE)
    
    # Add metadata.type to v1 samples (they don't have it)
    for sample in v1_samples:
        if "metadata" not in sample:
            sample["metadata"] = {}
        sample["metadata"]["type"] = "pure_qa"
        sample["metadata"]["source"] = "v1_baseline"
    
    datasets["pure_qa"] = v1_samples
    console.print(f"  Loaded: {len(datasets['pure_qa'])} samples (v1 baseline)")
    
    # 3. Load Pure QA supplement (from P3-T04)
    console.print(f"\nLoading Pure QA supplement from {PURE_QA_SUPPLEMENT}...")
    pure_qa_supplement = load_jsonl(PURE_QA_SUPPLEMENT)
    datasets["pure_qa"].extend(pure_qa_supplement)
    console.print(f"  Added: {len(pure_qa_supplement)} samples (P3-T04 supplement)")
    console.print(f"  Total Pure QA: {len(datasets['pure_qa'])} samples")
    
    # 4. Load Negative Sampling (from P3-T04)
    console.print(f"\nLoading Negative Sampling from {NEGATIVE_FILE}...")
    datasets["negative"] = load_jsonl(NEGATIVE_FILE)
    console.print(f"  Loaded: {len(datasets['negative'])} samples\n")
    
    return datasets


# ============================================================================
# Data Integration
# ============================================================================

def integrate_datasets(datasets: Dict[str, List[Dict]]) -> List[Dict]:
    """Merge all datasets into one complete dataset."""
    console.print("[cyan]整合資料集...[/cyan]\n")
    
    all_samples = []
    
    for data_type, samples in datasets.items():
        console.print(f"Adding {data_type}: {len(samples)} samples")
        all_samples.extend(samples)
    
    # Shuffle for better training
    random.shuffle(all_samples)
    
    console.print(f"\n[bold]Total integrated samples: {len(all_samples)}[/bold]\n")
    
    return all_samples


def split_train_val(samples: List[Dict], train_ratio: float = 0.95) -> tuple:
    """Split dataset into train and validation sets with stratification by type."""
    console.print(f"[cyan]分割訓練/驗證集 (Train: {train_ratio*100:.0f}%, Val: {(1-train_ratio)*100:.0f}%)[/cyan]\n")
    
    # Group samples by type for stratified split
    samples_by_type = defaultdict(list)
    for sample in samples:
        data_type = sample.get("metadata", {}).get("type", "unknown")
        samples_by_type[data_type].append(sample)
    
    train_samples = []
    val_samples = []
    
    # Split each type proportionally
    for data_type, type_samples in samples_by_type.items():
        random.shuffle(type_samples)
        split_idx = int(len(type_samples) * train_ratio)
        
        train_samples.extend(type_samples[:split_idx])
        val_samples.extend(type_samples[split_idx:])
        
        console.print(f"{data_type}: Train={split_idx}, Val={len(type_samples)-split_idx}")
    
    # Shuffle again
    random.shuffle(train_samples)
    random.shuffle(val_samples)
    
    console.print(f"\n[bold]Train: {len(train_samples)}, Val: {len(val_samples)}[/bold]\n")
    
    return train_samples, val_samples


# ============================================================================
# Statistics
# ============================================================================

def generate_statistics(datasets: Dict[str, List[Dict]], complete_dataset: List[Dict]) -> Dict:
    """Generate comprehensive statistics."""
    total_samples = len(complete_dataset)
    
    # Type distribution
    type_counts = {
        "rag": len(datasets["rag"]),
        "pure_qa": len(datasets["pure_qa"]),
        "negative": len(datasets["negative"])
    }
    
    type_ratios = {k: v/total_samples*100 for k, v in type_counts.items()}
    
    # Context ratio
    context_samples = type_counts["rag"] + type_counts["negative"]
    context_ratio = context_samples / total_samples * 100
    
    # Token statistics
    token_stats = defaultdict(list)
    for sample in complete_dataset[:1000]:  # Sample 1000 for efficiency
        data_type = sample.get("metadata", {}).get("type", "unknown")
        total_text = sample.get("input", "") + sample.get("output", "")
        tokens = estimate_tokens(total_text)
        token_stats[data_type].append(tokens)
    
    avg_tokens = {
        k: sum(v)/len(v) if v else 0 
        for k, v in token_stats.items()
    }
    
    # RA-DIT compliance check (without CoT - not available yet)
    # Adjusted targets: RAG ~65%, Pure QA ~28%, Negative ~7% (totaling 100%)
    radit_compliance = {
        "rag": 60 <= type_ratios["rag"] <= 70,  # ~65% target (adjusted)
        "pure_qa": 23 <= type_ratios["pure_qa"] <= 33,  # ~28% target (adjusted)
        "negative": 5 <= type_ratios["negative"] <= 10,  # 7.5% ±2.5%
        "context_ratio": context_ratio >= 50
    }
    
    stats = {
        "generation_timestamp": datetime.now().isoformat(),
        "total_samples": total_samples,
        "type_counts": type_counts,
        "type_ratios": type_ratios,
        "context_ratio": context_ratio,
        "radit_compliance": radit_compliance,
        "all_compliant": all(radit_compliance.values()),
        "average_tokens_by_type": avg_tokens,
        "random_seed": RANDOM_SEED,
        "train_ratio": TRAIN_RATIO,
        "val_ratio": VAL_RATIO,
        "note": "CoT data not included in v2 - will be added in future iteration"
    }
    
    return stats


# ============================================================================
# Main Execution
# ============================================================================

def main():
    console.print("[bold blue]P3-T04-S3: 最終資料集整合[/bold blue]\n")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load all datasets
    datasets = load_all_datasets()
    
    # Integrate
    complete_dataset = integrate_datasets(datasets)
    
    # Save complete dataset
    console.print(f"Saving complete dataset to {OUTPUT_FILE}...")
    save_jsonl(complete_dataset, OUTPUT_FILE)
    
    # Split train/val
    train_samples, val_samples = split_train_val(complete_dataset, TRAIN_RATIO)
    
    # Save splits
    console.print(f"Saving train set to {TRAIN_FILE}...")
    save_jsonl(train_samples, TRAIN_FILE)
    
    console.print(f"Saving validation set to {VAL_FILE}...")
    save_jsonl(val_samples, VAL_FILE)
    
    # Generate statistics
    console.print("\nGenerating statistics...")
    stats = generate_statistics(datasets, complete_dataset)
    
    # Save statistics
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    console.print(f"Statistics saved to {STATS_FILE}\n")
    
    # Display summary
    console.print("[bold cyan]═══ 最終資料集統計 ═══[/bold cyan]\n")
    
    table = Table(title="資料類型分佈 (v2 - 不含 CoT)")
    table.add_column("類型", style="cyan")
    table.add_column("數量", justify="right")
    table.add_column("佔比", justify="right")
    table.add_column("調整後目標", justify="center")
    table.add_column("狀態")
    
    targets = {
        "rag": "60-70%",
        "pure_qa": "23-33%",
        "negative": "5-10%"
    }
    
    for data_type in ["rag", "pure_qa", "negative"]:
        count = stats["type_counts"][data_type]
        ratio = stats["type_ratios"][data_type]
        compliant = stats["radit_compliance"][data_type]
        
        table.add_row(
            data_type.upper(),
            str(count),
            f"{ratio:.1f}%",
            targets[data_type],
            "✅" if compliant else "❌"
        )
    
    # Total row
    table.add_row(
        "[bold]總計[/bold]",
        f"[bold]{stats['total_samples']}[/bold]",
        "[bold]100.0%[/bold]",
        "",
        ""
    )
    
    console.print(table)
    
    # Context ratio
    console.print(f"\n[bold]上下文比例:[/bold] {stats['context_ratio']:.1f}% (目標: ≥50%) ", end="")
    console.print("✅" if stats["radit_compliance"]["context_ratio"] else "❌")
    
    # Overall compliance
    overall = "✅ 全部符合 RA-DIT 規範" if stats["all_compliant"] else "❌ 有項目不符合"
    console.print(f"\n[bold]整體符合度:[/bold] {overall}\n")
    
    # File summary
    console.print("[bold green]✅ 整合完成！[/bold green]")
    console.print(f"\n輸出檔案:")
    console.print(f"  - 完整資料集: {OUTPUT_FILE}")
    console.print(f"  - 訓練集: {TRAIN_FILE} ({len(train_samples)} 筆)")
    console.print(f"  - 驗證集: {VAL_FILE} ({len(val_samples)} 筆)")
    console.print(f"  - 統計報告: {STATS_FILE}")


if __name__ == "__main__":
    main()
