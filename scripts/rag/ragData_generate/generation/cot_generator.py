"""Generate Chain-of-Thought (CoT) reasoning using LLM.

This script generates reasoning chains for filtered CoT candidates:
1. Load candidate samples from Phase 1
2. Call kimi-k2 API via LiteLLM to generate reasoning chains
3. Handle retries, errors, and rate limiting
4. Output samples with generated reasoning

Why LLM-based CoT generation:
- Manual CoT annotation is time-consuming
- LLM can generate consistent, structured reasoning
- kimi-k2 has strong Chinese language understanding

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S7 Phase 2
"""

import json
import os
import sys
import time
import random
import warnings
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

# Suppress Pydantic warnings from LiteLLM
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.prompt import Confirm

# Try to import optional dependencies
try:
    import litellm
    # Suppress LiteLLM debug messages
    litellm.suppress_debug_info = True
    os.environ["LITELLM_LOG"] = "ERROR"
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Input paths
CANDIDATES_PATH = PROJECT_ROOT / "data" / "training" / "cot" / "cot_candidates.jsonl"
CONFIG_PATH = PROJECT_ROOT / "output" / "p3_t04" / "cot_generation_config.json"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "cot"
COT_OUTPUT_PATH = OUTPUT_DIR / "cot_with_reasoning.jsonl"
GENERATION_STATS_PATH = OUTPUT_DIR / "cot_generation_stats.json"
ERROR_LOG_PATH = OUTPUT_DIR / "cot_generation_errors.jsonl"

# Test mode flag (can be overridden by config file)
# Set to True for standalone testing, False for pipeline execution
TEST_MODE = True

# Default generation parameters
DEFAULT_CONFIG = {
    "target_count": 1500,
    "reasoning_length_min": 80,
    "reasoning_length_max": 120,
    "api_model": "openrouter/moonshotai/kimi-k2-0905",
    "retrieval_k": 3,
    "max_context_length": 500,
    "max_retries": 3,
    "timeout_seconds": 30,
}

# Rate limiting
# Why rate limiting:
# - Avoid API throttling
# - Ensure stable generation process
REQUESTS_PER_MINUTE = 50
REQUEST_DELAY_SECONDS = 60.0 / REQUESTS_PER_MINUTE  # ~1.2 seconds

console = Console()


# ============================================================================
# Prompt Templates
# ============================================================================

# Why this prompt design:
# - Clear role setting as ancient Chinese literature expert
# - Structured output format prevents parsing issues
# - Step-by-step reasoning requirement ensures CoT quality
# - Citation requirement ensures relevance to background
GENERATION_PROMPT_TEMPLATE = """你是一位專精於中國古典文學的中文系教授。請根據以下參考資料和問題，生成詳細的推理過程。

【參考資料】
{context}

【問題】
{question}

【最終答案】
{answer}

請生成推理步驟，說明如何從參考資料得出上述答案。

格式要求：
1. 分 3-5 個推理步驟
2. 每步需引用參考資料的具體內容
3. 推理邏輯需連貫，符合古文分析
4. 總長度 {length_min}-{length_max} 字

請直接輸出推理步驟，不需要其他說明："""

# Fallback prompt for when context is missing
FALLBACK_PROMPT_TEMPLATE = """你是一位專精於中國古典文學的中文系教授。請為以下問答生成推理過程。

【問題】
{question}

【答案】
{answer}

請生成 3-5 個推理步驟，說明如何得出此答案。
總長度 {length_min}-{length_max} 字。

請直接輸出推理步驟："""


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class CoTResult:
    """Result of CoT generation for a single sample."""
    original_index: int
    question: str
    original_answer: str
    context_used: str
    generated_reasoning: str
    reasoning_length: int
    generation_time_ms: int
    success: bool
    error_message: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = None


# ============================================================================
# Helper Functions
# ============================================================================

