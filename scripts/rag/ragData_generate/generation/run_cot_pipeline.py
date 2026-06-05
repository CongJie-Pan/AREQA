"""Main orchestrator for P3-T04-S7 CoT generation pipeline.

Usage:
  # Test mode (3 samples)
  python run_cot_pipeline.py --test --amount 3
  
  # Production mode (1500 samples)
  python run_cot_pipeline.py --amount 1500
  
  # Production mode with default (1500)
  python run_cot_pipeline.py

Author: AI Agent
Date: 2026-02-08
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

# Script paths
PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = Path(__file__).parent
VALIDATION_DIR = SCRIPTS_DIR.parent / "validation"
CONFIG_PATH = PROJECT_ROOT / "output" / "p3_t04" / "cot_generation_config.json"

PIPELINE_SCRIPTS = [
    ("Phase 0: 前置檢查", SCRIPTS_DIR / "preflight_checker.py"),
    ("Phase 1: 篩選候選", SCRIPTS_DIR / "filter_cot_candidates.py"),
    ("Phase 2: 生成 CoT", SCRIPTS_DIR / "cot_generator.py"),
    ("Phase 3: 格式轉換", SCRIPTS_DIR / "convert_to_radit_cot.py"),
    ("Phase 4: 驗證", VALIDATION_DIR / "validate_cot_format.py"),
]


def create_config(amount: int, is_test: bool):
    """Create configuration file with specified parameters.
    
    Why create config before running:
    - All sub-scripts read from the same config file
    - Ensures consistent parameters across all phases
    """
    config = {
        "target_count": amount,
        "reasoning_length_min": 80,
        "reasoning_length_max": 120,
        "api_model": "openrouter/moonshotai/kimi-k2-0905",
        "retrieval_k": 3,
        "max_context_length": 500,
        "max_retries": 3,
        "timeout_seconds": 30,
        "is_test_mode": is_test,
    }
    
    # Ensure output directory exists
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    return config


def run_pipeline(amount: int, is_test: bool, skip_preflight: bool = False):
    """Run all pipeline scripts in sequence.
    
    Args:
        amount: Target number of CoT samples to generate
        is_test: Whether this is a test run
        skip_preflight: Skip Phase 0 preflight checks
    """
    mode_text = "[yellow]🧪 測試模式[/yellow]" if is_test else "[green]📦 正式模式[/green]"
    
    console.print(Panel.fit(
        f"[bold cyan]P3-T04-S7 CoT Generation Pipeline[/bold cyan]\n"
        f"模式: {mode_text}\n"
        f"目標數量: [bold]{amount}[/bold] 筆",
        border_style="cyan",
        title="🚀 Pipeline Execution"
    ))
    console.print()
    
    # Create config file
    console.print("[dim]建立配置檔案...[/dim]")
    create_config(amount, is_test)
    console.print(f"[green]✅ 配置已保存: {CONFIG_PATH.relative_to(PROJECT_ROOT)}[/green]\n")
    
    # Determine which scripts to run
    scripts_to_run = PIPELINE_SCRIPTS if not skip_preflight else PIPELINE_SCRIPTS[1:]
    
    for i, (phase_name, script_path) in enumerate(scripts_to_run, 1):
        console.print(f"\n[bold]=== {phase_name} ===[/bold]")
        console.print(f"[dim]執行: {script_path.name}[/dim]\n")
        
        if not script_path.exists():
            console.print(f"[red]❌ 腳本不存在: {script_path}[/red]")
            return 1
        
        # Run the script with environment variable to pass config
        env = {"COT_CONFIG_PATH": str(CONFIG_PATH)}
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=script_path.parent,
            env={**__import__('os').environ, **env}
        )
        
        if result.returncode != 0:
            console.print(f"\n[red]❌ {phase_name} 失敗 (exit code: {result.returncode})[/red]")
            if not Confirm.ask("是否繼續執行下一階段？", default=False):
                return result.returncode
        else:
            console.print(f"[green]✅ {phase_name} 完成[/green]")
    
    console.print(Panel.fit(
        "[bold green]🎉 所有階段執行完成！[/bold green]",
        border_style="green"
    ))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="P3-T04-S7 CoT Generation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test mode with 3 samples
  python run_cot_pipeline.py --test --amount 3
  
  # Production mode with 1500 samples (default)
  python run_cot_pipeline.py
  
  # Production mode with custom amount
  python run_cot_pipeline.py --amount 500
  
  # Skip preflight checks (use with caution)
  python run_cot_pipeline.py --skip-preflight
        """
    )
    
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Run in test mode (default amount: 3)"
    )
    
    parser.add_argument(
        "--amount", "-a",
        type=int,
        default=None,
        help="Number of CoT samples to generate (default: 3 for test, 1500 for production)"
    )
    
    parser.add_argument(
        "--skip-preflight", "-s",
        action="store_true",
        help="Skip Phase 0 preflight checks"
    )
    
    args = parser.parse_args()
    
    # Determine amount based on mode
    if args.amount is not None:
        amount = args.amount
    elif args.test:
        amount = 3
    else:
        amount = 1500
    
    try:
        sys.exit(run_pipeline(
            amount=amount,
            is_test=args.test,
            skip_preflight=args.skip_preflight
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已取消[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]❌ 發生錯誤: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
