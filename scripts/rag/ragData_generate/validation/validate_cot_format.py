"""Validate CoT samples format and quality.

This script performs comprehensive validation of generated CoT samples:
1. Format validation (required markers, fields)
2. Token limit compliance
3. Reasoning quality checks (length, citations)
4. Generate audit report

Why validation:
- Ensure all samples meet RA-DIT specifications
- Catch issues before expensive training
- Provide quality metrics for review

Author: AI Agent  
Date: 2026-02-08
Task: P3-T04-S7 Phase 4
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict, field
from collections import Counter

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Input paths
COT_INPUT_PATH = PROJECT_ROOT / "data" / "training" / "cot" / "cot_samples.jsonl"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "output" / "p3_t04"
VALIDATION_REPORT_PATH = OUTPUT_DIR / "cot_validation_report.json"

# Validation thresholds
MIN_REASONING_LENGTH = 30
MAX_REASONING_LENGTH = 300
MAX_TOKENS = 2048
CHARS_PER_TOKEN = 1.3

# Required format markers (Chinese style)
REQUIRED_INPUT_MARKERS = ["【參考資料】", "【問題】"]
REQUIRED_OUTPUT_MARKERS = ["【思考過程】", "【答案】"]

# Citation indicators (suggests reasoning references background)
CITATION_INDICATORS = [
    "「", "」",  # Chinese quotes
    "《", "》",  # Book titles
    "根據", "文中",  # Reference phrases
    "提到", "記載",
    "所述", "所言",
]

console = Console()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ValidationIssue:
    """A single validation issue."""
    sample_index: int
    issue_type: str  # ERROR or WARNING
    issue_code: str
    message: str


@dataclass
class ValidationResult:
    """Validation result for a single sample."""
    index: int
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Validation Functions
# ============================================================================

def validate_format(sample: Dict[str, Any], index: int) -> ValidationResult:
    """Validate sample format compliance.
    
    Checks:
    - Required fields present
    - Required markers in input/output
    - Metadata completeness
    """
    result = ValidationResult(index=index, is_valid=True)
    
    # Check required fields
    required_fields = ["input", "output", "metadata"]
    for field_name in required_fields:
        if field_name not in sample:
            result.errors.append(f"missing_field:{field_name}")
            result.is_valid = False
    
    if not result.is_valid:
        return result
    
    input_text = sample.get("input", "")
    output_text = sample.get("output", "")
    
    # Check input markers
    for marker in REQUIRED_INPUT_MARKERS:
        if marker not in input_text:
            result.errors.append(f"missing_input_marker:{marker}")
            result.is_valid = False
    
    # Check output markers
    for marker in REQUIRED_OUTPUT_MARKERS:
        if marker not in output_text:
            result.errors.append(f"missing_output_marker:{marker}")
            result.is_valid = False
    
    # Check metadata type
    metadata = sample.get("metadata", {})
    if metadata.get("type") != "cot":
        result.warnings.append("unexpected_type")
    
    return result


def validate_token_limit(sample: Dict[str, Any], index: int) -> ValidationResult:
    """Validate token count is within limit."""
    result = ValidationResult(index=index, is_valid=True)
    
    input_text = sample.get("input", "")
    output_text = sample.get("output", "")
    total_text = input_text + output_text
    
    estimated_tokens = int(len(total_text) * CHARS_PER_TOKEN)
    result.metrics["estimated_tokens"] = estimated_tokens
    
    if estimated_tokens > MAX_TOKENS:
        result.errors.append(f"token_overflow:{estimated_tokens}")
        result.is_valid = False
    elif estimated_tokens > MAX_TOKENS * 0.9:
        result.warnings.append(f"near_token_limit:{estimated_tokens}")
    
    return result


def validate_reasoning_quality(sample: Dict[str, Any], index: int) -> ValidationResult:
    """Validate reasoning chain quality.
    
    Checks:
    - Reasoning length within bounds
    - Contains citation indicators (references background)
    - No refusal patterns
    """
    result = ValidationResult(index=index, is_valid=True)
    
    output_text = sample.get("output", "")
    
    # Extract reasoning (between 【思考過程】 and 【答案】)
    reasoning = ""
    if "【思考過程】" in output_text and "【答案】" in output_text:
        start = output_text.find("【思考過程】") + len("【思考過程】")
        end = output_text.find("【答案】")
        reasoning = output_text[start:end].strip()
    
    result.metrics["reasoning_length"] = len(reasoning)
    
    # Check length
    if len(reasoning) < MIN_REASONING_LENGTH:
        result.warnings.append(f"short_reasoning:{len(reasoning)}")
    elif len(reasoning) > MAX_REASONING_LENGTH:
        result.warnings.append(f"long_reasoning:{len(reasoning)}")
    
    # Check for citations
    has_citation = any(indicator in reasoning for indicator in CITATION_INDICATORS)
    result.metrics["has_citation"] = has_citation
    
    if not has_citation:
        result.warnings.append("no_citation")
    
    # Check for refusal patterns
    refusal_patterns = ["抱歉", "無法", "我不能", "作為AI", "I cannot"]
    for pattern in refusal_patterns:
        if pattern in reasoning:
            result.errors.append(f"refusal_detected:{pattern}")
            result.is_valid = False
            break
    
    # Count reasoning steps (by newlines or numbered list)
    step_count = len([line for line in reasoning.split("\n") if line.strip()])
    result.metrics["step_count"] = step_count
    
    if step_count < 2:
        result.warnings.append("few_steps")
    
    return result


def validate_input_quality(sample: Dict[str, Any], index: int) -> ValidationResult:
    """Validate input quality.
    
    Checks:
    - Input not too short
    - Question is present and non-empty
    """
    result = ValidationResult(index=index, is_valid=True)
    
    input_text = sample.get("input", "")
    result.metrics["input_length"] = len(input_text)
    
    if len(input_text) < 50:
        result.warnings.append(f"short_input:{len(input_text)}")
    
    # Extract question
    if "【問題】" in input_text:
        question = input_text.split("【問題】")[-1].strip()
        result.metrics["question_length"] = len(question)
        
        if len(question) < 10:
            result.warnings.append(f"short_question:{len(question)}")
    
    return result


# ============================================================================
# Main Validation
# ============================================================================

def validate_all_samples(samples: List[Dict[str, Any]]) -> Tuple[List[ValidationResult], Dict[str, Any]]:
    """Run all validations on all samples.
    
    Returns:
        Tuple of (results, summary_stats)
    """
    results: List[ValidationResult] = []
    
    stats = {
        "total_samples": len(samples),
        "valid_samples": 0,
        "invalid_samples": 0,
        "total_errors": 0,
        "total_warnings": 0,
        "error_types": Counter(),
        "warning_types": Counter(),
        "avg_reasoning_length": 0,
        "avg_step_count": 0,
        "citation_rate": 0,
    }
    
    total_reasoning_len = 0
    total_steps = 0
    citation_count = 0
    
    console.print(Panel(
        "[bold cyan]Phase 4: 驗證 CoT 資料[/bold cyan]",
        border_style="cyan"
    ))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]驗證樣本...", total=len(samples))
        
        for i, sample in enumerate(samples):
            progress.update(task, advance=1)
            
            # Run all validations
            format_result = validate_format(sample, i)
            token_result = validate_token_limit(sample, i)
            reasoning_result = validate_reasoning_quality(sample, i)
            input_result = validate_input_quality(sample, i)
            
            # Merge results
            combined = ValidationResult(
                index=i,
                is_valid=all([
                    format_result.is_valid,
                    token_result.is_valid,
                    reasoning_result.is_valid,
                    input_result.is_valid
                ]),
                errors=format_result.errors + token_result.errors + 
                       reasoning_result.errors + input_result.errors,
                warnings=format_result.warnings + token_result.warnings + 
                         reasoning_result.warnings + input_result.warnings,
                metrics={
                    **token_result.metrics,
                    **reasoning_result.metrics,
                    **input_result.metrics
                }
            )
            
            results.append(combined)
            
            # Update stats
            if combined.is_valid:
                stats["valid_samples"] += 1
            else:
                stats["invalid_samples"] += 1
            
            for error in combined.errors:
                stats["total_errors"] += 1
                error_type = error.split(":")[0]
                stats["error_types"][error_type] += 1
            
            for warning in combined.warnings:
                stats["total_warnings"] += 1
                warning_type = warning.split(":")[0]
                stats["warning_types"][warning_type] += 1
            
            # Accumulate metrics
            total_reasoning_len += combined.metrics.get("reasoning_length", 0)
            total_steps += combined.metrics.get("step_count", 0)
            if combined.metrics.get("has_citation"):
                citation_count += 1
    
    # Calculate averages
    if stats["valid_samples"] > 0:
        stats["avg_reasoning_length"] = total_reasoning_len // len(samples)
        stats["avg_step_count"] = total_steps / len(samples)
        stats["citation_rate"] = citation_count / len(samples) * 100
    
    # Convert Counter to dict for JSON
    stats["error_types"] = dict(stats["error_types"])
    stats["warning_types"] = dict(stats["warning_types"])
    
    return results, stats


def save_report(results: List[ValidationResult], stats: Dict[str, Any]):
    """Save validation report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Build report
    report = {
        "summary": stats,
        "sample_results": [asdict(r) for r in results[:100]],  # First 100 for brevity
        "issues": []
    }
    
    # Collect all issues
    for result in results:
        for error in result.errors:
            report["issues"].append({
                "index": result.index,
                "type": "ERROR",
                "code": error
            })
        for warning in result.warnings:
            report["issues"].append({
                "index": result.index,
                "type": "WARNING", 
                "code": warning
            })
    
    with open(VALIDATION_REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]✅ 驗證報告已保存至: {VALIDATION_REPORT_PATH.relative_to(PROJECT_ROOT)}[/green]")


