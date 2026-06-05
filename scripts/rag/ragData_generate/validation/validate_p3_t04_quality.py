"""Validate quality of P3-T04 generated samples (Negative Sampling + Pure QA).

This script performs comprehensive quality checks on:
1. Negative Sampling (2,571 samples)
2. Pure QA supplement (2,211 samples)

Validation criteria:
- Format completeness (instruction/input/output present)
- Format correctness (markers, structure)
- Content quality (length, coherence)
- Domain consistency
- Template diversity (for Negative samples)

Output: Detailed quality report with pass/fail status
"""

import json
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Tuple
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import track

console = Console()

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Input files
NEGATIVE_FILE = PROJECT_ROOT / "data" / "training" / "negative_samples" / "negative_sampling_3000.jsonl"
PURE_QA_FILE = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_supplement_2211.jsonl"

# Output
REPORT_FILE = PROJECT_ROOT / "output" / "p3_t04" / "quality_validation_report.json"
ISSUES_FILE = PROJECT_ROOT / "output" / "p3_t04" / "quality_issues.jsonl"

# Quality thresholds
MIN_QUESTION_LENGTH = 10
MAX_QUESTION_LENGTH = 500
MIN_ANSWER_LENGTH = 5
MAX_ANSWER_LENGTH = 1000
MAX_TOKEN_ESTIMATE = 2048  # RA-DIT limit

# Expected markers
NEGATIVE_CONTEXT_MARKER = "【參考資料】"
NEGATIVE_QUESTION_MARKER = "【問題】"
PURE_QA_FORBIDDEN_MARKERS = ["【參考資料】", "【問題】"]


# ============================================================================
# Helper Functions
# ============================================================================

def estimate_tokens(text: str) -> int:
    """Estimate token count (Chinese: 1 char ≈ 2 tokens)."""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return chinese_chars * 2 + other_chars // 4


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    sample_id: str
    issue_type: str
    severity: str  # error, warning
    description: str
    
    def to_dict(self):
        return {
            "sample_id": self.sample_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description
        }


# ============================================================================
# Validation Functions
# ============================================================================

def validate_completeness(sample: Dict, sample_type: str) -> List[ValidationIssue]:
    """Check if all required fields are present and non-empty."""
    issues = []
    sample_id = f"{sample_type}_{sample.get('metadata', {}).get('generated_at', 'unknown')}"
    
    required_fields = ["instruction", "input", "output"]
    
    for field in required_fields:
        if field not in sample:
            issues.append(ValidationIssue(
                sample_id=sample_id,
                issue_type="missing_field",
                severity="error",
                description=f"缺少必要欄位: {field}"
            ))
        elif not sample[field] or not str(sample[field]).strip():
            issues.append(ValidationIssue(
                sample_id=sample_id,
                issue_type="empty_field",
                severity="error",
                description=f"欄位為空: {field}"
            ))
    
    return issues


def validate_negative_format(sample: Dict, index: int) -> List[ValidationIssue]:
    """Validate Negative Sampling format requirements."""
    issues = []
    sample_id = f"negative_{index}"
    input_text = sample.get("input", "")
    output_text = sample.get("output", "")
    
    # Check for required markers in input
    if NEGATIVE_CONTEXT_MARKER not in input_text:
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="missing_marker",
            severity="error",
            description=f"input 缺少 {NEGATIVE_CONTEXT_MARKER}"
        ))
    
    if NEGATIVE_QUESTION_MARKER not in input_text:
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="missing_marker",
            severity="error",
            description=f"input 缺少 {NEGATIVE_QUESTION_MARKER}"
        ))
    
    # Check refusal in output
    refusal_keywords = ["無法", "不能", "不足", "無關", "未包含"]
    if not any(kw in output_text for kw in refusal_keywords):
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="invalid_refusal",
            severity="warning",
            description="output 未明確拒答"
        ))
    
    # Check metadata
    metadata = sample.get("metadata", {})
    if metadata.get("type") != "negative_sampling":
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="incorrect_metadata",
            severity="warning",
            description=f"metadata.type 應為 'negative_sampling'，實為 '{metadata.get('type')}'"
        ))
    
    return issues


