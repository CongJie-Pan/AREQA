"""Verify data sources for v2.1 dataset integration.

This script verifies all required data sources exist and reports their statistics.

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S6 Phase 1 - Data Verification
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Data sources for v2.1 integration
DATA_SOURCES = {
    "RAG Format": PROJECT_ROOT / "data" / "training" / "rag_format" / "backfilled_radit_format.jsonl",
    "Pure QA with Context": PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_with_context.jsonl",
    "CoT Samples": PROJECT_ROOT / "data" / "training" / "cot" / "cot_samples.jsonl",
    "QA Robustness": PROJECT_ROOT / "data" / "training" / "negative_samples" / "qa_robustness.jsonl",
    "RC Negative": PROJECT_ROOT / "data" / "training" / "negative_samples" / "rc_negative.jsonl",
}


def count_jsonl_lines(file_path: Path) -> int:
    """Count lines in JSONL file.
    
    Why: Need accurate sample counts for dataset planning
    """
    if not file_path.exists():
        return 0
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)


def verify_data_sources() -> Dict[str, Any]:
    """Verify all data sources and collect statistics.
    
    Returns:
        Dict with verification results
    """
    console.print(Panel(
        "[bold cyan]v2.1 Dataset Integration - Data Source Verification[/bold cyan]",
        border_style="cyan"
    ))
    
    results = {
        "sources": {},
        "total_samples": 0,
        "missing_sources": [],
        "all_sources_ready": True
    }
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Data Source", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Samples", justify="right", style="green")
    table.add_column("Size (MB)", justify="right")
    
    for source_name, source_path in DATA_SOURCES.items():
        if source_path.exists():
            sample_count = count_jsonl_lines(source_path)
            file_size_mb = source_path.stat().st_size / (1024 * 1024)
            
            results["sources"][source_name] = {
                "path": str(source_path),
                "exists": True,
                "samples": sample_count,
                "size_mb": round(file_size_mb, 2)
            }
            results["total_samples"] += sample_count
            
            table.add_row(
                source_name,
                "✅ Ready",
                f"{sample_count:,}",
                f"{file_size_mb:.2f}"
            )
        else:
            results["sources"][source_name] = {
                "path": str(source_path),
                "exists": False,
                "samples": 0,
                "size_mb": 0
            }
            results["missing_sources"].append(source_name)
            results["all_sources_ready"] = False
            
            table.add_row(
                source_name,
                "❌ Missing",
                "0",
                "0.00"
            )
    
    console.print(table)
    console.print()
    
    # Summary
    if results["all_sources_ready"]:
        console.print(Panel(
            f"[bold green]✅ All data sources ready![/bold green]\n"
            f"Total samples: [bold]{results['total_samples']:,}[/bold]",
            border_style="green"
        ))
    else:
        console.print(Panel(
            f"[bold red]❌ Missing sources:[/bold red]\n" +
            "\n".join(f"  • {s}" for s in results["missing_sources"]),
            border_style="red"
        ))
    
    return results


def main():
    """Main entry point."""
    try:
        results = verify_data_sources()
        
        # Save verification report
        output_dir = PROJECT_ROOT / "output" / "p3_t04"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = output_dir / "v2_1_verification_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        console.print(f"\n[dim]驗證報告已保存至: {report_path.relative_to(PROJECT_ROOT)}[/dim]")
        
        # Exit with appropriate code
        if results["all_sources_ready"]:
            console.print("\n[bold green]🎉 Data sources verified. Ready for integration![/bold green]")
            sys.exit(0)
        else:
            console.print("\n[bold red]⚠️ Please prepare missing data sources before integration.[/bold red]")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"\n[bold red]❌ Verification failed: {e}[/bold red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
