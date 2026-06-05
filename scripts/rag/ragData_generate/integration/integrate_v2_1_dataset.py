"""Integrate v2.1 final training dataset.

This script merges all data sources and creates train/val splits.

Author: AI Agent  
Date: 2026-02-08
Task: P3-T04-S6 Phase 2-4 - Integration, Splitting, Validation
"""

import json
import random
import sys
from pathlib import Path
from typing import Dict, Any, List
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

console = Console()

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Data sources
DATA_SOURCES = {
    "RAG Format": PROJECT_ROOT / "data" / "training" / "rag_format" / "backfilled_radit_format.jsonl",
    "Pure QA with Context": PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_with_context.jsonl",
    "CoT Samples": PROJECT_ROOT / "data" / "training" / "cot" / "cot_samples.jsonl",
    "QA Robustness": PROJECT_ROOT / "data" / "training" / "negative_samples" / "qa_robustness.jsonl",
    "RC Negative": PROJECT_ROOT / "data" / "training" / "negative_samples" / "rc_negative.jsonl",
}

# Output directory
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.1"

# Split ratio
TRAIN_RATIO = 0.95
VAL_RATIO = 0.05


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file.
    
    Why: Need to read all data sources
    """
    samples = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples


def add_source_metadata(samples: List[Dict], source_name: str) -> List[Dict]:
    """Add source tracking metadata.
    
    Why: Track which source each sample came from for analysis
    """
    for sample in samples:
        if 'metadata' not in sample:
            sample['metadata'] = {}
        sample['metadata']['source'] = source_name
    return samples


def merge_datasets() -> List[Dict[str, Any]]:
    """Merge all data sources.
    
    Returns:
        List of all samples with source metadata
    """
    console.print(Panel(
        "[bold cyan]v2.1 Dataset Integration - Merging Data Sources[/bold cyan]",
        border_style="cyan"
    ))
    
    all_samples = []
    source_counts = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Loading data sources...", total=len(DATA_SOURCES))
        
        for source_name, source_path in DATA_SOURCES.items():
            samples = load_jsonl(source_path)
            samples = add_source_metadata(samples, source_name)
            
            all_samples.extend(samples)
            source_counts[source_name] = len(samples)
            
            progress.update(task, advance=1)
    
    console.print(f"\n[green]✅ Loaded {len(all_samples):,} total samples[/green]\n")
    
    # Display source distribution
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Source", style="dim")
    table.add_column("Count", justify="right", style="green")
    table.add_column("Percentage", justify="right")
    
    for source_name, count in source_counts.items():
        percentage = (count / len(all_samples)) * 100
        table.add_row(source_name, f"{count:,}", f"{percentage:.1f}%")
    
    table.add_row("[bold]Total[/bold]", f"[bold]{len(all_samples):,}[/bold]", "[bold]100.0%[/bold]")
    
    console.print(table)
    console.print()
    
    return all_samples


def stratified_split(samples: List[Dict], train_ratio: float) -> tuple:
    """Perform stratified train/val split.
    
    Why: Maintain source distribution in both splits
    
    Args:
        samples: All samples
        train_ratio: Ratio for training set (e.g., 0.95)
    
    Returns:
        Tuple of (train_samples, val_samples)
    """
    console.print("[cyan]Performing stratified 95/5 train/val split...[/cyan]")
    
    # Group by source
    by_source = {}
    for sample in samples:
        source = sample.get('metadata', {}).get('source', 'unknown')
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(sample)
    
    train_samples = []
    val_samples = []
    
    # Split each source proportionally
    for source, source_samples in by_source.items():
        random.shuffle(source_samples)
        split_idx = int(len(source_samples) * train_ratio)
        
        train_samples.extend(source_samples[:split_idx])
        val_samples.extend(source_samples[split_idx:])
        
        console.print(f"  {source}: {split_idx:,} train / {len(source_samples) - split_idx:,} val")
    
    # Shuffle final splits
    random.shuffle(train_samples)
    random.shuffle(val_samples)
    
    console.print(f"\n[green]✅ Split complete:[/green]")
    console.print(f"  Training: {len(train_samples):,} samples ({len(train_samples)/len(samples)*100:.1f}%)")
    console.print(f"  Validation: {len(val_samples):,} samples ({len(val_samples)/len(samples)*100:.1f}%)\n")
    
    return train_samples, val_samples


def validate_dataset(samples: List[Dict], name: str) -> Dict[str, Any]:
    """Validate dataset quality.
    
    Why: Ensure format compliance and quality standards
    
    Returns:
        Validation statistics
    """
    stats = {
        "total": len(samples),
        "format_valid": 0,
        "has_input": 0,
        "has_output": 0,
        "has_metadata": 0,
        "source_distribution": Counter(),
    }
    
    for sample in samples:
        # Check format
        if 'input' in sample and 'output' in sample:
            stats["format_valid"] += 1
        
        if sample.get('input'):
            stats["has_input"] += 1
        
        if sample.get('output'):
            stats["has_output"] += 1
        
        if sample.get('metadata'):
            stats["has_metadata"] += 1
            source = sample['metadata'].get('source', 'unknown')
            stats["source_distribution"][source] += 1
    
    # Calculate percentages
    stats["format_valid_pct"] = (stats["format_valid"] / stats["total"]) * 100 if stats["total"] > 0 else 0
    
    console.print(f"\n[bold]Validation: {name}[/bold]")
    console.print(f"  Total samples: {stats['total']:,}")
    console.print(f"  Format valid: {stats['format_valid']:,} ({stats['format_valid_pct']:.1f}%)")
    console.print(f"  Has input: {stats['has_input']:,}")
    console.print(f"  Has output: {stats['has_output']:,}")
    console.print(f"  Has metadata: {stats['has_metadata']:,}")
    
    return stats


def save_dataset(samples: List[Dict], output_path: Path):
    """Save dataset to JSONL.
    
    Why: Persist integrated dataset
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    console.print(f"[green]✅ Saved to: {output_path.relative_to(PROJECT_ROOT)}[/green]")


