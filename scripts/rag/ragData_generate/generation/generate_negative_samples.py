"""Generate Negative Sampling for RA-DIT training data.

This script generates negative samples by pairing questions with unrelated contexts.
The goal is to train the model to recognize irrelevant context and refuse to answer.

Why Negative Sampling is critical:
- Prevents hallucination by teaching model to say "I don't know"
- RA-DIT paper §2.3 specifies 7.5% target ratio
- Current dataset has only 77 negative samples (0.2%), needs ~3,000

Strategy: Wrong Context Pairing
1. Cross-domain pairing (50%): Red Mansion questions ↔ Poetry/Analects contexts
2. Cross-topic pairing (30%): Character questions ↔ Poem analysis contexts
3. Temporal mismatch (20%): First 80 chapters ↔ Last 40 chapters

Output format (per data_format_spec.md §2.3):
{
  "instruction": "根據以下段落回答問題，若段落資訊不足以回答，請說明無法回答。",
  "input": "【參考資料】\n{unrelated_context}\n\n【問題】{question}",
  "output": "參考資料與問題無關，無法回答。",
  "metadata": {...}
}
"""

import json
import random
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict

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
CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "negative_samples"
OUTPUT_FILE = OUTPUT_DIR / "negative_sampling_3000.jsonl"
STATS_FILE = PROJECT_ROOT / "output" / "p3_t04" / "negative_sampling_stats.json"
AUDIT_SAMPLE_FILE = PROJECT_ROOT / "output" / "p3_t04" / "negative_audit_sample.jsonl"

# Target counts
TARGET_NEGATIVE_SAMPLES = 3000
AUDIT_SAMPLE_SIZE = 100

# Pairing strategy distribution
CROSS_DOMAIN_RATIO = 0.50  # 50% cross-domain
CROSS_TOPIC_RATIO = 0.30   # 30% cross-topic
TEMPORAL_MISMATCH_RATIO = 0.20  # 20% temporal

# Domain classification keywords
DOMAIN_KEYWORDS = {
    "red_mansion": ["紅樓夢", "賈寶玉", "林黛玉", "薛寶釵", "王熙鳳", "大觀園", "賈府", "榮國府", "寧國府"],
    "poetry": ["詩經", "唐詩", "宋詞", "詩詞", "律詩", "絕句", "古詩"],
    "classics": ["論語", "孟子", "大學", "中庸", "老子", "莊子", "史記", "左傳"],
    "poem_analysis": ["葬花吟", "芙蓉女兒誄", "好了歌", "枉凝眉", "終身誤"]
}

# Refusal templates (5 variations to prevent memorization)
REFUSAL_TEMPLATES = [
    "參考資料與問題無關，無法從給定的段落中回答此問題。",
    "提供的段落資訊不足以回答此問題。",
    "此段落內容與問題主題不符，無法回答。",
    "根據給定的參考資料，無法找到與問題相關的資訊。",
    "參考資料未包含回答此問題所需的資訊。"
]

INSTRUCTION_TEMPLATE = "根據以下段落回答問題，若段落資訊不足以回答，請說明無法回答。"


# ============================================================================
# Helper Functions
# ============================================================================

def classify_domain(text: str) -> str:
    """Classify text into domain category.
    
    Why domain classification:
    - Enables cross-domain pairing (most effective negative strategy)
    - Ensures context is truly unrelated to question
    """
    text_lower = text.lower()
    
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return domain
    
    return "other"


