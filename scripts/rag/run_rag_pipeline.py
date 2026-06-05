#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified RAG Pipeline Manager (Interactive)
=====================================
Orchestrates the complete RAG update process with interactive mode selection.
Features:
1. Data Batch Chunking
2. Indexing (BGE-M3 & BM25)
3. Verification (Audit & Evaluation)

Usage:
    python scripts/rag/run_rag_pipeline.py
"""

import sys
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown

# Setup
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

console = Console()

def run_step(name, command, cwd=None):
    """Run a subprocess step with visual feedback."""
    console.print(Panel(f"[bold cyan]🚀 {name}[/bold cyan]", expand=False))
    
    try:
        # Use shell=True for Windows compatibility with python commands
        result = subprocess.run(
            command, 
            cwd=cwd or PROJECT_ROOT, 
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
        if not Confirm.ask("是否要忽略錯誤並繼續執行下一步？", default=False):
            return False
        return True

def step_chunking():
    """Run Data Batch Chunking"""
    return run_step(
        "資料分塊處理 (Data Batch Chunking)",
        "python scripts/data_processing/transformers/chunk_documents_batch.py"
    )

def step_indexing():
    """Run Indexing (BGE-M3 + BM25)"""
    success = run_step(
        "BGE-M3 向量索引建置 (Vector Indexing)", 
        "python scripts/rag/indexing/p2_t09_bge_m3_indexer.py"
    )
    if not success: return False
    
    return run_step(
        "BM25 關鍵字索引建置 (Keyword Indexing)", 
        "python scripts/rag/indexing/p2_t10_bm25_indexer.py"
    )

def step_verification():
    """Run Verification (Audit + Evaluation)"""
    training_data = PROJECT_ROOT / "data" / "training" / "merged" / "all_training_data.jsonl"
    index_dir = PROJECT_ROOT / "data" / "rag" / "faiss_index"
    output_report = PROJECT_ROOT / "output" / "reports" / "rag_coverage_report.json"
    
    if not training_data.exists():
        console.print(f"[red]未找到訓練資料: {training_data}[/red]")
    else:
        success = run_step(
            "RAG 覆蓋率稽核 (Coverage Audit)",
            f'python scripts/data_processing/analysis/audit_rag_coverage.py --index_dir "{index_dir}" --training_data "{training_data}" --output "{output_report}"'
        )
        if not success: return False

    return run_step(
        "檢索準確度評估 (Retrieval Accuracy Evaluation)",
        "python scripts/rag/evaluation/unified_retrieval_eval.py --export"
    )

def main():
    while True:
        console.print("\n")
        console.print(Panel.fit(
            "[bold blue]🔄 Unified RAG System Manager[/bold blue]\n"
            "[dim]請選擇執行模式 (Select Mode)[/dim]",
            title="RAG Pipeline"
        ))
        
        console.print("1. [bold cyan]🚀 執行完整流程 (Full Pipeline)[/bold cyan]")
        console.print("   [dim](Chunking -> Indexing -> Audit -> Eval)[/dim]")
        console.print("2. [bold yellow]📦 僅執行資料分塊 (Chunking Only)[/bold yellow]")
        console.print("3. [bold green]🔍 僅執行索引建置 (Indexing Only)[/bold green]")
        console.print("   [dim](BGE-M3 + BM25)[/dim]")
        console.print("4. [bold magenta]✅ 僅執行驗證測試 (Verification Only)[/bold magenta]")
        console.print("   [dim](Coverage Audit + Retrieval Eval)[/dim]")
        console.print("5. [bold red]🚪 離開 (Exit)[/bold red]")
        
        choice = Prompt.ask("請輸入選項", choices=["1", "2", "3", "4", "5"], default="1")
        
        if choice == "1":
            console.print("[bold]開始執行完整流程...[/bold]")
            if step_chunking():
                if step_indexing():
                    step_verification()
        
        elif choice == "2":
            step_chunking()
            
        elif choice == "3":
            step_indexing()
            
        elif choice == "4":
            step_verification()
            
        elif choice == "5":
            console.print("[yellow]Bye![/yellow]")
            break
            
        console.print("\n" + "="*50)
        if not Confirm.ask("是否繼續執行其他任務？", default=True):
            break

if __name__ == "__main__":
    main()
