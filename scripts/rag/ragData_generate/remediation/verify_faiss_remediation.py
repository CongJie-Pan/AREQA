"""Verify FAISS Hybrid remediation quality.

Checks:
1. Format compliance (【參考資料】+ 【問題】)
2. Context quality (no "無相關資料")
3. Negative strategy (Parametric Fallback ratio)

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

# Fixed files
PURE_QA_FIXED = PROJECT_ROOT / "data" / "training" / "remediation" / "pure_qa_with_context_fixed.jsonl"
COT_FIXED = PROJECT_ROOT / "data" / "training" / "remediation" / "cot_samples_fixed.jsonl"
QA_ROB_FIXED = PROJECT_ROOT / "data" / "training" / "remediation" / "qa_robustness_fixed.jsonl"


def load_jsonl(path: Path):
    """Load JSONL file."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def check_format_compliance(samples, source_name):
    """Check RA-DIT format compliance."""
    total = len(samples)
    has_background = 0
    has_question = 0
    weak_context = 0
    empty_context = 0
    
    examples_good = []
    examples_bad = []
    
    for sample in samples:
        input_text = sample.get('input', '')
        
        # Check markers
        if '【參考資料】' in input_text:
            has_background += 1
        else:
            if len(examples_bad) < 2:
                examples_bad.append(input_text[:100])
        
        if '【問題】' in input_text:
            has_question += 1
        
        # Extract context
        if '【參考資料】' in input_text and '【問題】' in input_text:
            parts = input_text.split('【問題】')
            context = parts[0].replace('【參考資料】', '').strip()
            
            if not context or context == '':
                empty_context += 1
            elif '無相關資料' in context or '暫無直接相關' in context or len(context) < 20:
                weak_context += 1
            else:
                if len(examples_good) < 2:
                    examples_good.append(context[:150])
    
    return {
        'total': total,
        'has_background': has_background,
        'has_question': has_question,
        'weak_context': weak_context,
        'empty_context': empty_context,
        'good_examples': examples_good,
        'bad_examples': examples_bad
    }


def check_negative_strategy(samples):
    """Check Negative strategy."""
    total = len(samples)
    refusals = 0
    parametric = 0
    
    refusal_patterns = ['無法回答', '不能回答', '參考資料與問題無關', '無關', '拒答']
    
    for sample in samples:
        output = sample.get('output', '')
        if any(pattern in output for pattern in refusal_patterns):
            refusals += 1
        else:
            parametric += 1
    
    return {
        'total': total,
        'refusals': refusals,
        'parametric': parametric,
        'refusal_pct': refusals / total * 100 if total > 0 else 0,
        'parametric_pct': parametric / total * 100 if total > 0 else 0
    }


def main():
    console.print(Panel(
        "[bold cyan]FAISS Hybrid Remediation Quality Check[/bold cyan]\n"
        "Verifying format compliance and context quality",
        border_style="cyan"
    ))
    
    # Load files
    console.print("\n[cyan]Loading remediated files...[/cyan]")
    pure_qa = load_jsonl(PURE_QA_FIXED)
    cot = load_jsonl(COT_FIXED)
    qa_rob = load_jsonl(QA_ROB_FIXED)
    
    console.print(f"  Pure QA: {len(pure_qa)}")
    console.print(f"  CoT: {len(cot)}")
    console.print(f"  QA Robustness: {len(qa_rob)}\n")
    
    # Check each source
    sources = {
        'Pure QA': pure_qa,
        'CoT': cot,
        'QA Robustness': qa_rob
    }
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Source", style="dim")
    table.add_column("Total", justify="right")
    table.add_column("Has【參考資料】", justify="right")
    table.add_column("Has【問題】", justify="right")
    table.add_column("Weak Context", justify="right")
    table.add_column("Format OK", justify="center")
    
    all_checks = {}
    
    for source_name, samples in sources.items():
        check = check_format_compliance(samples, source_name)
        all_checks[source_name] = check
        
        format_ok = "✅" if check['has_background'] == check['total'] and check['has_question'] == check['total'] else "🔴"
        
        table.add_row(
            source_name,
            f"{check['total']:,}",
            f"{check['has_background']:,}",
            f"{check['has_question']:,}",
            f"{check['weak_context']:,}",
            format_ok
        )
    
    console.print(table)
    
    # Show examples
    console.print("\n[bold]Sample Context Quality (Pure QA):[/bold]\n")
    for i, ex in enumerate(all_checks['Pure QA']['good_examples'][:2], 1):
        console.print(f"[green]Example {i}:[/green] {ex}...\n")
    
    # Check Negative strategy
    console.print("\n[bold cyan]Negative Strategy Check:[/bold cyan]\n")
    neg_check = check_negative_strategy(qa_rob)
    
    neg_table = Table(show_header=True, header_style="bold magenta")
    neg_table.add_column("Metric", style="dim")
    neg_table.add_column("Count", justify="right")
    neg_table.add_column("Percentage", justify="right")
    neg_table.add_column("Status", justify="center")
    
    neg_table.add_row(
        "Refusals",
        f"{neg_check['refusals']:,}",
        f"{neg_check['refusal_pct']:.1f}%",
        "✅" if neg_check['refusal_pct'] < 5 else "🔴"
    )
    
    neg_table.add_row(
        "Parametric Fallback",
        f"{neg_check['parametric']:,}",
        f"{neg_check['parametric_pct']:.1f}%",
        "✅" if neg_check['parametric_pct'] > 95 else "🔴"
    )
    
    console.print(neg_table)
    
    # Verdict
    console.print("\n" + "="*80 + "\n")
    
    all_format_ok = all(
        check['has_background'] == check['total'] and check['has_question'] == check['total']
        for check in all_checks.values()
    )
    
    weak_context_total = sum(check['weak_context'] for check in all_checks.values())
    total_samples = sum(check['total'] for check in all_checks.values())
    weak_pct = weak_context_total / total_samples * 100
    
    neg_ok = neg_check['parametric_pct'] > 95
    
    if all_format_ok and weak_pct < 10 and neg_ok:
        console.print(Panel(
            "[bold green]✅ PASS: High-Quality Remediation![/bold green]\n\n"
            f"• Format Compliance: 100%\n"
            f"• Weak Context: {weak_pct:.1f}% (< 10% threshold)\n"
            f"• Parametric Fallback: {neg_check['parametric_pct']:.1f}% (> 95% target)\n\n"
            "[bold]Ready for v2.2 integration![/bold]",
            border_style="green"
        ))
    else:
        issues = []
        if not all_format_ok:
            issues.append("Format compliance failed")
        if weak_pct >= 10:
            issues.append(f"High weak context rate: {weak_pct:.1f}%")
        if not neg_ok:
            issues.append(f"Low Parametric Fallback: {neg_check['parametric_pct']:.1f}%")
        
        console.print(Panel(
            "[bold red]🔴 FAIL: Quality Issues Detected[/bold red]\n\n" +
            "\n".join(f"• {issue}" for issue in issues),
            border_style="red"
        ))


if __name__ == "__main__":
    main()
