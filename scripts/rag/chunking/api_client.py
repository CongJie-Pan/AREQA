#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Client Module - LiteLLM wrapper for Kimi K2 API
====================================================

Follows the same pattern as scripts/training/p2_t12_qa_generator/api_client.py
for consistency across the project.

Usage:
    from scripts.rag.chunking.api_client import api_client
    
    # Test connection
    success, msg = api_client.test_connection()
    
    # Generate content
    content, elapsed = api_client.generate("your prompt here")

Author: ML Engineer
Date: 2026-02-01
Task: P2-T01/T02 (Phase 2 - LLM-based Chunking)
"""

# ===== MUST BE BEFORE ANY OTHER IMPORTS =====
# Suppress LiteLLM stdout "Provider List" messages
import os
os.environ["LITELLM_LOG"] = "ERROR"
os.environ["LITELLM_PRINT_VERBOSE"] = "False"

# Monkey-patch to suppress litellm print statements (including empty lines)
class _SuppressLiteLLMPrint:
    """Suppress 'Provider List:' messages and empty lines from litellm."""
    _patched = False
    
    @classmethod
    def suppress_provider_list(cls):
        if cls._patched:
            return
        import builtins
        _original_print = builtins.print
        def _filtered_print(*args, **kwargs):
            # Suppress empty prints or prints with only whitespace
            if not args or (len(args) == 1 and (args[0] == "" or (isinstance(args[0], str) and args[0].strip() == ""))):
                return
            # Suppress Provider List messages
            if args and isinstance(args[0], str) and "Provider List:" in args[0]:
                return
            return _original_print(*args, **kwargs)
        builtins.print = _filtered_print
        cls._patched = True

_SuppressLiteLLMPrint.suppress_provider_list()
# =============================================

import sys
import time
import logging
from typing import Tuple, Optional
from pathlib import Path

# Rich imports for beautiful console output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    Console = None
    rprint = print

# Handle both direct execution and module import
if __name__ == "__main__":
    # When run directly, add parent directories to path
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(PROJECT_ROOT))
    from scripts.rag.chunking.config import (
        OPENROUTER_API_KEY,
        MODEL_NAME,
        API_TEMPERATURE,
        API_MAX_TOKENS,
        API_MAX_RETRIES,
        API_RETRY_DELAY,
        API_RATE_LIMIT_DELAY,
    )
else:
    # When imported as module
    from .config import (
        OPENROUTER_API_KEY,
        MODEL_NAME,
        API_TEMPERATURE,
        API_MAX_TOKENS,
        API_MAX_RETRIES,
        API_RETRY_DELAY,
        API_RATE_LIMIT_DELAY,
    )

# Configure logging
logger = logging.getLogger(__name__)


class APIClient:
    """LiteLLM API client for OpenRouter.
    
    This client wraps the LiteLLM library to provide a consistent interface
    for calling the OpenRouter API. It handles:
    - API key setup
    - Lazy loading of litellm
    - Automatic retry on rate limits and errors
    - Connection testing
    
    Example:
        client = APIClient()
        if client.test_connection()[0]:
            response, elapsed = client.generate("你好")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the API client.
        
        Args:
            api_key: Optional API key override. If not provided,
                    uses OPENROUTER_API_KEY from environment/config.
        """
        self.api_key = api_key or OPENROUTER_API_KEY
        self._completion = None
    
    def _get_completion_func(self):
        """Lazy load litellm completion function.
        
        Returns:
            litellm.completion function
            
        Raises:
            ImportError: If litellm is not installed
        """
        if self._completion is None:
            try:
                from litellm import completion
                self._completion = completion
            except ImportError:
                raise ImportError(
                    "LiteLLM not installed. Please install with:\n"
                    "  pip install litellm"
                )
        return self._completion
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test API connection with a simple request.
        
        Returns:
            Tuple of (success: bool, message: str)
            
        Example:
            >>> success, msg = client.test_connection()
            >>> if success:
            ...     print("Connected!")
        """
        if not self.api_key:
            return False, "OPENROUTER_API_KEY not set in environment"
        
        try:
            completion = self._get_completion_func()
            
            # Send simple test request
            response = completion(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": "你好"}],
                max_tokens=10,
                api_key=self.api_key,  # Pass API key directly for OpenRouter
            )
            
            return True, "Connection successful"
            
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                return False, "Invalid API Key"
            elif "429" in error_msg:
                return False, "Rate limit exceeded"
            elif "insufficient" in error_msg.lower():
                return False, "Insufficient balance"
            else:
                return False, f"Connection failed: {error_msg[:100]}"
    
    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Tuple[str, float]:
        """
        Call API to generate content with automatic retry.
        
        Args:
            prompt: Input prompt text
            temperature: Override default temperature (optional)
            max_tokens: Override default max tokens (optional)
            
        Returns:
            Tuple of (generated_content: str, elapsed_time: float)
            
        Raises:
            Exception: If all retries fail
            
        Example:
            >>> content, elapsed = client.generate("請分析這段古文...")
            >>> print(f"Generated in {elapsed:.2f}s: {content[:50]}...")
        """
        completion = self._get_completion_func()
        
        # Use defaults if not overridden
        temp = temperature if temperature is not None else API_TEMPERATURE
        tokens = max_tokens if max_tokens is not None else API_MAX_TOKENS
        
        for attempt in range(1, API_MAX_RETRIES + 1):
            try:
                start_time = time.time()
                
                response = completion(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temp,
                    max_tokens=tokens,
                    api_key=self.api_key,  # Pass API key directly for OpenRouter
                )
                
                elapsed = time.time() - start_time
                content = response.choices[0].message.content
                
                return content, elapsed
                
            except Exception as e:
                error_msg = str(e)
                
                # Handle rate limit
                if "429" in error_msg:
                    logger.warning(
                        f"Rate limit hit, retry {attempt}/{API_MAX_RETRIES} "
                        f"(waiting {API_RATE_LIMIT_DELAY}s)"
                    )
                    if attempt < API_MAX_RETRIES:
                        time.sleep(API_RATE_LIMIT_DELAY)
                    continue
                
                # Handle other errors
                logger.warning(
                    f"API error, retry {attempt}/{API_MAX_RETRIES}: "
                    f"{error_msg[:50]}"
                )
                if attempt < API_MAX_RETRIES:
                    time.sleep(API_RETRY_DELAY)
                continue
        
        # All retries failed
        raise Exception(f"API call failed after {API_MAX_RETRIES} retries")


