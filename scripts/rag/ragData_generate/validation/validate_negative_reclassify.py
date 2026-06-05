"""Validate reclassified Negative samples (P3-T04-S5).

This script validates the output of fix_negative_reclassify.py:
- QA Robustness: Must have correct answers (not refusal templates)
- RC Negative: Must have refusal templates
- Format completeness
- Metadata integrity

Output:
- Console summary with quality metrics
- Detailed validation report JSON
"""

import json
from pathlib import Path
from datetime import datetime
from collections import Counter

from rich.console import Console
from rich.table import Table
from rich.progress import track

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Input files
QA_ROBUSTNESS_FILE = PROJECT_ROOT / "data" / "training" / "negative_samples" / "qa_robustness.jsonl"
RC_NEGATIVE_FILE = PROJECT_ROOT / "data" / "training" / "negative_samples" / "rc_negative.jsonl"

# Output
OUTPUT_DIR = PROJECT_ROOT / "output" / "p3_t04"
REPORT_FILE = OUTPUT_DIR / "negative_reclassify_validation_report.json"
ISSUES_FILE = OUTPUT_DIR / "negative_reclassify_issues.jsonl"

# Strict refusal template patterns
# These patterns specifically match refusal templates, not normal content
REFUSAL_PATTERNS = [
    "抱歉，根據提供的",
    "資料中並未提及",
    "參考資料中沒有",
    "無法根據上述資料",
    "上文並未提到",
    "根據提供的資料無法回答",
    "資料不足以回答",
    "抱歉，我無法回答",
    "參考資料與問題無關"
]

console = Console()


# ============================================================================
# Helper Functions
# ============================================================================

def load_jsonl(path: Path):
    """Load samples from JSONL file."""
    samples = []
    if not path.exists():
        return samples
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def is_refusal_answer(answer: str) -> bool:
    """Check if answer is a refusal template.
    
    Why strict matching:
    - Loose keywords like '無法' appear in normal content ('貴公子無法...')
    - We need phrases that specifically indicate refusal, not just contain refusal words
    - Pattern must start with refusal phrases to avoid false positives
    """
    # Check if answer starts with typical refusal patterns
    answer_start = answer[:50].strip()
    
    return any(pattern in answer_start for pattern in REFUSAL_PATTERNS)


# ============================================================================
# Validation Logic
# ============================================================================

def validate_qa_robustness(sample: dict, idx: int) -> list:
    """Validate a QA Robustness sample.
    
    Requirements:
    - Must have metadata.type = "qa_robustness"
    - Output should NOT be a refusal (should be correct answer)
    - Must have proper input/output structure
    """
    issues = []
    
    meta = sample.get("metadata", {})
    out = sample.get("output", "")
    inp = sample.get("input", "")
    
    # Type check
    if meta.get("type") != "qa_robustness":
        issues.append(("error", "wrong_type", f"類型錯誤: {meta.get('type')} (應為 qa_robustness)"))
    
    # Answer check: should NOT be refusal
    if is_refusal_answer(out):
        issues.append(("error", "still_refusal", "輸出仍是拒答模板，應該是正確答案"))
    
    # Output check
    if not out.strip():
        issues.append(("error", "empty_output", "輸出為空"))
    
    if len(out) < 10:
        issues.append(("warning", "short_output", f"輸出過短 ({len(out)} 字)"))
    
    # Input check
    if "【參考資料】" not in inp:
        issues.append(("error", "missing_context_marker", "缺少【參考資料】標記"))
    
    if "【問題】" not in inp:
        issues.append(("error", "missing_question_marker", "缺少【問題】標記"))
    
    # Metadata check
    if meta.get("subtype") != "noise_tolerance":
        issues.append(("warning", "wrong_subtype", f"子類型錯誤: {meta.get('subtype')}"))
    
    return issues


