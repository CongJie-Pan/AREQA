"""Unified remediation script for v2.1 dataset format compliance.

This script fixes all format issues identified by RA-DIT evaluation:
1. Pure QA: Add retrieval backgrounds
2. CoT: Add retrieval backgrounds  
3. Negative: Fix sampling strategy (Knowledge QA should Fallback, not Refuse)

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S8
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import Counter
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

console = Console()

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Input paths
PURE_QA_PATH = PROJECT_ROOT / "data" / "training" / "pure_qa" / "pure_qa_with_context.jsonl"
COT_PATH = PROJECT_ROOT / "data" / "training" / "cot" / "cot_samples.jsonl"
NEGATIVE_PATH = PROJECT_ROOT / "data" / "training" / "negative_samples" / "qa_robustness.jsonl"

# FAISS paths
FAISS_MAPPING_PATH = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "training" / "remediation"
PURE_QA_FIXED = OUTPUT_DIR / "pure_qa_with_context_fixed.jsonl"
COT_FIXED = OUTPUT_DIR / "cot_samples_fixed.jsonl"
QA_ROBUSTNESS_FIXED = OUTPUT_DIR / "qa_robustness_fixed.jsonl"
RC_NEGATIVE_FIXED = OUTPUT_DIR / "rc_negative_fixed.jsonl"

# Keywords for RC classification
RC_KEYWORDS = ["根據上文", "依照文章", "從文中", "根據資料", "按照上述", "根據這段", "由上文"]


def load_jsonl(file_path: Path) -> List[Dict[str, Any]]:
    """Load JSONL file."""
    samples = []
    if not file_path.exists():
        console.print(f"[yellow]⚠️ File not found: {file_path}[/yellow]")
        return samples
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return samples


def save_jsonl(samples: List[Dict], output_path: Path):
    """Save samples to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    console.print(f"[green]✅ Saved to: {output_path.relative_to(PROJECT_ROOT)}[/green]")


def load_chunk_mapping() -> Dict[str, Any]:
    """Load FAISS chunk mapping for context retrieval.
    
    Why: Enable retrieval of context for Pure QA and CoT
    """
    if FAISS_MAPPING_PATH.exists():
        with open(FAISS_MAPPING_PATH, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)
            # Handle both dict and list formats
            if isinstance(mapping_data, dict):
                return mapping_data
            elif isinstance(mapping_data, list):
                # Convert list to dict with index as key
                return {str(i): chunk for i, chunk in enumerate(mapping_data)}
    return {}


def simple_retrieve_contexts(question: str, chunk_mapping: Dict, k: int = 3) -> List[str]:
    """Simple keyword-based retrieval fallback.
    
    Why: FAISS may not be available, use keyword matching as proxy
    
    Note: This is a simple fallback. For better results, use proper FAISS vector retrieval.
    """
    if not chunk_mapping:
        return []
    
    # Extract keywords from question
    question_words = set(re.findall(r'[\u4e00-\u9fff]+', question))
    
    # Score each chunk by keyword overlap
    scores = []
    for idx, chunk_data in chunk_mapping.items():
        if isinstance(chunk_data, dict):
            chunk_text = chunk_data.get('text', '') or chunk_data.get('content', '')
        else:
            chunk_text = str(chunk_data)
        
        chunk_words = set(re.findall(r'[\u4e00-\u9fff]+', chunk_text))
        overlap = len(question_words & chunk_words)
        
        if overlap > 0:
            scores.append((overlap, chunk_text, idx))
    
    # Sort by overlap score and return top-k
    scores.sort(reverse=True, key=lambda x: x[0])
    return [text for _, text, _ in scores[:k]]


def extract_question_from_input(input_text: str) -> str:
    """Extract question from input that may contain 【參考資料】and【問題】markers.
    
    Why: Need to handle inputs that already have some formatting
    """
    # Try to extract from【問題】marker
    if "【問題】" in input_text:
        parts = input_text.split("【問題】")
        if len(parts) > 1:
            return parts[1].strip()
    
    # Otherwise, return as-is
    return input_text.strip()


def format_input_with_context(question: str, contexts: List[str]) -> str:
    """Format input with retrieval background in RA-DIT format.
    
    Why: Ensure consistent format across all samples
    """
    context_text = "\n\n".join(contexts) if contexts else "無相關資料"
    
    return f"""【參考資料】
{context_text}

【問題】
{question}"""


