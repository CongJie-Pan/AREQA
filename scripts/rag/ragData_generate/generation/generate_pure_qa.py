"""Generate Pure QA samples by extracting from RAG format samples.

This script generates Pure QA by removing context from existing RAG samples.
The goal is to maintain domain consistency while training the model to answer
without always relying on external context (防止災難性遺忘).

Why extract from RAG samples:
- Ensures 100% domain consistency with RAG corpus
- Fast generation (no LLM needed)
- Factually correct (answers already verified)
- Current: 12,022 Pure QA (29.6%), Target: 14,233 (35%), Gap: 2,211

Strategy:
1. Load all RAG format samples
2. Randomly select 2,500 samples
3. Extract (question, answer), remove context
4. Filter and select final 2,211 samples

Output format (per data_format_spec.md §2.2):
{
  "instruction": "請回答以下關於中國文學的問題。",
  "input": "{question}",  # No context!
  "output": "{answer}",
  "metadata": {...}
}
"""

import json
import random
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict

from rich.console import Console
from rich.progress import track
from rich.table import Table

console = Console()

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Input paths
RAG_SAMPLES_PATH = PROJECT_ROOT / "data" / "training" / "rag_format" / "backfilled_radit_format.jsonl"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "pure_qa"
OUTPUT_FILE = OUTPUT_DIR / "pure_qa_supplement_2211.jsonl"
STATS_FILE = PROJECT_ROOT / "output" / "p3_t04" / "pure_qa_stats.json"
AUDIT_SAMPLE_FILE = PROJECT_ROOT / "output" / "p3_t04" / "pure_qa_audit_sample.jsonl"

# Parameters
TARGET_PURE_QA = 2211
CANDIDATE_POOL_SIZE = 2500  # Sample more for filtering
AUDIT_SAMPLE_SIZE = 50

INSTRUCTION_TEMPLATE = "請回答以下關於中國文學的問題。"


# ============================================================================
# Helper Functions
# ============================================================================

def extract_question_from_input(input_text: str) -> str:
    """Extract question from RAG format input.
    
    RAG format: 【參考資料】\n{context}\n\n【問題】{question}
    Pure QA format: {question}
    """
    if "【問題】" in input_text:
        return input_text.split("【問題】")[-1].strip()
    return input_text


def is_valid_question(question: str) -> bool:
    """Validate question quality.
    
    Filter out:
    - Too short (<10 chars)
    - Only punctuation
    - Contains context markers (shouldn't happen but check anyway)
    """
    if len(question) < 10:
        return False
    
    if "【參考資料】" in question or "【問題】" in question:
        return False
    
    # Must contain at least some Chinese characters
    if not any('\u4e00' <= c <= '\u9fff' for c in question):
        return False
    
    return True


def classify_source(metadata: Dict) -> str:
    """Classify sample by original source."""
    source = metadata.get("original_source", "unknown")
    
    # Normalize source names
    source_mapping = {
        "poem_qa": "詩詞分析",
        "rc_qa": "紅樓夢問答",
        "wiki_qa": "維基百科",
        "notes": "筆記",
        "chapter": "章節分析"
    }
    
    for key, label in source_mapping.items():
        if key in source:
            return label
    
    return "其他"


# ============================================================================
# Pure QA Generation
# ============================================================================

