#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master Pipeline Runner for Qwen3 RAG System
This script sequentially runs:
1. Hybrid Chunking
2. Index Rebuilding
3. Retrieval Evaluation
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()
# Ensure we map back to the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

def run_command(command: list, step_name: str):
    """Run a subprocess command and let it output directly to the terminal."""  
    console.print(Panel(f"[bold cyan]Starting:[/bold cyan] {step_name}\n[dim]Command: {' '.join(command)}[/dim]", border_style="cyan"))      

    try:
        # We do not use stdout=subprocess.PIPE here.
        # By letting the process inherit stdout/stderr, rich and tqdm       
        # progress bars from the children will render correctly in real-time.
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT)
        )

        process.wait()

        if process.returncode != 0:
            console.print(f"\n[bold red]❌ Error: {step_name} failed with return code {process.returncode}[/bold red]")
            sys.exit(process.returncode)

        console.print(f"\n[bold green]✅ Completed: {step_name}[/bold green]\n")

    except KeyboardInterrupt:
        console.print(f"\n[bold yellow]⚠️ Process interrupted by user during {step_name}[/bold yellow]")
        process.terminate()
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]❌ System Error running {step_name}: {str(e)}[/bold red]")
        sys.exit(1)

def check_prerequisites():
    """Verify API keys and essential files exist before starting."""
    import os
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    
    console.print("[cyan]Running Pre-flight Checks (API Connections & Files)...[/cyan]")
    
    # Check OpenRouter API
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        console.print("[bold red]❌ OPENROUTER_API_KEY not found in environment![/bold red]")
        sys.exit(1)
        
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key", 
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )
        if response.status_code == 200:
            console.print("[green]✅ OpenRouter API Connection: Successful[/green]")
        else:
            console.print(f"[bold red]❌ OpenRouter API auth failed: {response.status_code}[/bold red]")
            sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]❌ OpenRouter API Connection Error: {str(e)}[/bold red]")
        sys.exit(1)

    # Check input files
    data_dir = PROJECT_ROOT / "data" / "processed" / "GAOKAO_chinese"
    if not data_dir.exists() or not any(data_dir.glob("*.json*")):
        console.print("[yellow]⚠️ Warning: Expected data directory might be empty or missing.[/yellow]")
    else:
        console.print("[green]✅ Input Data Directory: Verified[/green]")
        
    console.print("[green]✅ Pre-flight checks passed.[/green]\n")

def main():
    parser = argparse.ArgumentParser(description="Master Pipeline Runner for Qwen3 RAG System")
    parser.add_argument("--limit", type=int, default=None, help="Limit the number of items processed in each step for testing")
    parser.add_argument("--mode", type=str, choices=["all", "1", "1.5", "2", "3", "1-1.5", "1-2", "2-3"], default="all", help="Execution mode: run specific steps or range of steps")
    parser.add_argument("--retry", action="store_true", help="Force restart from scratch (clear checkpoints)")
    args = parser.parse_args()

    console.rule("[bold magenta]Qwen3 RAG Complete Pipeline[/bold magenta]")
    console.print("\n[bold]This script will execute the following steps sequentially:[/bold]")
    console.print("  [cyan]1. Hybrid Chunking (run_hybrid_batch.py)[/cyan]")
    console.print("  [cyan]1.5. Quality Gate (verify_llm_chunking.py)[/cyan]")
    console.print("  [cyan]2. Rebuild FAISS Index (rebuild_index_qwen3.py)[/cyan]")
    console.print("  [cyan]3. Retrieval Evaluation (qwen3_retrieval_evaluation.py)[/cyan]\n")
    
    if args.limit:
        console.print(f"[bold yellow]⚠️ Testing Mode Active: Limiting to {args.limit} items per step[/bold yellow]\n")
    
    check_prerequisites()
    
    python_exec = sys.executable
    
    base_dir = Path("scripts/rag/qwen3_Encoder_rag_pipeline")
    
    all_steps = [
        {
            "name": "Step 1: Hybrid Chunking",
            "script": base_dir / "chunking" / "run_hybrid_batch.py",
            "args": (["--limit", str(args.limit)] if args.limit else []) + (["--retry"] if args.retry else [])
        },
        {
            "name": "Step 1.5: Quality Gate Verification",
            "script": base_dir / "chunking" / "verify_llm_chunking.py",
            "args": (["--limit", str(args.limit)] if args.limit else [])
        },
        {
            "name": "Step 2: Rebuild Index",
            "script": base_dir / "rebuild_index_qwen3.py",
             "args": (["--limit", str(args.limit)] if args.limit else []) + (["--retry"] if args.retry else [])
        },
        {
            "name": "Step 3: Retrieval Evaluation",
            "script": base_dir / "qwen3_retrieval_evaluation.py",
            "args": ["--samples-per-type", str(args.limit)] if args.limit else []
        }
    ]
    
    if args.mode == "1":
        steps = [all_steps[0]]
    elif args.mode == "1.5":
        steps = [all_steps[1]]
    elif args.mode == "2":
        steps = [all_steps[2]]
    elif args.mode == "3":
        steps = [all_steps[3]]
    elif args.mode == "1-1.5":
        steps = all_steps[0:2]
    elif args.mode == "1-2":
        steps = all_steps[0:3]
    elif args.mode == "2-3":
        steps = all_steps[2:4]
    else:
        steps = all_steps
        
    if args.mode != "all":
        console.print(f"[bold yellow]⚡ Running Mode Filter Active: Executing Mode '{args.mode}' ⚡[/bold yellow]\n")
        
    for step in steps:
        script_path = PROJECT_ROOT / step["script"]
        if not script_path.exists():
            console.print(f"[bold red]❌ Missing Script:[/bold red] {script_path}")
            sys.exit(1)
            
        # Execute the python script
        cmd = [python_exec, str(step["script"])] + step.get("args", [])
        run_command(cmd, step["name"])

    console.rule("[bold green]🎉 All Pipeline Steps Completed Successfully! 🎉[/bold green]")

if __name__ == "__main__":
    main()
