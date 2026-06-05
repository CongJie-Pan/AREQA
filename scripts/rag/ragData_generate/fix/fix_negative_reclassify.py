"""P3-T04-S5: Reclassify Negative Sampling into QA Robustness / RC Negative.

This script fixes the RA-DIT format issue identified by Perplexity AI:
- RA-DIT distinguishes two types of Negative training:
  1. QA Robustness: Wrong context + CORRECT answer (train to ignore noise)
  2. RC Negative: Wrong context + REFUSAL (train to refuse when asked about text)

Implementation:
- Load existing Negative samples
- Classify by question keywords (QA vs RC type)
- QA type: Replace refusal with original correct answer
- RC type: Keep refusal template

Reference:
- RA-DIT Paper Section 2.3, Appendix F
- p3_t04_v2_1_implementation_plan.md
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
from collections import Counter

from rich.console import Console
from rich.progress import track
from rich.table import Table

# ============================================================================
# Project Setup
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

console = Console()

# ============================================================================
# Configuration
# ============================================================================

# Input files
NEGATIVE_FILE = PROJECT_ROOT / "data" / "training" / "negative_samples" / "negative_sampling_3000.jsonl"

# Original QA sources for finding correct answers
RAG_FILE = PROJECT_ROOT / "data" / "training" / "rag_format" / "backfilled_radit_format.jsonl"
PURE_QA_FILE = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_with_context.jsonl"

# Output files
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "negative_samples"
QA_ROBUSTNESS_FILE = OUTPUT_DIR / "qa_robustness.jsonl"
RC_NEGATIVE_FILE = OUTPUT_DIR / "rc_negative.jsonl"
STATS_FILE = OUTPUT_DIR / "negative_reclassify_stats.json"
AUDIT_FILE = PROJECT_ROOT / "output" / "p3_t04" / "negative_reclassify_audit.jsonl"

# RC keywords: questions that explicitly reference the provided text
# These should remain as "refusal" type
RC_KEYWORDS = [
    "根據上文", "依照文章", "從文中", "根據資料", "按照上述",
    "根據以上", "依據上文", "從上文", "上文提到", "上述內容",
    "文章指出", "依照資料", "根據上述", "從資料中"
]


# ============================================================================
# Helper Functions
# ============================================================================

def load_jsonl(path: Path) -> List[Dict]:
    """Load samples from JSONL file."""
    samples = []
    if not path.exists():
        return samples
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def save_jsonl(samples: List[Dict], path: Path):
    """Save samples to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")


def extract_question(sample: Dict) -> str:
    """Extract question from sample input field."""
    input_text = sample.get("input", "")
    
    # Robust extraction using Regex for various question markers
    import re
    
    # Pattern to match question markers with optional whitespace
    pattern = r'(?:【問題】|問題：|Question:|問：)\s*(.*)'
    match = re.search(pattern, input_text, re.IGNORECASE | re.DOTALL)
    
    if match:
        return match.group(1).strip()
    
    # Fallback: if no marker, try to return the last paragraph
    parts = [p.strip() for p in input_text.split('\n\n') if p.strip()]
    if parts:
        return parts[-1]
        
    return input_text.strip()


def is_rc_type(question: str) -> bool:
    """Check if question is Reading Comprehension type.
    
    Why distinguish:
    - RC questions explicitly reference "the text" or "上文"
    - These SHOULD be refused when context is wrong
    - QA questions don't reference text, so model should use knowledge
    """
    return any(kw in question for kw in RC_KEYWORDS)


def build_answer_lookup(rag_samples: List[Dict], pure_qa_samples: List[Dict]) -> Dict[str, str]:
    """Build a lookup table from questions to correct answers.
    
    Why we need this:
    - Negative samples currently have refusal templates
    - For QA type, we need the ORIGINAL correct answer
    - We extract from RAG and Pure QA sources
    """
    lookup = {}
    
    def normalize_key(text: str) -> str:
        # Strip all whitespaces/newlines for robust exact matching
        import re
        return re.sub(r'\s+', '', text).strip()
    
    # Extract from RAG samples
    for sample in rag_samples:
        question = extract_question(sample)
        answer = sample.get("output", "")
        if question and answer:
            key = normalize_key(question)
            lookup[key] = answer
    
    # Extract from Pure QA samples
    for sample in pure_qa_samples:
        question = extract_question(sample)
        answer = sample.get("output", "")
        if question and answer:
            key = normalize_key(question)
            lookup[key] = answer
    
    return lookup