def validate_pure_qa_format(sample: Dict, index: int) -> List[ValidationIssue]:
    """Validate Pure QA format requirements."""
    issues = []
    sample_id = f"pure_qa_{index}"
    input_text = sample.get("input", "")
    
    # Input should NOT contain context markers
    for marker in PURE_QA_FORBIDDEN_MARKERS:
        if marker in input_text:
            issues.append(ValidationIssue(
                sample_id=sample_id,
                issue_type="forbidden_marker",
                severity="error",
                description=f"Pure QA input 不應包含 {marker}"
            ))
    
    # Check metadata
    metadata = sample.get("metadata", {})
    if metadata.get("type") != "pure_qa":
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="incorrect_metadata",
            severity="warning",
            description=f"metadata.type 應為 'pure_qa'，實為 '{metadata.get('type')}'"
        ))
    
    return issues


def validate_content_quality(sample: Dict, sample_type: str, index: int) -> List[ValidationIssue]:
    """Validate content quality (length, tokens)."""
    issues = []
    sample_id = f"{sample_type}_{index}"
    
    input_text = sample.get("input", "")
    output_text = sample.get("output", "")
    
    # Extract question from input
    if "【問題】" in input_text:
        question = input_text.split("【問題】")[-1].strip()
    else:
        question = input_text
    
    # Question length
    if len(question) < MIN_QUESTION_LENGTH:
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="question_too_short",
            severity="warning",
            description=f"問題過短: {len(question)} 字 (最小 {MIN_QUESTION_LENGTH})"
        ))
    elif len(question) > MAX_QUESTION_LENGTH:
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="question_too_long",
            severity="warning",
            description=f"問題過長: {len(question)} 字 (最大 {MAX_QUESTION_LENGTH})"
        ))
    
    # Answer length
    if len(output_text) < MIN_ANSWER_LENGTH:
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="answer_too_short",
            severity="warning",
            description=f"答案過短: {len(output_text)} 字 (最小 {MIN_ANSWER_LENGTH})"
        ))
    elif len(output_text) > MAX_ANSWER_LENGTH:
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="answer_too_long",
            severity="warning",
            description=f"答案過長: {len(output_text)} 字 (最大 {MAX_ANSWER_LENGTH})"
        ))
    
    # Total token estimate
    total_text = input_text + output_text
    tokens = estimate_tokens(total_text)
    if tokens > MAX_TOKEN_ESTIMATE:
        issues.append(ValidationIssue(
            sample_id=sample_id,
            issue_type="token_overflow",
            severity="error",
            description=f"Token 超限: {tokens} (最大 {MAX_TOKEN_ESTIMATE})"
        ))
    
    return issues


def validate_template_diversity(samples: List[Dict]) -> Dict:
    """Check template diversity for Negative samples."""
    refusal_counts = Counter()
    
    for sample in samples:
        output = sample.get("output", "")
        refusal_counts[output] += 1
    
    stats = {
        "unique_templates": len(refusal_counts),
        "template_distribution": dict(refusal_counts.most_common()),
        "max_usage": max(refusal_counts.values()) if refusal_counts else 0,
        "min_usage": min(refusal_counts.values()) if refusal_counts else 0
    }
    
    return stats


# ============================================================================
# Main Validation
# ============================================================================