def validate_rc_negative(sample: dict, idx: int) -> list:
    """Validate an RC Negative sample.
    
    Requirements:
    - Must have metadata.type = "rc_negative"
    - Output SHOULD be a refusal template
    - Must have proper input/output structure
    """
    issues = []
    
    meta = sample.get("metadata", {})
    out = sample.get("output", "")
    inp = sample.get("input", "")
    
    # Type check
    if meta.get("type") != "rc_negative":
        issues.append(("error", "wrong_type", f"類型錯誤: {meta.get('type')} (應為 rc_negative)"))
    
    # Answer check: SHOULD be refusal
    if not is_refusal_answer(out):
        issues.append(("warning", "not_refusal", "輸出不是拒答模板"))
    
    # Output check
    if not out.strip():
        issues.append(("error", "empty_output", "輸出為空"))
    
    # Input check
    if "【參考資料】" not in inp:
        issues.append(("error", "missing_context_marker", "缺少【參考資料】標記"))
    
    if "【問題】" not in inp:
        issues.append(("error", "missing_question_marker", "缺少【問題】標記"))
    
    return issues


def run_validation():
    """Run full validation on reclassified Negative samples."""
    console.print("[bold blue]P3-T04-S5 資料品質驗證[/bold blue]\n")
    
    # Load data
    console.print(f"Loading QA Robustness from {QA_ROBUSTNESS_FILE}...")
    qa_samples = load_jsonl(QA_ROBUSTNESS_FILE)
    console.print(f"Loaded {len(qa_samples)} QA Robustness samples")
    
    console.print(f"\nLoading RC Negative from {RC_NEGATIVE_FILE}...")
    rc_samples = load_jsonl(RC_NEGATIVE_FILE)
    console.print(f"Loaded {len(rc_samples)} RC Negative samples\n")
    
    # Validate each dataset
    all_issues = []
    error_count = 0
    warning_count = 0
    
    # Validate QA Robustness
    for idx, sample in enumerate(track(qa_samples, description="Validating QA Robustness...")):
        issues = validate_qa_robustness(sample, idx)
        
        for severity, issue_type, desc in issues:
            all_issues.append({
                "dataset": "qa_robustness",
                "index": idx,
                "severity": severity,
                "issue_type": issue_type,
                "description": desc
            })
            
            if severity == "error":
                error_count += 1
            else:
                warning_count += 1
    
    # Validate RC Negative
    for idx, sample in enumerate(track(rc_samples, description="Validating RC Negative...")):
        issues = validate_rc_negative(sample, idx)
        
        for severity, issue_type, desc in issues:
            all_issues.append({
                "dataset": "rc_negative",
                "index": idx,
                "severity": severity,
                "issue_type": issue_type,
                "description": desc
            })
            
            if severity == "error":
                error_count += 1
            else:
                warning_count += 1
    
    # Save issues
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if all_issues:
        with open(ISSUES_FILE, 'w', encoding='utf-8') as f:
            for issue in all_issues:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")
    
    # Issue type breakdown
    issue_types = Counter(i["issue_type"] for i in all_issues)
    
    # Check answer types
    qa_refusal_count = sum(1 for s in qa_samples if is_refusal_answer(s.get("output", "")))
    rc_refusal_count = sum(1 for s in rc_samples if is_refusal_answer(s.get("output", "")))
    
    # Build report
    report = {
        "timestamp": datetime.now().isoformat(),
        "datasets": {
            "qa_robustness": {
                "file": str(QA_ROBUSTNESS_FILE),
                "count": len(qa_samples),
                "refusal_answers": qa_refusal_count,
                "correct_answers": len(qa_samples) - qa_refusal_count
            },
            "rc_negative": {
                "file": str(RC_NEGATIVE_FILE),
                "count": len(rc_samples),
                "refusal_answers": rc_refusal_count,
                "non_refusal_answers": len(rc_samples) - rc_refusal_count
            }
        },
        "validation_result": {
            "errors": error_count,
            "warnings": warning_count,
            "status": "✅ PASS" if error_count == 0 else "❌ FAIL"
        },
        "issue_breakdown": dict(issue_types)
    }
    
    # Save report
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # Display results
    console.print("\n[bold cyan]═══ 驗證結果 ═══[/bold cyan]\n")
    
    # Summary table
    summary_table = Table(title="驗證摘要")
    summary_table.add_column("指標", style="cyan")
    summary_table.add_column("數值", justify="right")
    summary_table.add_column("狀態")
    
    summary_table.add_row("QA Robustness 樣本", str(len(qa_samples)), "")
    summary_table.add_row("RC Negative 樣本", str(len(rc_samples)), "")
    summary_table.add_row("總樣本數", str(len(qa_samples) + len(rc_samples)), "")
    summary_table.add_row("錯誤", str(error_count), "❌" if error_count > 0 else "✅")
    summary_table.add_row("警告", str(warning_count), "⚠️" if warning_count > 0 else "✅")
    
    console.print(summary_table)
    
    # Answer type distribution
    answer_table = Table(title="\n答案類型分佈")
    answer_table.add_column("資料集", style="cyan")
    answer_table.add_column("拒答", justify="right")
    answer_table.add_column("正確答案", justify="right")
    answer_table.add_column("狀態")
    
    qa_status = "❌" if qa_refusal_count > 0 else "✅"
    answer_table.add_row(
        "QA Robustness",
        str(qa_refusal_count),
        str(len(qa_samples) - qa_refusal_count),
        qa_status
    )
    
    rc_status = "✅" if rc_refusal_count == len(rc_samples) else "⚠️"
    answer_table.add_row(
        "RC Negative",
        str(rc_refusal_count),
        str(len(rc_samples) - rc_refusal_count),
        rc_status
    )
    
    console.print(answer_table)
    
    # Issue breakdown if any
    if issue_types:
        issue_table = Table(title="\n問題類型分佈")
        issue_table.add_column("問題類型", style="cyan")
        issue_table.add_column("數量", justify="right")
        
        for issue_type, count in issue_types.most_common():
            issue_table.add_row(issue_type, str(count))
        
        console.print(issue_table)
    
    # Investigation: Show failed samples
    if error_count > 0:
        console.print("\n[bold yellow]═══ 問題樣本調查 (前5個) ═══[/bold yellow]\n")
        
        # Get failed QA Robustness samples
        failed_qa_issues = [i for i in all_issues if i["dataset"] == "qa_robustness" and i["issue_type"] == "still_refusal"][:5]
        
        if failed_qa_issues:
            console.print("[bold red]QA Robustness 仍為拒答模板的樣本:[/bold red]\n")
            
            for i, issue in enumerate(failed_qa_issues, 1):
                idx = issue["index"]
                sample = qa_samples[idx]
                
                # Extract question
                inp = sample.get("input", "")
                question = inp.split("【問題】")[-1].strip() if "【問題】" in inp else inp[:100]
                
                # Get output
                output = sample.get("output", "")
                
                console.print(f"[cyan]{i}. Sample #{idx}[/cyan]")
                console.print(f"   問題: {question[:150]}{'...' if len(question) > 150 else ''}")
                console.print(f"   答案: [red]{output[:150]}{'...' if len(output) > 150 else ''}[/red]")
                console.print(f"   元數據: {sample.get('metadata', {})}")
                console.print()
    
    # Final status
    if error_count == 0:
        console.print("\n[bold green]✅ 驗證通過！資料品質良好。[/bold green]")
    else:
        console.print(f"\n[bold red]❌ 驗證失敗：發現 {error_count} 個錯誤[/bold red]")
        console.print("\n[yellow]建議：檢查 fix_negative_reclassify.py 的答案查找邏輯[/yellow]")
    
    console.print(f"\n報告已儲存至: {REPORT_FILE}")
    if all_issues:
        console.print(f"問題詳情: {ISSUES_FILE}")
    
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    exit(run_validation())