def display_summary(stats: Dict[str, Any]):
    """Display validation summary."""
    console.print("\n" + "=" * 50)
    console.print("[bold cyan]📊 驗證結果摘要[/bold cyan]\n")
    
    # Main stats table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("指標", style="dim")
    table.add_column("數值", style="green")
    
    table.add_row("總樣本數", f"{stats['total_samples']:,}")
    table.add_row("有效樣本", f"[bold green]{stats['valid_samples']:,}[/bold green]")
    table.add_row("無效樣本", f"[red]{stats['invalid_samples']}[/red]" if stats['invalid_samples'] > 0 else "0")
    table.add_row("總錯誤數", f"[red]{stats['total_errors']}[/red]" if stats['total_errors'] > 0 else "0")
    table.add_row("總警告數", f"[yellow]{stats['total_warnings']}[/yellow]" if stats['total_warnings'] > 0 else "0")
    table.add_row("平均推理長度", f"{stats['avg_reasoning_length']} 字")
    table.add_row("平均推理步數", f"{stats['avg_step_count']:.1f}")
    table.add_row("引用率", f"{stats['citation_rate']:.1f}%")
    
    console.print(table)
    
    # Validation verdict
    console.print()
    if stats["invalid_samples"] == 0:
        console.print("[bold green]✅ 驗證通過：所有樣本格式正確[/bold green]")
    else:
        console.print(f"[bold red]❌ 驗證失敗：{stats['invalid_samples']} 筆樣本有錯誤[/bold red]")
    
    warning_rate = stats['total_warnings'] / stats['total_samples'] * 100 if stats['total_samples'] > 0 else 0
    if warning_rate > 20:
        console.print(f"[yellow]⚠️ 警告率過高: {warning_rate:.1f}% (建議 < 20%)[/yellow]")
    else:
        console.print(f"[green]✅ 警告率正常: {warning_rate:.1f}%[/green]")
    
    # Error types
    if stats.get("error_types"):
        console.print("\n[bold]錯誤類型分佈:[/bold]")
        for etype, count in stats["error_types"].items():
            console.print(f"  [red]{etype}[/red]: {count}")
    
    # Warning types (top 5)
    if stats.get("warning_types"):
        console.print("\n[bold]警告類型分佈 (Top 5):[/bold]")
        sorted_warnings = sorted(stats["warning_types"].items(), key=lambda x: x[1], reverse=True)
        for wtype, count in sorted_warnings[:5]:
            console.print(f"  [yellow]{wtype}[/yellow]: {count}")


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Main entry point."""
    try:
        # Load samples
        if not COT_INPUT_PATH.exists():
            console.print(f"[red]❌ CoT 檔案不存在: {COT_INPUT_PATH}[/red]")
            console.print("[yellow]請先執行 convert_to_radit_cot.py[/yellow]")
            sys.exit(1)
        
        samples = []
        with open(COT_INPUT_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        
        if not samples:
            console.print("[red]❌ 未找到有效樣本[/red]")
            sys.exit(1)
        
        console.print(f"[dim]已載入 {len(samples):,} 筆樣本[/dim]\n")
        
        # Validate
        results, stats = validate_all_samples(samples)
        
        # Save report
        save_report(results, stats)
        
        # Display summary
        display_summary(stats)
        
        # Exit code based on validation result
        if stats["invalid_samples"] > 0:
            console.print("\n[bold yellow]⚠️ 驗證發現錯誤，請檢查報告並修正[/bold yellow]")
            sys.exit(1)
        
        console.print("\n[bold green]🎉 Phase 4 完成！CoT 資料驗證通過[/bold green]")
        console.print("[dim]可開始將資料整合至最終訓練集[/dim]")
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已取消[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]❌ 發生錯誤: {e}[/bold red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