def find_correct_answer(question: str, answer_lookup: Dict[str, str]) -> Tuple[str, bool]:
    """Find correct answer for a question.
    
    Returns:
        (answer, found): The correct answer and whether it was found
    """
    import re
    key = re.sub(r'\s+', '', question).strip()
    
    # Exact match only (ignoring whitespaces)
    if key in answer_lookup:
        return answer_lookup[key], True
    
    return "", False


# ============================================================================
# Main Processing
# ============================================================================

def reclassify_negative_samples(
    negative_samples: List[Dict],
    answer_lookup: Dict[str, str]
) -> Tuple[List[Dict], List[Dict], Dict]:
    """Reclassify Negative samples into QA Robustness and RC Negative.
    
    Why two types:
    - QA Robustness: Model learns to ignore wrong context and answer correctly
      - Example: Q="林黛玉是誰？" with wrong context → Answer correctly
    - RC Negative: Model learns to refuse when context doesn't match question
      - Example: Q="根據上文，賈寶玉做了什麼？" with wrong context → Refuse
    """
    qa_robustness = []
    rc_negative = []
    
    stats = {
        "total": len(negative_samples),
        "qa_robustness": 0,
        "rc_negative": 0,
        "qa_answer_found": 0,
        "qa_answer_not_found": 0
    }
    
    for sample in track(negative_samples, description="Reclassifying..."):
        question = extract_question(sample)
        
        if is_rc_type(question):
            # RC type: keep as refusal (no change needed)
            new_sample = {
                "instruction": sample.get("instruction", ""),
                "input": sample.get("input", ""),
                "output": sample.get("output", ""),  # Keep refusal template
                "metadata": {
                    **sample.get("metadata", {}),
                    "type": "rc_negative",
                    "subtype": "rc_refusal",
                    "reclassified_at": datetime.now().isoformat()
                }
            }
            rc_negative.append(new_sample)
            stats["rc_negative"] += 1
        else:
            # QA type: replace refusal with correct answer
            correct_answer, found = find_correct_answer(question, answer_lookup)
            
            if found:
                # Create QA Robustness sample with correct answer
                new_sample = {
                    "instruction": "請根據參考資料回答問題。如果參考資料不相關，請根據你的知識回答。",
                    "input": sample.get("input", ""),
                    "output": correct_answer,  # Use correct answer instead of refusal
                    "metadata": {
                        **sample.get("metadata", {}),
                        "type": "qa_robustness",
                        "subtype": "noise_tolerance",
                        "original_output_was_refusal": True,
                        "reclassified_at": datetime.now().isoformat()
                    }
                }
                qa_robustness.append(new_sample)
                stats["qa_robustness"] += 1
                stats["qa_answer_found"] += 1
            else:
                # Couldn't find correct answer, keep as RC type
                new_sample = {
                    "instruction": sample.get("instruction", ""),
                    "input": sample.get("input", ""),
                    "output": sample.get("output", ""),
                    "metadata": {
                        **sample.get("metadata", {}),
                        "type": "rc_negative",
                        "subtype": "answer_not_found",
                        "reclassified_at": datetime.now().isoformat()
                    }
                }
                rc_negative.append(new_sample)
                stats["rc_negative"] += 1
                stats["qa_answer_not_found"] += 1
    
    return qa_robustness, rc_negative, stats