def load_config() -> Dict[str, Any]:
    """Load generation configuration.
    
    Priority: Environment variable > Config file > Defaults
    """
    # Check for config path from environment (set by pipeline)
    config_from_env = os.getenv("COT_CONFIG_PATH")
    
    if config_from_env and Path(config_from_env).exists():
        with open(config_from_env, 'r', encoding='utf-8') as f:
            config = json.load(f)
            console.print(f"[dim]已從 pipeline 配置載入參數[/dim]")
            return {**DEFAULT_CONFIG, **config}
    
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return {**DEFAULT_CONFIG, **config}
    
    # Use TEST_MODE default if no config
    console.print("[yellow]⚠️ 配置檔案不存在，使用預設值[/yellow]")
    if TEST_MODE:
        console.print("[yellow]🧪 獨立測試模式：目標 3 筆[/yellow]")
        return {**DEFAULT_CONFIG, "target_count": 3}
    return DEFAULT_CONFIG


def load_candidates() -> List[Dict[str, Any]]:
    """Load candidate samples from Phase 1 output."""
    if not CANDIDATES_PATH.exists():
        console.print(f"[red]❌ 候選檔案不存在: {CANDIDATES_PATH}[/red]")
        console.print("[yellow]請先執行 filter_cot_candidates.py[/yellow]")
        return []
    
    candidates = []
    with open(CANDIDATES_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    
    return candidates


def prepare_context(candidate: Dict[str, Any], max_length: int = 500) -> str:
    """Prepare context from candidate for prompt.
    
    Why combine contexts:
    - Original context may be relevant
    - Retrieved contexts add diversity
    - Truncation ensures token limit compliance
    """
    contexts = []
    
    # Use original context if available
    if candidate.get("original_context"):
        contexts.append(candidate["original_context"])
    
    # Add retrieved contexts
    for ctx in candidate.get("retrieved_contexts", []):
        if ctx and ctx not in contexts:
            contexts.append(ctx)
    
    # Combine and truncate
    combined = "\n\n".join(contexts[:3])  # Max 3 contexts
    if len(combined) > max_length:
        combined = combined[:max_length] + "..."
    
    return combined


def generate_cot_with_llm(
    question: str,
    answer: str,
    context: str,
    config: Dict[str, Any],
    api_key: str
) -> Tuple[Optional[str], Optional[str]]:
    """Generate Chain-of-Thought reasoning using LLM.
    
    Returns:
        Tuple of (reasoning_text, error_message)
    """
    if not LITELLM_AVAILABLE:
        return None, "litellm not installed"
    
    # Prepare prompt
    if context:
        prompt = GENERATION_PROMPT_TEMPLATE.format(
            context=context,
            question=question,
            answer=answer,
            length_min=config["reasoning_length_min"],
            length_max=config["reasoning_length_max"]
        )
    else:
        prompt = FALLBACK_PROMPT_TEMPLATE.format(
            question=question,
            answer=answer,
            length_min=config["reasoning_length_min"],
            length_max=config["reasoning_length_max"]
        )
    
    try:
        response = litellm.completion(
            model=config["api_model"],
            messages=[{
                "role": "user",
                "content": prompt
            }],
            api_key=api_key,
            max_tokens=400,
            temperature=0.7,
            timeout=config["timeout_seconds"]
        )
        
        reasoning = response.choices[0].message.content.strip()
        return reasoning, None
        
    except Exception as e:
        return None, str(e)


async def generate_cot_with_llm_async(
    question: str,
    answer: str,
    context: str,
    config: Dict[str, Any],
    api_key: str,
    semaphore: asyncio.Semaphore
) -> Tuple[Optional[str], Optional[str]]:
    """Async version of CoT generation with concurrency control.
    
    Why async:
    - Enable concurrent API requests
    - 5-10x speed improvement
    - Semaphore controls max concurrent requests
    
    Returns:
        Tuple of (reasoning_text, error_message)
    """
    if not LITELLM_AVAILABLE:
        return None, "litellm not installed"
    
    # Acquire semaphore (limit concurrency)
    async with semaphore:
        # Prepare prompt (same as sync version)
        if context:
            prompt = GENERATION_PROMPT_TEMPLATE.format(
                context=context,
                question=question,
                answer=answer,
                length_min=config["reasoning_length_min"],
                length_max=config["reasoning_length_max"]
            )
        else:
            prompt = FALLBACK_PROMPT_TEMPLATE.format(
                question=question,
                answer=answer,
                length_min=config["reasoning_length_min"],
                length_max=config["reasoning_length_max"]
            )
        
        try:
            # Use acompletion for async call
            response = await litellm.acompletion(
                model=config["api_model"],
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                api_key=api_key,
                max_tokens=400,
                temperature=0.7,
                timeout=config["timeout_seconds"]
            )
            
            reasoning = response.choices[0].message.content.strip()
            return reasoning, None
            
        except Exception as e:
            return None, str(e)


def validate_reasoning(reasoning: str, config: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate generated reasoning quality.
    
    Why validation:
    - Ensure minimum quality standards
    - Filter out API errors or garbage output
    
    Returns:
        Tuple of (is_valid, warning_message)
    """
    if not reasoning:
        return False, "empty_reasoning"
    
    min_len = config["reasoning_length_min"]
    max_len = config["reasoning_length_max"]
    
    if len(reasoning) < min_len * 0.5:  # Allow some tolerance
        return True, "short_reasoning"
    
    if len(reasoning) > max_len * 2:  # Too long
        return True, "long_reasoning"
    
    # Check for common error patterns
    error_patterns = [
        "抱歉", "無法", "我不能", "作為AI",
        "I cannot", "I'm sorry", "As an AI"
    ]
    
    for pattern in error_patterns:
        if pattern in reasoning:
            return False, "refusal_detected"
    
    return True, ""


# ============================================================================
# Main Generation Loop
# ============================================================================

def generate_cot_samples(
    candidates: List[Dict[str, Any]],
    config: Dict[str, Any],
    target_count: int
) -> Tuple[List[CoTResult], Dict[str, Any]]:
    """Generate CoT reasoning for candidate samples.
    
    Args:
        candidates: List of candidate dictionaries
        config: Generation configuration
        target_count: Target number of successful generations
    
    Returns:
        Tuple of (results, stats)
    """
    # Check API key (from .env or environment)
    if DOTENV_AVAILABLE:
        console.print("[dim]✅ 已從 .env 載入環境變數[/dim]")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        console.print("[red]❌ OPENROUTER_API_KEY 環境變數未設定[/red]")
        console.print("[yellow]請確認 .env 檔案包含: OPENROUTER_API_KEY=your_key[/yellow]")
        return [], {"error": "no_api_key"}
    
    results: List[CoTResult] = []
    stats = {
        "total_candidates": len(candidates),
        "target_count": target_count,
        "success_count": 0,
        "warning_count": 0,
        "failure_count": 0,
        "retry_count": 0,
        "warning_types": {},
        "error_types": {},
        "avg_reasoning_length": 0,
        "avg_generation_time_ms": 0,
        "start_time": datetime.now().isoformat(),
    }
    
    total_length = 0
    total_time = 0
    
    mode_text = "[yellow]🧪 測試模式[/yellow]" if TEST_MODE else "[green]📦 生產模式[/green]"
    console.print(Panel(
        f"[bold cyan]Phase 2: 生成 CoT 推理鏈[/bold cyan]\n"
        f"模式: {mode_text}\n"
        f"目標數量: {target_count} 筆\n"
        f"候選數量: {len(candidates)} 筆",
        border_style="cyan"
    ))
    
    # Shuffle candidates for diversity
    random.shuffle(candidates)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task(
            f"[cyan]生成 CoT (已成功: 0/{target_count})...",
            total=min(len(candidates), target_count * 2)
        )
        
        for i, candidate in enumerate(candidates):
            # Check if we've reached target
            if stats["success_count"] >= target_count:
                console.print(f"\n[green]✅ 達到目標數量: {target_count}[/green]")
                break
            
            progress.update(task, advance=1, description=
                f"[cyan]生成 CoT (已成功: {stats['success_count']}/{target_count}, "
                f"失敗: {stats['failure_count']})..."
            )
            
            # Rate limiting
            time.sleep(REQUEST_DELAY_SECONDS)
            
            # Prepare inputs
            question = candidate.get("question", "")
            answer = candidate.get("original_answer", "")
            context = prepare_context(candidate, config["max_context_length"])
            
            # Generate with retries
            reasoning = None
            error_msg = None
            retries = 0
            start_time = time.time()
            
            for attempt in range(config["max_retries"]):
                reasoning, error_msg = generate_cot_with_llm(
                    question, answer, context, config, api_key
                )
                
                if reasoning:
                    break
                
                retries += 1
                stats["retry_count"] += 1
                time.sleep(1)  # Brief pause before retry
            
            generation_time = int((time.time() - start_time) * 1000)
            
            # Validate result
            if reasoning:
                is_valid, warning = validate_reasoning(reasoning, config)
                
                if is_valid:
                    result = CoTResult(
                        original_index=candidate.get("original_index", i),
                        question=question,
                        original_answer=answer,
                        context_used=context,
                        generated_reasoning=reasoning,
                        reasoning_length=len(reasoning),
                        generation_time_ms=generation_time,
                        success=True,
                        retry_count=retries,
                        metadata=candidate.get("metadata", {})
                    )
                    results.append(result)
                    stats["success_count"] += 1
                    total_length += len(reasoning)
                    total_time += generation_time
                    
                    if warning:
                        stats["warning_count"] += 1
                        stats["warning_types"][warning] = stats["warning_types"].get(warning, 0) + 1
                else:
                    stats["failure_count"] += 1
                    stats["error_types"][warning] = stats["error_types"].get(warning, 0) + 1
            else:
                stats["failure_count"] += 1
                error_type = error_msg[:50] if error_msg else "unknown_error"
                stats["error_types"][error_type] = stats["error_types"].get(error_type, 0) + 1
            
            # Save checkpoint after each successful generation
            # Why every 1 sample:
            # - Prevent data loss from crashes or interruptions
            # - CoT generation is slow (~1.2s per sample)
            # - Disk write is fast compared to API call time
            if stats["success_count"] > 0:
                save_checkpoint(results, stats)
    
    # Calculate averages
    if stats["success_count"] > 0:
        stats["avg_reasoning_length"] = total_length // stats["success_count"]
        stats["avg_generation_time_ms"] = total_time // stats["success_count"]
    
    stats["end_time"] = datetime.now().isoformat()
    
    return results, stats


def save_checkpoint(results: List[CoTResult], stats: Dict[str, Any]):
    """Save checkpoint during generation.
    
    Why checkpoints:
    - Long-running process
    - Recover from crashes
    """
    checkpoint_path = OUTPUT_DIR / "cot_checkpoint.jsonl"
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def save_results(results: List[CoTResult], stats: Dict[str, Any]):
    """Save final results and statistics."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save CoT samples
    with open(COT_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
    
    console.print(f"[green]✅ CoT 資料已保存至: {COT_OUTPUT_PATH.relative_to(PROJECT_ROOT)}[/green]")
    
    # Save stats
    with open(GENERATION_STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]✅ 統計資料已保存至: {GENERATION_STATS_PATH.relative_to(PROJECT_ROOT)}[/green]")


async def generate_cot_samples_async(
    candidates: List[Dict[str, Any]],
    config: Dict[str, Any],
    target_count: int,
    max_concurrent: int = 6
) -> Tuple[List[CoTResult], Dict[str, Any]]:
    """Async concurrent CoT generation for 5-10x speedup."""
    if DOTENV_AVAILABLE:
        console.print("[dim]✅ 已從 .env 載入環境變數[/dim]")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        console.print("[red]❌ OPENROUTER_API_KEY 環境變數未設定[/red]")
        return [], {"error": "no_api_key"}
    
    results = []
    results_lock = asyncio.Lock()
    stats = {
        "total_candidates": len(candidates),
        "target_count": target_count,
        "success_count": 0,
        "warning_count": 0,
        "failure_count": 0,
        "retry_count": 0,
        "warning_types": {},
        "error_types": {},
        "avg_reasoning_length": 0,
        "avg_generation_time_ms": 0,
        "start_time": datetime.now().isoformat(),
    }
    stats_lock = asyncio.Lock()
    total_length = [0]
    total_time = [0]
    
    is_test = config.get("is_test_mode", False)
    mode_text = "[yellow]🧪 測試模式[/yellow]" if is_test else "[green]📦 生產模式[/green]"
    console.print(Panel(
        f"[bold cyan]Phase 2: 生成 CoT 推理鏈 (並發模式)[/bold cyan]\n"
        f"模式: {mode_text}\n"
        f"目標數量: {target_count} 筆\n"
        f"候選數量: {len(candidates)} 筆\n"
        f"並發數: [bold]{max_concurrent}[/bold] 個同時請求",
        border_style="cyan"
    ))
    
    random.shuffle(candidates)
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_one(i, candidate):
        question = candidate.get("question", "")
        answer = candidate.get("original_answer", "")
        context = prepare_context(candidate, config["max_context_length"])
        
        reasoning, error_msg, retries = None, None, 0
        start_time = time.time()
        
        for attempt in range(config["max_retries"]):
            reasoning, error_msg = await generate_cot_with_llm_async(
                question, answer, context, config, api_key, semaphore
            )
            if reasoning:
                break
            retries += 1
            async with stats_lock:
                stats["retry_count"] += 1
            await asyncio.sleep(0.5)
        
        generation_time = int((time.time() - start_time) * 1000)
        
        if reasoning:
            is_valid, warning = validate_reasoning(reasoning, config)
            if is_valid:
                result = CoTResult(
                    original_index=candidate.get("original_index", i),
                    question=question,
                    original_answer=answer,
                    context_used=context,
                    generated_reasoning=reasoning,
                    reasoning_length=len(reasoning),
                    generation_time_ms=generation_time,
                    success=True,
                    retry_count=retries,
                    metadata=candidate.get("metadata", {})
                )
                async with results_lock:
                    results.append(result)
                async with stats_lock:
                    stats["success_count"] += 1
                    total_length[0] += len(reasoning)
                    total_time[0] += generation_time
                    if warning:
                        stats["warning_count"] += 1
                        stats["warning_types"][warning] = stats["warning_types"].get(warning, 0) + 1
            else:
                async with stats_lock:
                    stats["failure_count"] += 1
                    stats["error_types"][warning] = stats["error_types"].get(warning, 0) + 1
        else:
            async with stats_lock:
                stats["failure_count"] += 1
                if error_msg:
                    stats["error_types"][error_msg[:50]] = stats["error_types"].get(error_msg[:50], 0) + 1
    
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), TimeRemainingColumn(), console=console
    ) as progress:
        task = progress.add_task(
            f"[cyan]生成 CoT (已成功: 0/{target_count})...",
            total=min(len(candidates), target_count * 2)
        )
        
        batch_size = max_concurrent
        for batch_start in range(0, len(candidates), batch_size):
            if stats["success_count"] >= target_count:
                console.print(f"\n[green]✅ 達到目標數量: {target_count}[/green]")
                break
            
            batch_end = min(batch_start + batch_size, len(candidates))
            batch = candidates[batch_start:batch_end]
            tasks = [process_one(batch_start + j, c) for j, c in enumerate(batch)]
            await asyncio.gather(*tasks)
            
            progress.update(task, advance=len(batch), description=
                f"[cyan]生成 CoT (已成功: {stats['success_count']}/{target_count}, "
                f"失敗: {stats['failure_count']})..."
            )
            
            if stats["success_count"] > 0 and stats["success_count"] % 50 == 0:
                save_checkpoint(results, stats)
    
    if stats["success_count"] > 0:
        stats["avg_reasoning_length"] = total_length[0] // stats["success_count"]
        stats["avg_generation_time_ms"] = total_time[0] // stats["success_count"]
    stats["end_time"] = datetime.now().isoformat()
    
    return results, stats


def display_summary(stats: Dict[str, Any]):
    """Display generation summary."""
    console.print("\n" + "=" * 50)
    console.print("[bold cyan]📊 生成結果摘要[/bold cyan]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("指標", style="dim")
    table.add_column("數值", style="green")
    
    table.add_row("候選總數", f"{stats['total_candidates']:,}")
    table.add_row("目標數量", f"{stats['target_count']:,}")
    table.add_row("成功生成", f"[bold green]{stats['success_count']:,}[/bold green]")
    table.add_row("生成警告", f"[yellow]{stats['warning_count']}[/yellow]" if stats['warning_count'] > 0 else "0")
    table.add_row("生成失敗", f"[red]{stats['failure_count']}[/red]" if stats['failure_count'] > 0 else "0")
    table.add_row("總重試次數", str(stats['retry_count']))
    table.add_row("平均推理長度", f"{stats['avg_reasoning_length']} 字")
    table.add_row("平均生成時間", f"{stats['avg_generation_time_ms']} ms")
    
    console.print(table)
    
    # Success rate
    total_attempts = stats["success_count"] + stats["failure_count"]
    if total_attempts > 0:
        success_rate = stats["success_count"] / total_attempts * 100
        console.print(f"\n[bold]成功率: {success_rate:.1f}%[/bold]")
    
    # Warning types
    if stats.get("warning_types"):
        console.print("\n[bold]警告類型分佈:[/bold]")
        for wtype, count in stats["warning_types"].items():
            console.print(f"  {wtype}: {count}")
    
    # Error types (top 5)
    if stats.get("error_types"):
        console.print("\n[bold]錯誤類型 (Top 5):[/bold]")
        sorted_errors = sorted(stats["error_types"].items(), key=lambda x: x[1], reverse=True)
        for etype, count in sorted_errors[:5]:
            console.print(f"  {etype[:50]}: {count}")


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Main entry point."""
    try:
        # Check litellm availability
        if not LITELLM_AVAILABLE:
            console.print("[red]❌ litellm 未安裝[/red]")
            console.print("[yellow]請執行: pip install litellm[/yellow]")
            sys.exit(1)
        
        # Load config and candidates
        config = load_config()
        candidates = load_candidates()
        
        if not candidates:
            console.print("[red]❌ 未找到候選樣本，請先執行 filter_cot_candidates.py[/red]")
            sys.exit(1)
        
        console.print(f"[dim]已載入 {len(candidates):,} 筆候選樣本[/dim]")
        
        target_count = config.get("target_count", 1500)
        max_concurrent = config.get("max_concurrent", 6)  # Default 6 concurrent requests
        
        # Auto-proceed without confirmation for pipeline automation
        console.print(f"[cyan]開始生成 {target_count} 筆 CoT 資料（並發數：{max_concurrent}）...[/cyan]\n")
        
        # Generate CoT samples using async concurrent version
        results, stats = asyncio.run(
            generate_cot_samples_async(candidates, config, target_count, max_concurrent)
        )
        
        if not results:
            console.print("[red]❌ 未生成任何 CoT 樣本[/red]")
            sys.exit(1)
        
        # Save results
        save_results(results, stats)
        
        # Display summary
        display_summary(stats)
        
        console.print("\n[bold green]🎉 Phase 2 完成！[/bold green]")
        console.print("[dim]下一步: 執行 convert_to_radit_cot.py 轉換格式[/dim]")
        
        # Offer to continue
        if Confirm.ask("\n是否立即執行格式轉換？", default=True):
            console.print("[cyan]執行 convert_to_radit_cot.py...[/cyan]")
            # Note: In production, would call subprocess or import
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已取消[/yellow]")
        # Save any results generated so far
        console.print("[dim]正在保存已生成的資料...[/dim]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]❌ 發生錯誤: {e}[/bold red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
