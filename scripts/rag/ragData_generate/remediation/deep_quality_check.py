"""Deep quality check with random sampling across all sources.

This script randomly samples from each source type to verify:
1. Background coverage for each source
2. Negative sampling strategy

Author: AI Agent
Date: 2026-02-08
"""

import json
import random
from pathlib import Path
from typing import Dict, List
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
V2_2_COMPLETE = PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.2" / "complete_training_dataset.jsonl"

# Refusal keywords
REFUSAL_KEYWORDS = ["無法回答", "不能回答", "參考資料與問題無關", "無關", "拒答", "沒有提到", "未提及"]


def load_all_samples_by_source() -> Dict[str, List[Dict]]:
    """Load all samples grouped by source."""
    console.print("[cyan]Loading all samples from v2.2...[/cyan]")
    
    by_source = {}
    
    with open(V2_2_COMPLETE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                sample = json.loads(line)
                source = sample.get('metadata', {}).get('source', 'unknown')
                
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(sample)
            except json.JSONDecodeError:
                continue
    
    console.print(f"[green]✅ Loaded {sum(len(v) for v in by_source.values()):,} samples across {len(by_source)} sources[/green]\n")
    
    return by_source


def check_source_quality(samples: List[Dict], source_name: str, sample_size: int = 100) -> Dict:
    """Check quality of a specific source."""
    # Random sample
    check_samples = random.sample(samples, min(sample_size, len(samples)))
    
    stats = {
        "total_in_source": len(samples),
        "sampled": len(check_samples),
        "has_background": 0,
        "empty_input": 0,
        "refusals": 0,
        "answers": 0,
        "sample_inputs": [],
        "sample_outputs": []
    }
    
    for sample in check_samples:
        input_text = sample.get('input', '')
        output_text = sample.get('output', '')
        
        # Check background
        if not input_text:
            stats["empty_input"] += 1
        elif '【參考資料】' in input_text:
            stats["has_background"] += 1
        
        # Check refusal (for Negative samples)
        if "Robustness" in source_name or "Negative" in source_name:
            is_refusal = any(kw in output_text for kw in REFUSAL_KEYWORDS)
            if is_refusal:
                stats["refusals"] += 1
            else:
                stats["answers"] += 1
        
        # Store samples
        if len(stats["sample_inputs"]) < 2:
            stats["sample_inputs"].append({
                "has_bg": '【參考資料】' in input_text,
                "text": input_text[:150] if input_text else "EMPTY"
            })
        
        if len(stats["sample_outputs"]) < 2 and output_text:
            stats["sample_outputs"].append(output_text[:100])
    
    stats["bg_coverage_pct"] = (stats["has_background"] / stats["sampled"] * 100) if stats["sampled"] > 0 else 0
    stats["empty_pct"] = (stats["empty_input"] / stats["sampled"] * 100) if stats["sampled"] > 0 else 0
    
    if stats["refusals"] + stats["answers"] > 0:
        total_neg = stats["refusals"] + stats["answers"]
        stats["refusal_pct"] = (stats["refusals"] / total_neg * 100)
        stats["answer_pct"] = (stats["answers"] / total_neg * 100)
    
    return stats


def main():
    """Main quality check."""
    # Set random seed
    random.seed(42)
    
    console.print(Panel(
        "[bold green]v2.2 Deep Quality Check (Random Sampling)[/bold green]\n"
        "Randomly sampling from each source to verify quality",
        border_style="green"
    ))
    
    # Load all samples by source
    by_source = load_all_samples_by_source()
    
    # Check each source
    results = {}
    
    for source_name, samples in sorted(by_source.items()):
        console.print(f"[bold cyan]Checking {source_name}...[/bold cyan]")
        stats = check_source_quality(samples, source_name, sample_size=100)
        results[source_name] = stats
        
        console.print(f"  Total samples: {stats['total_in_source']:,}")
        console.print(f"  Sampled: {stats['sampled']}")
        console.print(f"  Background coverage: {stats['bg_coverage_pct']:.1f}%")
        console.print(f"  Empty input: {stats['empty_pct']:.1f}%")
        
        if "Robustness" in source_name or "Negative" in source_name:
            console.print(f"  Parametric Fallback: {stats.get('answer_pct', 0):.1f}%")
            console.print(f"  Refusals: {stats.get('refusal_pct', 0):.1f}%")
        
        if stats["sample_inputs"]:
            console.print(f"  [dim]Sample: {stats['sample_inputs'][0]['text'][:80]}...[/dim]")
        console.print()
    
    # Summary table
    console.print("\n[bold]Quality Summary:[/bold]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Source", style="dim")
    table.add_column("Total", justify="right")
    table.add_column("Background", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Notes")
    
    for source_name in sorted(results.keys()):
        stats = results[source_name]
        status = "✅" if stats['bg_coverage_pct'] >= 95 else "🔴"
        
        notes = []
        if stats['empty_pct'] > 5:
            notes.append(f"{stats['empty_pct']:.0f}% empty")
        if "Robustness" in source_name and stats.get('answer_pct', 0) > 0:
            notes.append(f"{stats.get('answer_pct', 0):.0f}% Fallback")
        
        table.add_row(
            source_name,
            f"{stats['total_in_source']:,}",
            f"{stats['bg_coverage_pct']:.1f}%",
            status,
            ", ".join(notes) if notes else "OK"
        )
    
    console.print(table)
    
    # Overall verdict
    console.print()
    issues = []
    
    for source_name, stats in results.items():
        if stats['bg_coverage_pct'] < 95:
            issues.append(f"{source_name}: Only {stats['bg_coverage_pct']:.1f}% background coverage")
        
        if "Robustness" in source_name:
            refusal_pct = stats.get('refusal_pct', 0)
            if refusal_pct > 5:
                issues.append(f"{source_name}: {refusal_pct:.1f}% still refusing (expected <1%)")
    
    if issues:
        console.print(Panel(
            "[bold red]🔴 QUALITY ISSUES FOUND[/bold red]\n\n" +
            "\n".join(f"• {issue}" for issue in issues) +
            "\n\n[bold]Dataset needs further fixing![/bold]",
            border_style="red"
        ))
    else:
        console.print(Panel(
            "[bold green]✅ All Quality Checks Passed![/bold green]\n\n"
            "Dataset is ready for LM Fine-tuning!",
            border_style="green"
        ))


if __name__ == "__main__":
    main()
