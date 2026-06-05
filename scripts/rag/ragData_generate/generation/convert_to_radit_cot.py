"""Convert CoT samples to RA-DIT format with randomized markers.

This script converts generated CoT reasoning to the final training format:
1. Load CoT samples from Phase 2
2. Apply randomized markers (RA-DIT Appendix C)
3. Convert to project's ancient Chinese format
4. Output final training-ready JSONL

Why randomized markers:
- RA-DIT paper shows they prevent overfitting to format tokens
- Improves model generalization across different prompt styles
- Essential for retrieval-augmented instruction tuning

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S7 Phase 3
"""

import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import Counter

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Input paths
COT_INPUT_PATH = PROJECT_ROOT / "data" / "training" / "cot" / "cot_with_reasoning.jsonl"
CONFIG_PATH = PROJECT_ROOT / "output" / "p3_t04" / "cot_generation_config.json"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "cot"
FINAL_COT_PATH = OUTPUT_DIR / "cot_samples.jsonl"
CONVERSION_STATS_PATH = OUTPUT_DIR / "cot_conversion_stats.json"
AUDIT_SAMPLE_PATH = PROJECT_ROOT / "output" / "p3_t04" / "cot_audit_sample.jsonl"

# Randomized marker options (RA-DIT Appendix C)
# Why these specific markers:
# - Match RA-DIT paper's documented options
# - Include empty string to train on no-marker format
INST_START_OPTIONS = ["Q:", "Question:", ""]  # Empty = no marker
INST_END = "\n"  # Fixed: always newline
ANSWER_START_OPTIONS = ["A:", "Answer:"]

# Token limit for training
MAX_TOKENS = 2048
CHARS_PER_TOKEN_ESTIMATE = 1.3  # Conservative for Chinese

console = Console()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class RaDITCoTSample:
    """Final RA-DIT CoT training sample."""
    input: str
    output: str
    metadata: Dict[str, Any]


# ============================================================================
# Marker Randomization
# ============================================================================

def randomize_markers() -> Dict[str, str]:
    """Generate randomized format markers.
    
    Why randomization:
    - RA-DIT paper Appendix C recommends this
    - Prevents model from overfitting to specific tokens
    - Each sample gets a random combination
    
    Returns:
        Dict with marker keys and values
    """
    return {
        "inst_s": random.choice(INST_START_OPTIONS),
        "inst_e": INST_END,
        "answer_s": random.choice(ANSWER_START_OPTIONS),
    }


def format_radit_style(
    background: str,
    question: str,
    reasoning: str,
    answer: str,
    markers: Dict[str, str]
) -> Tuple[str, str]:
    """Format sample in RA-DIT style.
    
    RA-DIT format:
        Background: {retrieved passage}
        
        <inst_s> {question}
        {reasoning chain}
        <answer_s> {answer}
    
    Returns:
        Tuple of (input_text, output_text)
    """
    # Build input
    if markers["inst_s"]:
        input_text = f"Background: {background}\n\n{markers['inst_s']} {question}{markers['inst_e']}"
    else:
        input_text = f"Background: {background}\n\n{question}{markers['inst_e']}"
    
    # Build output
    output_text = f"{reasoning}\n{markers['answer_s']} {answer}"
    
    return input_text, output_text


def format_ancient_chinese_style(
    background: str,
    question: str,
    reasoning: str,
    answer: str
) -> Tuple[str, str]:
    """Format sample in project's ancient Chinese style.
    
    Why this format:
    - Consistent with existing training data
    - Uses Chinese markers for better model learning
    - Clear separation of reasoning and answer
    
    Format:
        Input: 【參考資料】\n{context}\n\n【問題】{question}
        Output: 【思考過程】\n{reasoning}\n\n【答案】{answer}
    
    Returns:
        Tuple of (input_text, output_text)
    """
    input_text = f"【參考資料】\n{background}\n\n【問題】{question}"
    output_text = f"【思考過程】\n{reasoning}\n\n【答案】{answer}"
    
    return input_text, output_text


