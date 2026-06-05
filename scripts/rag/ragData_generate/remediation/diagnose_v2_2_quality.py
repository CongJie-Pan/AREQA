"""Diagnose v2.2 dataset quality issues.

This script checks the actual file contents to verify:
1. Pure QA background coverage
2. CoT background coverage
3. Negative sampling strategy (Refusal vs Parametric Fallback)

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S8 Quality Verification
"""

import json
from pathlib import Path
from typing import Dict, List
from collections import Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Paths to check
V2_2_COMPLETE = PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.2" / "complete_training_dataset.jsonl"
REMEDIATED_PURE_QA = PROJECT_ROOT / "data" / "training" / "remediation" / "pure_qa_with_context_fixed.jsonl"
REMEDIATED_COT = PROJECT_ROOT / "data" / "training" / "remediation" / "cot_samples_fixed.jsonl"
REMEDIATED_QA_ROB = PROJECT_ROOT / "data" / "training" / "remediation" / "qa_robustness_fixed.jsonl"


def load_jsonl_sample(file_path: Path, max_samples: int = 1000) -> List[Dict]:
    """Load sample from JSONL."""
    samples = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= max_samples:
                break
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples


def check_background_coverage(samples: List[Dict], source_filter: str = None) -> Dict:
    """Check if samples have 【參考資料】 background."""
    stats = {
        "total": 0,
        "has_background": 0,
        "empty_input": 0,
        "input_samples": []
    }
    
    for sample in samples:
        source = sample.get('metadata', {}).get('source', '')
        
        # Filter by source if specified
        if source_filter and source_filter not in source:
            continue
        
        stats["total"] += 1
        input_text = sample.get('input', '')
        
        if not input_text:
            stats["empty_input"] += 1
        elif '【參考資料】' in input_text:
            stats["has_background"] += 1
        
        # Store first 3 samples for inspection
        if len(stats["input_samples"]) < 3:
            stats["input_samples"].append({
                "source": source,
                "input": input_text[:200] if input_text else "EMPTY",
                "has_background": '【參考資料】' in input_text
            })
    
    stats["coverage_pct"] = (stats["has_background"] / stats["total"] * 100) if stats["total"] > 0 else 0
    stats["empty_pct"] = (stats["empty_input"] / stats["total"] * 100) if stats["total"] > 0 else 0
    
    return stats


def check_negative_strategy(samples: List[Dict], source_filter: str = "Robustness") -> Dict:
    """Check Negative sampling strategy."""
    refusal_keywords = ["無法回答", "不能回答", "參考資料與問題無關", "無關", "拒答", "沒有提到", "未提及"]
    
    stats = {
        "total": 0,
        "refusals": 0,
        "answers": 0,
        "refusal_samples": []
    }
    
    for sample in samples:
        source = sample.get('metadata', {}).get('source', '')
        
        if source_filter and source_filter not in source:
            continue
        
        stats["total"] += 1
        output = sample.get('output', '')
        
        is_refusal = any(kw in output for kw in refusal_keywords)
        
        if is_refusal:
            stats["refusals"] += 1
            if len(stats["refusal_samples"]) < 3:
                stats["refusal_samples"].append({
                    "output": output[:100],
                    "has_refusal": True
                })
        else:
            stats["answers"] += 1
    
    stats["refusal_pct"] = (stats["refusals"] / stats["total"] * 100) if stats["total"] > 0 else 0
    stats["answer_pct"] = (stats["answers"] / stats["total"] * 100) if stats["total"] > 0 else 0
    
    return stats