def fix_pure_qa(samples: List[Dict], chunk_mapping: Dict) -> List[Dict]:
    """Fix Pure QA samples by adding retrieval backgrounds.
    
    Why: Pure QA currently lacks【參考資料】, violating RA-DIT format
    """
    console.print(Panel(
        "[bold cyan]Step 1: Fixing Pure QA Samples[/bold cyan]\n"
        f"Adding retrieval backgrounds to {len(samples)} Pure QA samples",
        border_style="cyan"
    ))
    
    fixed_samples = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Processing Pure QA...", total=len(samples))
        
        for sample in samples:
            # Extract question from current input
            question = extract_question_from_input(sample.get('input', ''))
            
            # Retrieve contexts
            contexts = simple_retrieve_contexts(question, chunk_mapping, k=3)
            
            # Format new input with background
            sample['input'] = format_input_with_context(question, contexts)
            
            # Update metadata
            if 'metadata' not in sample:
                sample['metadata'] = {}
            sample['metadata']['remediation'] = 'added_retrieval_background'
            sample['metadata']['retrieval_count'] = len(contexts)
            
            fixed_samples.append(sample)
            progress.update(task, advance=1)
    
    console.print(f"[green]✅ Fixed {len(fixed_samples)} Pure QA samples[/green]\n")
    return fixed_samples


def fix_cot(samples: List[Dict], chunk_mapping: Dict) -> List[Dict]:
    """Fix CoT samples by adding retrieval backgrounds.
    
    Why: CoT should demonstrate how to use retrieval to reason
    """
    console.print(Panel(
        "[bold cyan]Step 2: Fixing CoT Samples[/bold cyan]\n"
        f"Adding retrieval backgrounds to {len(samples)} CoT samples",
        border_style="cyan"
    ))
    
    fixed_samples = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Processing CoT...", total=len(samples))
        
        for sample in samples:
            # Extract question - try from metadata first, then from input
            question = sample.get('metadata', {}).get('original_question', '')
            if not question:
                question = sample.get('question', '')
            if not question:
                question = extract_question_from_input(sample.get('input', ''))
            
            # Retrieve contexts
            contexts = simple_retrieve_contexts(question, chunk_mapping, k=3)
            
            # Format new input with background
            sample['input'] = format_input_with_context(question, contexts)
            
            # Update metadata
            if 'metadata' not in sample:
                sample['metadata'] = {}
            sample['metadata']['remediation'] = 'added_retrieval_background'
            sample['metadata']['retrieval_count'] = len(contexts)
            
            # Keep output unchanged (already has【思考過程】and【答案】)
            
            fixed_samples.append(sample)
            progress.update(task, advance=1)
    
    console.print(f"[green]✅ Fixed {len(fixed_samples)} CoT samples[/green]\n")
    return fixed_samples


def classify_negative_type(question: str) -> str:
    """Classify negative sample as RC (Reading Comprehension) or Knowledge QA.
    
    Why: RC questions should refuse when context is wrong,
         Knowledge QA should fallback to parametric memory
    
    Returns:
        'rc' or 'qa'
    """
    # RC questions explicitly reference the context
    for keyword in RC_KEYWORDS:
        if keyword in question:
            return 'rc'
    
    # Default to Knowledge QA
    return 'qa'