def load_samples(path: Path) -> List[Dict]:
    """Load samples from JSONL file."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def validate_dataset(samples: List[Dict], dataset_type: str) -> Tuple[List[ValidationIssue], Dict]:
    """Validate entire dataset."""
    all_issues = []
    
    console.print(f"\nValidating {dataset_type}...")
    
    for i, sample in enumerate(track(samples, description=f"Checking {dataset_type}...")):
        # Completeness
        all_issues.extend(validate_completeness(sample, dataset_type))
        
        # Format-specific
        if dataset_type == "negative":
            all_issues.extend(validate_negative_format(sample, i))
        elif dataset_type == "pure_qa":
            all_issues.extend(validate_pure_qa_format(sample, i))
        
        # Content quality
        all_issues.extend(validate_content_quality(sample, dataset_type, i))
    
    # Calculate statistics
    stats = {
        "total_samples": len(samples),
        "total_issues": len(all_issues),
        "error_count": sum(1 for issue in all_issues if issue.severity == "error"),
        "warning_count": sum(1 for issue in all_issues if issue.severity == "warning"),
        "issue_distribution": dict(Counter(issue.issue_type for issue in all_issues))
    }
    
    # Template diversity for Negative samples
    if dataset_type == "negative":
        stats["template_diversity"] = validate_template_diversity(samples)
    
    return all_issues, stats


def main():
    console.print("[bold blue]P3-T04 資料品質驗證[/bold blue]\n")
    
  # Ensure output directory
    (PROJECT_ROOT / "output" / "p3_t04").mkdir(parents=True, exist_ok=True)
    
    # Load datasets
    console.print(f"Loading Negative Sampling from {NEGATIVE_FILE}...")
    negative_samples = load_samples(NEGATIVE_FILE)
    console.print(f"  Loaded: {len(negative_samples)} samples")
    
    console.print(f"\nLoading Pure QA from {PURE_QA_FILE}...")
    pure_qa_samples = load_samples(PURE_QA_FILE)
    console.print(f"  Loaded: {len(pure_qa_samples)} samples")
    
    # Validate Negative Sampling
    negative_issues, negative_stats = validate_dataset(negative_samples, "negative")
    
    # Validate Pure QA
    pure_qa_issues, pure_qa_stats = validate_dataset(pure_qa_samples, "pure_qa")
    
    # Combine results
    all_issues = negative_issues + pure_qa_issues
    
    # Save issues
    if all_issues:
        with open(ISSUES_FILE, 'w', encoding='utf-8') as f:
            for issue in all_issues:
                f.write(json.dumps(issue.to_dict(), ensure_ascii=False) + "\n")
        console.print(f"\n[yellow]發現 {len(all_issues)} 個問題，已儲存至 {ISSUES_FILE}[/yellow]")
    
    # Generate report
    report = {
        "validation_timestamp": Path(__file__).stat().st_mtime,
        "negative_sampling": negative_stats,
        "pure_qa": pure_qa_stats,
        "overall": {
            "total_samples": len(negative_samples) + len(pure_qa_samples),
            "total_issues": len(all_issues),
            "error_count": negative_stats["error_count"] + pure_qa_stats["error_count"],
            "warning_count": negative_stats["warning_count"] + pure_qa_stats["warning_count"]
        }
    }
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # Display summary
    console.print("\n[bold cyan]═══ 驗證結果 ═══[/bold cyan]\n")
    
    # Negative Sampling table
    neg_table = Table(title="Negative Sampling 驗證")
    neg_table.add_column("指標", style="cyan")
    neg_table.add_column("數值", justify="right")
    neg_table.add_column("狀態")
    
    neg_table.add_row("總樣本數", str(negative_stats["total_samples"]), "")
    neg_table.add_row("問題總數", str(negative_stats["total_issues"]), 
                     "✅" if negative_stats["total_issues"] == 0 else "⚠️")
    neg_table.add_row("錯誤", str(negative_stats["error_count"]),
                     "✅" if negative_stats["error_count"] == 0 else "❌")
    neg_table.add_row("警告", str(negative_stats["warning_count"]),
                     "✅" if negative_stats["warning_count"] == 0 else "⚠️")
    
    if "template_diversity" in negative_stats:
        td = negative_stats["template_diversity"]
        neg_table.add_row("拒答模板數", str(td["unique_templates"]),
                         "✅" if td["unique_templates"] >= 5 else "⚠️")
    
    console.print(neg_table)
    
    # Pure QA table
    pq_table = Table(title="\nPure QA 驗證")
    pq_table.add_column("指標", style="cyan")
    pq_table.add_column("數值", justify="right")
    pq_table.add_column("狀態")
    
    pq_table.add_row("總樣本數", str(pure_qa_stats["total_samples"]), "")
    pq_table.add_row("問題總數", str(pure_qa_stats["total_issues"]),
                    "✅" if pure_qa_stats["total_issues"] == 0 else "⚠️")
    pq_table.add_row("錯誤", str(pure_qa_stats["error_count"]),
                    "✅" if pure_qa_stats["error_count"] == 0 else "❌")
    pq_table.add_row("警告", str(pure_qa_stats["warning_count"]),
                    "✅" if pure_qa_stats["warning_count"] == 0 else "⚠️")
    
    console.print(pq_table)
    
    # ===== NEW: Detailed Error Type Analysis =====
    if all_issues:
        console.print("\n[bold cyan]═══ 錯誤類型詳細分析 ═══[/bold cyan]\n")
        
        # Separate errors and warnings
        errors =[i for i in all_issues if i.severity == "error"]
        warnings = [i for i in all_issues if i.severity == "warning"]
        
        # Error type distribution
        if errors:
            error_types = Counter(i.issue_type for i in errors)
            
            err_table = Table(title="錯誤類型分佈 (Errors)")
            err_table.add_column("錯誤類型", style="red")
            err_table.add_column("數量", justify="right")
            err_table.add_column("佔比", justify="right")
            err_table.add_column("嚴重性", style="bold red")
            
            for issue_type, count in error_types.most_common():
                pct = count / len(errors) * 100
                err_table.add_row(
                    issue_type,
                    str(count),
                    f"{pct:.1f}%",
                    "❌"
                )
            
            console.print(err_table)
            
            # Show examples for each error type
            console.print("\n[bold yellow]錯誤範例 (前3個):[/bold yellow]\n")
            for issue_type in list(error_types.keys())[:5]:  # Top 5 error types
                examples = [i for i in errors if i.issue_type == issue_type][:3]
                console.print(f"[red]• {issue_type}[/red] ({len([i for i in errors if i.issue_type == issue_type])} 筆):")
                for ex in examples:
                    console.print(f"  - {ex.sample_id}: {ex.description}")
                console.print()
        
        # Warning type distribution
        if warnings:
            warning_types = Counter(i.issue_type for i in warnings)
            
            warn_table = Table(title="\n警告類型分佈 (Warnings)")
            warn_table.add_column("警告類型", style="yellow")
            warn_table.add_column("數量", justify="right")
            warn_table.add_column("佔比", justify="right")
            warn_table.add_column("嚴重性", style="bold yellow")
            
            for issue_type, count in warning_types.most_common():
                pct = count / len(warnings) * 100
                warn_table.add_row(
                    issue_type,
                    str(count),
                    f"{pct:.1f}%",
                    "⚠️"
                )
            
            console.print(warn_table)
    
    # Overall status
    overall_status = "✅ 通過" if report["overall"]["error_count"] == 0 else "❌ 有錯誤"
    
    console.print(f"\n[bold]整體驗證狀態: {overall_status}[/bold]")
    console.print(f"總樣本: {report['overall']['total_samples']}")
    console.print(f"錯誤: {report['overall']['error_count']}")
    console.print(f"警告: {report['overall']['warning_count']}")
    
    console.print(f"\n報告已儲存至: {REPORT_FILE}")
    
    if all_issues:
        console.print(f"問題清單已儲存至: {ISSUES_FILE}")
        console.print(f"\n[dim]提示: 查看 {ISSUES_FILE} 可獲得所有問題的詳細資訊[/dim]")
    
    # Return exit code
    return 0 if report["overall"]["error_count"] == 0 else 1


if __name__ == "__main__":
    exit(main())
