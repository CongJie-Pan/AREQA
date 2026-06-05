#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run RAG Verification Steps (Audit + Retrieval Evaluation)
Usage: python scripts/rag/run_verification.py
"""

import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def run_step(name, command):
    """Run a subprocess step with visual feedback."""
    console.print(Panel(f"[bold cyan]🚀 {name}[/bold cyan]", expand=False))
    
    try:
        # Use shell=True for Windows compatibility
        result = subprocess.run(
            command, 
            cwd=PROJECT_ROOT, 
            shell=True, 
            check=True,
            text=True
        )
        console.print(f"[bold green]✔ {name} 執行成功[/bold green]\n")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]❌ {name} 執行失敗！[/bold red]")
        console.print(f"[red]指令: {command}[/red]")
        console.print(f"[red]錯誤: {e}[/red]")
        sys.exit(1)

def main():
    console.print("[bold]🔄 Starting RAG Verification Process[/bold]")
    console.print(f"[dim]Project Root: {PROJECT_ROOT}[/dim]\n")

    # Step 1: Coverage Audit
    # Maps training questions to retrieved chunks to check recall
    training_data = PROJECT_ROOT / "data" / "training" / "merged" / "all_training_data.jsonl"
    index_dir = PROJECT_ROOT / "data" / "rag" / "faiss_index"
    output_report = PROJECT_ROOT / "output" / "reports" / "rag_coverage_report.json"
    
    audit_cmd = f'python scripts/data_processing/analysis/audit_rag_coverage.py --index_dir "{index_dir}" --training_data "{training_data}" --output "{output_report}"'
    
    run_step(
        "RAG 覆蓋率稽核 (Coverage Audit)",
        audit_cmd
    )

    # Step 2: Retrieval Evaluation
    # Runs automated queries and scores precision/recall
    eval_cmd = "python scripts/rag/evaluation/unified_retrieval_eval.py --export"
    
    run_step(
        "檢索準確度評估 (Retrieval Accuracy Evaluation)",
        eval_cmd
    )

    console.print(Panel("[bold green]✨ 驗證與評估任務已完成！ ✨[/bold green]", title="總結"))

if __name__ == "__main__":
    main()
