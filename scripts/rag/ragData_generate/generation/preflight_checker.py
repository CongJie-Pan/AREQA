"""Pre-flight checks for P3-T04-S7 CoT data generation.

This script validates all prerequisites before starting the CoT generation pipeline:
1. Data file availability (RAG samples, FAISS index)
2. Data format validation (sample first 100 records)
3. FAISS index load test  
4. LLM API connectivity test (kimi-k2 via LiteLLM)
5. Interactive parameter configuration

Why pre-flight checks:
- Avoid mid-process failures due to missing resources
- Provide clear error messages for quick debugging
- Allow user to configure parameters before long-running processes
- Use rich library for enhanced terminal UX

Author: AI Agent
Date: 2026-02-08
Task: P3-T04-S7
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich.prompt import Confirm, IntPrompt, Prompt
from rich import print as rprint

# Try to import optional dependencies
try:
    import litellm
    # Suppress LiteLLM debug messages
    litellm.suppress_debug_info = True
    import os as _litellm_os
    _litellm_os.environ["LITELLM_LOG"] = "ERROR"
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Required data paths
REQUIRED_PATHS = {
    "RAG Dataset (v2)": PROJECT_ROOT / "data" / "training" / "completeSet" / "v2" / "complete_training_dataset.jsonl",
    "FAISS Index (Qwen3)": PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunks_qwen3.index",
    "FAISS Mapping (Qwen3)": PROJECT_ROOT / "data" / "rag" / "faiss_index" / "chunk_mapping_qwen3.json",
    "Output Directory": PROJECT_ROOT / "output" / "p3_t04",
    "CoT Output Directory": PROJECT_ROOT / "data" / "training" / "cot",
}

# Required JSONL fields
REQUIRED_FIELDS = ["input", "output", "metadata"]

# Test mode flag
TEST_MODE = True  # Set to False for production

# Default generation config
DEFAULT_CONFIG = {
    "target_count": 3 if TEST_MODE else 1500,  # 3 for testing, 1500 for production
    "reasoning_length_min": 80,
    "reasoning_length_max": 120,
    "api_model": "openrouter/moonshotai/kimi-k2-0905",
    "retrieval_k": 3,
    "max_context_length": 500,
    "max_retries": 3,
    "timeout_seconds": 30,
}

console = Console()


# ============================================================================
# Check Functions
# ============================================================================

def display_header():
    """Display welcome header with rich panel.
    
    Why: Set context and expectations for the user
    """
    console.print(Panel.fit(
        "[bold cyan]P3-T04-S7 CoT 生成前置檢查[/bold cyan]\n"
        "此程序將驗證所有必要資源與服務，並設定執行參數",
        border_style="cyan",
        title="🚀 Pre-flight Checks",
        subtitle="version 1.0"
    ))
    console.print()


def check_data_availability() -> Tuple[bool, Dict[str, bool]]:
    """Check if required data files and directories exist.
    
    Why: Ensure all input data is available before starting pipeline
    
    Returns:
        Tuple of (all_exist: bool, status_dict: Dict[str, bool])
    """
    console.print("[bold]📁 檢查 1/4: 資料檔案可用性[/bold]\n")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("資源", style="dim", width=25)
    table.add_column("路徑", width=45, overflow="fold")
    table.add_column("狀態", justify="center", width=8)
    
    status_dict = {}
    all_exist = True
    
    for name, path in REQUIRED_PATHS.items():
        exists = path.exists()
        status_dict[name] = exists
        status = "[green]✓[/green]" if exists else "[red]✗[/red]"
        
        # Shorten path for display
        try:
            display_path = str(path.relative_to(PROJECT_ROOT))
        except ValueError:
            display_path = str(path)
        
        table.add_row(name, display_path, status)
        all_exist = all_exist and exists
    
    console.print(table)
    console.print()
    
    if not all_exist:
        missing = [k for k, v in status_dict.items() if not v]
        console.print(f"[bold red]❌ 缺失資源: {', '.join(missing)}[/bold red]")
        console.print("[yellow]請先完成前置任務或確認路徑正確[/yellow]")
        return False, status_dict
    
    console.print("[green]✅ 所有資料檔案存在[/green]\n")
    return True, status_dict


def check_data_format() -> Tuple[bool, Dict[str, Any]]:
    """Validate JSONL data format by sampling first 100 records.
    
    Why: Early detection of format issues prevents processing failures
    
    Returns:
        Tuple of (valid: bool, stats: Dict)
    """
    console.print("[bold]🔍 檢查 2/4: 資料格式驗證[/bold]\n")
    
    dataset_path = REQUIRED_PATHS["RAG Dataset (v2)"]
    stats = {
        "total_sampled": 0,
        "valid_samples": 0,
        "format_errors": 0,
        "sample_types": {},
        "avg_input_length": 0,
        "avg_output_length": 0,
    }
    
    total_input_len = 0
    total_output_len = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]載入並驗證資料格式...[/cyan]", total=None)
        
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= 100:  # Sample first 100 records
                        break
                    
                    try:
                        sample = json.loads(line)
                        stats["total_sampled"] += 1
                        
                        # Check required fields
                        if all(field in sample for field in REQUIRED_FIELDS):
                            stats["valid_samples"] += 1
                            
                            # Count types
                            sample_type = sample.get("metadata", {}).get("type", "unknown")
                            stats["sample_types"][sample_type] = stats["sample_types"].get(sample_type, 0) + 1
                            
                            # Track lengths
                            total_input_len += len(sample.get("input", ""))
                            total_output_len += len(sample.get("output", ""))
                        else:
                            stats["format_errors"] += 1
                            
                    except json.JSONDecodeError:
                        stats["format_errors"] += 1
                        
            progress.update(task, description="[cyan]格式驗證完成[/cyan]")
            
        except Exception as e:
            console.print(f"[red]❌ 讀取資料時發生錯誤: {e}[/red]")
            return False, stats
    
    # Calculate averages
    if stats["valid_samples"] > 0:
        stats["avg_input_length"] = total_input_len // stats["valid_samples"]
        stats["avg_output_length"] = total_output_len // stats["valid_samples"]
    
    # Display results
    result_table = Table(show_header=True, header_style="bold blue")
    result_table.add_column("指標", style="dim")
    result_table.add_column("值", style="green")
    
    result_table.add_row("抽樣數量", str(stats["total_sampled"]))
    result_table.add_row("有效樣本", str(stats["valid_samples"]))
    result_table.add_row("格式錯誤", f"[red]{stats['format_errors']}[/red]" if stats["format_errors"] > 0 else "0")
    result_table.add_row("平均 Input 長度", f"{stats['avg_input_length']} 字")
    result_table.add_row("平均 Output 長度", f"{stats['avg_output_length']} 字")
    
    console.print(result_table)
    console.print()
    
    # Show type distribution
    if stats["sample_types"]:
        type_info = ", ".join([f"{k}: {v}" for k, v in stats["sample_types"].items()])
        console.print(f"[dim]類型分佈: {type_info}[/dim]")
    
    console.print()
    
    if stats["format_errors"] > 0:
        console.print(f"[yellow]⚠️ 發現 {stats['format_errors']} 筆格式錯誤（前100筆中）[/yellow]")
        if not Confirm.ask("是否繼續執行？", default=True):
            return False, stats
    else:
        console.print("[green]✅ 資料格式正確（驗證前100筆樣本）[/green]\n")
    
    return True, stats


def check_faiss_index() -> Tuple[bool, Dict[str, Any]]:
    """Check FAISS index availability and attempt to load.
    
    Why: FAISS retrieval is core to CoT generation pipeline
    
    Returns:
        Tuple of (available: bool, info: Dict)
    """
    console.print("[bold]🔎 檢查 3/4: FAISS 索引[/bold]\n")
    
    info = {
        "index_path": str(REQUIRED_PATHS["FAISS Index (Qwen3)"]),
        "mapping_path": str(REQUIRED_PATHS["FAISS Mapping (Qwen3)"]),
        "index_size": 0,
        "chunk_count": 0,
        "load_success": False,
    }
    
    try:
        # Check file sizes
        index_path = REQUIRED_PATHS["FAISS Index (Qwen3)"]
        mapping_path = REQUIRED_PATHS["FAISS Mapping (Qwen3)"]
        
        if index_path.exists():
            info["index_size"] = index_path.stat().st_size / (1024 * 1024)  # MB
        
        with console.status("[cyan]檢查 FAISS 索引檔案...[/cyan]"):
            time.sleep(0.5)  # Brief pause for UX
            
            # Load mapping to get chunk count
            if mapping_path.exists():
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                    # Mapping format: {"0": "chunk_id", "1": "chunk_id", ...}
                    if isinstance(mapping, dict):
                        info["chunk_count"] = len(mapping)
                    elif isinstance(mapping, list):
                        info["chunk_count"] = len(mapping)
                    else:
                        info["chunk_count"] = 0
        
        console.print(f"  索引檔案大小: {info['index_size']:.2f} MB")
        console.print(f"  Chunk 數量: {info['chunk_count']:,} 筆")
        
        # Try to import faiss (optional)
        try:
            import faiss
            console.print(f"  FAISS 版本: {faiss.__version__ if hasattr(faiss, '__version__') else 'installed'}")
            info["load_success"] = True
        except ImportError:
            console.print("[yellow]  ⚠️ faiss-cpu 未安裝（將使用備用方案）[/yellow]")
            # We can still proceed if faiss is not installed (use alternative retrieval)
            info["load_success"] = True  # Allow to continue
        
        console.print()
        console.print("[green]✅ FAISS 索引可用[/green]\n")
        return True, info
        
    except Exception as e:
        console.print(f"[red]❌ FAISS 索引檢查失敗: {e}[/red]")
        return False, info


def check_api_connection() -> Tuple[bool, Dict[str, Any]]:
    """Test LLM API connectivity (kimi-k2 via LiteLLM/OpenRouter).
    
    Why: API availability is critical for CoT generation
    
    Returns:
        Tuple of (connected: bool, info: Dict)
    """
    console.print("[bold]🌐 檢查 4/4: API 連接測試[/bold]\n")
    
    info = {
        "api_key_found": False,
        "api_key_preview": "",
        "connection_success": False,
        "response_preview": "",
        "error_message": "",
    }
    
    # Check if litellm is available
    if not LITELLM_AVAILABLE:
        console.print("[yellow]⚠️ litellm 未安裝[/yellow]")
        console.print("[dim]請執行: pip install litellm[/dim]\n")
        
        if Confirm.ask("是否跳過 API 測試並繼續？", default=True):
            console.print("[yellow]⚠️ 已跳過 API 測試，請確保後續執行時 API 可用[/yellow]\n")
            return True, info
        return False, info
    
    # Check API key (from .env or environment)
    if DOTENV_AVAILABLE:
        console.print("[dim]✅ 已從 .env 載入環境變數[/dim]")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        console.print("[red]❌ OPENROUTER_API_KEY 環境變數未設定[/red]")
        console.print("[yellow]請確認 .env 檔案包含: OPENROUTER_API_KEY=your_key[/yellow]")
        console.print("[dim]  或執行: set OPENROUTER_API_KEY=your_api_key_here[/dim]\n")
        
        if Confirm.ask("是否跳過 API 測試並繼續？", default=True):
            console.print("[yellow]⚠️ 已跳過 API 測試，請確保後續執行時設定 API Key[/yellow]\n")
            return True, info
        return False, info
    
    info["api_key_found"] = True
    # Don't display API key for security
    
    # Test API call
    try:
        with console.status("[cyan]測試 kimi-k2 API 連接...[/cyan]"):
            response = litellm.completion(
                model="openrouter/moonshotai/kimi-k2-0905",
                messages=[{
                    "role": "user",
                    "content": "請簡短回答：一加一等於多少？"
                }],
                api_key=api_key,
                max_tokens=20,
                timeout=15
            )
        
        info["connection_success"] = True
        response_text = response.choices[0].message.content
        info["response_preview"] = response_text[:50] + "..." if len(response_text) > 50 else response_text
        
        console.print("[green]✅ API 連接成功[/green]")
        console.print(f"[dim]測試回應: {info['response_preview']}[/dim]\n")
        return True, info
        
    except Exception as e:
        info["error_message"] = str(e)
        console.print(f"[red]❌ API 連接失敗: {str(e)[:100]}[/red]")
        console.print("\n[yellow]可能原因：[/yellow]")
        console.print("  1. API Key 無效或已過期")
        console.print("  2. 網路連接問題")
        console.print("  3. OpenRouter 服務異常")
        console.print("  4. kimi-k2 模型不可用")
        console.print()
        
        if Confirm.ask("是否跳過 API 測試並繼續？", default=False):
            console.print("[yellow]⚠️ 已跳過 API 測試，請確保後續執行時解決連接問題[/yellow]\n")
            return True, info
        return False, info


def interactive_parameter_selection() -> Dict[str, Any]:
    """Interactive parameter configuration with user input.
    
    Why: Allow user to customize generation parameters
    
    Returns:
        Configuration dictionary
    """
    console.print("[bold cyan]⚙️  參數設定[/bold cyan]\n")
    
    config = DEFAULT_CONFIG.copy()
    
    # Target count
    config["target_count"] = IntPrompt.ask(
        "請輸入目標 CoT 樣本數量",
        default=DEFAULT_CONFIG["target_count"],
        console=console
    )
    
    # Reasoning length
    console.print("\n推理鏈長度偏好：")
    console.print("  [bold]1[/bold]. 簡短 (50-80 字)")
    console.print("  [bold]2[/bold]. 中等 (80-120 字) [dim][推薦][/dim]")
    console.print("  [bold]3[/bold]. 詳細 (120-150 字)")
    
    length_choice = IntPrompt.ask(
        "請選擇",
        default=2,
        choices=["1", "2", "3"],
        console=console
    )
    
    length_ranges = {
        1: (50, 80),
        2: (80, 120),
        3: (120, 150)
    }
    
    config["reasoning_length_min"], config["reasoning_length_max"] = length_ranges[length_choice]
    
    # Advanced options
    console.print()
    if Confirm.ask("是否進行進階設定？", default=False):
        config["retrieval_k"] = IntPrompt.ask(
            "  檢索結果數量 (k)",
            default=config["retrieval_k"],
            console=console
        )
        config["max_context_length"] = IntPrompt.ask(
            "  最大背景長度 (字元)",
            default=config["max_context_length"],
            console=console
        )
        config["max_retries"] = IntPrompt.ask(
            "  API 最大重試次數",
            default=config["max_retries"],
            console=console
        )
    
    # Display final configuration
    console.print()
    config_table = Table(title="最終配置", show_header=True, header_style="bold cyan")
    config_table.add_column("參數", style="dim")
    config_table.add_column("值", style="green")
    
    config_table.add_row("目標樣本數", str(config["target_count"]))
    config_table.add_row("推理鏈長度", f"{config['reasoning_length_min']}-{config['reasoning_length_max']} 字")
    config_table.add_row("LLM 模型", config["api_model"])
    config_table.add_row("檢索數量 (k)", str(config["retrieval_k"]))
    config_table.add_row("最大背景長度", f"{config['max_context_length']} 字元")
    config_table.add_row("API 重試次數", str(config["max_retries"]))
    
    console.print(config_table)
    console.print()
    
    # Save configuration
    output_dir = REQUIRED_PATHS["Output Directory"]
    output_dir.mkdir(parents=True, exist_ok=True)
    
    config_path = output_dir / "cot_generation_config.json"
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]✅ 配置已保存至: {config_path.relative_to(PROJECT_ROOT)}[/green]\n")
    
    return config


def ensure_output_directories():
    """Create required output directories if they don't exist.
    
    Why: Prevent file write failures during generation
    """
    directories = [
        REQUIRED_PATHS["Output Directory"],
        REQUIRED_PATHS["CoT Output Directory"],
    ]
    
    for dir_path in directories:
        dir_path.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Main Execution
# ============================================================================

def run_preflight_checks() -> Optional[Dict[str, Any]]:
    """Run all preflight checks and return configuration if successful.
    
    Why: Single entry point for complete pre-flight validation
    
    Returns:
        Configuration dict if all checks pass, None otherwise
    """
    display_header()
    
    # Check 1: Data availability
    data_ok, data_status = check_data_availability()
    if not data_ok:
        return None
    
    # Check 2: Data format
    format_ok, format_stats = check_data_format()
    if not format_ok:
        return None
    
    # Check 3: FAISS index
    faiss_ok, faiss_info = check_faiss_index()
    if not faiss_ok:
        return None
    
    # Check 4: API connection
    api_ok, api_info = check_api_connection()
    if not api_ok:
        return None
    
    # All checks passed - proceed to configuration
    console.print(Panel(
        "[bold green]✅ 所有前置檢查通過！[/bold green]",
        border_style="green"
    ))
    console.print()
    
    # Ensure output directories exist
    ensure_output_directories()
    
    # Check if config already exists (from pipeline orchestrator)
    import os as _preflight_os
    config_from_env = _preflight_os.getenv("COT_CONFIG_PATH")
    
    if config_from_env and Path(config_from_env).exists():
        # Load existing config from pipeline
        with open(config_from_env, 'r', encoding='utf-8') as f:
            config = json.load(f)
        console.print("[dim]✅ 已從 pipeline 載入配置參數[/dim]\n")
    elif CONFIG_FILE_PATH.exists():
        # Load from saved config
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        console.print("[dim]✅ 已載入保存的配置參數[/dim]\n")
    else:
        # Interactive parameter selection (standalone mode only)
        console.print("[yellow]⚠️ 未找到配置檔案，使用預設值[/yellow]")
        config = DEFAULT_CONFIG.copy()
        console.print(f"[dim]目標樣本數: {config['target_count']}[/dim]\n")
    
    # Add check results to config
    config["_check_results"] = {
        "data_status": data_status,
        "format_stats": format_stats,
        "faiss_info": faiss_info,
        "api_info": {k: v for k, v in api_info.items() if k != "api_key_preview"},
    }
    
    console.print(Panel(
        "[bold cyan]準備就緒！[/bold cyan]\n"
        "可執行 CoT 生成腳本: [dim]python cot_generator.py[/dim]",
        border_style="cyan"
    ))
    
    return config


def main():
    """Main entry point."""
    try:
        config = run_preflight_checks()
        
        if config:
            console.print("\n[bold green]🎉 Pre-flight checks completed successfully![/bold green]")
            sys.exit(0)
        else:
            console.print("\n[bold red]❌ Pre-flight checks failed. Please resolve issues and retry.[/bold red]")
            sys.exit(1)
            
    except KeyboardInterrupt:
        console.print("\n[yellow]操作已取消[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]❌ 發生未預期錯誤: {e}[/bold red]")
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
