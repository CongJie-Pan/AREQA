"""
Debug script to identify why BM25+Reranker produced 0.0 metrics.
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "rag" / "evaluation"))

# Load the report
REPORT_PATH = PROJECT_ROOT / "output" / "reports" / "retrieval_eval" / "lightweight_eval_20260202_190337.json"

with open(REPORT_PATH, 'r', encoding='utf-8') as f:
    report = json.load(f)

print("=" * 70)
print("BM25 RERANKER EVALUATION FAILURE ANALYSIS")
print("=" * 70)

for strategy, metrics in report["metrics"].items():
    overall = metrics["overall"]
    print(f"\n{strategy.upper()}:")
    print(f"  Total Queries: {overall['total_queries']}")
    print(f"  MRR: {overall['mrr']}")
    print(f"  Hit@10: {overall['hit@10']}")
    print(f"  Avg Latency: {overall['avg_latency_ms']}ms")
    
    if overall['mrr'] == 0.0 and overall['avg_latency_ms'] == 0.0:
        print("  ❌ COMPLETE FAILURE: All queries returned empty results")
        print("     Likely cause: Exception in rerank() method caught by evaluation loop")

print("\n" + "=" * 70)
print("RECOMMENDATION:")
print("=" * 70)
print("Run with error logging enabled to see actual exception:")
print("  python scripts/rag/evaluation/bm25_reranker_eval.py --samples-per-type 1")
print("=" * 70)
