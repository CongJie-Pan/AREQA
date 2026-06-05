"""Filter and select candidates for CoT (Chain-of-Thought) generation.

This script filters RAG samples to identify questions suitable for CoT generation:
1. Filter questions containing reasoning keywords (為什麼, 如何, 分析, etc.)
2. Exclude simple factual questions (誰, 什麼, 哪裡, etc.)
3. Retrieve background context using FAISS (k=3)
4. Output candidate samples ready for CoT generation

Why this filtering:
- CoT is most valuable for reasoning-type questions
- Simple factual recall doesn't benefit from chain-of-thought
- Pre-filtering reduces LLM API calls and costs

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S7 Phase 1
"""

import json
import os
import random
import sys
import re
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
RAG_DATASET_PATH = PROJECT_ROOT / "data" / "training" / "completeSet" / "v2" / "complete_training_dataset.jsonl"
FAISS_MAPPING_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json"
CONFIG_PATH = PROJECT_ROOT / "output" / "p3_t04" / "cot_generation_config.json"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "cot"
CANDIDATES_OUTPUT_PATH = OUTPUT_DIR / "cot_candidates.jsonl"
STATS_OUTPUT_PATH = OUTPUT_DIR / "candidate_filter_stats.json"

# Filtering keywords
# Why these keywords:
# - Reasoning questions require explanation (為什麼, 如何)
# - Analysis questions need structured thinking (分析, 比較, 評價)
# - These benefit most from chain-of-thought generation
REASONING_KEYWORDS = [
    "為什麼", "為何", "如何", "怎麼", "怎樣",
    "分析", "比較", "評價", "評論", "論述",
    "推論", "推測", "推斷", "解釋", "說明",
    "意義", "象徵", "寓意", "隱喻", "暗示",
    "關係", "影響", "原因", "目的", "意圖",
]

# Why filter out factual questions:
# - Simple factual recall: "誰是林黛玉?" doesn't need CoT
# - CoT adds unnecessary complexity for these
FACTUAL_KEYWORDS = [
    "誰是", "誰的", "什麼是", "什麼時候", "何時",
    "哪裡", "哪一", "幾個", "多少", "是否",
]

# Minimum question length to filter out too simple questions
MIN_QUESTION_LENGTH = 10

console = Console()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class CotCandidate:
    """A candidate sample for CoT generation."""
    original_index: int
    question: str
    original_answer: str
    original_context: Optional[str]
    retrieved_contexts: List[str]  # k=3 retrieved passages
    reasoning_keywords_found: List[str]
    source_type: str  # rag / pure_qa / etc.
    metadata: Dict[str, Any]


# ============================================================================
# Helper Functions
# ============================================================================

def load_config() -> Dict[str, Any]:
    """Load generation configuration from preflight checker output.
    
    Why: Use consistent parameters across all scripts
    """
    # Check for config path from environment (set by pipeline)
    config_from_env = os.getenv("COT_CONFIG_PATH")
    
    if config_from_env and Path(config_from_env).exists():
        with open(config_from_env, 'r', encoding='utf-8') as f:
            config = json.load(f)
            console.print(f"[dim]已從 pipeline 配置載入參數[/dim]")
            return config
    
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        console.print("[yellow]⚠️ 配置檔案不存在，使用預設值[/yellow]")
        return {"target_count": 1500, "retrieval_k": 3, "max_context_length": 500, "is_test_mode": False}


def extract_question_from_input(input_text: str) -> str:
    """Extract question from RAG format input.
    
    Input format: 【參考資料】\n{context}\n\n【問題】{question}
    """
    if "【問題】" in input_text:
        return input_text.split("【問題】")[-1].strip()
    return input_text.strip()


def extract_context_from_input(input_text: str) -> Optional[str]:
    """Extract context from RAG format input."""
    if "【參考資料】" in input_text and "【問題】" in input_text:
        start = input_text.find("【參考資料】") + len("【參考資料】")
        end = input_text.find("【問題】")
        return input_text[start:end].strip()
    return None