def fix_negative(samples: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Fix negative sampling strategy.
    
    Why: Current strategy has all samples refusing,
         but Knowledge QA should answer correctly (Parametric Fallback)
    
    Returns:
        Tuple of (qa_robustness_samples, rc_negative_samples)
    """
    console.print(Panel(
        "[bold cyan]Step 3: Fixing Negative Sampling Strategy[/bold cyan]\n"
        f"Classifying {len(samples)} negative samples",
        border_style="cyan"
    ))
    
    qa_robustness = []
    rc_negative = []
    
    refusal_patterns = ["無法回答", "不能回答", "參考資料與問題無關", "無關", "拒答"]
    
    for sample in samples:
        question = extract_question_from_input(sample.get('input', ''))
        neg_type = classify_negative_type(question)
        
        if neg_type == 'rc':
            # Reading Comprehension - keep refusal
            if 'metadata' not in sample:
                sample['metadata'] = {}
            sample['metadata']['negative_type'] = 'rc_negative'
            sample['metadata']['remediation'] = 'kept_refusal_for_rc'
            rc_negative.append(sample)
        else:
            # Knowledge QA - should answer correctly, not refuse
            current_output = sample.get('output', '')
            is_refusal = any(pattern in current_output for pattern in refusal_patterns)
            
            if is_refusal:
                # Try to find correct answer from metadata
                correct_answer = sample.get('metadata', {}).get('original_answer', '')
                if not correct_answer:
                    correct_answer = sample.get('original_answer', '')
                
                if correct_answer:
                    sample['output'] = correct_answer
                    if 'metadata' not in sample:
                        sample['metadata'] = {}
                    sample['metadata']['remediation'] = 'changed_refusal_to_parametric_fallback'
                else:
                    # Can't find answer, log warning and keep in QA robustness
                    console.print(f"[yellow]⚠️ No correct answer found for sample, keeping refusal[/yellow]")
                    if 'metadata' not in sample:
                        sample['metadata'] = {}
                    sample['metadata']['remediation'] = 'refusal_kept_no_answer_found'
            
            if 'metadata' not in sample:
                sample['metadata'] = {}
            sample['metadata']['negative_type'] = 'qa_robustness'
            qa_robustness.append(sample)
    
    console.print(f"[green]✅ QA Robustness (Parametric Fallback): {len(qa_robustness)} samples[/green]")
    console.print(f"[green]✅ RC Negative (Refusal): {len(rc_negative)} samples[/green]\n")
    
    return qa_robustness, rc_negative


def generate_report(pure_qa_fixed, cot_fixed, qa_rob, rc_neg) -> Dict:
    """Generate remediation report."""
    report = {
        "remediation_date": "2026-02-08",
        "task": "P3-T04-S8",
        "fixed_counts": {
            "pure_qa": len(pure_qa_fixed),
            "cot": len(cot_fixed),
            "qa_robustness": len(qa_rob),
            "rc_negative": len(rc_neg),
            "total": len(pure_qa_fixed) + len(cot_fixed) + len(qa_rob) + len(rc_neg)
        },
        "negative_split": {
            "qa_robustness_percentage": len(qa_rob) / (len(qa_rob) + len(rc_neg)) * 100 if (len(qa_rob) + len(rc_neg)) > 0 else 0,
            "rc_negative_percentage": len(rc_neg) / (len(qa_rob) + len(rc_neg)) * 100 if (len(qa_rob) + len(rc_neg)) > 0 else 0
        },
        "remediation_actions": {
            "pure_qa": "added_retrieval_background",
            "cot": "added_retrieval_background",
            "qa_robustness": "changed_refusal_to_parametric_fallback",
            "rc_negative": "kept_refusal"
        }
    }
    
    return report


def main():
    """Main entry point."""
    try:
        console.print(Panel(
            "[bold magenta]v2.1 Dataset Format Remediation[/bold magenta]\n"
            "[bold]Task: P3-T04-S8[/bold]\n\n"
            "Fixing format compliance issues identified by RA-DIT evaluation",
            border_style="magenta"
        ))
        
        # Load chunk mapping
        console.print("[cyan]Loading FAISS chunk mapping...[/cyan]")
        chunk_mapping = load_chunk_mapping()
        console.print(f"[green]✅ Loaded {len(chunk_mapping)} chunks[/green]\n")
        
        # Load samples
        console.print("[cyan]Loading samples...[/cyan]")
        pure_qa_samples = load_jsonl(PURE_QA_PATH)
        cot_samples = load_jsonl(COT_PATH)
        negative_samples = load_jsonl(NEGATIVE_PATH)
        console.print(f"  Pure QA: {len(pure_qa_samples)}")
        console.print(f"  CoT: {len(cot_samples)}")
        console.print(f"  Negative: {len(negative_samples)}\n")
        
        # Step 1: Fix Pure QA
        pure_qa_fixed = fix_pure_qa(pure_qa_samples, chunk_mapping)
        save_jsonl(pure_qa_fixed, PURE_QA_FIXED)
        
        # Step 2: Fix CoT
        cot_fixed = fix_cot(cot_samples, chunk_mapping)
        save_jsonl(cot_fixed, COT_FIXED)
        
        # Step 3: Fix Negative Strategy
        qa_rob_fixed, rc_neg_fixed = fix_negative(negative_samples)
        save_jsonl(qa_rob_fixed, QA_ROBUSTNESS_FIXED)
        save_jsonl(rc_neg_fixed, RC_NEGATIVE_FIXED)
        
        # Generate report
        report = generate_report(pure_qa_fixed, cot_fixed, qa_rob_fixed, rc_neg_fixed)
        
        report_path = OUTPUT_DIR / "remediation_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        console.print(f"\n[green]✅ Report saved to: {report_path.relative_to(PROJECT_ROOT)}[/green]")
        
        # Summary
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Category", style="dim")
        table.add_column("Count", justify="right", style="green")
        table.add_column("Action", style="cyan")
        
        table.add_row("Pure QA (Fixed)", f"{len(pure_qa_fixed):,}", "Added retrieval background")
        table.add_row("CoT (Fixed)", f"{len(cot_fixed):,}", "Added retrieval background")
        table.add_row("QA Robustness (Fixed)", f"{len(qa_rob_fixed):,}", "Parametric Fallback")
        table.add_row("RC Negative (Fixed)", f"{len(rc_neg_fixed):,}", "Kept refusal")
        table.add_row("[bold]Total[/bold]", f"[bold]{report['fixed_counts']['total']:,}[/bold]", "")
        
        console.print()
        console.print(table)
        
        console.print(Panel(
            f"[bold green]✅ Remediation Complete![/bold green]\n\n"
            f"Fixed files in: {OUTPUT_DIR.relative_to(PROJECT_ROOT)}\n\n"
            f"[bold]Next Step:[/bold] Re-integrate as v2.2 using:\n"
            f"  Updated Pure QA: {PURE_QA_FIXED.name}\n"
            f"  Updated CoT: {COT_FIXED.name}\n"
            f"  Updated Negative: {QA_ROBUSTNESS_FIXED.name} + {RC_NEGATIVE_FIXED.name}",
            border_style="green"
        ))
        
        sys.exit(0)
        
    except Exception as e:
        console.print(f"\n[bold red]❌ Remediation failed: {e}[/bold red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
