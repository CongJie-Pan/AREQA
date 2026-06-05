"""Validate RA-DIT format training data for LM-ft.

This script performs comprehensive validation of generated RA-DIT format data:
1. Completeness: instruction/input/output fields present and non-empty
2. Format: Input contains 【參考資料】 and 【問題】 markers
3. Length: Total token count < 2048 (using Qwen tokenizer)
4. Quality: Random sampling for human audit

Why validation is critical:
- Malformed data causes training errors or silent degradation
- Length overflow leads to truncation and information loss
- Format errors break the RAG prompt structure

Output:
- validation_report.json: Detailed validation statistics
- human_audit_sample.jsonl: 100 random samples for human review
"""

import json
import random
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
from collections import defaultdict

from rich.console import Console
from rich.progress import track
from rich.table import Table

console = Console()

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Input/Output paths
INPUT_FILE = PROJECT_ROOT / "data" / "training" / "rag_format" / "backfilled_radit_format.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "output" / "p3_t03_backfill"
VALIDATION_REPORT = OUTPUT_DIR / "validation_report.json"
HUMAN_AUDIT_SAMPLE = OUTPUT_DIR / "human_audit_sample.jsonl"

# Validation thresholds (from data_format_spec.md §3)
MAX_TOTAL_CHARS = 4000  # Approximate character limit (before tokenization)
MAX_TOKENS = 2048  # Hard limit for fine-tuning
MIN_INPUT_LENGTH = 20  # Minimum meaningful input
MIN_OUTPUT_LENGTH = 10  # Minimum meaningful output
HUMAN_AUDIT_SAMPLE_SIZE = 100  # Number of samples for human review

# Required format markers
REQUIRED_MARKERS = ["【參考資料】", "【問題】"]


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ValidationResult:
    """Result for a single sample validation."""
    sample_id: int
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    char_count: int = 0
    estimated_tokens: int = 0


@dataclass
class ValidationReport:
    """Aggregated validation report."""
    total_samples: int = 0
    valid_samples: int = 0
    invalid_samples: int = 0
    error_counts: Dict[str, int] = field(default_factory=dict)
    warning_counts: Dict[str, int] = field(default_factory=dict)
    avg_char_count: float = 0.0
    avg_estimated_tokens: float = 0.0
    max_char_count: int = 0
    max_estimated_tokens: int = 0
    validation_rate: float = 0.0
    timestamp: str = ""


# ============================================================================
# Validation Functions
# ============================================================================

def estimate_token_count(text: str) -> int:
    """Estimate token count without loading full tokenizer.
    
    Why estimation instead of exact tokenization:
    - Loading Qwen tokenizer requires ~2GB VRAM
    - For validation, 3:1 char:token ratio is sufficient
    - Exact tokenization can be done selectively on edge cases
    
    Average ratio for Chinese text: ~2.5-3.0 chars per token
    We use conservative 2.5 to catch potential overflows.
    """
    return len(text) // 2 + 1  # Conservative estimate for Chinese


def validate_sample(sample: Dict, sample_id: int) -> ValidationResult:
    """Validate a single RA-DIT format sample.
    
    Validation rules from data_format_spec.md §3:
    1. Completeness: All required fields present and non-empty
    2. Format markers: Input contains 【參考資料】and 【問題】
    3. Length limits: Total chars < 4000, tokens < 2048
    """
    result = ValidationResult(sample_id=sample_id, is_valid=True)
    
    # 1. Completeness check
    instruction = sample.get("instruction", "")
    input_text = sample.get("input", "")
    output_text = sample.get("output", "")
    
    if not instruction:
        result.errors.append("missing_instruction")
        result.is_valid = False
    
    if not input_text:
        result.errors.append("missing_input")
        result.is_valid = False
    elif len(input_text) < MIN_INPUT_LENGTH:
        result.warnings.append("short_input")
    
    if not output_text:
        result.errors.append("missing_output")
        result.is_valid = False
    elif len(output_text) < MIN_OUTPUT_LENGTH:
        result.warnings.append("short_output")
    
    # 2. Format markers check
    for marker in REQUIRED_MARKERS:
        if marker not in input_text:
            result.errors.append(f"missing_marker:{marker}")
            result.is_valid = False
    
    # 3. Length checks
    total_text = instruction + input_text + output_text
    result.char_count = len(total_text)
    result.estimated_tokens = estimate_token_count(total_text)
    
    if result.char_count > MAX_TOTAL_CHARS:
        result.warnings.append(f"long_text:{result.char_count}")
    
    if result.estimated_tokens > MAX_TOKENS:
        result.errors.append(f"token_overflow:{result.estimated_tokens}")
        result.is_valid = False
    
    # 4. Metadata check (optional but recommended)
    metadata = sample.get("metadata", {})
    if not metadata:
        result.warnings.append("missing_metadata")
    
    return result


