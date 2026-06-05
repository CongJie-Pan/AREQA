"""Check file counts and paths for v2.2 integration issue.

This script identifies why remediated files weren't integrated into v2.2.

Author: AI Agent
Date: 2026-02-08
"""

import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Expected paths
paths_to_check = {
    "RAG Format": PROJECT_ROOT / "data" / "training" / "rag_format" / "backfilled_radit_format.jsonl",
    "Pure QA Fixed": PROJECT_ROOT / "data" / "training" / "remediation" / "pure_qa_with_context_fixed.jsonl",
    "CoT Fixed": PROJECT_ROOT / "data" / "training" / "remediation" / "cot_samples_fixed.jsonl",
    "QA Robustness Fixed": PROJECT_ROOT / "data" / "training" / "remediation" / "qa_robustness_fixed.jsonl",
    "RC Negative Fixed": PROJECT_ROOT / "data" / "training" / "remediation" / "rc_negative_fixed.jsonl",
    "v2.2 Complete": PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.2" / "complete_training_dataset.jsonl",
    "v2.2 Train": PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.2" / "train.jsonl",
    "v2.2 Val": PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.2" / "val.jsonl",
}


def count_lines(file_path: Path) -> int:
    """Count lines in JSONL file."""
    if not file_path.exists():
        return -1
    
    count = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        for _ in f:
            count += 1
    return count


def check_source_distribution(file_path: Path, max_lines: int = 10000) -> dict:
    """Check source distribution in a dataset file."""
    if not file_path.exists():
        return {}
    
    sources = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            try:
                sample = json.loads(line)
                source = sample.get('metadata', {}).get('source', 'unknown')
                sources[source] = sources.get(source, 0) + 1
            except json.JSONDecodeError:
                continue
    return sources


def main():
    """Main diagnostic."""
    console.print(Panel(
        "[bold cyan]v2.2 Integration Path Diagnostic[/bold cyan]\n"
        "Checking file existence, line counts, and source distribution",
        border_style="cyan"
    ))
    
    # Check all files
    console.print("\n[bold]File Existence and Line Counts:[/bold]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("File", style="dim")
    table.add_column("Exists", justify="center")
    table.add_column("Lines", justify="right", style="green")
    table.add_column("Path", style="dim", no_wrap=False)
    
    total_expected = 0
    
    for name, path in paths_to_check.items():
        exists = "✅" if path.exists() else "🔴"
        lines = count_lines(path)
        line_str = f"{lines:,}" if lines >= 0 else "N/A"
        
        table.add_row(
            name,
            exists,
            line_str,
            str(path.relative_to(PROJECT_ROOT)) if path.exists() else "NOT FOUND"
        )
        
        # Calculate expected total
        if name in ["RAG Format", "Pure QA Fixed", "CoT Fixed", "QA Robustness Fixed", "RC Negative Fixed"]:
            if lines > 0:
                total_expected += lines
    
    console.print(table)
    
    console.print(f"\n[bold]Expected total from sources: {total_expected:,}[/bold]")
    
    # Check v2.2 complete source distribution
    console.print("\n[bold]v2.2 Complete Dataset Source Distribution:[/bold]\n")
    
    v2_2_path = paths_to_check["v2.2 Complete"]
    if v2_2_path.exists():
        sources = check_source_distribution(v2_2_path, max_lines=25000)
        
        src_table = Table(show_header=True, header_style="bold cyan")
        src_table.add_column("Source", style="dim")
        src_table.add_column("Count", justify="right", style="green")
        src_table.add_column("Percentage", justify="right")
        
        total = sum(sources.values())
        
        for source, count in sorted(sources.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total > 0 else 0
            src_table.add_row(source, f"{count:,}", f"{pct:.1f}%")
        
        src_table.add_row("[bold]Total (sampled)[/bold]", f"[bold]{total:,}[/bold]", "[bold]100.0%[/bold]")
        
        console.print(src_table)
        
        # Analysis
        console.print("\n[bold]Analysis:[/bold]")
        
        expected_sources = ["RAG Format", "Pure QA (Fixed)", "CoT (Fixed)", "QA Robustness (Fixed)"]
        missing_sources = [s for s in expected_sources if s not in sources or sources.get(s, 0) == 0]
        
        if missing_sources:
            console.print(Panel(
                f"[bold red]🔴 INTEGRATION FAILED[/bold red]\n\n"
                f"Missing sources in v2.2: {', '.join(missing_sources)}\n\n"
                f"[bold]Possible causes:[/bold]\n"
                f"1. integrate_v2_2_dataset.py didn't load these files\n"
                f"2. Files were empty when script ran\n"
                f"3. Source metadata wasn't added correctly",
                border_style="red"
            ))
        else:
            console.print("[green]✅ All sources present in v2.2[/green]")
    else:
        console.print("[red]🔴 v2.2 complete dataset file not found[/red]")
    
    # Sample check
    console.print("\n[bold]Sample Input Check (v2.2 Complete):[/bold]\n")
    
    if v2_2_path.exists():
        with open(v2_2_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= 3:
                    break
                sample = json.loads(line)
                source = sample.get('metadata', {}).get('source', 'unknown')
                input_text = sample.get('input', '')
                has_bg = '【參考資料】' in input_text
                
                console.print(f"Sample {i+1}:")
                console.print(f"  Source: {source}")
                console.print(f"  Has 【參考資料】: {has_bg}")
                console.print(f"  Input preview: {input_text[:100]}...")
                console.print()


if __name__ == "__main__":
    main()
