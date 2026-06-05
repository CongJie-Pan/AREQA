#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Golden Cases for Retrieval Evaluation
============================================

This script automatically generates a highly realistic "Golden Set" for evaluating 
the RAG retrieval pipeline. It samples chunks from all 6 categories in the 
`data/rag/source` directory and uses an LLM (via OpenRouter) to generate 
contextually appropriate queries and expected responses.

Output format is fully compatible with `qwen3_retrieval_evaluation.py`.

Usage:
    python scripts/rag/qwen3_Encoder_rag_pipeline/generate_golden_cases.py --samples-per-type 3

Author: RAG Pipeline Team
Date: 2026-03-15
"""

import os
import sys
import json
import random
import argparse
import logging
import requests
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm
from dotenv import load_dotenv

# ============================================================================
# Configuration
# ============================================================================
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "hybrid_smart_chunks.json"
OUTPUT_DIR = PROJECT_ROOT / "data" / "evaluation"
OUTPUT_PATH = OUTPUT_DIR / "golden_cases_rag.json"

random.seed(42)

# Source File Mapping to Match New Source Hierarchy
SOURCE_FILE_MAP = {
    "rc_poems.json": "classical_texts",
    "shijing.jsonl": "classical_texts",
    "examAtricle.json": "exam_materials",
    "redream_full_content.jsonl": "redChamber_text",
    "generated_cai_annotation.jsonl": "scholarly_analysis",
    "qaSynthesisArticle.json": "structured_contents",
    "transfernotesArticle.json": "structured_contents",
    "wiki_red_chamber.json": "wiki"
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Functions
# ============================================================================

def load_and_group_chunks() -> dict:
    """Load chunks and group them by the 6 new categories."""
    logger.info(f"Loading chunks from {CHUNKS_PATH}...")
    if not CHUNKS_PATH.exists():
        logger.error(f"Chunks file not found at {CHUNKS_PATH}")
        sys.exit(1)
        
    with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
        
    grouped = defaultdict(list)
    for chunk in chunks:
        source_type = chunk.get('source_type')
        if not source_type and 'metadata' in chunk:
            source_file = chunk['metadata'].get('source_file', '') or chunk['metadata'].get('source', '')
            if source_file in SOURCE_FILE_MAP:
                source_type = SOURCE_FILE_MAP[source_file]
                
        # Skip chunks that don't belong to any known category
        if not source_type or source_type == 'unknown':
            continue
            
        grouped[source_type].append(chunk)
        
    for k, v in grouped.items():
        logger.info(f"  - {k}: {len(v)} chunks")
        
    return dict(grouped)

def generate_golden_case_via_llm(chunk: dict, source_type: str, api_key: str) -> dict:
    """Call OpenRouter LLM to generate a question and answer for a specific chunk."""
    text = chunk.get('page_content', chunk.get('text', ''))
    if not text or len(text) < 20:
        return None
        
    chunk_id = chunk.get('chunk_id') or chunk.get('metadata', {}).get('chunk_id', 'unknown_chunk')
    doc_id = chunk.get('doc_id') or chunk.get('metadata', {}).get('doc_id', chunk_id)
    
    prompt = f"""你是一位中國古典文學與歷史考試出題專家。
請根據以下提供的文言文或文學相關文本，設計一個高質量的「使用者提問 (query)」與「預期解答 (expected_response)」。

要求：
1. 提問 (query) 必須自然，像是學生的真實發問（例如：「請問這段話的意思是什麼？」、「紅樓夢中關於...的描述是？」、「什麼是...？」）。
2. 解答 (expected_response) 必須精確總結文本內容。
3. 嚴格限以 JSON 格式輸出，不可包含任何其他說明文字！

文本來源分類：{source_type}
文本內容：
{text[:500]}

請輸出JSON格式：
{{
    "query": "你的提問",
    "expected_response": "你的預期解答",
    "type": "reasoning" // 可填寫 fact, reasoning, summary 其中之一
}}
"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen/qwen3-30b-a3b-instruct-2507",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that only outputs strictly valid JSON mapping to the requested schema."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=15)
        if response.ok:
            content = response.json()["choices"][0]["message"]["content"].strip()
            # Clean markdown JSON block if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
                
            res_dict = json.loads(content.strip())
            
            # Format to precisely match qwen3_retrieval_evaluation.py expectations
            return {
                "id": f"golden_q_{chunk_id}",
                "query": res_dict.get("query", "獲取問題失敗"),
                "expected_response": res_dict.get("expected_response", ""),
                "type": res_dict.get("type", "fact"),
                "source_type": source_type,
                "relevant_chunk_ids": [chunk_id],
                "relevant_doc_ids": [doc_id]
            }
    except Exception as e:
        logger.warning(f"LLM API failed for chunk {chunk_id}: {e}")
        
    return None

def main():
    parser = argparse.ArgumentParser(description="Generate Golden Cases for Retrieval Eval")
    parser.add_argument("--samples", type=int, default=3, help="Number of chunks to sample per source category")
    args = parser.parse_args()
    
    load_dotenv()
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.error("No OPENROUTER_API_KEY found in environment variables. Please set it in .env file.")
        sys.exit(1)
        
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    grouped_chunks = load_and_group_chunks()
    
    golden_cases = []
    
    for source_type, chunks in grouped_chunks.items():
        logger.info(f"Generating queries for category: {source_type}")
        sample_size = min(args.samples, len(chunks))
        sampled_chunks = random.sample(chunks, sample_size)
        
        for chunk in tqdm(sampled_chunks, desc=source_type):
            case = generate_golden_case_via_llm(chunk, source_type, api_key)
            if case:
                golden_cases.append(case)
                
    if golden_cases:
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(golden_cases, f, indent=4, ensure_ascii=False)
        logger.info(f"Successfully generated {len(golden_cases)} golden cases.")
        logger.info(f"Saved to {OUTPUT_PATH}")
        logger.info("Next, you can run the evaluation script using this file:")
        logger.info(f"python scripts/rag/qwen3_Encoder_rag_pipeline/qwen3_retrieval_evaluation.py")
    else:
        logger.error("Failed to generate any golden cases.")


if __name__ == "__main__":
    main()