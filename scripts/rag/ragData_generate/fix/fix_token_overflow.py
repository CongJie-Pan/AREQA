"""Fix token overflow issues in P3-T04 generated data.

This script removes samples that exceed the 2048 token limit.

Why removal instead of truncation:
- Only 72 samples affected (2.8% of Negative, 1.5% overall)
- Truncation may damage context coherence
- Final count still exceeds RA-DIT requirements
- Maintains data quality

Results:
- Negative: 2,571 → 2,499 (-72, -2.8%)
- Pure QA: No changes (all pass)
- Total: Still well above minimum requirements
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

from rich.console import Console
from rich.table import Table

console = Console()

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Input/Output
NEGATIVE_FILE = PROJECT_ROOT / "data" / "training" / "negative_samples" / "negative_sampling_3000.jsonl"
PURE_QA_FILE = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_supplement_2211.jsonl"

ISSUES_FILE = PROJECT_ROOT / "output" / "p3_t04" / "quality_issues.jsonl"

# Backup
BACKUP_DIR = PROJECT_ROOT / "output" / "p3_t04" / "backup"

# Token limit
MAX_TOKENS = 2048


# ============================================================================
# Helper Functions
# ============================================================================

def estimate_tokens(text: str) -> int:
    """Estimate token count (Chinese: 1 char ≈ 2 tokens)."""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars * 2 + other_chars // 4


def load_samples(path: Path):
    """Load samples from JSONL file."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def save_samples(samples, path: Path):
    """Save samples to JSONL file."""
    with open(path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def load_issues(path: Path):
    """Load validation issues."""
    issues = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                issues.append(json.loads(line))
    return issues


def get_overflow_sample_ids(issues):
    """Extract sample IDs with token overflow."""
    overflow_ids = set()
    for issue in issues:
        if issue['issue_type'] == 'token_overflow' and issue['severity'] == 'error':
            overflow_ids.add(issue['sample_id'])
    return overflow_ids


# ============================================================================
# Main Fix
# ============================================================================

def main():
    console.print("[bold blue]P3-T04 Token Overflow 修復[/bold blue]\n")
    
    # Create backup directory
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load validation issues
    console.print(f"Loading issues from {ISSUES_FILE}...")
    issues = load_issues(ISSUES_FILE)
    overflow_ids = get_overflow_sample_ids(issues)
    console.print(f"  Found {len(overflow_ids)} overflow samples\n")
    
    # === Fix Negative Samples ===
    console.print("[cyan]處理 Negative Sampling...[/cyan]")
    negative_samples = load_samples(NEGATIVE_FILE)
    console.print(f"  原始樣本數: {len(negative_samples)}")
    
    # Backup
    backup_neg = BACKUP_DIR / f"negative_sampling_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    shutil.copy(NEGATIVE_FILE, backup_neg)
    console.print(f"  備份至: {backup_neg}")
    
    # Filter out overflow samples
    negative_fixed = []
    negative_removed = 0
    
    for i, sample in enumerate(negative_samples):
        sample_id = f"negative_{i}"
        
        if sample_id in overflow_ids:
            negative_removed += 1
        else:
            negative_fixed.append(sample)
    
    # Save fixed version
    save_samples(negative_fixed, NEGATIVE_FILE)
    console.print(f"  移除: {negative_removed} 筆")
    console.print(f"  保留: {len(negative_fixed)} 筆\n")
    
    # === Fix Pure QA (if needed) ===
    console.print("[cyan]處理 Pure QA...[/cyan]")
    pure_qa_samples = load_samples(PURE_QA_FILE)
    console.print(f"  原始樣本數: {len(pure_qa_samples)}")
    
    # Check for overflow
    pure_qa_overflow = [sid for sid in overflow_ids if sid.startswith("pure_qa_")]
    
    if pure_qa_overflow:
        # Backup
        backup_pq = BACKUP_DIR / f"pure_qa_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        shutil.copy(PURE_QA_FILE, backup_pq)
        console.print(f"  備份至: {backup_pq}")
        
        # Filter
        pure_qa_fixed = []
        pure_qa_removed = 0
        
        for i, sample in enumerate(pure_qa_samples):
            sample_id = f"pure_qa_{i}"
            
            if sample_id in overflow_ids:
                pure_qa_removed += 1
            else:
                pure_qa_fixed.append(sample)
        
        # Save
        save_samples(pure_qa_fixed, PURE_QA_FILE)
        console.print(f"  移除: {pure_qa_removed} 筆")
        console.print(f"  保留: {len(pure_qa_fixed)} 筆\n")
    else:
        console.print("  無需修復 ✅\n")
        pure_qa_fixed = pure_qa_samples
    
    # === Summary ===
    console.print("[bold cyan]═══ 修復結果 ═══[/bold cyan]\n")
    
    table = Table(title="資料集變化")
    table.add_column("資料集", style="cyan")
    table.add_column("修復前", justify="right")
    table.add_column("移除", justify="right", style="red")
    table.add_column("修復後", justify="right", style="green")
    table.add_column("變化率", justify="right")
    
    neg_change = -negative_removed / len(negative_samples) * 100 if negative_samples else 0
    table.add_row(
        "Negative Sampling",
        str(len(negative_samples)),
        str(negative_removed),
        str(len(negative_fixed)),
        f"{neg_change:.1f}%"
    )
    
    if pure_qa_overflow:
        pq_change = -len(pure_qa_overflow) / len(pure_qa_samples) * 100 if pure_qa_samples else 0
        table.add_row(
            "Pure QA",
            str(len(pure_qa_samples)),
            str(len(pure_qa_overflow)),
            str(len(pure_qa_fixed)),
            f"{pq_change:.1f}%"
        )
    else:
        table.add_row("Pure QA", str(len(pure_qa_samples)), "0", str(len(pure_qa_samples)), "0.0%")
    
    total_before = len(negative_samples) + len(pure_qa_samples)
    total_after = len(negative_fixed) + len(pure_qa_fixed)
    total_removed = total_before - total_after
    total_change = -total_removed / total_before * 100 if total_before else 0
    
    table.add_row(
        "[bold]總計[/bold]",
        f"[bold]{total_before}[/bold]",
        f"[bold]{total_removed}[/bold]",
        f"[bold]{total_after}[/bold]",
        f"[bold]{total_change:.1f}%[/bold]"
    )
    
    console.print(table)
    
    console.print(f"\n[green]✅ 修復完成！[/green]")
    console.print(f"   備份位置: {BACKUP_DIR}")
    console.print(f"\n[yellow]建議: 重新執行 validate_p3_t04_quality.py 驗證修復結果[/yellow]")


if __name__ == "__main__":
    main()