# ============================================================================
# Token Estimation
# ============================================================================

def estimate_tokens(text: str) -> int:
    """Estimate token count for text.
    
    Why estimation:
    - Actual tokenization varies by model
    - Chinese characters typically ~1.3 tokens each
    - Conservative estimate to ensure compliance
    """
    return int(len(text) * CHARS_PER_TOKEN_ESTIMATE)


def check_token_limit(input_text: str, output_text: str) -> Tuple[bool, int]:
    """Check if sample exceeds token limit.
    
    Returns:
        Tuple of (is_within_limit, total_tokens)
    """
    total_text = input_text + output_text
    estimated_tokens = estimate_tokens(total_text)
    return estimated_tokens <= MAX_TOKENS, estimated_tokens


# ============================================================================
# Main Conversion
# ============================================================================

def load_cot_samples() -> List[Dict[str, Any]]:
    """Load CoT samples from Phase 2 output."""
    if not COT_INPUT_PATH.exists():
        console.print(f"[red]❌ CoT 檔案不存在: {COT_INPUT_PATH}[/red]")
        console.print("[yellow]請先執行 cot_generator.py[/yellow]")
        return []
    
    samples = []
    with open(COT_INPUT_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    
    return samples


def convert_to_final_format(
    samples: List[Dict[str, Any]],
    use_chinese_format: bool = True
) -> Tuple[List[RaDITCoTSample], Dict[str, Any]]:
    """Convert CoT samples to final training format.
    
    Args:
        samples: Raw CoT samples from generator
        use_chinese_format: Use 【】 markers (True) or RA-DIT English markers (False)
    
    Returns:
        Tuple of (converted_samples, stats)
    """
    converted: List[RaDITCoTSample] = []
    stats = {
        "total_input": len(samples),
        "successful": 0,
        "token_overflow": 0,
        "empty_reasoning": 0,
        "marker_distribution": {
            "inst_s": Counter(),
            "answer_s": Counter(),
        },
        "avg_input_length": 0,
        "avg_output_length": 0,
        "avg_reasoning_length": 0,
    }
    
    total_input_len = 0
    total_output_len = 0
    total_reasoning_len = 0
    
    console.print(Panel(
        "[bold cyan]Phase 3: 轉換為 RA-DIT 格式[/bold cyan]",
        border_style="cyan"
    ))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]轉換格式...", total=len(samples))
        
        for sample in samples:
            progress.update(task, advance=1)
            
            # Extract fields
            background = sample.get("context_used", "")
            question = sample.get("question", "")
            reasoning = sample.get("generated_reasoning", "")
            answer = sample.get("original_answer", "")
            
            # Skip empty reasoning
            if not reasoning or not reasoning.strip():
                stats["empty_reasoning"] += 1
                continue
            
            # Generate randomized markers
            markers = randomize_markers()
            stats["marker_distribution"]["inst_s"][markers["inst_s"] or "(empty)"] += 1
            stats["marker_distribution"]["answer_s"][markers["answer_s"]] += 1
            
            # Format based on preference
            if use_chinese_format:
                input_text, output_text = format_ancient_chinese_style(
                    background, question, reasoning, answer
                )
            else:
                input_text, output_text = format_radit_style(
                    background, question, reasoning, answer, markers
                )
            
            # Check token limit
            within_limit, token_count = check_token_limit(input_text, output_text)
            if not within_limit:
                stats["token_overflow"] += 1
                continue
            
            # Build metadata
            original_metadata = sample.get("metadata", {})
            metadata = {
                "type": "cot",
                "subtype": "retrieval_augmented_cot",
                "has_context": True,
                "reasoning_length": len(reasoning),
                "format": "chinese" if use_chinese_format else "radit",
                "markers_used": markers,
                "original_index": sample.get("original_index", -1),
                "generation_time_ms": sample.get("generation_time_ms", 0),
                **{k: v for k, v in original_metadata.items() if k not in ["type", "subtype"]}
            }
            
            converted_sample = RaDITCoTSample(
                input=input_text,
                output=output_text,
                metadata=metadata
            )
            converted.append(converted_sample)
            
            stats["successful"] += 1
            total_input_len += len(input_text)
            total_output_len += len(output_text)
            total_reasoning_len += len(reasoning)
    
    # Calculate averages
    if stats["successful"] > 0:
        stats["avg_input_length"] = total_input_len // stats["successful"]
        stats["avg_output_length"] = total_output_len // stats["successful"]
        stats["avg_reasoning_length"] = total_reasoning_len // stats["successful"]
    
    # Convert Counter to dict for JSON
    stats["marker_distribution"]["inst_s"] = dict(stats["marker_distribution"]["inst_s"])
    stats["marker_distribution"]["answer_s"] = dict(stats["marker_distribution"]["answer_s"])
    
    return converted, stats