def diagnose_v2_2_complete():
    """Diagnose the complete v2.2 dataset."""
    console.print(Panel(
        "[bold red]🚨 v2.2 Dataset Quality Diagnosis[/bold red]\n"
        "Checking actual file contents for compliance issues",
        border_style="red"
    ))
    
    console.print(f"\n[cyan]Loading v2.2 complete dataset (first 5000 samples)...[/cyan]")
    samples = load_jsonl_sample(V2_2_COMPLETE, max_samples=5000)
    console.print(f"Loaded: {len(samples)} samples\n")
    
    # Check by source
    sources = ["RAG Format", "Pure QA", "CoT", "QA Robustness"]
    
    results = {}
    
    for source in sources:
        console.print(f"[bold cyan]Checking {source}...[/bold cyan]")
        
        # Background coverage
        bg_stats = check_background_coverage(samples, source_filter=source)
        results[source] = bg_stats
        
        console.print(f"  Total samples: {bg_stats['total']}")
        console.print(f"  Has 【參考資料】: {bg_stats['has_background']} ({bg_stats['coverage_pct']:.1f}%)")
        console.print(f"  Empty input: {bg_stats['empty_input']} ({bg_stats['empty_pct']:.1f}%)")
        
        # Show sample
        if bg_stats["input_samples"]:
            console.print(f"  [dim]Sample: {bg_stats['input_samples'][0]['input'][:100]}...[/dim]")
        console.print()
    
    # Check Negative strategy
    console.print(f"[bold cyan]Checking Negative Strategy (QA Robustness)...[/bold cyan]")
    neg_stats = check_negative_strategy(samples)
    
    console.print(f"  Total: {neg_stats['total']}")
    console.print(f"  Refusals: {neg_stats['refusals']} ({neg_stats['refusal_pct']:.1f}%)")
    console.print(f"  Answers: {neg_stats['answers']} ({neg_stats['answer_pct']:.1f}%)")
    
    if neg_stats["refusal_samples"]:
        console.print(f"  [dim]Sample refusal: {neg_stats['refusal_samples'][0]['output']}[/dim]")
    console.print()
    
    # Summary table
    table = Table(show_header=True, header_style="bold red")
    table.add_column("Source", style="dim")
    table.add_column("Samples", justify="right")
    table.add_column("Background Coverage", justify="right")
    table.add_column("Status", justify="center")
    
    for source in sources:
        if source in results:
            stats = results[source]
            status = "✅" if stats['coverage_pct'] >= 95 else "🔴"
            table.add_row(
                source,
                f"{stats['total']}",
                f"{stats['coverage_pct']:.1f}%",
                status
            )
    
    # Add negative row
    status = "✅" if neg_stats['answer_pct'] >= 95 else "🔴"
    table.add_row(
        "Negative (Fallback %)",
        f"{neg_stats['total']}",
        f"{neg_stats['answer_pct']:.1f}%",
        status
    )
    
    console.print(table)
    
    # Overall verdict
    console.print()
    issues = []
    
    for source in ["Pure QA", "CoT"]:
        if source in results and results[source]['coverage_pct'] < 95:
            issues.append(f"{source}: {results[source]['coverage_pct']:.1f}% coverage (expected 100%)")
    
    if neg_stats['refusal_pct'] > 5:
        issues.append(f"Negative: {neg_stats['refusal_pct']:.1f}% still refusing (expected <1%)")
    
    if issues:
        console.print(Panel(
            "[bold red]🔴 CRITICAL ISSUES FOUND[/bold red]\n\n" +
            "\n".join(f"• {issue}" for issue in issues) +
            "\n\n[bold]Dataset NOT ready for training![/bold]",
            border_style="red"
        ))
    else:
        console.print(Panel(
            "[bold green]✅ All checks passed![/bold green]\n"
            "Dataset ready for training.",
            border_style="green"
        ))


def diagnose_remediated_files():
    """Check if remediated files have correct format."""
    console.print(Panel(
        "[bold cyan]Checking Remediated Files[/bold cyan]",
        border_style="cyan"
    ))
    
    files = {
        "Pure QA Fixed": REMEDIATED_PURE_QA,
        "CoT Fixed": REMEDIATED_COT,
        "QA Robustness Fixed": REMEDIATED_QA_ROB
    }
    
    for name, path in files.items():
        if not path.exists():
            console.print(f"[red]✗ {name}: File not found[/red]")
            continue
        
        samples = load_jsonl_sample(path, max_samples=100)
        bg_stats = check_background_coverage(samples)
        
        console.print(f"\n[bold]{name}[/bold]")
        console.print(f"  Samples: {bg_stats['total']}")
        console.print(f"  Background: {bg_stats['coverage_pct']:.1f}%")
        console.print(f"  Empty input: {bg_stats['empty_pct']:.1f}%")
        
        if bg_stats["input_samples"]:
            console.print(f"  [dim]Sample: {bg_stats['input_samples'][0]['input'][:150]}...[/dim]")
    
    console.print()


def main():
    """Main entry point."""
    # Check remediated files first
    diagnose_remediated_files()
    
    console.print("\n" + "="*80 + "\n")
    
    # Check final v2.2 dataset
    diagnose_v2_2_complete()


if __name__ == "__main__":
    main()