def load_rag_samples(path: Path) -> List[Dict]:
    """Load RAG format samples."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def extract_pure_qa_from_rag(rag_sample: Dict) -> Dict:
    """Convert RAG sample to Pure QA format.
    
    Transformation:
    - Remove 【參考資料】 section
    - Keep question and answer
    - Update metadata
    """
    question = extract_question_from_input(rag_sample.get("input", ""))
    answer = rag_sample.get("output", "")
    metadata = rag_sample.get("metadata", {})
    
    pure_qa = {
        "instruction": INSTRUCTION_TEMPLATE,
        "input": question,
        "output": answer,
        "metadata": {
            "type": "pure_qa",
            "generation_method": "extracted_from_rag",
            "original_rag_id": metadata.get("qa_id"),
            "original_source": metadata.get("original_source", "unknown"),
            "source_classification": classify_source(metadata),
            "extracted_at": datetime.now().isoformat()
        }
    }
    
    return pure_qa


def generate_pure_qa_samples(
    rag_samples: List[Dict],
    target_count: int,
    candidate_pool_size: int
) -> List[Dict]:
    """Generate Pure QA samples by extracting from RAG samples.
    
    Process:
    1. Randomly sample candidate_pool_size samples from RAG
    2. Extract question-answer pairs
    3. Filter by quality
    4. Select final target_count samples (balanced by source)
    """
    console.print(f"Sampling {candidate_pool_size} candidates from {len(rag_samples)} RAG samples...")
    
    # Random sample
    candidates = random.sample(rag_samples, min(candidate_pool_size, len(rag_samples)))
    
    # Extract Pure QA
    console.print("Extracting Pure QA from candidates...")
    pure_qa_pool = []
    for sample in track(candidates, description="Extracting..."):
        pure_qa = extract_pure_qa_from_rag(sample)
        
        # Validate
        if is_valid_question(pure_qa["input"]):
            pure_qa_pool.append(pure_qa)
    
    console.print(f"Valid Pure QA pool: {len(pure_qa_pool)}")
    
    # Stratified sampling by source for balanced dataset
    samples_by_source = defaultdict(list)
    for sample in pure_qa_pool:
        source = sample["metadata"]["source_classification"]
        samples_by_source[source].append(sample)
    
    # Calculate proportional allocation
    total_valid = len(pure_qa_pool)
    selected = []
    
    for source, samples in samples_by_source.items():
        # Proportional to source representation
        source_ratio = len(samples) / total_valid
        source_quota = int(target_count * source_ratio)
        
        # Sample from this source
        n_to_sample = min(source_quota, len(samples))
        selected.extend(random.sample(samples, n_to_sample))
    
    # If we don't have enough, fill remainder randomly
    if len(selected) < target_count:
        remaining_pool = [s for s in pure_qa_pool if s not in selected]
        n_needed = target_count - len(selected)
        if remaining_pool:
            selected.extend(random.sample(remaining_pool, min(n_needed, len(remaining_pool))))
    
    # Shuffle final selection
    random.shuffle(selected)
    
    return selected[:target_count]


# ============================================================================
# Main Execution
# ============================================================================

def main():
    console.print("[bold blue]P3-T04-S2: Pure QA 補充生成[/bold blue]\n")
    
    # Ensure output directories exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "output" / "p3_t04").mkdir(parents=True, exist_ok=True)
    
    # Load RAG samples
    console.print(f"Loading RAG samples from {RAG_SAMPLES_PATH}...")
    rag_samples = load_rag_samples(RAG_SAMPLES_PATH)
    console.print(f"Loaded {len(rag_samples)} RAG samples\n")
    
    # Generate Pure QA
    console.print(f"Target: {TARGET_PURE_QA} Pure QA samples")
    console.print(f"Strategy: Extract from RAG samples (no LLM needed)\n")
    
    pure_qa_samples = generate_pure_qa_samples(
        rag_samples,
        target_count=TARGET_PURE_QA,
        candidate_pool_size=CANDIDATE_POOL_SIZE
    )
    
    console.print(f"\nGenerated: {len(pure_qa_samples)} Pure QA samples\n")
    
    # Save main output
    console.print(f"Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for sample in pure_qa_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    # Save audit sample
    audit_samples = random.sample(pure_qa_samples, min(AUDIT_SAMPLE_SIZE, len(pure_qa_samples)))
    with open(AUDIT_SAMPLE_FILE, 'w', encoding='utf-8') as f:
        for sample in audit_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    console.print(f"Saved {len(audit_samples)} audit samples to {AUDIT_SAMPLE_FILE}")
    
    # Statistics
    source_distribution = defaultdict(int)
    for sample in pure_qa_samples:
        source = sample["metadata"]["source_classification"]
        source_distribution[source] += 1
    
    avg_question_length = sum(len(s["input"]) for s in pure_qa_samples) / len(pure_qa_samples)
    avg_answer_length = sum(len(s["output"]) for s in pure_qa_samples) / len(pure_qa_samples)
    
    stats = {
        "total_generated": len(pure_qa_samples),
        "target_count": TARGET_PURE_QA,
        "candidate_pool_size": CANDIDATE_POOL_SIZE,
        "source_distribution": dict(source_distribution),
        "avg_question_length": avg_question_length,
        "avg_answer_length": avg_answer_length,
        "extraction_method": "from_rag_samples",
        "generated_at": datetime.now().isoformat()
    }
    
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    console.print(f"Saved statistics to {STATS_FILE}")
    
    # Display summary
    console.print("\n[bold cyan]═══ 生成完成 ═══[/bold cyan]\n")
    
    table = Table(title="Pure QA 統計")
    table.add_column("指標", style="cyan")
    table.add_column("數值", justify="right")
    
    table.add_row("總生成數", str(len(pure_qa_samples)))
    table.add_row("目標數量", str(TARGET_PURE_QA))
    table.add_row("完成率", f"{len(pure_qa_samples)/TARGET_PURE_QA*100:.1f}%")
    table.add_row("平均問題長度", f"{avg_question_length:.0f} 字")
    table.add_row("平均答案長度", f"{avg_answer_length:.0f} 字")
    
    console.print(table)
    
    # Source distribution
    source_table = Table(title="\n來源分佈")
    source_table.add_column("來源", style="cyan")
    source_table.add_column("數量", justify="right")
    source_table.add_column("佔比", justify="right")
    
    for source, count in sorted(source_distribution.items(), key=lambda x: -x[1]):
        pct = count / len(pure_qa_samples) * 100
        source_table.add_row(source, str(count), f"{pct:.1f}%")
    
    console.print(source_table)
    
    console.print(f"\n[green]✅ 生成完成！[/green]")
    console.print(f"   輸出檔案: {OUTPUT_FILE}")
    console.print(f"   審核樣本: {AUDIT_SAMPLE_FILE} ({AUDIT_SAMPLE_SIZE} 筆)")
    console.print(f"\n[bold]特點：[/bold]")
    console.print(f"   ✅ 100% 領域一致性（從 RAG 提取）")
    console.print(f"   ✅ 事實正確性有保證（已驗證答案）")
    console.print(f"   ✅ 快速生成（無需 LLM）")


if __name__ == "__main__":
    main()
