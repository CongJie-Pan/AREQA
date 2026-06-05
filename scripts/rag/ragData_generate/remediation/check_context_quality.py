"""Check for '無相關資料' in background contexts.

This identifies samples where retrieval returned no relevant content.

Author: AI Agent  
Date: 2026-02-08
"""

import json
import random
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
V2_2_COMPLETE = PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.2" / "complete_training_dataset.jsonl"


def check_context_quality():
    """Check quality of retrieval contexts."""
    console.print(Panel(
        "[bold yellow]Checking Background Context Quality[/bold yellow]\n"
        "Identifying '無相關資料' samples",
        border_style="yellow"
    ))
    
    console.print("[cyan]Loading and analyzing samples...[/cyan]\n")
    
    by_source = {}
    
    with open(V2_2_COMPLETE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                sample = json.loads(line)
                source = sample.get('metadata', {}).get('source', 'unknown')
                
                if source not in by_source:
                    by_source[source] = {
                        "total": 0,
                        "no_context": 0,
                        "has_context": 0,
                        "examples_no_context": [],
                        "examples_has_context": []
                    }
                
                input_text = sample.get('input', '')
                by_source[source]["total"] += 1
                
                # Extract context part
                if '【參考資料】' in input_text and '【問題】' in input_text:
                    context = input_text.split('【問題】')[0].replace('【參考資料】', '').strip()
                    
                    if context == '無相關資料' or context == '' or len(context) < 20:
                        by_source[source]["no_context"] += 1
                        if len(by_source[source]["examples_no_context"]) < 2:
                            by_source[source]["examples_no_context"].append({
                                "input": input_text[:200],
                                "context": context
                            })
                    else:
                        by_source[source]["has_context"] += 1
                        if len(by_source[source]["examples_has_context"]) < 2:
                            by_source[source]["examples_has_context"].append({
                                "context": context[:150]
                            })
                
            except json.JSONDecodeError:
                continue
    
    # Results table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Source", style="dim")
    table.add_column("Total", justify="right")
    table.add_column("No Context", justify="right", style="red")
    table.add_column("Has Context", justify="right", style="green")
    table.add_column("No Context %", justify="right")
    table.add_column("Status")
    
    issues = []
    
    for source in sorted(by_source.keys()):
        stats = by_source[source]
        no_ctx_pct = (stats["no_context"] / stats["total"] * 100) if stats["total"] > 0 else 0
        
        status = "🔴" if no_ctx_pct > 10 else "⚠️" if no_ctx_pct > 0 else "✅"
        
        table.add_row(
            source,
            f"{stats['total']:,}",
            f"{stats['no_context']:,}",
            f"{stats['has_context']:,}",
            f"{no_ctx_pct:.1f}%",
            status
        )
        
        if no_ctx_pct > 10:
            issues.append(f"{source}: {no_ctx_pct:.1f}% samples have no useful context")
    
    console.print(table)
    console.print()
    
    # Show examples
    console.print("[bold]Examples of '無相關資料':[/bold]\n")
    for source, stats in by_source.items():
        if stats["no_context"] > 0 and stats["examples_no_context"]:
            console.print(f"[yellow]{source}:[/yellow]")
            console.print(f"  {stats['examples_no_context'][0]['input'][:200]}...")
            console.print()
    
    # Verdict
    if issues:
        console.print(Panel(
            "[bold red]🔴 CONTEXT QUALITY ISSUES[/bold red]\n\n" +
            "\n".join(f"• {issue}" for issue in issues) +
            "\n\n[bold]Retrieval is too weak![/bold]\n"
            "Keyword-based retrieval with k=3 is finding no relevant chunks.\n\n"
            "[cyan]Recommendation:[/cyan]\n"
            "1. Increase k from 3 to 5 or 10\n"
            "2. Use FAISS vector retrieval instead of keyword matching\n"
            "3. Accept that some samples will have weak context (this is still better than no context marker)",
            border_style="red"
        ))
    else:
        console.print(Panel(
            "[bold green]✅ Context quality acceptable[/bold green]\n"
            "Most samples have meaningful retrieval backgrounds.",
            border_style="green"
        ))


if __name__ == "__main__":
    check_context_quality()
