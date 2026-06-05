#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run both BGE-M3 and BM25 indexers sequentially.
Usage: python scripts/rag/run_reindexing.py
"""

import subprocess
import sys
from rich.console import Console

console = Console()

def run_command(command):
    console.print(f"\n[bold cyan]🚀 Running: {command}[/bold cyan]")
    try:
        # shell=True allows using the full command string
        result = subprocess.run(command, shell=True, check=True)
        console.print(f"[bold green]✅ Success: {command}[/bold green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]❌ Error running command: {command}[/bold red]")
        console.print(f"[red]Exit code: {e.returncode}[/red]")
        sys.exit(e.returncode)

def main():
    console.print("[bold]🔄 Starting RAG Re-indexing Sequence[/bold]")
    
    # 1. BGE-M3 Indexer (Vector Index)
    run_command("python scripts/rag/indexing/p2_t09_bge_m3_indexer.py")
    
    # 2. BM25 Indexer (Keyword Index)
    run_command("python scripts/rag/indexing/p2_t10_bm25_indexer.py")
    
    console.print("\n" + "="*50)
    console.print("[bold green]🎉 All indexing tasks completed successfully![/bold green]")
    console.print("="*50)

if __name__ == "__main__":
    main()
