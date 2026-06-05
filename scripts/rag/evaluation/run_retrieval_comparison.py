#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Retrieval Comparison Pipeline

This script runs BOTH evaluation pipelines sequentially:
1. BM25 + Reranker (bm25_reranker_eval.py)
2. FAISS Semantic Search (faiss_retrieval_eval.py)

Then generates a unified comparison report.

Why Sequential (Not Parallel)?
==============================
- GPU memory constraint (GTX 1650 4GB)
- Each script loads different models:
  - BM25+Reranker: Only loads Qwen3-Reranker (~1.5GB)
  - FAISS: Only loads Qwen3-Embedding (~1.2GB)
- Running sequentially ensures no OOM errors

What This Script Answers:
=========================
1. BM25 (keyword) vs FAISS (semantic) - Which retrieval base is better?
2. Does Reranker help? (BM25+Reranker vs FAISS-only)
3. Does Query Expansion help? (Expanded vs Baseline)
4. What's the latency trade-off?

Usage:
    python scripts/rag/evaluation/run_retrieval_comparison.py
    python scripts/rag/evaluation/run_retrieval_comparison.py --samples-per-type 5
    python scripts/rag/evaluation/run_retrieval_comparison.py --skip-bm25  # Only run FAISS
    python scripts/rag/evaluation/run_retrieval_comparison.py --skip-faiss # Only run BM25

