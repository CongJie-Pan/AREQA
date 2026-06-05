#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chunk 品質驗證腳本
六維度驗證架構
"""

import re
import difflib
from datetime import datetime
import json
import logging
import numpy as np

# ============== 新增 Rich 終端顯示 ==============
from rich.logging import RichHandler
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import track

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("quality_gate")
# ==============================================

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
    
# 取決於環境，有可能需要額外的模型：

# Dimension 1：Source Fidelity
def remove_contextual_prefix(chunk_text: str) -> str:
    """
    從 chunk 中移除 Tier 3 加上的 contextual prefix，以便比對原始文本。
    """
    clean_text = chunk_text
    
    # 移除 AI 動態脈絡前綴
    ai_prefix_pattern = r"^【AI 動態脈絡】：.*?\n"
    clean_text = re.sub(ai_prefix_pattern, "", clean_text)
    
    # 移除章節脈絡前綴
    chapter_prefix_pattern = r"^此段落的章節脈絡為：.*?\n\n"
    clean_text = re.sub(chapter_prefix_pattern, "", clean_text)
    
    return clean_text.strip()

def verify_source_fidelity(chunk_text: str, original_text: str, threshold: float = 0.85) -> dict:
    """
    驗證 chunk 文字是否為原始文件的子字串。
    使用 SequenceMatcher 計算最長公共子序列比率。
    """
    # 先移除 Tier 3 加上的 contextual prefix
    clean_chunk = remove_contextual_prefix(chunk_text)
    
    # 精確子字串匹配（最嚴格）
    exact_match = clean_chunk in original_text
    
    # 模糊匹配（容忍微小差異，如換行符變化）
    matcher = difflib.SequenceMatcher(None, clean_chunk, original_text)
    best_match = matcher.find_longest_match(0, len(clean_chunk), 0, len(original_text))
    coverage_ratio = best_match.size / len(clean_chunk) if clean_chunk else 0
    
    return {
        "exact_match": exact_match,
        "coverage_ratio": coverage_ratio,
        "pass": exact_match or coverage_ratio >= threshold,
        "flag": "HALLUCINATION_RISK" if coverage_ratio < threshold else "OK"
    }

# Dimension 2：Artifact Detection
ARTIFACT_PATTERNS = [
    r"古文數據增強助手",
    r"以下[是為].*?(整理|摘要|分析|重點)",
    r"作為[一個]?AI",
    r"潛在搜尋問句",
    r"白話文摘要",
    r"任務要求",
    r"好的[，,]",
    r"請注意[，,].*?截止",
    r"以上是.*?的(回答|分析|摘要)",
    r"split_after",  # LLM boundary detection 的指令洩漏
]

def detect_artifacts(chunk_text: str) -> dict:
    found = []
    for pattern in ARTIFACT_PATTERNS:
        if re.search(pattern, chunk_text):
            found.append(pattern)
    return {
        "clean": len(found) == 0,
        "artifacts_found": found,
        "flag": "CONTAMINATED" if found else "CLEAN"
    }

# Dimension 3：Length Distribution
def analyze_length_distribution(chunks: list, min_len=50, max_len=1500) -> dict:
    lengths = [len(c["page_content"]) for c in chunks]
    
    if not lengths:
        return {
            "total_chunks": 0,
            "pass": False
        }
    
    too_short = [i for i, l in enumerate(lengths) if l < min_len]
    too_long = [i for i, l in enumerate(lengths) if l > max_len]
    
    mean_len = sum(lengths) / len(lengths)
    variance = sum((l - mean_len)**2 for l in lengths) / len(lengths)
    
    return {
        "total_chunks": len(chunks),
        "mean_length": mean_len,
        "median_length": sorted(lengths)[len(lengths)//2],
        "std_length": variance ** 0.5,
        "too_short_indices": too_short,
        "too_long_indices": too_long,
        "outlier_ratio": (len(too_short) + len(too_long)) / len(chunks),
        "pass": (len(too_short) + len(too_long)) / len(chunks) < 0.1  # 異常率 < 10%
    }

# Dimension 4：Semantic Coherence
def check_semantic_coherence(chunk_text: str, model) -> dict:
    """計算 chunk 內句子間的最小 cosine similarity"""
    if model is None:
        return {"coherence_score": 1.0, "pass": True, "note": "Model not loaded"}
        
    sentences = re.split(r'[。！？\n]+', chunk_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    
    if len(sentences) < 2:
        return {"coherence_score": 1.0, "pass": True}
    
    embeddings = model.encode(sentences)
    min_sim = 1.0
    for i in range(len(embeddings) - 1):
        norm_a = np.linalg.norm(embeddings[i])
        norm_b = np.linalg.norm(embeddings[i+1])
        if norm_a == 0 or norm_b == 0:
            sim = 0
        else:
            sim = np.dot(embeddings[i], embeddings[i+1]) / (norm_a * norm_b)
        min_sim = min(min_sim, sim)
    
    return {
        "coherence_score": float(min_sim),
        "pass": min_sim > 0.3,  # 閾值：最低相似度 > 0.3
        "flag": "INCOHERENT" if min_sim <= 0.3 else "OK"
    }

# Dimension 5：Golden Set Retrieval
def retrieve_top_k(query: str, chunks: list, embedding_model, k: int=5) -> list:
    """一個簡單的基於 cosine similarity 的檢索示範"""
    if not chunks or embedding_model is None:
        return []
    
    query_emb = embedding_model.encode([query])[0]
    chunk_texts = [c["page_content"] for c in chunks]
    chunk_embs = embedding_model.encode(chunk_texts)
    
    scores = []
    for i, emb in enumerate(chunk_embs):
        norm_q = np.linalg.norm(query_emb)
        norm_c = np.linalg.norm(emb)
        
        if norm_q == 0 or norm_c == 0:
            score = 0
        else:
            score = np.dot(query_emb, emb) / (norm_q * norm_c)
        scores.append((score, chunks[i]))
        
    scores.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scores[:k]]

def evaluate_golden_set(chunks, embedding_model, test_set, top_k=5):
    """使用黃金測試集計算 Recall@k"""
    if not test_set or embedding_model is None:
        return {"mean_keyword_recall": 0, "detail": []}
        
    results = []
    for test in test_set:
        retrieved = retrieve_top_k(test["query"], chunks, embedding_model, k=top_k)
        
        # Keyword-level recall
        retrieved_text = " ".join([c["page_content"] for c in retrieved])
        keyword_hits = sum(1 for kw in test["expected_keywords"] if kw in retrieved_text)
        keyword_recall = keyword_hits / len(test["expected_keywords"]) if test["expected_keywords"] else 0
        
        results.append({
            "query": test["query"],
            "keyword_recall": keyword_recall,
            "pass": keyword_recall >= 0.8
        })
    
    avg_recall = sum(r["keyword_recall"] for r in results) / len(results) if results else 0
    return {"mean_keyword_recall": avg_recall, "detail": results}

# Dimension 6：Coverage & Overlap
def check_coverage(chunks, original_text: str) -> dict:
    """檢查 chunks 是否覆蓋原始文件的所有內容"""
    covered_chars = set()
    for chunk in chunks:
        clean = remove_contextual_prefix(chunk["page_content"])
        start = original_text.find(clean[:50])  # 用前 50 字定位
        if start >= 0:
            covered_chars.update(range(start, start + len(clean)))
    
    # 移除空白字元後計算覆蓋率
    meaningful_chars = set(i for i, c in enumerate(original_text) if not c.isspace())
    coverage = len(covered_chars & meaningful_chars) / len(meaningful_chars) if meaningful_chars else 0
    
    return {
        "coverage_ratio": coverage,
        "pass": coverage >= 0.95,  # 至少覆蓋 95% 的有意義文字
        "gap_count": len(meaningful_chars - covered_chars)
    }

# 整合：品質閘門腳本
def quality_gate(chunks, original_texts, embedding_model=None, golden_set=None):
    """
    品質閘門：評估六種維度
    """
    if golden_set is None:
        golden_set = []
        
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_chunks": len(chunks),
        "dimensions": {}
    }
    
    # Dim 1: Source Fidelity
    logger.info("Evaluating Source Fidelity...")
    fidelity_results = [verify_source_fidelity(c["page_content"], orig) 
                        for c, orig in track(zip(chunks, original_texts), total=len(chunks), description="Fidelity")]
    fidelity_pass_rate = sum(1 for r in fidelity_results if r["pass"]) / len(fidelity_results) if fidelity_results else 0
    report["dimensions"]["source_fidelity"] = {
        "pass_rate": fidelity_pass_rate,
        "details": fidelity_results
    }
    
    # Dim 2: Artifact Detection
    logger.info("Evaluating Artifact Detection...")
    artifact_results = [detect_artifacts(c["page_content"]) for c in track(chunks, description="Artifacts")]
    contamination_rate = sum(1 for r in artifact_results if not r["clean"]) / len(artifact_results) if artifact_results else 0
    report["dimensions"]["artifact_detection"] = {
        "contamination_rate": contamination_rate,
        "details": artifact_results
    }
    
    # Dim 3: Length Distribution
    logger.info("Evaluating Length Distribution...")
    length_report = analyze_length_distribution(chunks)
    report["dimensions"]["length_distribution"] = length_report
    
    # Dim 4: Semantic Coherence
    logger.info("Evaluating Semantic Coherence...")
    coherence_results = [check_semantic_coherence(c["page_content"], embedding_model) for c in track(chunks, description="Coherence")]
    coherence_pass_rate = sum(1 for r in coherence_results if r["pass"]) / len(coherence_results) if coherence_results else 0
    report["dimensions"]["semantic_coherence"] = {
        "pass_rate": coherence_pass_rate,
        "details": coherence_results
    }
    
    # Dim 5: Golden Set Retrieval
    logger.info("Evaluating Golden Set Retrieval...")
    golden_eval_report = evaluate_golden_set(chunks, embedding_model, golden_set)
    report["dimensions"]["golden_set"] = golden_eval_report
    
    # Dim 6: Coverage
    logger.info("Evaluating Coverage...")
    # Group original texts by doc_id to match with chunks based on doc_id
    # Since quality_gate signature expects lists mapped together, we assume simplistic 1-to-1 processing in batch
    # Or for simplify, just measure overall coverage for one big document
    # A robust approach loops over chunks and a single original doc text
    # Assuming original_texts is a single string or chunks belong to one original string here:
    if isinstance(original_texts, list) and len(original_texts) > 0:
        coverage_report = check_coverage(chunks, "".join(original_texts))
    elif isinstance(original_texts, str):
        coverage_report = check_coverage(chunks, original_texts)
    else:
        coverage_report = {"coverage_ratio": 0, "pass": False, "gap_count": 0}
        
    report["dimensions"]["coverage"] = coverage_report
    
    # 最終決策
    gate_passed = (
        fidelity_pass_rate >= 0.95 and        # 95% chunk 來源可驗證
        contamination_rate == 0.0 and         # 零容忍汙染
        length_report.get("outlier_ratio", 1.0) < 0.1  # 異常長度 < 10%
    )
    
    report["gate_passed"] = gate_passed
    return report

def print_quality_report(report: dict):
    """
    使用 Rich 格式化輸出品質報告
    """
    gate_color = "green" if report["gate_passed"] else "red"
    gate_status = "[PASSED]" if report["gate_passed"] else "[FAILED]"
    
    console.print(Panel(
        f"[bold {gate_color}]Quality Gate Status: {gate_status}[/bold {gate_color}]\n"
        f"Total Chunks Analyzed: {report['total_chunks']}\n"
        f"Timestamp: {report['timestamp']}",
        title="[bold cyan]Chunking Quality Report",
        expand=False
    ))
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Dimension", style="dim", width=25)
    table.add_column("Result / Metric", justify="left")
    table.add_column("Status", justify="center")
    
    # Dim 1: Fidelity
    fidelity_rate = report["dimensions"]["source_fidelity"]["pass_rate"]
    f_status = "[green]Pass" if fidelity_rate >= 0.95 else "[red]Fail"
    table.add_row("1. Source Fidelity", f"Pass Rate: {fidelity_rate:.1%}", f_status)
    
    # Dim 2: Artifacts
    contam_rate = report["dimensions"]["artifact_detection"]["contamination_rate"]
    a_status = "[green]Pass" if contam_rate == 0 else "[red]Fail"
    table.add_row("2. Artifact Detection", f"Contamination: {contam_rate:.1%}", a_status)
    
    # Dim 3: Length
    length_rep = report["dimensions"]["length_distribution"]
    if length_rep.get("total_chunks", 0) > 0:
        l_outlier = length_rep.get("outlier_ratio", 1.0)
        l_status = "[green]Pass" if l_outlier < 0.1 else "[red]Fail"
        table.add_row("3. Length Distribution", 
                      f"Mean: {length_rep.get('mean_length', 0):.0f} chars\nOutliers: {l_outlier:.1%}", 
                      l_status)
    else:
        table.add_row("3. Length Distribution", "No chunks", "[yellow]N/A")
        
    # Dim 4: Coherence
    coherence_rate = report["dimensions"]["semantic_coherence"]["pass_rate"]
    c_status = "[green]Pass" if coherence_rate >= 0.8 else "[yellow]Warn"
    table.add_row("4. Semantic Coherence", f"Pass Rate: {coherence_rate:.1%}", c_status)
    
    # Dim 5: Golden Set
    golden_recall = report["dimensions"]["golden_set"]["mean_keyword_recall"]
    g_status = "[green]Pass" if golden_recall >= 0.8 else "[yellow]Warn"
    table.add_row("5. Golden Set Retrieval", f"Mean Recall: {golden_recall:.1%}", g_status)
    
    # Dim 6: Coverage
    coverage_ratio = report["dimensions"]["coverage"]["coverage_ratio"]
    cov_status = "[green]Pass" if coverage_ratio >= 0.95 else "[red]Fail"
    table.add_row("6. Coverage & Overlap", f"Coverage Ratio: {coverage_ratio:.1%}", cov_status)
    
    console.print(table)
    console.print()

import argparse
import sys
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks_file", type=str, default="")
    parser.add_argument("--source_dir", type=str, default="data/rag/source")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not args.chunks_file:
        # Dynamically find the latest chunks file
        chunks_dir = Path("data/rag/chunks")
        all_chunks = list(chunks_dir.glob("hybrid_smart_chunks*.json"))
        if not all_chunks:
            logger.error("No chunks file found in data/rag/chunks/")
            sys.exit(1)
        chunks_path = sorted(all_chunks, key=lambda x: x.stat().st_mtime)[-1]
    else:
        chunks_path = Path(args.chunks_file)

    if not chunks_path.exists():
        logger.error(f"Chunks file not found: {chunks_path}")
        sys.exit(1)

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    if args.limit:
        chunks = chunks[:args.limit]
        logger.info(f"Limiting quality gate to {args.limit} chunks.")

    # Reconstruct original texts
    original_texts = []
    source_dir = Path(args.source_dir)
    
    # Simple cache to avoid reading the same file repeatedly
    _cache = {}
    
    for c in chunks:
        # Assuming run_hybrid_batch.py structure where metadata includes 'source' or 'source_file'
        src_name = c.get("metadata", {}).get("source_file", "") or c.get("metadata", {}).get("source", "")
        # fallback if not found
        if not src_name:
            original_texts.append(c.get("page_content", ""))
            continue
            
        if src_name not in _cache:
            # Perform a recursive search to find the file in subdirectories
            found_paths = list(source_dir.rglob(src_name))
            if found_paths and found_paths[0].is_file():
                possible_path = found_paths[0]
                with open(possible_path, "r", encoding="utf-8") as bf:
                    raw_content = bf.read()
                    if possible_path.suffix == '.jsonl':
                        texts = []
                        for row in raw_content.strip().split('\n'):
                            if not row.strip(): continue
                            try:
                                data = json.loads(row)
                                for n in data.get("nodes", [{}]):
                                    c1 = n.get("content", {})
                                    t1 = c1 if isinstance(c1, str) else c1.get("text", "") if isinstance(c1, dict) else ""
                                    c2 = data.get("content", {})
                                    t2 = c2 if isinstance(c2, str) else c2.get("text", "") if isinstance(c2, dict) else ""
                                    texts.append(t1 or t2)
                            except json.JSONDecodeError: continue
                        _cache[src_name] = "\n".join(texts)
                    elif possible_path.suffix == '.json':
                        try:
                            dlist = json.loads(raw_content)
                            if isinstance(dlist, dict): dlist = [dlist]
                            texts = []
                            for data in dlist:
                                for n in data.get("nodes", [{}]):
                                    c1 = n.get("content", {})
                                    t1 = c1 if isinstance(c1, str) else c1.get("text", "") if isinstance(c1, dict) else ""
                                    c2 = data.get("content", {})
                                    t2 = c2 if isinstance(c2, str) else c2.get("text", "") if isinstance(c2, dict) else ""
                                    texts.append(t1 or t2)
                            _cache[src_name] = "\n".join(texts)
                        except json.JSONDecodeError:
                            _cache[src_name] = raw_content
                    else:
                        _cache[src_name] = raw_content
            else:
                _cache[src_name] = "" # Not found or unsupported format inside directly
                logger.warning(f"Source file not found in source_dir: {src_name}")
        
        original_texts.append(_cache[src_name])

    report = quality_gate(chunks, original_texts)
    print_quality_report(report)

    if not report["gate_passed"]:
        logger.error("[FAILED] Quality Gate Failed!")
        sys.exit(1)
    else:
        logger.info("[PASSED] Quality Gate Passed!")

if __name__ == "__main__":
    main()
