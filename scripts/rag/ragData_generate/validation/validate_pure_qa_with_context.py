"""Validate Pure QA with Context data quality (P3-T04-S4).

This script validates the output of fix_pure_qa_add_retrieval.py:
- Format completeness (【參考資料】and【問題】markers)
- Context quality (similarity scores distribution)
- Token limit compliance
- Metadata integrity

Output:
- Console summary with quality metrics
- Detailed validation report JSON
"""

import json
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

from rich.console import Console
from rich.table import Table
from rich.progress import track

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Input file
INPUT_FILE = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_with_context.jsonl"

# Output
OUTPUT_DIR = PROJECT_ROOT / "output" / "p3_t04"
REPORT_FILE = OUTPUT_DIR / "pure_qa_with_context_validation_report.json"
ISSUES_FILE = OUTPUT_DIR / "pure_qa_with_context_issues.jsonl"

# Thresholds
TOKEN_LIMIT = 2048
MIN_SIMILARITY = 0.5  # Below this is considered low quality
HIGH_SIMILARITY = 0.8  # Above this is considered good

console = Console()


# ============================================================================
# Helper Functions
# ============================================================================

def load_jsonl(path: Path):
    """Load samples from JSONL file."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def estimate_tokens(text: str) -> int:
    """Estimate token count for Chinese text."""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars * 2 + other_chars // 4


# ============================================================================
# Validation Logic
# ============================================================================

def validate_sample(sample: dict, idx: int) -> list:
    """Validate a single sample.
    
    Returns list of issues: [(severity, issue_type, description)]
    """
    issues = []
    
    inp = sample.get("input", "")
    out = sample.get("output", "")
    meta = sample.get("metadata", {})
    
    # Format validation
    if "【參考資料】" not in inp:
        issues.append(("error", "missing_context_marker", "缺少【參考資料】標記"))
    
    if "【問題】" not in inp:
        issues.append(("error", "missing_question_marker", "缺少【問題】標記"))
    
    # Content validation
    if not out.strip():
        issues.append(("error", "empty_output", "輸出為空"))
    
    if len(inp) < 50:
        issues.append(("warning", "short_input", f"輸入過短 ({len(inp)} 字)"))
    
    if len(out) < 20:
        issues.append(("warning", "short_output", f"輸出過短 ({len(out)} 字)"))
    
    # Token validation
    total_text = inp + out
    tokens = estimate_tokens(total_text)
    if tokens > TOKEN_LIMIT:
        issues.append(("error", "token_overflow", f"超過 token 限制 ({tokens} > {TOKEN_LIMIT})"))
    
    # Similarity validation
    similarity = meta.get("retrieval_similarity", 0)
    if similarity < MIN_SIMILARITY:
        issues.append(("warning", "low_similarity", f"相似度過低 ({similarity:.3f})"))
    
    # Metadata validation
    if meta.get("type") != "pure_qa_with_context":
        issues.append(("warning", "wrong_type", f"類型標記錯誤: {meta.get('type')}"))
    
    if "context_length" not in meta:
        issues.append(("warning", "missing_context_length", "缺少 context_length 元數據"))
    
    return issues


def run_validation():
    """Run full validation on Pure QA with Context dataset."""
    console.print("[bold blue]P3-T04-S4 資料品質驗證[/bold blue]\n")
    
    # Load data
    console.print(f"Loading from {INPUT_FILE}...")
    samples = load_jsonl(INPUT_FILE)
    console.print(f"Loaded {len(samples)} samples\n")
    
    # Validate each sample
    all_issues = []
    error_count = 0
    warning_count = 0
    similarity_scores = []
    context_lengths = []
    
    for idx, sample in enumerate(track(samples, description="Validating...")):
        issues = validate_sample(sample, idx)
        
        for severity, issue_type, desc in issues:
            all_issues.append({
                "index": idx,
                "severity": severity,
                "issue_type": issue_type,
                "description": desc
            })
            
            if severity == "error":
                error_count += 1
            else:
                warning_count += 1
        
        # Collect statistics
        meta = sample.get("metadata", {})
        similarity_scores.append(meta.get("retrieval_similarity", 0))
        context_lengths.append(meta.get("context_length", 0))
    
    # Save issues
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if all_issues:
        with open(ISSUES_FILE, 'w', encoding='utf-8') as f:
            for issue in all_issues:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")
    
    # Calculate statistics
    similarity_distribution = {
        "> 0.9": sum(1 for s in similarity_scores if s > 0.9),
        "0.8-0.9": sum(1 for s in similarity_scores if 0.8 <= s <= 0.9),
        "0.7-0.8": sum(1 for s in similarity_scores if 0.7 <= s < 0.8),
        "0.6-0.7": sum(1 for s in similarity_scores if 0.6 <= s < 0.7),
        "< 0.6": sum(1 for s in similarity_scores if s < 0.6)
    }
    
    avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0
    avg_context_len = sum(context_lengths) / len(context_lengths) if context_lengths else 0
    
    # Issue type breakdown
    issue_types = Counter(i["issue_type"] for i in all_issues)
    
    # Build report
    report = {
        "timestamp": datetime.now().isoformat(),
        "input_file": str(INPUT_FILE),
        "total_samples": len(samples),
        "validation_result": {
            "errors": error_count,
            "warnings": warning_count,
            "status": "✅ PASS" if error_count == 0 else "❌ FAIL"
        },
        "similarity_distribution": similarity_distribution,
        "statistics": {
            "avg_similarity": avg_similarity,
            "avg_context_length": avg_context_len,
            "min_similarity": min(similarity_scores) if similarity_scores else 0,
            "max_similarity": max(similarity_scores) if similarity_scores else 0
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
    
    summary_table.add_row("總樣本數", str(len(samples)), "")
    summary_table.add_row("錯誤", str(error_count), "❌" if error_count > 0 else "✅")
    summary_table.add_row("警告", str(warning_count), "⚠️" if warning_count > 0 else "✅")
    summary_table.add_row("平均相似度", f"{avg_similarity:.4f}", "✅" if avg_similarity >= 0.7 else "⚠️")
    summary_table.add_row("平均 Context 長度", f"{avg_context_len:.0f} 字", "")
    
    console.print(summary_table)
    
    # Similarity distribution table
    sim_table = Table(title="\n相似度分佈")
    sim_table.add_column("範圍", style="cyan")
    sim_table.add_column("數量", justify="right")
    sim_table.add_column("佔比", justify="right")
    
    for range_name, count in similarity_distribution.items():
        percentage = count / len(samples) * 100 if samples else 0
        style = "green" if range_name in ["> 0.9", "0.8-0.9"] else "yellow" if range_name == "0.7-0.8" else "red"
        sim_table.add_row(range_name, str(count), f"{percentage:.1f}%", style=style)
    
    console.print(sim_table)
    
    # Issue breakdown if any
    if issue_types:
        issue_table = Table(title="\n問題類型分佈")
        issue_table.add_column("問題類型", style="cyan")
        issue_table.add_column("數量", justify="right")
        
        for issue_type, count in issue_types.most_common():
            issue_table.add_row(issue_type, str(count))
        
        console.print(issue_table)
    
    # Final status
    if error_count == 0:
        console.print("\n[bold green]✅ 驗證通過！資料品質良好。[/bold green]")
    else:
        console.print(f"\n[bold red]❌ 驗證失敗：發現 {error_count} 個錯誤[/bold red]")
    
    console.print(f"\n報告已儲存至: {REPORT_FILE}")
    if all_issues:
        console.print(f"問題詳情: {ISSUES_FILE}")
    
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    exit(run_validation())