# Global client instance for convenience
api_client = APIClient()


# ============================================================================
# Standalone testing
# ============================================================================

def main():
    """Test the API client."""
    console = Console() if HAS_RICH else None
    
    if HAS_RICH:
        console.print(Panel.fit(
            "[bold cyan]Kimi K2 API 客戶端測試[/bold cyan]",
            border_style="cyan"
        ))
    else:
        print("=" * 60)
        print("API 客戶端測試")
        print("=" * 60)
    
    # Check API key
    if not MOONSHOT_API_KEY:
        if HAS_RICH:
            console.print("[red]❌ 未設定 MOONSHOT_API_KEY[/red]")
            console.print("   [yellow]請在 .env 檔案或環境變數中設定[/yellow]")
        else:
            print("❌ 未設定 MOONSHOT_API_KEY")
            print("   請在 .env 檔案或環境變數中設定")
        return
    
    # Display config
    if HAS_RICH:
        config_table = Table(show_header=False, box=None)
        config_table.add_row("[cyan]模型：[/cyan]", MODEL_NAME)
        config_table.add_row("[cyan]API 位址：[/cyan]", MOONSHOT_API_BASE)
        console.print(config_table)
    else:
        print(f"模型：{MODEL_NAME}")
        print(f"API 位址：{MOONSHOT_API_BASE}")
        print("-" * 60)
    
    # Test connection
    if HAS_RICH:
        console.print("\n[bold]📡 測試連線中...[/bold]")
    else:
        print("\n📡 測試連線中...")
    
    success, msg = api_client.test_connection()
    
    if success:
        if HAS_RICH:
            console.print(f"[green]✅ {msg}[/green]")
            console.print("\n[bold]📝 測試生成功能...[/bold]")
        else:
            print(f"✅ {msg}")
            print("\n📝 測試生成功能...")
        
        try:
            content, elapsed = api_client.generate(
                "請用一句話描述《紅樓夢》的主題。",
                max_tokens=100
            )
            if HAS_RICH:
                console.print(f"[green]✅ 生成耗時 {elapsed:.2f} 秒：[/green]")
                console.print(Panel(content, border_style="green", title="回應內容"))
            else:
                print(f"✅ 生成耗時 {elapsed:.2f} 秒：")
                print(f"   {content}")
        except Exception as e:
            if HAS_RICH:
                console.print(f"[red]❌ 生成失敗：{e}[/red]")
            else:
                print(f"❌ 生成失敗：{e}")
    else:
        if HAS_RICH:
            console.print(f"[red]❌ {msg}[/red]")
        else:
            print(f"❌ {msg}")


if __name__ == "__main__":
    main()
