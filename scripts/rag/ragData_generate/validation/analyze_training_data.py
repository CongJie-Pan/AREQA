"""Analyze training data composition to identify format types.

This script scans all training data and classifies samples into:
- RAG Format: Contains context (【參考資料】)
- Pure QA: No context
- Negative Sampling: Contains context but refuses to answer
- CoT: Contains reasoning steps

Why this analysis is needed:
- Verify current dataset composition
- Identify gaps before LM-ft training
- Ensure compliance with RA-DIT spec (50% context samples)
"""

import json
from pathlib import Path
from collections import defaultdict
from rich.console import Console
from rich.table import Table

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Directories to scan
TRAINING_DIRS = [
    PROJECT_ROOT / "data" / "training" / "rag_format",
    PROJECT_ROOT / "data" / "training" / "merged",
    PROJECT_ROOT / "data" / "training" / "cot",
    PROJECT_ROOT / "data" / "training" / "socratic",
]


def classify_sample(sample: dict) -> str:
    """Classify a sample into format type.
    
    Classification logic:
    1. Check if input contains 【參考資料】 → has context
    2. If has context + output refuses → Negative
    3. If has context + normal answer → RAG
    4. If no context + has <thought> → CoT
    5. If no context + normal answer → Pure QA
    """
    instruction = sample.get("instruction", "")
    input_text = sample.get("input", "")
    output_text = sample.get("output", "")
    
    has_context = "【參考資料】" in input_text or "Context:" in input_text
    has_thought = "<thought>" in output_text or sample.get("is_cot", False)
    has_socratic = sample.get("is_socratic", False)
    
    # Check for refusal keywords (negative sampling)
    refusal_keywords = ["無法回答", "不足以回答", "無關", "無法從給定", "參考資料"]
    is_refusal = any(kw in output_text for kw in refusal_keywords)
    
    # Classification
    if has_context and is_refusal:
        return "negative_sampling"
    elif has_context:
        return "rag_format"
    elif has_thought:
        return "cot"
    elif has_socratic:
        return "socratic"
    else:
        return "pure_qa"


def load_jsonl(path: Path) -> list:
    """Load samples from JSONL file."""
    samples = []
    if not path.exists():
        return samples
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return samples


def analyze_directory(dir_path: Path) -> dict:
    """Analyze all JSONL files in directory."""
    stats = defaultdict(int)
    all_samples = []
    
    if not dir_path.exists():
        return stats
    
    # Find all .jsonl files
    for jsonl_file in dir_path.rglob("*.jsonl"):
        samples = load_jsonl(jsonl_file)
        all_samples.extend(samples)
    
    # Classify samples
    for sample in all_samples:
        format_type = classify_sample(sample)
        stats[format_type] += 1
    
    stats["total"] = len(all_samples)
    return stats