def generate_statistics(all_samples, train_samples, val_samples) -> Dict:
    """Generate comprehensive statistics.
    
    Why: Document dataset composition for reference
    """
    stats = {
        "total_samples": len(all_samples),
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "train_ratio": len(train_samples) / len(all_samples),
        "val_ratio": len(val_samples) / len(all_samples),
        "source_distribution": {},
        "train_source_distribution": {},
        "val_source_distribution": {},
    }
    
    # Overall distribution
    for sample in all_samples:
        source = sample.get('metadata', {}).get('source', 'unknown')
        stats["source_distribution"][source] = stats["source_distribution"].get(source, 0) + 1
    
    # Train distribution
    for sample in train_samples:
        source = sample.get('metadata', {}).get('source', 'unknown')
        stats["train_source_distribution"][source] = stats["train_source_distribution"].get(source, 0) + 1
    
    # Val distribution
    for sample in val_samples:
        source = sample.get('metadata', {}).get('source', 'unknown')
        stats["val_source_distribution"][source] = stats["val_source_distribution"].get(source, 0) + 1
    
    return stats


def generate_readme(stats: Dict) -> str:
    """Generate human-readable README.
    
    Why: Provide documentation for dataset users
    """
    readme = f"""# v2.1 Training Dataset

## Overview
Complete training dataset for ancient Chinese literature Q&A, following RA-DIT format.

**Total Samples**: {stats['total_samples']:,}
- **Training**: {stats['train_samples']:,} ({stats['train_ratio']*100:.1f}%)
- **Validation**: {stats['val_samples']:,} ({stats['val_ratio']*100:.1f}%)

## Data Composition

### Overall Distribution
"""
    
    for source, count in sorted(stats['source_distribution'].items(), key=lambda x: -x[1]):
        pct = (count / stats['total_samples']) * 100
        readme += f"- **{source}**: {count:,} samples ({pct:.1f}%)\n"
    
    readme += """
### Training Set Distribution
"""
    
    for source, count in sorted(stats['train_source_distribution'].items(), key=lambda x: -x[1]):
        pct = (count / stats['train_samples']) * 100
        readme += f"- **{source}**: {count:,} samples ({pct:.1f}%)\n"
    
    readme += """
### Validation Set Distribution
"""
    
    for source, count in sorted(stats['val_source_distribution'].items(), key=lambda x: -x[1]):
        pct = (count / stats['val_samples']) * 100
        readme += f"- **{source}**: {count:,} samples ({pct:.1f}%)\n"
    
    readme += f"""
## File Structure

- `complete_training_dataset.jsonl` - Full merged dataset ({stats['total_samples']:,} samples)
- `train.jsonl` - Training split ({stats['train_samples']:,} samples, {stats['train_ratio']*100:.1f}%)
- `val.jsonl` - Validation split ({stats['val_samples']:,} samples, {stats['val_ratio']*100:.1f}%)
- `final_dataset_stats.json` - Detailed statistics
- `README.md` - This file

## Data Format

All samples follow RA-DIT format with:
- `input`: Question with context
- `output`: Answer
- `metadata`: Source tracking and additional info

## Generation Date
2026-02-08

## Task
P3-T04-S6: v2.1 Dataset Integration
"""
    
    return readme


def main():
    """Main entry point."""
    try:
        # Set random seed for reproducibility
        random.seed(42)
        
        # Step 1: Merge datasets
        all_samples = merge_datasets()
        
        # Step 2: Train/val split
        train_samples, val_samples = stratified_split(all_samples, TRAIN_RATIO)
        
        # Step 3: Validate
        validate_dataset(all_samples, "Complete Dataset")
        validate_dataset(train_samples, "Training Set")
        validate_dataset(val_samples, "Validation Set")
        
        # Step 4: Save datasets
        console.print("\n[cyan]Saving datasets...[/cyan]")
        save_dataset(all_samples, OUTPUT_DIR / "complete_training_dataset.jsonl")
        save_dataset(train_samples, OUTPUT_DIR / "train.jsonl")
        save_dataset(val_samples, OUTPUT_DIR / "val.jsonl")
        
        # Step 5: Generate statistics and README
        console.print("\n[cyan]Generating reports...[/cyan]")
        stats = generate_statistics(all_samples, train_samples, val_samples)
        
        stats_path = OUTPUT_DIR / "final_dataset_stats.json"
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        console.print(f"[green]✅ Statistics saved to: {stats_path.relative_to(PROJECT_ROOT)}[/green]")
        
        readme_content = generate_readme(stats)
        readme_path = OUTPUT_DIR / "README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        console.print(f"[green]✅ README saved to: {readme_path.relative_to(PROJECT_ROOT)}[/green]")
        
        # Success summary
        console.print(Panel(
            f"[bold green]🎉 v2.1 Dataset Integration Complete![/bold green]\n\n"
            f"[bold]Created:[/bold]\n"
            f"  • Complete dataset: {len(all_samples):,} samples\n"
            f"  • Training set: {len(train_samples):,} samples\n"
            f"  • Validation set: {len(val_samples):,} samples\n\n"
            f"[bold]Output:[/bold] {OUTPUT_DIR.relative_to(PROJECT_ROOT)}",
            border_style="green"
        ))
        
        sys.exit(0)
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Integration failed: {e}[/bold red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