def extract_chapter_info(text: str) -> Optional[int]:
    """Extract chapter number from Red Mansion content.
    
    Why chapter extraction:
    - Enables temporal mismatch pairing
    - Questions about chapter 5 + context from chapter 80 = mismatch
    """
    import re
    
    # Match patterns like "第X回", "第X章"
    patterns = [
        r"第(\d+)回",
        r"第(\d+)章",
        r"回(\d+)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    
    return None


def is_temporally_mismatched(q_chapter: Optional[int], c_chapter: Optional[int]) -> bool:
    """Check if question and context chapters are temporally mismatched.
    
    Mismatch definition:
    - First 80 chapters (original Cao Xueqin) vs Last 40 chapters (Gao E continuation)
    - Or significant chapter gap (>30 chapters difference)
    """
    if q_chapter is None or c_chapter is None:
        return False
    
    # First 80 vs Last 40
    if (q_chapter <= 80 and c_chapter > 80) or (q_chapter > 80 and c_chapter <= 80):
        return True
    
    # Significant gap
    if abs(q_chapter - c_chapter) > 30:
        return True
    
    return False


# ============================================================================
# Data Loading
# ============================================================================

def load_rag_samples(path: Path) -> List[Dict]:
    """Load RAG format samples."""
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    return samples


def load_chunks(path: Path) -> List[Dict]:
    """Load chunk data for context pool."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_question_from_input(input_text: str) -> str:
    """Extract question from RAG format input.
    
    Input format: 【參考資料】\n{context}\n\n【問題】{question}
    """
    if "【問題】" in input_text:
        return input_text.split("【問題】")[-1].strip()
    return input_text


def extract_context_from_input(input_text: str) -> str:
    """Extract context from RAG format input."""
    if "【參考資料】" in input_text and "【問題】" in input_text:
        context_part = input_text.split("【問題】")[0]
        context = context_part.replace("【參考資料】", "").strip()
        return context
    return ""


# ============================================================================
# Negative Sample Generation
# ============================================================================

@dataclass
class NegativePair:
    """A negative sample pairing."""
    question: str
    question_domain: str
    question_source: str
    wrong_context: str
    context_domain: str
    context_source: str
    mismatch_type: str  # cross_domain, cross_topic, temporal


def find_cross_domain_pairs(
    rag_samples: List[Dict],
    chunks: List[Dict],
    count: int
) -> List[NegativePair]:
    """Generate cross-domain negative pairs.
    
    Strategy:
    - Red Mansion question + Poetry/Classics context
    - Poetry question + Red Mansion context
    """
    pairs = []
    
    # Classify samples and chunks by domain
    questions_by_domain = defaultdict(list)
    for sample in rag_samples:
        question = extract_question_from_input(sample.get("input", ""))
        domain = classify_domain(question)
        questions_by_domain[domain].append({
            "question": question,
            "source": sample.get("metadata", {}).get("original_source", "unknown")
        })
    
    contexts_by_domain = defaultdict(list)
    for chunk in chunks:
        text = chunk.get("text", "")
        domain = classify_domain(text)
        contexts_by_domain[domain].append({
            "text": text,
            "chunk_id": chunk.get("chunk_id", "")
        })
    
    # Create cross-domain pairs
    domain_pairs = [
        ("red_mansion", "poetry"),
        ("red_mansion", "classics"),
        ("poetry", "red_mansion"),
        ("classics", "red_mansion"),
        ("poem_analysis", "classics"),
    ]
    
    pairs_per_combination = count // len(domain_pairs) + 1
    
    for q_domain, c_domain in domain_pairs:
        q_list = questions_by_domain.get(q_domain, [])
        c_list = contexts_by_domain.get(c_domain, [])
        
        if not q_list or not c_list:
            continue
        
        for _ in range(min(pairs_per_combination, len(q_list))):
            q = random.choice(q_list)
            c = random.choice(c_list)
            
            pairs.append(NegativePair(
                question=q["question"],
                question_domain=q_domain,
                question_source=q["source"],
                wrong_context=c["text"][:512],  # Truncate to 512 chars
                context_domain=c_domain,
                context_source=c["chunk_id"],
                mismatch_type="cross_domain"
            ))
            
            if len(pairs) >= count:
                return pairs[:count]
    
    return pairs


def find_cross_topic_pairs(
    rag_samples: List[Dict],
    count: int
) -> List[NegativePair]:
    """Generate cross-topic negative pairs within same domain.
    
    Strategy:
    - Character question + Poem analysis context (both Red Mansion)
    - Plot question + Character analysis context
    """
    pairs = []
    
    # Topic classification within Red Mansion
    character_keywords = ["賈寶玉", "林黛玉", "薛寶釵", "王熙鳳", "賈璉", "賈政", "賈母"]
    poem_keywords = ["葬花吟", "芙蓉女兒誄", "好了歌", "詩詞", "詩句"]
    plot_keywords = ["情節", "故事", "發生", "結局", "結婚"]
    
    character_questions = []
    poem_contexts = []
    plot_questions = []
    character_contexts = []
    
    for sample in rag_samples:
        question = extract_question_from_input(sample.get("input", ""))
        context = extract_context_from_input(sample.get("input", ""))
        source = sample.get("metadata", {}).get("original_source", "unknown")
        
        # Classify question
        if any(kw in question for kw in character_keywords):
            character_questions.append({"question": question, "source": source})
        elif any(kw in question for kw in plot_keywords):
            plot_questions.append({"question": question, "source": source})
        
        # Classify context
        if any(kw in context for kw in poem_keywords):
            poem_contexts.append({"text": context[:512], "source": source})
        elif any(kw in context for kw in character_keywords):
            character_contexts.append({"text": context[:512], "source": source})
    
    # Create cross-topic pairs
    topic_pairs = [
        (character_questions, poem_contexts, "character_q_poem_c"),
        (plot_questions, character_contexts, "plot_q_character_c"),
    ]
    
    for q_list, c_list, mismatch_subtype in topic_pairs:
        if not q_list or not c_list:
            continue
        
        for _ in range(count // len(topic_pairs)):
            q = random.choice(q_list)
            c = random.choice(c_list)
            
            pairs.append(NegativePair(
                question=q["question"],
                question_domain="red_mansion",
                question_source=q["source"],
                wrong_context=c["text"],
                context_domain="red_mansion",
                context_source=c["source"],
                mismatch_type=f"cross_topic:{mismatch_subtype}"
            ))
            
            if len(pairs) >= count:
                return pairs[:count]
    
    return pairs


def find_temporal_mismatch_pairs(
    rag_samples: List[Dict],
    count: int
) -> List[NegativePair]:
    """Generate temporal mismatch negative pairs.
    
    Strategy:
    - First 80 chapters question + Last 40 chapters context
    - Or significant chapter gap (>30 chapters)
    """
    pairs = []
    
    # Separate by chapter range
    first_80_samples = []
    last_40_samples = []
    
    for sample in rag_samples:
        question = extract_question_from_input(sample.get("input", ""))
        context = extract_context_from_input(sample.get("input", ""))
        full_text = question + " " + context
        
        chapter = extract_chapter_info(full_text)
        
        if chapter is not None:
            if chapter <= 80:
                first_80_samples.append({
                    "question": question,
                    "context": context[:512],
                    "chapter": chapter,
                    "source": sample.get("metadata", {}).get("original_source", "unknown")
                })
            else:
                last_40_samples.append({
                    "question": question,
                    "context": context[:512],
                    "chapter": chapter,
                    "source": sample.get("metadata", {}).get("original_source", "unknown")
                })
    
    # Create temporal mismatch pairs
    for _ in range(count):
        if not first_80_samples or not last_40_samples:
            break
        
        # First 80 question + Last 40 context
        q_sample = random.choice(first_80_samples)
        c_sample = random.choice(last_40_samples)
        
        pairs.append(NegativePair(
            question=q_sample["question"],
            question_domain="red_mansion",
            question_source=q_sample["source"],
            wrong_context=c_sample["context"],
            context_domain="red_mansion",
            context_source=c_sample["source"],
            mismatch_type=f"temporal:ch{q_sample['chapter']}_vs_ch{c_sample['chapter']}"
        ))
        
        if len(pairs) >= count:
            break
    
    return pairs


def generate_negative_samples(pairs: List[NegativePair]) -> List[Dict]:
    """Convert negative pairs to training format."""
    samples = []
    
    for i, pair in enumerate(pairs):
        # Select refusal template (rotate through 5 templates)
        refusal = REFUSAL_TEMPLATES[i % len(REFUSAL_TEMPLATES)]
        
        sample = {
            "instruction": INSTRUCTION_TEMPLATE,
            "input": f"【參考資料】\n{pair.wrong_context}\n\n【問題】{pair.question}",
            "output": refusal,
            "metadata": {
                "type": "negative_sampling",
                "mismatch_type": pair.mismatch_type,
                "question_domain": pair.question_domain,
                "context_domain": pair.context_domain,
                "question_source": pair.question_source,
                "context_source": pair.context_source,
                "refusal_template_id": i % len(REFUSAL_TEMPLATES),
                "generated_at": datetime.now().isoformat()
            }
        }
        samples.append(sample)
    
    return samples


# ============================================================================
# Main Execution
# ============================================================================

def main():
    console.print("[bold blue]P3-T04-S1: Negative Sampling 生成[/bold blue]\n")
    
    # Ensure output directories exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "output" / "p3_t04").mkdir(parents=True, exist_ok=True)
    
    # Load data
    console.print("Loading RAG samples...")
    rag_samples = load_rag_samples(RAG_SAMPLES_PATH)
    console.print(f"Loaded {len(rag_samples)} RAG samples\n")
    
    console.print("Loading chunks...")
    chunks = load_chunks(CHUNKS_PATH)
    console.print(f"Loaded {len(chunks)} chunks\n")
    
    # Calculate target counts
    cross_domain_count = int(TARGET_NEGATIVE_SAMPLES * CROSS_DOMAIN_RATIO)
    cross_topic_count = int(TARGET_NEGATIVE_SAMPLES * CROSS_TOPIC_RATIO)
    temporal_count = int(TARGET_NEGATIVE_SAMPLES * TEMPORAL_MISMATCH_RATIO)
    
    console.print(f"Target: {TARGET_NEGATIVE_SAMPLES} negative samples")
    console.print(f"  - Cross-domain: {cross_domain_count} (50%)")
    console.print(f"  - Cross-topic: {cross_topic_count} (30%)")
    console.print(f"  - Temporal mismatch: {temporal_count} (20%)\n")
    
    # Generate pairs
    all_pairs = []
    
    console.print("Generating cross-domain pairs...")
    cross_domain_pairs = find_cross_domain_pairs(rag_samples, chunks, cross_domain_count)
    all_pairs.extend(cross_domain_pairs)
    console.print(f"  Generated: {len(cross_domain_pairs)}")
    
    console.print("Generating cross-topic pairs...")
    cross_topic_pairs = find_cross_topic_pairs(rag_samples, cross_topic_count)
    all_pairs.extend(cross_topic_pairs)
    console.print(f"  Generated: {len(cross_topic_pairs)}")
    
    console.print("Generating temporal mismatch pairs...")
    temporal_pairs = find_temporal_mismatch_pairs(rag_samples, temporal_count)
    all_pairs.extend(temporal_pairs)
    console.print(f"  Generated: {len(temporal_pairs)}")
    
    console.print(f"\nTotal pairs: {len(all_pairs)}\n")
    
    # Shuffle for variety
    random.shuffle(all_pairs)
    
    # Convert to training format
    console.print("Converting to training format...")
    negative_samples = generate_negative_samples(all_pairs)
    
    # Save main output
    console.print(f"Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for sample in negative_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    # Save audit sample
    audit_samples = random.sample(negative_samples, min(AUDIT_SAMPLE_SIZE, len(negative_samples)))
    with open(AUDIT_SAMPLE_FILE, 'w', encoding='utf-8') as f:
        for sample in audit_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    console.print(f"Saved {len(audit_samples)} audit samples to {AUDIT_SAMPLE_FILE}")
    
    # Statistics
    stats = {
        "total_generated": len(negative_samples),
        "cross_domain_count": len(cross_domain_pairs),
        "cross_topic_count": len(cross_topic_pairs),
        "temporal_count": len(temporal_pairs),
        "refusal_template_distribution": {
            f"template_{i}": sum(1 for s in negative_samples 
                                if s["metadata"]["refusal_template_id"] == i)
            for i in range(len(REFUSAL_TEMPLATES))
        },
        "mismatch_type_distribution": {},
        "generated_at": datetime.now().isoformat()
    }
    
    # Count mismatch types
    for sample in negative_samples:
        mt = sample["metadata"]["mismatch_type"].split(":")[0]
        stats["mismatch_type_distribution"][mt] = stats["mismatch_type_distribution"].get(mt, 0) + 1
    
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    console.print(f"Saved statistics to {STATS_FILE}")
    
    # Display summary
    console.print("\n[bold cyan]═══ 生成完成 ═══[/bold cyan]\n")
    
    table = Table(title="Negative Sampling 統計")
    table.add_column("指標", style="cyan")
    table.add_column("數量", justify="right")
    table.add_column("佔比", justify="right")
    
    table.add_row("總計", str(len(negative_samples)), "100%")
    table.add_row("跨領域配對", str(len(cross_domain_pairs)), 
                  f"{len(cross_domain_pairs)/len(negative_samples)*100:.1f}%")
    table.add_row("跨主題配對", str(len(cross_topic_pairs)),
                  f"{len(cross_topic_pairs)/len(negative_samples)*100:.1f}%")
    table.add_row("時序錯配", str(len(temporal_pairs)),
                  f"{len(temporal_pairs)/len(negative_samples)*100:.1f}%")
    
    console.print(table)
    
    console.print(f"\n[green]✅ 生成完成！[/green]")
    console.print(f"   輸出檔案: {OUTPUT_FILE}")
    console.print(f"   審核樣本: {AUDIT_SAMPLE_FILE} ({AUDIT_SAMPLE_SIZE} 筆)")


if __name__ == "__main__":
    main()