Author: ML Engineer
Date: 2026-02-02
"""

import os
import sys
import json
import subprocess
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = PROJECT_ROOT / "scripts" / "rag" / "evaluation"
OUTPUT_DIR = PROJECT_ROOT / "output" / "reports" / "retrieval_eval"

# Scripts
BM25_RERANKER_SCRIPT = EVAL_DIR / "bm25_reranker_eval.py"
FAISS_SCRIPT = EVAL_DIR / "faiss_retrieval_eval.py"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_evaluation_script(script_path: Path, samples_per_type: int) -> bool:
    """Run an evaluation script and return success status."""
    logger.info(f"\n{'='*70}")
    logger.info(f"Running: {script_path.name}")
    logger.info(f"{'='*70}")
    
    cmd = [
        sys.executable,
        str(script_path),
        "--strategy", "all",
        "--samples-per-type", str(samples_per_type)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=False,  # Let output show in real-time
            text=True
        )
        
        if result.returncode == 0:
            logger.info(f"✅ {script_path.name} completed successfully")
            return True
        else:
            logger.error(f"❌ {script_path.name} failed with return code {result.returncode}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Failed to run {script_path.name}: {e}")
        return False


def find_latest_report(prefix: str) -> Optional[Path]:
    """Find the latest report file with given prefix."""
    if not OUTPUT_DIR.exists():
        return None
    
    reports = list(OUTPUT_DIR.glob(f"{prefix}_*.json"))
    if not reports:
        return None
    
    # Sort by modification time, get latest
    reports.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return reports[0]


def load_report(report_path: Path) -> Optional[Dict]:
    """Load a JSON report."""
    try:
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {report_path}: {e}")
        return None


def generate_comparison_report(
    bm25_report: Optional[Dict],
    faiss_report: Optional[Dict]
) -> Dict:
    """
    Generate unified comparison report with detailed breakdowns.
    
    This function preserves fine-grained metrics (by_query_type, by_difficulty)
    that are crucial for understanding where each method excels.
    """
    
    timestamp = datetime.now().isoformat()
    
    comparison = {
        "report_date": timestamp,
        "comparison_type": "BM25+Reranker vs FAISS Semantic Search",
        "purpose": "Evaluate keyword matching + neural reranking vs pure semantic similarity",
        "strategies_evaluated": [],
        "unified_ranking": [],
        "by_query_type_comparison": {},  # NEW: Detailed query type breakdown
        "by_difficulty_comparison": {},  # NEW: Detailed difficulty breakdown
        "key_findings": [],
        "recommendations": []
    }
    
    # Collect all strategies with full metrics
    all_strategies = []
    
    # Helper to extract detailed metrics
    def extract_strategy_metrics(report: Dict, pipeline_name: str) -> List[Dict]:
        strategies = []
        for strategy, data in report.get("metrics", {}).items():
            overall = data["overall"]
            strategies.append({
                "strategy": f"{pipeline_name}: {strategy}",
                "pipeline": pipeline_name,
                "strategy_name": strategy,
                "mrr": overall["mrr"],
                "mrr_ci_low": overall["mrr_ci_low"],
                "mrr_ci_high": overall["mrr_ci_high"],
                "hit@1": overall.get("hit@1", 0),
                "hit@5": overall.get("hit@5", 0),
                "hit@10": overall["hit@10"],
                "hit@20": overall.get("hit@20", 0),
                "latency_ms": overall["avg_latency_ms"],
                "p95_latency_ms": overall.get("p95_latency_ms", 0),
                "by_query_type": data.get("by_query_type", {}),
                "by_difficulty": data.get("by_difficulty", {}),
                "by_source_type": data.get("by_source_type", {})
            })
            comparison["strategies_evaluated"].append(f"{pipeline_name}_{strategy}")
        return strategies
    
    if bm25_report:
        all_strategies.extend(extract_strategy_metrics(bm25_report, "BM25+Reranker"))
    
    if faiss_report:
        all_strategies.extend(extract_strategy_metrics(faiss_report, "FAISS"))
    
    # Sort by MRR
    all_strategies.sort(key=lambda x: x["mrr"], reverse=True)
    comparison["unified_ranking"] = all_strategies
    
    # ============================================================================
    # NEW: Generate Query Type Comparison (Critical for understanding strengths)
    # ============================================================================
    query_types = set()
    for s in all_strategies:
        query_types.update(s.get("by_query_type", {}).keys())
    
    for qt in query_types:
        comparison["by_query_type_comparison"][qt] = {
            "description": _get_query_type_description(qt),
            "strategies": []
        }
        for s in all_strategies:
            qt_data = s.get("by_query_type", {}).get(qt, {})
            if qt_data:
                comparison["by_query_type_comparison"][qt]["strategies"].append({
                    "strategy": s["strategy"],
                    "mrr": qt_data.get("mrr", 0),
                    "hit@10": qt_data.get("hit@10", 0),
                    "count": qt_data.get("count", 0)
                })
        # Sort by MRR within each query type
        comparison["by_query_type_comparison"][qt]["strategies"].sort(
            key=lambda x: x["mrr"], reverse=True
        )
    
    # ============================================================================
    # NEW: Generate Difficulty Comparison
    # ============================================================================
    difficulties = ["easy", "medium", "hard"]
    for diff in difficulties:
        comparison["by_difficulty_comparison"][diff] = {"strategies": []}
        for s in all_strategies:
            diff_data = s.get("by_difficulty", {}).get(diff, {})
            if diff_data:
                comparison["by_difficulty_comparison"][diff]["strategies"].append({
                    "strategy": s["strategy"],
                    "mrr": diff_data.get("mrr", 0),
                    "hit@10": diff_data.get("hit@10", 0),
                    "count": diff_data.get("count", 0)
                })
        comparison["by_difficulty_comparison"][diff]["strategies"].sort(
            key=lambda x: x["mrr"], reverse=True
        )
    
    # ============================================================================
    # Generate Key Findings
    # ============================================================================
    if all_strategies:
        best = all_strategies[0]
        comparison["key_findings"].append(
            f"🏆 Best Overall: {best['strategy']} (MRR: {best['mrr']:.4f}, Hit@10: {best['hit@10']:.1%})"
        )
        
        # Best for each query type
        for qt, qt_data in comparison["by_query_type_comparison"].items():
            if qt_data["strategies"]:
                best_qt = qt_data["strategies"][0]
                comparison["key_findings"].append(
                    f"📝 Best for '{qt}' queries: {best_qt['strategy']} (MRR: {best_qt['mrr']:.4f})"
                )
        
        # Compare BM25 vs FAISS best
        bm25_best = next((s for s in all_strategies if s["pipeline"] == "BM25+Reranker"), None)
        faiss_best = next((s for s in all_strategies if s["pipeline"] == "FAISS"), None)
        
        if bm25_best and faiss_best:
            if bm25_best["mrr"] > faiss_best["mrr"]:
                diff = (bm25_best["mrr"] - faiss_best["mrr"]) / faiss_best["mrr"] * 100 if faiss_best["mrr"] > 0 else 0
                comparison["key_findings"].append(
                    f"📊 BM25+Reranker outperforms FAISS by {diff:.1f}% overall"
                )
            else:
                diff = (faiss_best["mrr"] - bm25_best["mrr"]) / bm25_best["mrr"] * 100 if bm25_best["mrr"] > 0 else 0
                comparison["key_findings"].append(
                    f"📊 FAISS outperforms BM25+Reranker by {diff:.1f}% overall"
                )
            
            # Latency comparison
            if bm25_best["latency_ms"] < faiss_best["latency_ms"]:
                comparison["key_findings"].append(
                    f"⚡ BM25+Reranker is faster ({bm25_best['latency_ms']:.0f}ms vs {faiss_best['latency_ms']:.0f}ms)"
                )
            else:
                comparison["key_findings"].append(
                    f"⚡ FAISS is faster ({faiss_best['latency_ms']:.0f}ms vs {bm25_best['latency_ms']:.0f}ms)"
                )
    
    # Generate recommendations based on query type analysis
    _generate_recommendations(comparison)
    
    return comparison


def _get_query_type_description(qt: str) -> str:
    """Get human-readable description for query type."""
    descriptions = {
        "keyword": "Direct keyword matching (e.g., '賈寶玉 林黛玉')",
        "summary": "Natural language summary queries",
        "semantic": "Question-format semantic queries (e.g., '什麼是紅樓夢的主題？')",
        "keyword_question": "Keyword-based questions (e.g., '關於賈寶玉的內容')"
    }
    return descriptions.get(qt, f"Query type: {qt}")


def _generate_recommendations(comparison: Dict):
    """Generate actionable recommendations based on analysis."""
    qt_comparison = comparison.get("by_query_type_comparison", {})
    
    # Check if FAISS excels at semantic queries
    semantic_data = qt_comparison.get("semantic", {})
    keyword_data = qt_comparison.get("keyword", {})
    
    if semantic_data.get("strategies") and keyword_data.get("strategies"):
        semantic_best = semantic_data["strategies"][0]
        keyword_best = keyword_data["strategies"][0]
        
        if "FAISS" in semantic_best["strategy"] and "BM25" in keyword_best["strategy"]:
            comparison["recommendations"].append(
                "🔀 Consider Hybrid Routing: Use BM25 for keyword-heavy queries, FAISS for semantic queries"
            )
        
    # Check overall performance
    if comparison["unified_ranking"]:
        best = comparison["unified_ranking"][0]
        if "hybrid" in best["strategy"].lower() or "rrf" in best.get("strategy_name", "").lower():
            comparison["recommendations"].append(
                "✅ Hybrid fusion (RRF) shows best results - recommend for production"
            )
        elif "reranker" in best["strategy"].lower():
            comparison["recommendations"].append(
                "✅ BM25+Reranker excels - neural reranking adds significant value"
            )
        elif "faiss_only" in best.get("strategy_name", ""):
            comparison["recommendations"].append(
                "✅ Pure semantic search is sufficient - Reranker overhead may not be justified"
            )


def save_comparison_report(report: Dict):
    """Save the unified comparison report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON
    json_path = OUTPUT_DIR / f"unified_comparison_{timestamp}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"Unified report saved: {json_path}")
    
    # Markdown
    md_path = OUTPUT_DIR / f"unified_comparison_{timestamp}.md"
    md_content = generate_markdown(report)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    logger.info(f"Markdown saved: {md_path}")
    
    return json_path, md_path


