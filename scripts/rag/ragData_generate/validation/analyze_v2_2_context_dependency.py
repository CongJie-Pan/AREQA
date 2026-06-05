"""Analyze v2.2 dataset for Context Dependency risk.

This script checks:
1. Format distribution (RAG vs Pure QA)
2. Negative Sampling quality (Parametric Fallback)
3. Context Dependency risk assessment

Author: AI Agent
Date: 2026-02-09
Task: P3-T09 Pre-training Validation
"""

import json
import re
from pathlib import Path
from typing import Dict, List
from collections import defaultdict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATASET_PATH = PROJECT_ROOT / "data" / "training" / "completeSet" / "v2.2" / "complete_training_dataset.jsonl"


def load_dataset(path: Path) -> List[Dict]:
    """Load JSONL dataset."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def analyze_format_distribution(samples: List[Dict]) -> Dict:
    """Analyze format types in dataset.
    
    Returns:
        - rag_format: Has【參考資料】
        - pure_qa: No【參考資料】(direct question)
    """
    stats = {
        'total': len(samples),
        'rag_format': 0,
        'pure_qa': 0,
        'has_background_marker': 0,
        'has_question_marker': 0
    }
    
    rag_examples = []
    pure_qa_examples = []
    
    for sample in samples:
        input_text = sample.get('input', '')
        
        # Check markers
        has_bg = '【參考資料】' in input_text
        has_q = '【問題】' in input_text
        
        if has_bg:
            stats['has_background_marker'] += 1
        if has_q:
            stats['has_question_marker'] += 1
        
        # Classify
        if has_bg and has_q:
            stats['rag_format'] += 1
            if len(rag_examples) < 3:
                rag_examples.append(input_text[:100])
        else:
            stats['pure_qa'] += 1
            if len(pure_qa_examples) < 3:
                pure_qa_examples.append(input_text[:100])
    
    # Calculate percentages
    stats['rag_pct'] = (stats['rag_format'] / stats['total']) * 100
    stats['pure_qa_pct'] = (stats['pure_qa'] / stats['total']) * 100
    
    return stats, rag_examples, pure_qa_examples


def analyze_negative_sampling(samples: List[Dict]) -> Dict:
    """Analyze Negative Sampling quality."""
    negative_stats = {
        'total_negative': 0,
        'parametric_fallback': 0,
        'refusal': 0,
        'forced_fallback': 0,
        'kept_existing': 0,
        'failed_no_gt': 0
    }
    
    refusal_patterns = ['無法回答', '不能回答', '參考資料與問題無關', '無關', '拒答']
    
    negative_samples = []
    
    for sample in samples:
        metadata = sample.get('metadata', {})
        negative_type = metadata.get('negative_type', '')
        
        if negative_type in ['qa_robustness', 'rc_negative']:
            negative_stats['total_negative'] += 1
            
            output = sample.get('output', '')
            is_refusal = any(pattern in output for pattern in refusal_patterns)
            
            if is_refusal:
                negative_stats['refusal'] += 1
            else:
                negative_stats['parametric_fallback'] += 1
            
            # Check remediation type
            remediation = metadata.get('remediation', '')
            if remediation == 'forced_parametric_fallback':
                negative_stats['forced_fallback'] += 1
            elif remediation == 'kept_existing_answer':
                negative_stats['kept_existing'] += 1
            elif remediation == 'failed_fallback_no_gt':
                negative_stats['failed_no_gt'] += 1
            
            if len(negative_samples) < 5:
                negative_samples.append({
                    'input': sample.get('input', '')[:150],
                    'output': output[:100],
                    'is_refusal': is_refusal,
                    'remediation': remediation
                })
    
    # Calculate percentages
    if negative_stats['total_negative'] > 0:
        negative_stats['fallback_pct'] = (negative_stats['parametric_fallback'] / negative_stats['total_negative']) * 100
        negative_stats['refusal_pct'] = (negative_stats['refusal'] / negative_stats['total_negative']) * 100
    else:
        negative_stats['fallback_pct'] = 0
        negative_stats['refusal_pct'] = 0
    
    return negative_stats, negative_samples


def assess_context_dependency_risk(format_stats: Dict, negative_stats: Dict) -> Dict:
    """Assess risk of Context Dependency.
    
    Risk factors:
    - High RAG format ratio (>90%)
    - Low Negative Sampling ratio (<10%)
    - High refusal rate in Negative samples (>5%)
    """
    risk = {
        'overall_risk': 'UNKNOWN',
        'risk_factors': [],
        'mitigations': []
    }
    
    # Check RAG format ratio
    rag_pct = format_stats['rag_pct']
    if rag_pct >= 100:
        risk['risk_factors'].append(f"100% RAG format (no Pure QA)")
    elif rag_pct > 90:
        risk['risk_factors'].append(f"{rag_pct:.1f}% RAG format (very high)")
    
    # Check Negative Sampling ratio
    negative_ratio = (negative_stats['total_negative'] / format_stats['total']) * 100
    if negative_ratio < 5:
        risk['risk_factors'].append(f"Only {negative_ratio:.1f}% Negative Sampling")
    elif negative_ratio >= 10:
        risk['mitigations'].append(f"✅ {negative_ratio:.1f}% Negative Sampling (adequate)")
    
    # Check Parametric Fallback quality
    fallback_pct = negative_stats['fallback_pct']
    if fallback_pct < 95:
        risk['risk_factors'].append(f"Only {fallback_pct:.1f}% Parametric Fallback")
    else:
        risk['mitigations'].append(f"✅ {fallback_pct:.1f}% Parametric Fallback (RA-DIT compliant)")
    
    # Overall assessment
    if len(risk['risk_factors']) == 0:
        risk['overall_risk'] = 'LOW'
    elif len(risk['risk_factors']) == 1 and len(risk['mitigations']) >= 2:
        risk['overall_risk'] = 'MODERATE (Mitigated by Negative Sampling)'
    elif len(risk['risk_factors']) >= 2:
        risk['overall_risk'] = 'HIGH'
    else:
        risk['overall_risk'] = 'MODERATE'
    
    return risk


def main():
    """Main analysis."""
    console.print(Panel(
        "[bold cyan]v2.2 Dataset Context Dependency Analysis[/bold cyan]\n"
        "Analyzing format distribution and Negative Sampling quality",
        border_style="cyan"
    ))
    
    # Load dataset
    console.print(f"\n[cyan]Loading dataset from:[/cyan] {DATASET_PATH.relative_to(PROJECT_ROOT)}")
    samples = load_dataset(DATASET_PATH)
    console.print(f"[green]Loaded {len(samples):,} samples[/green]\n")
    
    # Analyze format distribution
    console.print("[bold]1. Format Distribution Analysis[/bold]\n")
    format_stats, rag_ex, pure_ex = analyze_format_distribution(samples)
    
    format_table = Table(show_header=True, header_style="bold magenta")
    format_table.add_column("Format Type", style="dim")
    format_table.add_column("Count", justify="right")
    format_table.add_column("Percentage", justify="right")
    format_table.add_column("RA-DIT Requirement", justify="center")
    
    format_table.add_row(
        "RAG Format (【參考資料】+ 【問題】)",
        f"{format_stats['rag_format']:,}",
        f"{format_stats['rag_pct']:.1f}%",
        "✅ Must have"
    )
    
    format_table.add_row(
        "Pure QA (No background)",
        f"{format_stats['pure_qa']:,}",
        f"{format_stats['pure_qa_pct']:.1f}%",
        "⚠️ Optional"
    )
    
    console.print(format_table)
    console.print()
    
    # Analyze Negative Sampling
    console.print("[bold]2. Negative Sampling Analysis[/bold]\n")
    negative_stats, neg_samples = analyze_negative_sampling(samples)
    
    negative_table = Table(show_header=True, header_style="bold magenta")
    negative_table.add_column("Metric", style="dim")
    negative_table.add_column("Count", justify="right")
    negative_table.add_column("Percentage", justify="right")
    negative_table.add_column("Status", justify="center")
    
    negative_table.add_row(
        "Total Negative Samples",
        f"{negative_stats['total_negative']:,}",
        f"{(negative_stats['total_negative']/format_stats['total'])*100:.1f}%",
        "✅" if negative_stats['total_negative'] > 0 else "🔴"
    )
    
    negative_table.add_row(
        "Parametric Fallback",
        f"{negative_stats['parametric_fallback']:,}",
        f"{negative_stats['fallback_pct']:.1f}%",
        "✅" if negative_stats['fallback_pct'] >= 99 else "⚠️"
    )
    
    negative_table.add_row(
        "Refusal",
        f"{negative_stats['refusal']:,}",
        f"{negative_stats['refusal_pct']:.1f}%",
        "✅" if negative_stats['refusal_pct'] < 1 else "⚠️"
    )
    
    console.print(negative_table)
    console.print()
    
    # Remediation breakdown
    if negative_stats['total_negative'] > 0:
        console.print("[bold]Remediation Strategy Breakdown:[/bold]")
        console.print(f"  - Forced Parametric Fallback: {negative_stats['forced_fallback']:,}")
        console.print(f"  - Kept Existing Answer: {negative_stats['kept_existing']:,}")
        console.print(f"  - Failed (No GT): {negative_stats['failed_no_gt']:,}\n")
    
    # Show examples
    if neg_samples:
        console.print("[bold]Sample Negative Examples:[/bold]\n")
        for i, ex in enumerate(neg_samples[:3], 1):
            console.print(f"[cyan]Example {i}:[/cyan]")
            console.print(f"  Input: {ex['input']}...")
            console.print(f"  Output: {ex['output']}...")
            console.print(f"  Is Refusal: {ex['is_refusal']}")
            console.print(f"  Remediation: {ex['remediation']}\n")
    
    # Risk assessment
    console.print("[bold]3. Context Dependency Risk Assessment[/bold]\n")
    risk = assess_context_dependency_risk(format_stats, negative_stats)
    
    risk_table = Table(show_header=True, header_style="bold magenta")
    risk_table.add_column("Assessment", style="dim", width=40)
    risk_table.add_column("Details", width=60)
    
    # Overall risk
    risk_color = "green" if risk['overall_risk'] == 'LOW' else "yellow" if 'MODERATE' in risk['overall_risk'] else "red"
    risk_table.add_row(
        "Overall Risk Level",
        f"[{risk_color}]{risk['overall_risk']}[/{risk_color}]"
    )
    
    # Risk factors
    if risk['risk_factors']:
        for factor in risk['risk_factors']:
            risk_table.add_row("🔴 Risk Factor", f"[red]{factor}[/red]")
    
    # Mitigations
    if risk['mitigations']:
        for mitigation in risk['mitigations']:
            risk_table.add_row("✅ Mitigation", f"[green]{mitigation}[/green]")
    
    console.print(risk_table)
    console.print()
    
    # Final verdict
    console.print("=" * 80 + "\n")
    
    if risk['overall_risk'] == 'LOW':
        console.print(Panel(
            "[bold green]✅ LOW RISK: Dataset is well-balanced[/bold green]\n\n"
            "The combination of RAG format and strong Negative Sampling should prevent Context Dependency.",
            border_style="green"
        ))
    elif 'MODERATE' in risk['overall_risk']:
        console.print(Panel(
            "[bold yellow]⚠️ MODERATE RISK (Mitigated)[/bold yellow]\n\n"
            f"• Format: {format_stats['rag_pct']:.1f}% RAG (100% = pure RA-DIT)\n"
            f"• Negative Sampling: {(negative_stats['total_negative']/format_stats['total'])*100:.1f}% with {negative_stats['fallback_pct']:.1f}% Parametric Fallback\n\n"
            "✅ **RA-DIT Design**: Negative Sampling should prevent Context Dependency\n"
            "⚠️ **Recommendation**: Monitor model behavior during inference testing",
            border_style="yellow"
        ))
    else:
        console.print(Panel(
            "[bold red]🔴 HIGH RISK: Potential Context Dependency[/bold red]\n\n"
            "Recommendations:\n"
            "1. Increase Negative Sampling ratio to 15-20%\n"
            "2. Add Pure QA samples (10-20%)\n"
            "3. Verify Parametric Fallback quality",
            border_style="red"
        ))
    
    # RA-DIT Compliance Summary
    console.print("\n[bold]RA-DIT Compliance Summary:[/bold]")
    console.print(f"  • Retrieval Context: {format_stats['rag_pct']:.1f}% ({'✅ 100%' if format_stats['rag_pct'] == 100 else '⚠️ Not 100%'})")
    console.print(f"  • Parametric Fallback: {negative_stats['fallback_pct']:.1f}% ({'✅ ≥99%' if negative_stats['fallback_pct'] >= 99 else '🔴 <99%'})")
    console.print(f"  • Negative Sampling: {(negative_stats['total_negative']/format_stats['total'])*100:.1f}% (📊 Adequate if ≥10%)")


if __name__ == "__main__":
    main()
