"""Validate remediation results and assess risks.

This script checks for the three identified risks and provides actionable recommendations.

Author: AI Agent
Date: 2026-02-08  
Task: P3-T04-S8 Validation
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import Counter
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Fixed data paths
PURE_QA_FIXED = PROJECT_ROOT / "data" / "training" / "remediation" / "pure_qa_with_context_fixed.jsonl"
COT_FIXED = PROJECT_ROOT / "data" / "training" / "remediation" / "cot_samples_fixed.jsonl"
QA_ROBUSTNESS_FIXED = PROJECT_ROOT / "data" / "training" / "remediation" / "qa_robustness_fixed.jsonl"
RC_NEGATIVE_FIXED = PROJECT_ROOT / "data" / "training" / "remediation" / "rc_negative_fixed.jsonl"


def load_jsonl(file_path: Path) -> List[Dict]:
    """Load JSONL file."""
    samples = []
    if not file_path.exists():
        return samples
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples


def check_retrieval_quality(samples: List[Dict], sample_size: int = 50) -> Dict:
    """Risk 1: Check retrieval quality.
    
    Why: Simple keyword matching may produce poor results
    """
    console.print("\n[bold cyan]Risk 1: Retrieval Quality Assessment[/bold cyan]")
    
    stats = {
        "total_samples": len(samples),
        "samples_with_context": 0,
        "context_lengths": [],
        "retrieval_counts": []
    }
    
    # Check first N samples
    check_samples = samples[:min(sample_size, len(samples))]
    
    for sample in check_samples:
        input_text = sample.get('input', '')
        
        # Count if has background
        if '【參考資料】' in input_text:
            stats["samples_with_context"] += 1
            
            # Extract context
            if '【問題】' in input_text:
                context = input_text.split('【問題】')[0].replace('【參考資料】', '').strip()
                stats["context_lengths"].append(len(context))
        
        # Check retrieval count from metadata
        retrieval_count = sample.get('metadata', {}).get('retrieval_count', 0)
        stats["retrieval_counts"].append(retrieval_count)
    
    # Calculate metrics
    coverage = (stats["samples_with_context"] / len(check_samples)) * 100
    avg_context_len = sum(stats["context_lengths"]) / len(stats["context_lengths"]) if stats["context_lengths"] else 0
    avg_retrieval = sum(stats["retrieval_counts"]) / len(stats["retrieval_counts"]) if stats["retrieval_counts"] else 0
    
    console.print(f"  Checked: {len(check_samples)} samples")
    console.print(f"  Background coverage: {coverage:.1f}%")
    console.print(f"  Avg context length: {avg_context_len:.0f} chars")
    console.print(f"  Avg retrievals per sample: {avg_retrieval:.1f}")
    
    if coverage < 100:
        console.print(f"  [yellow]⚠️ Warning: {100-coverage:.1f}% samples missing background[/yellow]")
    else:
        console.print(f"  [green]✅ All samples have background[/green]")
    
    return stats


def check_rc_classification(negative_samples: List[Dict]) -> Dict:
    """Risk 2: Check RC vs QA classification accuracy.
    
    Why: All 2545 samples classified as QA (0 RC samples) suggests issue
    """
    console.print("\n[bold cyan]Risk 2: RC Classification Assessment[/bold cyan]")
    
    RC_KEYWORDS = ["根據上文", "依照文章", "從文中", "根據資料", "按照上述", "根據這段", "由上文"]
    
    stats = {
        "total": len(negative_samples),
        "qa_type": 0,
        "rc_type": 0,
        "rc_keywords_found": Counter(),
        "sample_questions": []
    }
    
    for sample in negative_samples:
        input_text = sample.get('input', '')
        
        # Extract question
        if '【問題】' in input_text:
            question = input_text.split('【問題】')[1].strip()
        else:
            question = input_text.strip()
        
        # Check for RC keywords
        found_keywords = []
        for keyword in RC_KEYWORDS:
            if keyword in question:
                found_keywords.append(keyword)
                stats["rc_keywords_found"][keyword] += 1
        
        # Classify
        neg_type = sample.get('metadata', {}).get('negative_type', 'unknown')
        if neg_type == 'rc_negative':
            stats["rc_type"] += 1
        else:
            stats["qa_type"] += 1
        
        # Store first 10 questions for review
        if len(stats["sample_questions"]) < 10:
            stats["sample_questions"].append({
                "question": question[:100],  # Truncate for display
                "type": neg_type,
                "has_rc_keywords": len(found_keywords) > 0
            })
    
    console.print(f"  Total negative samples: {stats['total']}")
    console.print(f"  Classified as QA: {stats['qa_type']} ({stats['qa_type']/stats['total']*100:.1f}%)")
    console.print(f"  Classified as RC: {stats['rc_type']} ({stats['rc_type']/stats['total']*100:.1f}%)")
    
    if stats["rc_type"] == 0:
        console.print(f"  [red]🔴 CRITICAL: 0 RC samples detected![/red]")
        console.print(f"  [yellow]This suggests:[/yellow]")
        console.print(f"    1. Original samples may not contain RC keywords")
        console.print(f"    2. Question extraction may be incorrect")
        console.print(f"  [cyan]Recommendation: Manual review needed[/cyan]")
    
    # Show keyword distribution
    if stats["rc_keywords_found"]:
        console.print(f"\n  RC Keywords found:")
        for kw, count in stats["rc_keywords_found"].most_common():
            console.print(f"    • {kw}: {count}")
    else:
        console.print(f"  [yellow]⚠️ No RC keywords found in any sample[/yellow]")
    
    return stats


def check_token_limits(samples: List[Dict], max_tokens: int = 2048) -> Dict:
    """Risk 3: Check for token limit violations.
    
    Why: Adding context may cause overflow
    
    Note: This uses character count as proxy (Chinese ~1.5 chars per token)
    """
    console.print("\n[bold cyan]Risk 3: Token Limit Assessment[/bold cyan]")
    
    stats = {
        "total": len(samples),
        "overflow_samples": 0,
        "max_length": 0,
        "avg_length": 0,
        "length_distribution": Counter()
    }
    
    lengths = []
    
    for sample in samples:
        input_text = sample.get('input', '')
        output_text = sample.get('output', '')
        total_length = len(input_text) + len(output_text)
        
        lengths.append(total_length)
        
        # Estimate tokens (Chinese: ~1.5 chars per token)
        estimated_tokens = total_length / 1.5
        
        if estimated_tokens > max_tokens:
            stats["overflow_samples"] += 1
        
        # Bucket for distribution
        bucket = (int(estimated_tokens) // 500) * 500
        stats["length_distribution"][bucket] += 1
    
    stats["max_length"] = max(lengths) if lengths else 0
    stats["avg_length"] = sum(lengths) / len(lengths) if lengths else 0
    stats["max_tokens_estimate"] = stats["max_length"] / 1.5
    stats["avg_tokens_estimate"] = stats["avg_length"] / 1.5
    
    console.print(f"  Total samples: {stats['total']}")
    console.print(f"  Avg length: {stats['avg_length']:.0f} chars ({stats['avg_tokens_estimate']:.0f} tokens est.)")
    console.print(f"  Max length: {stats['max_length']} chars ({stats['max_tokens_estimate']:.0f} tokens est.)")
    console.print(f"  Overflow samples (>{max_tokens}): {stats['overflow_samples']}")
    
    if stats["overflow_samples"] > 0:
        console.print(f"  [yellow]⚠️ Warning: {stats['overflow_samples']} samples exceed {max_tokens} tokens[/yellow]")
        console.print(f"  [cyan]Recommendation: Truncate or remove overflow samples[/cyan]")
    else:
        console.print(f"  [green]✅ All samples within token limit[/green]")
    
    return stats


def check_missing_answers(qa_robustness: List[Dict]) -> Dict:
    """Check samples that still have refusal (couldn't find correct answer)."""
    console.print("\n[bold cyan]Additional Check: Missing Answers[/bold cyan]")
    
    refusal_patterns = ["無法回答", "不能回答", "參考資料與問題無關", "無關", "拒答"]
    
    stats = {
        "total": len(qa_robustness),
        "still_refusing": 0,
        "fixed_to_answer": 0
    }
    
    for sample in qa_robustness:
        output = sample.get('output', '')
        
        if any(pattern in output for pattern in refusal_patterns):
            stats["still_refusing"] += 1
        else:
            stats["fixed_to_answer"] += 1
    
    console.print(f"  QA Robustness samples: {stats['total']}")
    console.print(f"  Fixed to answer: {stats['fixed_to_answer']} ({stats['fixed_to_answer']/stats['total']*100:.1f}%)")
    console.print(f"  Still refusing: {stats['still_refusing']} ({stats['still_refusing']/stats['total']*100:.1f}%)")
    
    if stats["still_refusing"] > 0:
        console.print(f"  [yellow]⚠️ {stats['still_refusing']} samples couldn't find correct answer[/yellow]")
        console.print(f"  [cyan]Impact: These will still refuse (acceptable for robustness)[/cyan]")
    
    return stats


def main():
    """Main validation entry point."""
    console.print(Panel(
        "[bold magenta]P3-T04-S8 Remediation Validation[/bold magenta]\n"
        "Checking for identified risks",
        border_style="magenta"
    ))
    
    # Load data
    console.print("[cyan]Loading fixed data...[/cyan]")
    pure_qa = load_jsonl(PURE_QA_FIXED)
    cot = load_jsonl(COT_FIXED)
    qa_robustness = load_jsonl(QA_ROBUSTNESS_FIXED)
    rc_negative = load_jsonl(RC_NEGATIVE_FIXED)
    
    console.print(f"  Pure QA: {len(pure_qa)}")
    console.print(f"  CoT: {len(cot)}")
    console.print(f"  QA Robustness: {len(qa_robustness)}")
    console.print(f"  RC Negative: {len(rc_negative)}")
    
    all_samples = pure_qa + cot + qa_robustness + rc_negative
    
    # Run checks
    retrieval_stats = check_retrieval_quality(pure_qa + cot, sample_size=100)
    rc_stats = check_rc_classification(qa_robustness + rc_negative)
    token_stats = check_token_limits(all_samples)
    answer_stats = check_missing_answers(qa_robustness)
    
    # Summary
    console.print("\n" + "="*80)
    console.print(Panel(
        "[bold]Risk Assessment Summary[/bold]\n\n"
        f"[bold cyan]Risk 1 - Retrieval Quality:[/bold cyan]\n"
        f"  Status: {'[green]✅ PASSED[/green]' if retrieval_stats['samples_with_context'] > 0 else '[red]❌ FAILED[/red]'}\n"
        f"  Coverage: {(retrieval_stats['samples_with_context']/100)*100:.1f}%\n\n"
        f"[bold cyan]Risk 2 - RC Classification:[/bold cyan]\n"
        f"  Status: {'[red]🔴 CRITICAL[/red]' if rc_stats['rc_type'] == 0 else '[green]✅ PASSED[/green]'}\n"
        f"  RC Samples: {rc_stats['rc_type']} (Need manual review!)\n\n"
        f"[bold cyan]Risk 3 - Token Overflow:[/bold cyan]\n"
        f"  Status: {'[green]✅ PASSED[/green]' if token_stats['overflow_samples'] == 0 else '[yellow]⚠️ WARNING[/yellow]'}\n"
        f"  Overflow: {token_stats['overflow_samples']} samples\n\n"
        f"[bold cyan]Additional - Missing Answers:[/bold cyan]\n"
        f"  Still refusing: {answer_stats['still_refusing']} samples (acceptable)",
        border_style="yellow" if rc_stats['rc_type'] == 0 else "green"
    ))
    
    # Recommendations
    console.print("\n[bold magenta]Recommendations:[/bold magenta]")
    
    if rc_stats['rc_type'] == 0:
        console.print("  🔴 [bold]CRITICAL:[/bold] Manual review needed for Negative samples")
        console.print("     • Check if original samples contain '根據上文' style questions")
        console.print("     • May need to manually label RC samples")
        console.print("     • Current assumption: All are Knowledge QA (Parametric Fallback)")
    
    if token_stats['overflow_samples'] > 0:
        console.print(f"  ⚠️ [bold]WARNING:[/bold] {token_stats['overflow_samples']} samples exceed token limit")
        console.print("     • Consider truncating context or removing samples")
    
    if answer_stats['still_refusing'] > 0:
        console.print(f"  ℹ️ [bold]INFO:[/bold] {answer_stats['still_refusing']} samples still refuse")
        console.print("     • These couldn't find correct answers in metadata")
        console.print("     • Acceptable for robustness training")
    
    console.print("\n[green]✅ Validation complete[/green]")


if __name__ == "__main__":
    main()