def generate_markdown(report: Dict) -> str:
    """Generate comprehensive markdown report with query type breakdowns."""
    lines = [
        "# Unified Retrieval Comparison Report",
        "",
        f"**Date**: {report['report_date']}",
        f"**Comparison**: {report['comparison_type']}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "### Key Findings",
        ""
    ]
    
    for finding in report.get("key_findings", []):
        lines.append(f"- {finding}")
    
    lines.extend([
        "",
        "### Recommendations",
        ""
    ])
    
    for rec in report.get("recommendations", []):
        lines.append(f"- {rec}")
    
    lines.extend([
        "",
        "---",
        "",
        "## Overall Strategy Ranking",
        "",
        "| Rank | Strategy | MRR (95% CI) | Hit@1 | Hit@5 | Hit@10 | Latency |",
        "|------|----------|--------------|-------|-------|--------|---------|"
    ])
    
    for i, strategy in enumerate(report.get("unified_ranking", []), 1):
        ci = f"{strategy.get('mrr_ci_low', 0):.3f}-{strategy.get('mrr_ci_high', 0):.3f}"
        lines.append(
            f"| {i} | {strategy['strategy']} | "
            f"{strategy['mrr']:.4f} ({ci}) | "
            f"{strategy.get('hit@1', 0):.1%} | "
            f"{strategy.get('hit@5', 0):.1%} | "
            f"{strategy['hit@10']:.1%} | "
            f"{strategy['latency_ms']:.0f}ms |"
        )
    
    # ============================================================================
    # NEW: Query Type Breakdown (Critical Analysis Section)
    # ============================================================================
    lines.extend([
        "",
        "---",
        "",
        "## 📊 Performance by Query Type",
        "",
        "> This section reveals where each retrieval method excels.",
        "> - **keyword**: Direct keyword matching (easy difficulty)",
        "> - **summary**: Natural language queries (medium difficulty)",
        "> - **semantic**: Question-format queries (hard difficulty)",
        ""
    ])
    
    qt_comparison = report.get("by_query_type_comparison", {})
    for qt, qt_data in qt_comparison.items():
        if not qt_data.get("strategies"):
            continue
        
        lines.extend([
            f"### Query Type: `{qt}`",
            "",
            f"*{qt_data.get('description', '')}*",
            "",
            "| Rank | Strategy | MRR | Hit@10 | Samples |",
            "|------|----------|-----|--------|---------|"
        ])
        
        for i, s in enumerate(qt_data["strategies"], 1):
            lines.append(
                f"| {i} | {s['strategy']} | {s['mrr']:.4f} | {s['hit@10']:.1%} | {s['count']} |"
            )
        
        # Add insight
        if qt_data["strategies"]:
            best = qt_data["strategies"][0]
            lines.extend([
                "",
                f"**Winner for {qt}**: {best['strategy']} (MRR: {best['mrr']:.4f})",
                ""
            ])
    
    # ============================================================================
    # NEW: Difficulty Breakdown
    # ============================================================================
    lines.extend([
        "",
        "---",
        "",
        "## 📈 Performance by Difficulty Level",
        ""
    ])
    
    diff_comparison = report.get("by_difficulty_comparison", {})
    for diff in ["easy", "medium", "hard"]:
        diff_data = diff_comparison.get(diff, {})
        if not diff_data.get("strategies"):
            continue
        
        emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(diff, "")
        lines.extend([
            f"### {emoji} Difficulty: `{diff}`",
            "",
            "| Rank | Strategy | MRR | Hit@10 | Samples |",
            "|------|----------|-----|--------|---------|"
        ])
        
        for i, s in enumerate(diff_data["strategies"], 1):
            lines.append(
                f"| {i} | {s['strategy']} | {s['mrr']:.4f} | {s['hit@10']:.1%} | {s['count']} |"
            )
        lines.append("")
    
    lines.extend([
        "",
        "---",
        "",
        "## Methodology",
        "",
        "### BM25 + Reranker Pipeline",
        "1. **BM25 Retrieval**: Character-level tokenization, TF-IDF based scoring",
        "2. **Qwen3-Reranker**: Cross-encoder neural reranking of top candidates",
        "",
        "### FAISS Pipeline",
        "1. **Query Encoding**: Qwen3-Embedding encodes query to 1024-dim vector",
        "2. **Vector Search**: FAISS IndexFlatIP for inner product similarity",
        "3. **Hybrid (RRF)**: Reciprocal Rank Fusion combines FAISS + BM25 rankings",
        "",
        "### Query Generation Strategy",
        "- **Easy (keyword)**: Direct keywords from chunk metadata",
        "- **Medium (summary)**: Natural language summaries",
        "- **Hard (semantic)**: LLM-rewritten question-format queries",
        "",
        "### Why This Comparison Matters",
        "- **BM25**: Excels at exact keyword matching (e.g., '賈寶玉')",
        "- **FAISS**: Excels at semantic similarity (e.g., '紅樓夢主角' → 賈寶玉)",
        "- **Hybrid RRF**: Combines both strengths without score normalization issues",
        "",
        "---",
        "",
        "*Generated by run_retrieval_comparison.py*"
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Complete Retrieval Comparison Pipeline")
    parser.add_argument(
        "--samples-per-type",
        type=int,
        default=5,
        help="Samples per source type (default: 5)"
    )
    parser.add_argument(
        "--skip-bm25",
        action="store_true",
        help="Skip BM25+Reranker evaluation"
    )
    parser.add_argument(
        "--skip-faiss",
        action="store_true",
        help="Skip FAISS evaluation"
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("COMPLETE RETRIEVAL COMPARISON PIPELINE")
    print("=" * 70)
    print(f"Samples per type: {args.samples_per_type}")
    print(f"Run BM25+Reranker: {not args.skip_bm25}")
    print(f"Run FAISS: {not args.skip_faiss}")
    print("=" * 70)
    
    bm25_success = False
    faiss_success = False
    
    # Run BM25 + Reranker evaluation
    if not args.skip_bm25:
        if BM25_RERANKER_SCRIPT.exists():
            bm25_success = run_evaluation_script(BM25_RERANKER_SCRIPT, args.samples_per_type)
        else:
            logger.error(f"Script not found: {BM25_RERANKER_SCRIPT}")
    else:
        logger.info("Skipping BM25+Reranker evaluation")
    
    # Run FAISS evaluation
    if not args.skip_faiss:
        if FAISS_SCRIPT.exists():
            faiss_success = run_evaluation_script(FAISS_SCRIPT, args.samples_per_type)
        else:
            logger.error(f"Script not found: {FAISS_SCRIPT}")
    else:
        logger.info("Skipping FAISS evaluation")
    
    # Load reports and generate comparison
    print("\n" + "=" * 70)
    print("GENERATING UNIFIED COMPARISON REPORT")
    print("=" * 70)
    
    bm25_report = None
    faiss_report = None
    
    if bm25_success:
        bm25_report_path = find_latest_report("lightweight_eval")
        if bm25_report_path:
            bm25_report = load_report(bm25_report_path)
            logger.info(f"Loaded BM25 report: {bm25_report_path.name}")
    
    if faiss_success:
        faiss_report_path = find_latest_report("faiss_eval")
        if faiss_report_path:
            faiss_report = load_report(faiss_report_path)
            logger.info(f"Loaded FAISS report: {faiss_report_path.name}")
    
    if bm25_report or faiss_report:
        comparison = generate_comparison_report(bm25_report, faiss_report)
        json_path, md_path = save_comparison_report(comparison)
        
        # Print summary
        print("\n" + "=" * 70)
        print("COMPARISON COMPLETE")
        print("=" * 70)
        
        print("\n📊 UNIFIED RANKING:")
        for i, s in enumerate(comparison.get("unified_ranking", [])[:5], 1):
            print(f"  {i}. {s['strategy']}")
            print(f"     MRR: {s['mrr']:.4f} | Hit@10: {s['hit@10']:.1%} | Latency: {s['latency_ms']:.0f}ms")
        
        print("\n🔍 KEY FINDINGS:")
        for finding in comparison.get("key_findings", []):
            print(f"  {finding}")
        
        print("\n✅ RECOMMENDATIONS:")
        for rec in comparison.get("recommendations", []):
            print(f"  {rec}")
        
        print("\n" + "=" * 70)
        print(f"📁 Reports saved to: {OUTPUT_DIR}")
        print("=" * 70)
    else:
        logger.error("No reports generated. Please check individual script outputs.")
        sys.exit(1)


if __name__ == "__main__":
    main()