def main():
    """Main entry point."""
    console.print("[bold blue]P3-T04-S5: Negative Sampling 重分類[/bold blue]\n")
    
    # Load Negative samples
    console.print(f"Loading Negative samples from {NEGATIVE_FILE}...")
    negative_samples = load_jsonl(NEGATIVE_FILE)
    console.print(f"Loaded {len(negative_samples)} samples\n")
    
    # Load answer sources
    console.print("Loading answer sources for QA Robustness...")
    console.print(f"  Loading RAG samples from {RAG_FILE}...")
    rag_samples = load_jsonl(RAG_FILE)
    console.print(f"    Loaded: {len(rag_samples)} samples")
    
    console.print(f"  Loading Pure QA samples from {PURE_QA_FILE}...")
    pure_qa_samples = load_jsonl(PURE_QA_FILE)
    console.print(f"    Loaded: {len(pure_qa_samples)} samples")
    
    # Build answer lookup
    console.print("\nBuilding answer lookup table...")
    answer_lookup = build_answer_lookup(rag_samples, pure_qa_samples)
    console.print(f"Answer lookup: {len(answer_lookup)} entries\n")
    
    # Reclassify
    console.print("[bold]Reclassifying Negative samples...[/bold]")
    qa_robustness, rc_negative, stats = reclassify_negative_samples(
        negative_samples, answer_lookup
    )
    
    # Save results
    console.print(f"\nSaving QA Robustness to {QA_ROBUSTNESS_FILE}...")
    save_jsonl(qa_robustness, QA_ROBUSTNESS_FILE)
    
    console.print(f"Saving RC Negative to {RC_NEGATIVE_FILE}...")
    save_jsonl(rc_negative, RC_NEGATIVE_FILE)
    
    # Save audit samples
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    audit_samples = qa_robustness[:25] + rc_negative[:25]
    save_jsonl(audit_samples, AUDIT_FILE)
    console.print(f"Saved {len(audit_samples)} audit samples to {AUDIT_FILE}")
    
    # Save statistics
    stats_report = {
        "timestamp": datetime.now().isoformat(),
        "input": {
            "negative_samples": len(negative_samples),
            "rag_sources": len(rag_samples),
            "pure_qa_sources": len(pure_qa_samples),
            "answer_lookup_size": len(answer_lookup)
        },
        "output": {
            "qa_robustness": len(qa_robustness),
            "rc_negative": len(rc_negative),
            "qa_robustness_ratio": len(qa_robustness) / len(negative_samples) * 100 if negative_samples else 0,
            "rc_negative_ratio": len(rc_negative) / len(negative_samples) * 100 if negative_samples else 0
        },
        "details": {
            "qa_answer_found": stats["qa_answer_found"],
            "qa_answer_not_found": stats["qa_answer_not_found"]
        },
        "rc_keywords_used": RC_KEYWORDS
    }
    
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats_report, f, ensure_ascii=False, indent=2)
    
    # Display summary
    console.print("\n[bold cyan]═══ 重分類完成 ═══[/bold cyan]\n")
    
    table = Table(title="Negative Sampling 重分類統計")
    table.add_column("類型", style="cyan")
    table.add_column("數量", justify="right")
    table.add_column("佔比", justify="right")
    table.add_column("說明")
    
    table.add_row(
        "QA Robustness",
        str(len(qa_robustness)),
        f"{len(qa_robustness)/len(negative_samples)*100:.1f}%",
        "錯 context + 正確答案 (抗噪訓練)"
    )
    table.add_row(
        "RC Negative",
        str(len(rc_negative)),
        f"{len(rc_negative)/len(negative_samples)*100:.1f}%",
        "錯 context + 拒答 (謹慎訓練)"
    )
    table.add_row(
        "[bold]總計[/bold]",
        f"[bold]{len(qa_robustness) + len(rc_negative)}[/bold]",
        "[bold]100%[/bold]",
        ""
    )
    
    console.print(table)
    
    # QA answer finding stats
    console.print(f"\n[bold]QA 答案查找統計:[/bold]")
    console.print(f"  找到正確答案: {stats['qa_answer_found']}")
    console.print(f"  未找到答案 (歸入 RC): {stats['qa_answer_not_found']}")
    
    console.print(f"\n[bold green]✅ 完成！[/bold green]")
    console.print(f"   QA Robustness: {QA_ROBUSTNESS_FILE}")
    console.print(f"   RC Negative: {RC_NEGATIVE_FILE}")
    console.print(f"   統計報告: {STATS_FILE}")
    console.print(f"   審核樣本: {AUDIT_FILE} (50 筆)")
    
    return 0


if __name__ == "__main__":
    exit(main())