def is_reasoning_question(question: str) -> Tuple[bool, List[str]]:
    """Check if question requires reasoning (not just factual recall).
    
    Why this classification:
    - CoT generation is expensive (LLM API calls)
    - Only reasoning questions benefit from chain-of-thought
    - Filter out simple factual questions to reduce costs
    
    Returns:
        Tuple of (is_reasoning: bool, keywords_found: list)
    """
    # First, check if it's explicitly a factual question
    for keyword in FACTUAL_KEYWORDS:
        if keyword in question:
            return False, []
    
    # Then, check for reasoning keywords
    keywords_found = []
    for keyword in REASONING_KEYWORDS:
        if keyword in question:
            keywords_found.append(keyword)
    
    # Must have at least one reasoning keyword
    if keywords_found:
        return True, keywords_found
    
    # If no keywords but question is long and complex, might still be reasoning
    # Use question length as a secondary heuristic
    if len(question) > 50 and any(char in question for char in ["？", "?", "。"]):
        return True, ["(complex_structure)"]
    
    return False, []


def load_chunk_mapping() -> Dict[str, Any]:
    """Load FAISS chunk mapping for context retrieval.
    
    Why: Enable retrieval of additional context for CoT
    """
    if FAISS_MAPPING_PATH.exists():
        with open(FAISS_MAPPING_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def simple_retrieve_contexts(question: str, chunk_mapping: Dict, k: int = 3) -> List[str]:
    """Simple keyword-based retrieval fallback when FAISS is not available.
    
    Why this fallback:
    - FAISS may not be installed
    - Provides basic context retrieval for CoT generation
    - Uses keyword matching as simple similarity proxy
    
    Note: For production, use proper FAISS vector retrieval
    """
    if not chunk_mapping:
        return []
    
    # Extract keywords from question
    question_words = set(re.findall(r'[\u4e00-\u9fff]+', question))
    
    # Score chunks by keyword overlap
    scored_chunks = []
    chunks = chunk_mapping if isinstance(chunk_mapping, list) else chunk_mapping.get("chunks", [])
    
    for chunk in chunks[:1000]:  # Limit search for performance
        if isinstance(chunk, dict):
            content = chunk.get("content", chunk.get("text", ""))
        else:
            content = str(chunk)
        
        chunk_words = set(re.findall(r'[\u4e00-\u9fff]+', content))
        overlap = len(question_words & chunk_words)
        
        if overlap > 0:
            scored_chunks.append((overlap, content[:500]))  # Limit length
    
    # Return top-k
    scored_chunks.sort(reverse=True)
    return [chunk for _, chunk in scored_chunks[:k]]


# ============================================================================
# Main Processing
# ============================================================================

def filter_cot_candidates(
    target_count: int = 2500,
    retrieval_k: int = 3,
    max_context_length: int = 500,
    is_test_mode: bool = False
) -> List[CotCandidate]:
    """Filter RAG samples to select CoT candidates.
    
    Why target 2500:
    - Generation will have some failures (~40%)
    - Need buffer to reach 1500 successful samples
    
    Args:
        target_count: Target number of candidates to select
        retrieval_k: Number of contexts to retrieve
        max_context_length: Maximum context length in characters
        is_test_mode: Whether running in test mode
    
    Returns:
        List of CotCandidate objects
    """
    console.print(Panel(
        "[bold cyan]Phase 1: 篩選 CoT 候選問題[/bold cyan]",
        border_style="cyan"
    ))
    
    candidates: List[CotCandidate] = []
    stats = {
        "total_loaded": 0,
        "reasoning_questions": 0,
        "factual_questions": 0,
        "too_short": 0,
        "selected": 0,
        "keyword_distribution": Counter(),
        "source_distribution": Counter(),
    }
    
    # Load chunk mapping for retrieval
    console.print("\n[cyan]載入 FAISS chunk mapping...[/cyan]")
    chunk_mapping = load_chunk_mapping()
    console.print(f"[dim]已載入 {len(chunk_mapping) if isinstance(chunk_mapping, list) else 'mapping'} chunks[/dim]\n")
    
    # Load and filter RAG samples
    console.print("[cyan]載入並篩選 RAG 資料...[/cyan]")
    
    all_samples = []
    with open(RAG_DATASET_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                sample = json.loads(line)
                all_samples.append(sample)
            except json.JSONDecodeError:
                continue
    
    stats["total_loaded"] = len(all_samples)
    console.print(f"[dim]載入 {stats['total_loaded']:,} 筆樣本[/dim]\n")
    
    # Filter for reasoning questions
    reasoning_samples = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]篩選推理性問題...", total=len(all_samples))
        
        for idx, sample in enumerate(all_samples):
            progress.update(task, advance=1)
            
            input_text = sample.get("input", "")
            output_text = sample.get("output", "")
            metadata = sample.get("metadata", {})
            
            # Extract question
            question = extract_question_from_input(input_text)
            
            # Check minimum length
            if len(question) < MIN_QUESTION_LENGTH:
                stats["too_short"] += 1
                continue
            
            # Check if reasoning question
            is_reasoning, keywords_found = is_reasoning_question(question)
            
            if is_reasoning:
                stats["reasoning_questions"] += 1
                for kw in keywords_found:
                    stats["keyword_distribution"][kw] += 1
                
                # Extract original context if present
                original_context = extract_context_from_input(input_text)
                
                # Get source type
                source_type = metadata.get("type", "unknown")
                stats["source_distribution"][source_type] += 1
                
                reasoning_samples.append({
                    "idx": idx,
                    "question": question,
                    "answer": output_text,
                    "context": original_context,
                    "keywords": keywords_found,
                    "source_type": source_type,
                    "metadata": metadata,
                })
            else:
                stats["factual_questions"] += 1
    
    console.print(f"\n[green]✅ 發現 {stats['reasoning_questions']:,} 筆推理性問題[/green]")
    console.print(f"[dim]過濾掉 {stats['factual_questions']:,} 筆事實性問題, {stats['too_short']} 筆過短問題[/dim]\n")
    
    # Random sample to target count if we have more
    if len(reasoning_samples) > target_count:
        console.print(f"[cyan]隨機抽樣 {target_count:,} 筆...[/cyan]")
        random.shuffle(reasoning_samples)
        reasoning_samples = reasoning_samples[:target_count]
    
    # In test mode, limit to 10 samples max
    if is_test_mode and len(reasoning_samples) > 10:
        console.print(f"[yellow]🧪 測試模式：限制為 10 筆候選[/yellow]")
        reasoning_samples = reasoning_samples[:10]
    
    # Retrieve additional contexts
    console.print("[cyan]檢索背景資料...[/cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]檢索 k=3 背景...", total=len(reasoning_samples))
        
        for sample in reasoning_samples:
            progress.update(task, advance=1)
            
            # Retrieve contexts
            retrieved = simple_retrieve_contexts(
                sample["question"],
                chunk_mapping,
                k=retrieval_k
            )
            
            # Truncate to max length
            retrieved = [ctx[:max_context_length] for ctx in retrieved]
            
            candidate = CotCandidate(
                original_index=sample["idx"],
                question=sample["question"],
                original_answer=sample["answer"],
                original_context=sample["context"],
                retrieved_contexts=retrieved,
                reasoning_keywords_found=sample["keywords"],
                source_type=sample["source_type"],
                metadata=sample["metadata"],
            )
            candidates.append(candidate)
    
    stats["selected"] = len(candidates)
    
    return candidates, stats


def save_candidates(candidates: List[CotCandidate], stats: Dict[str, Any]):
    """Save filtered candidates and statistics to files."""
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save candidates as JSONL
    with open(CANDIDATES_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        for candidate in candidates:
            f.write(json.dumps(asdict(candidate), ensure_ascii=False) + "\n")
    
    console.print(f"[green]✅ 候選資料已保存至: {CANDIDATES_OUTPUT_PATH.relative_to(PROJECT_ROOT)}[/green]")
    
    # Save stats
    # Convert Counter to dict for JSON serialization
    stats["keyword_distribution"] = dict(stats["keyword_distribution"])
    stats["source_distribution"] = dict(stats["source_distribution"])
    
    with open(STATS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]✅ 統計資料已保存至: {STATS_OUTPUT_PATH.relative_to(PROJECT_ROOT)}[/green]")


def display_summary(candidates: List[CotCandidate], stats: Dict[str, Any]):
    """Display summary statistics."""
    
    console.print("\n" + "=" * 50)
    console.print("[bold cyan]📊 篩選結果摘要[/bold cyan]\n")
    
    # Main stats table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("指標", style="dim")
    table.add_column("數值", style="green")
    
    table.add_row("載入總筆數", f"{stats['total_loaded']:,}")
    table.add_row("推理性問題", f"{stats['reasoning_questions']:,}")
    table.add_row("事實性問題 (過濾)", f"{stats['factual_questions']:,}")
    table.add_row("問題過短 (過濾)", str(stats['too_short']))
    table.add_row("最終選取", f"[bold]{stats['selected']:,}[/bold]")
    
    console.print(table)
    
    # Keyword distribution (top 10)
    if stats.get("keyword_distribution"):
        console.print("\n[bold]Top 10 推理關鍵詞:[/bold]")
        kw_dist = stats["keyword_distribution"]
        if isinstance(kw_dist, Counter):
            top_keywords = kw_dist.most_common(10)
        else:
            top_keywords = sorted(kw_dist.items(), key=lambda x: x[1], reverse=True)[:10]
        
        for kw, count in top_keywords:
            console.print(f"  {kw}: {count}")
    
    # Source distribution
    if stats.get("source_distribution"):
        console.print("\n[bold]來源類型分佈:[/bold]")
        for source, count in stats["source_distribution"].items():
            console.print(f"  {source}: {count}")
    
    # Sample preview
    if candidates:
        console.print("\n[bold]樣本預覽 (隨機3筆):[/bold]")
        previews = random.sample(candidates, min(3, len(candidates)))
        for i, c in enumerate(previews, 1):
            console.print(f"\n[dim]--- 樣本 {i} ---[/dim]")
            console.print(f"[cyan]問題:[/cyan] {c.question[:100]}...")
            console.print(f"[cyan]關鍵詞:[/cyan] {', '.join(c.reasoning_keywords_found)}")
            console.print(f"[cyan]檢索背景數:[/cyan] {len(c.retrieved_contexts)}")


# ============================================================================
# Main Execution
# ============================================================================

def main():
    """Main entry point."""
    try:
        # Load config
        config = load_config()
        target = config.get("target_count", 1500)
        is_test_mode = config.get("is_test_mode", False)
        # Request more candidates than target since generation has failures
        candidate_target = int(target * 1.7)
        retrieval_k = config.get("retrieval_k", 3)
        max_context_length = config.get("max_context_length", 500)
        
        console.print(f"[dim]目標候選數: {candidate_target} (基於最終目標 {target} 筆)[/dim]\n")
        
        # Filter candidates
        candidates, stats = filter_cot_candidates(
            target_count=candidate_target,
            retrieval_k=retrieval_k,
            max_context_length=max_context_length,
            is_test_mode=is_test_mode
        )
        
        if not candidates:
            console.print("[red]❌ 未找到符合條件的候選問題[/red]")
            sys.exit(1)
        
        # Save results
        save_candidates(candidates, stats)
        
        # Display summary
        display_summary(candidates, stats)
        
        console.print("\n[bold green]🎉 Phase 1 完成！[/bold green]")
        console.print("[dim]下一步: 執行 cot_generator.py 生成推理鏈[/dim]")
        
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