def save_results(samples: List[RaDITCoTSample], stats: Dict[str, Any]):
    """Save converted samples and statistics."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save final samples
    with open(FINAL_COT_PATH, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
    
    console.print(f"[green]✅ 最終 CoT 資料已保存至: {FINAL_COT_PATH.relative_to(PROJECT_ROOT)}[/green]")
    
    # Save stats
    with open(CONVERSION_STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]✅ 轉換統計已保存至: {CONVERSION_STATS_PATH.relative_to(PROJECT_ROOT)}[/green]")
    
    # Save audit sample (random 50)
    if samples:
        audit_dir = AUDIT_SAMPLE_PATH.parent
        audit_dir.mkdir(parents=True, exist_ok=True)
        
        audit_samples = random.sample(samples, min(50, len(samples)))
        with open(AUDIT_SAMPLE_PATH, 'w', encoding='utf-8') as f:
            for sample in audit_samples:
                f.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
        
        console.print(f"[green]✅ 審核樣本已保存至: {AUDIT_SAMPLE_PATH.relative_to(PROJECT_ROOT)}[/green]")


def display_summary(stats: Dict[str, Any]):
    """Display conversion summary."""
    console.print("\n" + "=" * 50)
    console.print("[bold cyan]📊 轉換結果摘要[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("指標", style="dim")
    table.add_column("數值", style="green")
    
    table.add_row("輸入樣本數", f"{stats['total_input']:,}")
    table.add_row("成功轉換", f"[bold green]{stats['successful']:,}[/bold green]")
    table.add_row("Token 超限", f"{stats['token_overflow']}")
    table.add_row("空白推理", f"{stats['empty_reasoning']}")
    table.add_row("平均 Input 長度", f"{stats['avg_input_length']} 字")
    table.add_row("平均 Output 長度", f"{stats['avg_output_length']} 字")
    table.add_row("平均推理長度", f"{stats['avg_reasoning_length']} 字")
    
    console.print(table)
    
    # Marker distribution
    console.print("\n[bold]標記分佈:[/bold]")
    console.print("  inst_s:", dict(stats["marker_distribution"]["inst_s"]))
    console.print("  answer_s:", dict(stats["marker_distribution"]["answer_s"]))


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Main entry point."""
    try:
        # Load samples
        samples = load_cot_samples()
        
        if not samples:
            console.print("[red]❌ 未找到 CoT 樣本，請先執行 cot_generator.py[/red]")
            sys.exit(1)
        
        console.print(f"[dim]已載入 {len(samples):,} 筆 CoT 樣本[/dim]\n")
        
        # Convert
        converted, stats = convert_to_final_format(samples, use_chinese_format=True)
        
        if not converted:
            console.print("[red]❌ 未成功轉換任何樣本[/red]")
            sys.exit(1)
        
        # Save results
        save_results(converted, stats)
        
        # Display summary
        display_summary(stats)
        
        console.print("\n[bold green]🎉 Phase 3 完成！[/bold green]")
        console.print("[dim]下一步: 執行 validate_cot_format.py 驗證資料[/dim]")
        
        # Offer to continue
        if Confirm.ask("\n是否立即執行格式驗證？", default=True):
            console.print("[cyan]執行 validate_cot_format.py...[/cyan]")
        
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