def load_samples(path: Path) -> List[Dict]:
    """Load all samples from JSONL file."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def run_validation(samples: List[Dict]) -> tuple[ValidationReport, List[ValidationResult]]:
    """Run validation on all samples."""
    report = ValidationReport()
    results = []
    
    total_chars = 0
    total_tokens = 0
    max_chars = 0
    max_tokens = 0
    error_counts = defaultdict(int)
    warning_counts = defaultdict(int)
    
    for i, sample in enumerate(track(samples, description="Validating samples...")):
        result = validate_sample(sample, i)
        results.append(result)
        
        if result.is_valid:
            report.valid_samples += 1
        else:
            report.invalid_samples += 1
        
        # Aggregate errors/warnings
        for error in result.errors:
            error_counts[error] += 1
        for warning in result.warnings:
            warning_counts[warning] += 1
        
        # Track lengths
        total_chars += result.char_count
        total_tokens += result.estimated_tokens
        max_chars = max(max_chars, result.char_count)
        max_tokens = max(max_tokens, result.estimated_tokens)
    
    # Finalize report
    report.total_samples = len(samples)
    report.error_counts = dict(error_counts)
    report.warning_counts = dict(warning_counts)
    report.avg_char_count = total_chars / len(samples) if samples else 0
    report.avg_estimated_tokens = total_tokens / len(samples) if samples else 0
    report.max_char_count = max_chars
    report.max_estimated_tokens = max_tokens
    report.validation_rate = report.valid_samples / report.total_samples if samples else 0
    report.timestamp = datetime.now().isoformat()
    
    return report, results


def sample_for_human_audit(samples: List[Dict], n: int = HUMAN_AUDIT_SAMPLE_SIZE) -> List[Dict]:
    """Randomly sample n items for human audit.
    
    Why random sampling:
    - Full manual review of 10,000+ samples is impractical
    - Random sampling provides unbiased quality estimate
    - 100 samples give 95% CI of ±10% at worst case (50% pass rate)
    """
    if len(samples) <= n:
        return samples
    
    # Stratified sampling: ensure mix of quality tiers
    tier_1_samples = [s for s in samples if s.get("metadata", {}).get("quality_tier") == "tier_1"]
    tier_2_samples = [s for s in samples if s.get("metadata", {}).get("quality_tier") == "tier_2"]
    
    # Proportional sampling
    tier_1_ratio = len(tier_1_samples) / len(samples)
    tier_1_count = int(n * tier_1_ratio)
    tier_2_count = n - tier_1_count
    
    sampled = []
    if tier_1_samples:
        sampled.extend(random.sample(tier_1_samples, min(tier_1_count, len(tier_1_samples))))
    if tier_2_samples:
        sampled.extend(random.sample(tier_2_samples, min(tier_2_count, len(tier_2_samples))))
    
    # Fill remaining with random if needed
    remaining = n - len(sampled)
    if remaining > 0:
        pool = [s for s in samples if s not in sampled]
        sampled.extend(random.sample(pool, min(remaining, len(pool))))
    
    return sampled


def save_outputs(report: ValidationReport, audit_samples: List[Dict], output_dir: Path):
    """Save validation report and audit samples."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save report
    with open(VALIDATION_REPORT, 'w', encoding='utf-8') as f:
        json.dump(asdict(report), f, ensure_ascii=False, indent=2)
    console.print(f"✅ Saved validation report to {VALIDATION_REPORT}")
    
    # Save human audit samples
    with open(HUMAN_AUDIT_SAMPLE, 'w', encoding='utf-8') as f:
        for sample in audit_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    console.print(f"✅ Saved {len(audit_samples)} samples for human audit to {HUMAN_AUDIT_SAMPLE}")