def main():
    """Main entry point."""
    console.print("[bold blue]Training Data Composition Analysis[/bold blue]\n")
    
    # Analyze each directory
    all_stats = defaultdict(int)
    dir_stats = {}
    
    for dir_path in TRAINING_DIRS:
        console.print(f"Analyzing {dir_path.name}...")
        stats = analyze_directory(dir_path)
        dir_stats[dir_path.name] = stats
        
        # Aggregate
        for k, v in stats.items():
            all_stats[k] += v
    
    console.print("\n")
    
    # Display summary by directory
    for dir_name, stats in dir_stats.items():
        if stats.get("total", 0) == 0:
            continue
        
        table = Table(title=f"{dir_name}")
        table.add_column("Format Type", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Percentage", justify="right")
        
        total = stats["total"]
        for format_type in ["rag_format", "pure_qa", "negative_sampling", "cot", "socratic"]:
            count = stats.get(format_type, 0)
            pct = (count / total * 100) if total > 0 else 0
            if count > 0:
                table.add_row(format_type, str(count), f"{pct:.1f}%")
        
        table.add_row("", "", "", style="dim")
        table.add_row("TOTAL", str(total), "100.0%", style="bold")
        
        console.print(table)
        console.print()
    
    # Overall summary
    console.print("[bold cyan]═══ Overall Summary ═══[/bold cyan]\n")
    
    summary_table = Table(title="All Training Data")
    summary_table.add_column("Format Type", style="cyan")
    summary_table.add_column("Count", justify="right")
    summary_table.add_column("Percentage", justify="right")
    summary_table.add_column("Target %", justify="right")
    summary_table.add_column("Status", justify="center")
    
    total = all_stats["total"]
    
    # Define targets from data_format_spec.md
    targets = {
        "rag_format": (50, 5),  # 50% ±5%
        "pure_qa": (35, 5),     # 35% ±5%
        "negative_sampling": (7.5, 2.5),  # 7.5% ±2.5%
        "cot": (7.5, 2.5),      # 7.5% ±2.5%
    }
    
    for format_type, (target, tolerance) in targets.items():
        count = all_stats.get(format_type, 0)
        pct = (count / total * 100) if total > 0 else 0
        
        # Check status
        if pct >= target - tolerance and pct <= target + tolerance:
            status = "✅"
            style = "green"
        elif count == 0:
            status = "❌"
            style = "red"
        else:
            status = "⚠️"
            style = "yellow"
        
        summary_table.add_row(
            format_type,
            str(count),
            f"{pct:.1f}%",
            f"{target}% ±{tolerance}%",
            status,
            style=style
        )
    
    # Add socratic if present
    if all_stats.get("socratic", 0) > 0:
        count = all_stats["socratic"]
        pct = (count / total * 100) if total > 0 else 0
        summary_table.add_row(
            "socratic",
            str(count),
            f"{pct:.1f}%",
            "-",
            "ℹ️",
            style="dim"
        )
    
    summary_table.add_row("", "", "", "", "", style="dim")
    summary_table.add_row("TOTAL", str(total), "100.0%", "", "", style="bold")
    
    console.print(summary_table)
    
    # Context ratio check
    console.print("\n[bold cyan]═══ RA-DIT Compliance Check ═══[/bold cyan]\n")
    
    context_samples = all_stats.get("rag_format", 0) + all_stats.get("negative_sampling", 0)
    context_ratio = (context_samples / total * 100) if total > 0 else 0
    
    compliance_table = Table(title="Context Sample Ratio")
    compliance_table.add_column("Metric", style="cyan")
    compliance_table.add_column("Value", justify="right")
    compliance_table.add_column("Requirement", justify="right")
    compliance_table.add_column("Status", justify="center")
    
    requirement_met = context_ratio >= 50
    status = "✅ PASS" if requirement_met else "❌ FAIL"
    style = "green" if requirement_met else "red"
    
    compliance_table.add_row(
        "Context Samples (RAG + Negative)",
        str(context_samples),
        "-",
        ""
    )
    compliance_table.add_row(
        "Context Ratio",
        f"{context_ratio:.1f}%",
        "≥ 50%",
        status,
        style=style
    )
    
    console.print(compliance_table)
    
    # Recommendations
    console.print("\n[bold cyan]═══ Recommendations ═══[/bold cyan]\n")
    
    if all_stats.get("negative_sampling", 0) == 0:
        console.print("❌ [red]Missing Negative Sampling[/red]")
        console.print("   → Generate ~1,000 negative samples\n")
    
    pure_qa_count = all_stats.get("pure_qa", 0)
    pure_qa_pct = (pure_qa_count / total * 100) if total > 0 else 0
    if pure_qa_pct < 30:
        target_count = int(total * 0.35)
        gap = target_count - pure_qa_count
        console.print(f"⚠️ [yellow]Insufficient Pure QA[/yellow]")
        console.print(f"   Current: {pure_qa_count} ({pure_qa_pct:.1f}%)")
        console.print(f"   Target: {target_count} (35%)")
        console.print(f"   → Need {gap} more Pure QA samples\n")
    
    if requirement_met:
        console.print("✅ [green]Context ratio meets RA-DIT requirements[/green]\n")
    else:
        console.print(f"❌ [red]Context ratio too low ({context_ratio:.1f}% < 50%)[/red]")
        console.print("   → Increase RAG or Negative samples\n")


if __name__ == "__main__":
    main()