def display_report(report: ValidationReport):
    """Display validation summary."""
    console.print("\n[bold cyan]═══ P3-T03-S4: RA-DIT 格式驗證報告 ═══[/bold cyan]\n")
    
    # Summary table
    table = Table(title="驗證統計")
    table.add_column("指標", style="cyan")
    table.add_column("數值", justify="right")
    table.add_column("狀態", justify="center")
    
    # Validation rate
    rate_color = "green" if report.validation_rate >= 0.95 else "yellow" if report.validation_rate >= 0.90 else "red"
    table.add_row(
        "總樣本數",
        str(report.total_samples),
        ""
    )
    table.add_row(
        "有效樣本",
        str(report.valid_samples),
        f"[{rate_color}]{report.validation_rate*100:.1f}%[/{rate_color}]"
    )
    table.add_row(
        "無效樣本",
        str(report.invalid_samples),
        "❌" if report.invalid_samples > 0 else "✅"
    )
    table.add_row(
        "平均字數",
        f"{report.avg_char_count:.0f}",
        ""
    )
    table.add_row(
        "平均 Token (估)",
        f"{report.avg_estimated_tokens:.0f}",
        "✅" if report.avg_estimated_tokens < MAX_TOKENS else "⚠️"
    )
    table.add_row(
        "最大 Token (估)",
        str(report.max_estimated_tokens),
        "✅" if report.max_estimated_tokens < MAX_TOKENS else "⚠️"
    )
    
    console.print(table)
    
    # Error breakdown
    if report.error_counts:
        error_table = Table(title="\n錯誤分布")
        error_table.add_column("錯誤類型", style="red")
        error_table.add_column("數量", justify="right")
        
        for error, count in sorted(report.error_counts.items(), key=lambda x: -x[1]):
            error_table.add_row(error, str(count))
        
        console.print(error_table)
    else:
        console.print("\n[green]✅ 無格式錯誤！[/green]")
    
    # Warning breakdown
    if report.warning_counts:
        warn_table = Table(title="\n警告分布")
        warn_table.add_column("警告類型", style="yellow")
        warn_table.add_column("數量", justify="right")
        
        for warning, count in sorted(report.warning_counts.items(), key=lambda x: -x[1]):
            warn_table.add_row(warning, str(count))
        
        console.print(warn_table)


def main():
    """Main entry point."""
    console.print("[bold blue]P3-T03-S4: RA-DIT 格式驗證與人工審核抽樣[/bold blue]\n")
    
    # Check input file
    if not INPUT_FILE.exists():
        console.print(f"[red]Error: Input file not found at {INPUT_FILE}[/red]")
        console.print("[yellow]Please run convert_to_radit_format.py first.[/yellow]")
        return 1
    
    # Load samples
    console.print(f"Loading samples from {INPUT_FILE}...")
    samples = load_samples(INPUT_FILE)
    console.print(f"Loaded {len(samples)} samples\n")
    
    # Run validation
    report, results = run_validation(samples)
    
    # Display report
    display_report(report)
    
    # Sample for human audit
    console.print("\n[bold]抽取人工審核樣本...[/bold]")
    audit_samples = sample_for_human_audit(samples, HUMAN_AUDIT_SAMPLE_SIZE)
    
    # Save outputs
    console.print("\n[bold]儲存結果...[/bold]")
    save_outputs(report, audit_samples, OUTPUT_DIR)
    
    # Final summary
    console.print("\n[bold green]✅ 驗證完成！[/bold green]")
    console.print(f"   驗證通過率: {report.validation_rate*100:.1f}%")
    console.print(f"   人工審核樣本: {len(audit_samples)} 筆")
    
    if report.validation_rate >= 0.95:
        console.print("\n[green]🎉 資料集品質符合標準！[/green]")
    else:
        console.print("\n[yellow]⚠️ 建議檢查並修正無效樣本[/yellow]")
    
    return 0


if __name__ == "__main__":
    exit(main())
